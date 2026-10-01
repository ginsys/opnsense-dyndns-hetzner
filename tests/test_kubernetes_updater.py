"""Tests for the kubernetes apex DNS annotation updater."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from opnsense_dyndns_hetzner.kubernetes_updater import (
    TARGET_ANNOTATION_KEYS,
    _update_httproutes,
    _update_ingresses,
    update_apex_dns_annotations,
)

NEW_KEY = "external-dns.kubernetes.io/target"
ALPHA_KEY = "external-dns.alpha.kubernetes.io/target"
TARGET = "1.2.3.4,5.6.7.8"
STALE = "9.9.9.9"
SELECTOR = "ginsys.net/apex-dns=true"


def make_networking_api(annotations: dict[str, str] | None) -> MagicMock:
    """Create a NetworkingV1Api stand-in listing one ingress with the given annotations."""
    ing = MagicMock()
    ing.metadata.namespace = "web"
    ing.metadata.name = "apex"
    ing.metadata.annotations = annotations

    api = MagicMock()
    api.list_ingress_for_all_namespaces.return_value.items = [ing]
    return api


def make_custom_api(annotations: dict[str, str] | None) -> MagicMock:
    """Create a CustomObjectsApi stand-in listing one HTTPRoute with the given annotations."""
    metadata: dict[str, Any] = {"namespace": "web", "name": "apex"}
    if annotations is not None:
        metadata["annotations"] = annotations

    api = MagicMock()
    api.list_cluster_custom_object.return_value = {"items": [{"metadata": metadata}]}
    return api


def run_ingresses(api: MagicMock, dry_run: bool = False) -> bool:
    """Run the ingress updater against a stand-in API."""
    return _update_ingresses(
        networking_v1_api=api,
        label_selector=SELECTOR,
        annotation_keys=TARGET_ANNOTATION_KEYS,
        target_value=TARGET,
        dry_run=dry_run,
    )


def run_httproutes(api: MagicMock, dry_run: bool = False) -> bool:
    """Run the HTTPRoute updater against a stand-in API."""
    return _update_httproutes(
        custom_api=api,
        label_selector=SELECTOR,
        annotation_keys=TARGET_ANNOTATION_KEYS,
        target_value=TARGET,
        dry_run=dry_run,
    )


def assert_patched_both_keys(patch_call: MagicMock) -> None:
    """Assert exactly one patch was sent and it sets both target keys."""
    patch_call.assert_called_once()
    body = patch_call.call_args.kwargs["body"]
    assert body == {"metadata": {"annotations": {NEW_KEY: TARGET, ALPHA_KEY: TARGET}}}
    assert patch_call.call_args.kwargs["name"] == "apex"
    assert patch_call.call_args.kwargs["namespace"] == "web"


class TestTargetAnnotationKeys:
    """Tests for the transitional key set."""

    def test_both_prefixes(self) -> None:
        """Both the new and the alpha prefix are written."""
        assert set(TARGET_ANNOTATION_KEYS) == {NEW_KEY, ALPHA_KEY}


class TestUpdateIngresses:
    """Tests for _update_ingresses."""

    def test_neither_key_patches_both(self) -> None:
        """An ingress with no annotations gets one patch carrying both keys."""
        api = make_networking_api(None)

        assert run_ingresses(api) is True
        assert_patched_both_keys(api.patch_namespaced_ingress)

    def test_both_keys_current_not_patched(self) -> None:
        """An ingress with both keys at the target is left alone."""
        api = make_networking_api({NEW_KEY: TARGET, ALPHA_KEY: TARGET})

        assert run_ingresses(api) is False
        api.patch_namespaced_ingress.assert_not_called()

    def test_only_alpha_key_current_patches_both(self) -> None:
        """An ingress with only the alpha key at the target is patched on both keys."""
        api = make_networking_api({ALPHA_KEY: TARGET})

        assert run_ingresses(api) is True
        assert_patched_both_keys(api.patch_namespaced_ingress)

    def test_only_new_key_current_patches_both(self) -> None:
        """An ingress with only the new key at the target is patched on both keys."""
        api = make_networking_api({NEW_KEY: TARGET, ALPHA_KEY: STALE})

        assert run_ingresses(api) is True
        assert_patched_both_keys(api.patch_namespaced_ingress)

    def test_dry_run_does_not_patch(self) -> None:
        """Dry run reports an update without patching."""
        api = make_networking_api({ALPHA_KEY: STALE})

        assert run_ingresses(api, dry_run=True) is True
        api.patch_namespaced_ingress.assert_not_called()


class TestUpdateHttproutes:
    """Tests for _update_httproutes."""

    def test_neither_key_patches_both(self) -> None:
        """An HTTPRoute with no annotations gets one patch carrying both keys."""
        api = make_custom_api(None)

        assert run_httproutes(api) is True
        assert_patched_both_keys(api.patch_namespaced_custom_object)

    def test_both_keys_current_not_patched(self) -> None:
        """An HTTPRoute with both keys at the target is left alone."""
        api = make_custom_api({NEW_KEY: TARGET, ALPHA_KEY: TARGET})

        assert run_httproutes(api) is False
        api.patch_namespaced_custom_object.assert_not_called()

    def test_only_alpha_key_current_patches_both(self) -> None:
        """An HTTPRoute with only the alpha key at the target is patched on both keys."""
        api = make_custom_api({ALPHA_KEY: TARGET})

        assert run_httproutes(api) is True
        assert_patched_both_keys(api.patch_namespaced_custom_object)

    def test_only_new_key_current_patches_both(self) -> None:
        """An HTTPRoute with only the new key at the target is patched on both keys."""
        api = make_custom_api({NEW_KEY: TARGET})

        assert run_httproutes(api) is True
        assert_patched_both_keys(api.patch_namespaced_custom_object)


class TestUpdateApexDnsAnnotations:
    """Tests for update_apex_dns_annotations wiring."""

    def test_writes_both_keys_on_both_resource_kinds(self) -> None:
        """The public entry point patches ingresses and HTTPRoutes with both keys."""
        networking_api = make_networking_api(None)
        custom_api = make_custom_api(None)

        with (
            patch("opnsense_dyndns_hetzner.kubernetes_updater.config.load_incluster_config"),
            patch(
                "opnsense_dyndns_hetzner.kubernetes_updater.client.NetworkingV1Api",
                return_value=networking_api,
            ),
            patch(
                "opnsense_dyndns_hetzner.kubernetes_updater.client.CustomObjectsApi",
                return_value=custom_api,
            ),
        ):
            assert update_apex_dns_annotations(["5.6.7.8", "1.2.3.4"], SELECTOR) is True

        assert_patched_both_keys(networking_api.patch_namespaced_ingress)
        assert_patched_both_keys(custom_api.patch_namespaced_custom_object)
