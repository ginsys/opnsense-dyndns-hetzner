"""Main entry point for opnsense-dyndns-hetzner."""

import argparse
import signal
import sys
import time
from pathlib import Path

import structlog

from .config import Config, load_config
from .hetzner import HetznerDNSClient
from .opnsense import OPNsenseClient


def configure_logging(level: str) -> None:
    """Configure structlog for stdout logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog, level.upper(), structlog.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Dynamic DNS updater for Hetzner Cloud DNS using OPNsense WAN IPs"
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't make changes, just log what would be done",
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        default="info",
        help="Logging level (default: info)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't loop)",
    )
    return parser.parse_args()


class GracefulShutdown:
    """Handle graceful shutdown on SIGTERM/SIGINT."""

    def __init__(self) -> None:
        self.should_exit = False
        signal.signal(signal.SIGTERM, self._handler)
        signal.signal(signal.SIGINT, self._handler)

    def _handler(self, signum: int, frame: object) -> None:
        logger = structlog.get_logger()
        logger.info("Received shutdown signal", signal=signum)
        self.should_exit = True


def run_update(
    config: Config,
    opnsense: OPNsenseClient,
    hetzner: HetznerDNSClient,
    dry_run: bool,
) -> None:
    """Run a single update cycle."""
    logger = structlog.get_logger()

    # Get current IPs from OPNsense
    try:
        interface_ips = opnsense.get_interface_ips()
    except Exception as e:
        logger.error("Failed to get IPs from OPNsense", error=str(e))
        return

    if not interface_ips:
        logger.warning("No interface IPs found")
        return

    logger.debug("Retrieved interface IPs", ips=interface_ips)

    # Process each record
    for record in config.records:
        # Gather IPs for this record's interfaces
        desired_ips = []
        missing_interfaces = []

        for iface in record.interfaces:
            if iface in interface_ips:
                desired_ips.append(interface_ips[iface])
            else:
                missing_interfaces.append(iface)

        if missing_interfaces:
            logger.warning(
                "Missing interfaces for record",
                hostname=record.hostname,
                missing=missing_interfaces,
            )

        if not desired_ips:
            logger.warning(
                "No IPs available for record, skipping",
                hostname=record.hostname,
            )
            continue

        # Sync DNS records
        try:
            hetzner.sync_a_records(record.hostname, desired_ips, dry_run=dry_run)
        except Exception as e:
            logger.error(
                "Failed to sync DNS records",
                hostname=record.hostname,
                error=str(e),
            )


def main() -> None:
    """Main entry point."""
    args = parse_args()
    configure_logging(args.log_level)
    logger = structlog.get_logger()

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error("Failed to load configuration", error=str(e))
        sys.exit(1)

    # Override dry_run from CLI if specified
    dry_run = args.dry_run or config.settings.dry_run

    logger.info(
        "Starting opnsense-dyndns-hetzner",
        zone=config.hetzner.zone,
        interval=config.settings.interval,
        dry_run=dry_run,
        record_count=len(config.records),
    )

    shutdown = GracefulShutdown()

    with OPNsenseClient(config.opnsense) as opnsense, HetznerDNSClient(config.hetzner) as hetzner:
        while not shutdown.should_exit:
            run_update(config, opnsense, hetzner, dry_run)

            if args.once:
                break

            # Sleep with interrupt checking
            for _ in range(config.settings.interval):
                if shutdown.should_exit:
                    break
                time.sleep(1)

    logger.info("Shutting down")


if __name__ == "__main__":
    main()
