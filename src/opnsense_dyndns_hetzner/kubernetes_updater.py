"""Kubernetes Ingress/HTTPRoute annotation updater for apex DNS."""

import structlog
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = structlog.get_logger(__name__)


def update_apex_dns_annotations(
    ips: list[str],
    label_selector: str = "ginsys.net/apex-dns=true",
    dry_run: bool = False,
) -> bool:
    """
    Update external-dns.alpha.kubernetes.io/target annotation on labeled resources.

    Args:
        ips: List of IP addresses to set as target
        label_selector: Kubernetes label selector for finding resources
        dry_run: If True, only log what would be changed

    Returns:
        True if any resources were updated, False otherwise
    """
    if not ips:
        logger.warning("No IPs provided for kubernetes annotation update")
        return False

    target_value = ",".join(sorted(ips))
    annotation_key = "external-dns.alpha.kubernetes.io/target"
    updated = False

    logger.info(
        "Updating kubernetes resources",
        ips=ips,
        target=target_value,
        label_selector=label_selector,
        dry_run=dry_run,
    )

    try:
        # Load in-cluster config
        config.load_incluster_config()
    except config.ConfigException:
        logger.error("Failed to load in-cluster kubernetes config")
        return False

    # Update Ingresses
    updated |= _update_ingresses(
        networking_v1_api=client.NetworkingV1Api(),
        label_selector=label_selector,
        annotation_key=annotation_key,
        target_value=target_value,
        dry_run=dry_run,
    )

    # Update HTTPRoutes
    updated |= _update_httproutes(
        custom_api=client.CustomObjectsApi(),
        label_selector=label_selector,
        annotation_key=annotation_key,
        target_value=target_value,
        dry_run=dry_run,
    )

    return updated


def _update_ingresses(
    networking_v1_api: client.NetworkingV1Api,
    label_selector: str,
    annotation_key: str,
    target_value: str,
    dry_run: bool,
) -> bool:
    """Update Ingress resources with the target annotation."""
    updated = False

    try:
        ingresses = networking_v1_api.list_ingress_for_all_namespaces(
            label_selector=label_selector
        )
    except ApiException as e:
        logger.error("Failed to list ingresses", error=str(e))
        return False

    for ing in ingresses.items:
        namespace = ing.metadata.namespace
        name = ing.metadata.name
        current = ing.metadata.annotations.get(annotation_key) if ing.metadata.annotations else None

        if current == target_value:
            logger.debug(
                "Ingress annotation already up-to-date",
                namespace=namespace,
                name=name,
                target=target_value,
            )
            continue

        logger.info(
            "Updating ingress annotation",
            namespace=namespace,
            name=name,
            old=current,
            new=target_value,
            dry_run=dry_run,
        )

        if not dry_run:
            try:
                # Patch annotation
                body = {
                    "metadata": {
                        "annotations": {
                            annotation_key: target_value
                        }
                    }
                }
                networking_v1_api.patch_namespaced_ingress(
                    name=name,
                    namespace=namespace,
                    body=body,
                )
                updated = True
            except ApiException as e:
                logger.error(
                    "Failed to patch ingress",
                    namespace=namespace,
                    name=name,
                    error=str(e),
                )
        else:
            updated = True

    return updated


def _update_httproutes(
    custom_api: client.CustomObjectsApi,
    label_selector: str,
    annotation_key: str,
    target_value: str,
    dry_run: bool,
) -> bool:
    """Update HTTPRoute resources with the target annotation."""
    updated = False

    try:
        httproutes = custom_api.list_cluster_custom_object(
            group="gateway.networking.k8s.io",
            version="v1",
            plural="httproutes",
            label_selector=label_selector,
        )
    except ApiException as e:
        logger.error("Failed to list httproutes", error=str(e))
        return False

    for route in httproutes.get("items", []):
        namespace = route["metadata"]["namespace"]
        name = route["metadata"]["name"]
        annotations = route.get("metadata", {}).get("annotations", {})
        current = annotations.get(annotation_key)

        if current == target_value:
            logger.debug(
                "HTTPRoute annotation already up-to-date",
                namespace=namespace,
                name=name,
                target=target_value,
            )
            continue

        logger.info(
            "Updating httproute annotation",
            namespace=namespace,
            name=name,
            old=current,
            new=target_value,
            dry_run=dry_run,
        )

        if not dry_run:
            try:
                # Patch annotation
                body = {
                    "metadata": {
                        "annotations": {
                            annotation_key: target_value
                        }
                    }
                }
                custom_api.patch_namespaced_custom_object(
                    group="gateway.networking.k8s.io",
                    version="v1",
                    plural="httproutes",
                    name=name,
                    namespace=namespace,
                    body=body,
                )
                updated = True
            except ApiException as e:
                logger.error(
                    "Failed to patch httproute",
                    namespace=namespace,
                    name=name,
                    error=str(e),
                )
        else:
            updated = True

    return updated
