"""Hetzner Cloud DNS API client for managing A records."""

from dataclasses import dataclass

import httpx
import structlog

from .config import HetznerConfig

logger = structlog.get_logger()

HETZNER_DNS_API_BASE = "https://dns.hetzner.com/api/v1"


@dataclass
class DNSRecord:
    """Represents a DNS A record."""

    id: str
    name: str
    type: str
    value: str
    ttl: int
    zone_id: str


class HetznerDNSClient:
    """Client for Hetzner Cloud DNS API."""

    def __init__(self, config: HetznerConfig) -> None:
        self.config = config
        self._client = httpx.Client(
            headers={
                "Auth-API-Token": config.token,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        self._zone_id: str | None = None

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "HetznerDNSClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get_zone_id(self) -> str:
        """Get the zone ID for the configured zone name."""
        if self._zone_id is not None:
            return self._zone_id

        url = f"{HETZNER_DNS_API_BASE}/zones"
        logger.debug("Fetching zones from Hetzner DNS", url=url)

        response = self._client.get(url, params={"name": self.config.zone})
        response.raise_for_status()

        data = response.json()
        zones = data.get("zones", [])

        for zone in zones:
            if zone["name"] == self.config.zone:
                self._zone_id = zone["id"]
                logger.debug("Found zone", zone=self.config.zone, zone_id=self._zone_id)
                return self._zone_id

        raise ValueError(f"Zone '{self.config.zone}' not found in Hetzner DNS")

    def get_a_records(self, hostname: str) -> list[DNSRecord]:
        """
        Get all A records for a hostname.

        Args:
            hostname: The hostname (without zone suffix)

        Returns:
            List of DNSRecord objects for the hostname
        """
        zone_id = self._get_zone_id()
        url = f"{HETZNER_DNS_API_BASE}/records"

        response = self._client.get(url, params={"zone_id": zone_id})
        response.raise_for_status()

        data = response.json()
        records = data.get("records", [])

        result = []
        for record in records:
            if record["type"] == "A" and record["name"] == hostname:
                result.append(
                    DNSRecord(
                        id=record["id"],
                        name=record["name"],
                        type=record["type"],
                        value=record["value"],
                        ttl=record.get("ttl", self.config.ttl),
                        zone_id=record["zone_id"],
                    )
                )

        logger.debug("Found A records", hostname=hostname, count=len(result))
        return result

    def create_a_record(self, hostname: str, ip: str) -> DNSRecord:
        """
        Create a new A record.

        Args:
            hostname: The hostname (without zone suffix)
            ip: The IPv4 address

        Returns:
            The created DNSRecord
        """
        zone_id = self._get_zone_id()
        url = f"{HETZNER_DNS_API_BASE}/records"

        payload = {
            "zone_id": zone_id,
            "type": "A",
            "name": hostname,
            "value": ip,
            "ttl": self.config.ttl,
        }

        logger.info("Creating A record", hostname=hostname, ip=ip, ttl=self.config.ttl)
        response = self._client.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        record = data["record"]

        return DNSRecord(
            id=record["id"],
            name=record["name"],
            type=record["type"],
            value=record["value"],
            ttl=record.get("ttl", self.config.ttl),
            zone_id=record["zone_id"],
        )

    def update_a_record(self, record_id: str, hostname: str, ip: str) -> DNSRecord:
        """
        Update an existing A record.

        Args:
            record_id: The record ID to update
            hostname: The hostname (without zone suffix)
            ip: The new IPv4 address

        Returns:
            The updated DNSRecord
        """
        zone_id = self._get_zone_id()
        url = f"{HETZNER_DNS_API_BASE}/records/{record_id}"

        payload = {
            "zone_id": zone_id,
            "type": "A",
            "name": hostname,
            "value": ip,
            "ttl": self.config.ttl,
        }

        logger.info("Updating A record", hostname=hostname, ip=ip, record_id=record_id)
        response = self._client.put(url, json=payload)
        response.raise_for_status()

        data = response.json()
        record = data["record"]

        return DNSRecord(
            id=record["id"],
            name=record["name"],
            type=record["type"],
            value=record["value"],
            ttl=record.get("ttl", self.config.ttl),
            zone_id=record["zone_id"],
        )

    def delete_a_record(self, record_id: str) -> None:
        """
        Delete an A record.

        Args:
            record_id: The record ID to delete
        """
        url = f"{HETZNER_DNS_API_BASE}/records/{record_id}"

        logger.info("Deleting A record", record_id=record_id)
        response = self._client.delete(url)
        response.raise_for_status()

    def sync_a_records(self, hostname: str, desired_ips: list[str], dry_run: bool = False) -> bool:
        """
        Synchronize A records for a hostname to match desired IPs.

        This will:
        - Create records for IPs that don't exist
        - Update records to match desired IPs
        - Delete extra records

        Args:
            hostname: The hostname (without zone suffix)
            desired_ips: List of IPv4 addresses to set
            dry_run: If True, don't make changes, just log

        Returns:
            True if changes were made (or would be made in dry_run), False otherwise
        """
        current_records = self.get_a_records(hostname)
        current_ips = {r.value for r in current_records}
        desired_ips_set = set(desired_ips)

        # Check if any changes needed
        if current_ips == desired_ips_set:
            logger.debug(
                "No changes needed",
                hostname=hostname,
                current_ips=sorted(current_ips),
            )
            return False

        logger.info(
            "Syncing A records",
            hostname=hostname,
            current_ips=sorted(current_ips),
            desired_ips=sorted(desired_ips_set),
            dry_run=dry_run,
        )

        if dry_run:
            return True

        # Strategy: delete all existing, create new
        # This is simpler than trying to match/update individual records
        for record in current_records:
            self.delete_a_record(record.id)

        for ip in sorted(desired_ips):  # Sort for deterministic order
            self.create_a_record(hostname, ip)

        return True
