# opnsense-dyndns-hetzner

Dynamic DNS updater for Hetzner Cloud DNS using OPNsense WAN interface IPs.

## Overview

This tool queries OPNsense for WAN interface IP addresses and updates A records in Hetzner Cloud DNS. It supports:

- Multiple interfaces with logical names
- Multiple A records per hostname (for redundancy)
- Configurable update interval
- Dry-run mode for testing
- Only updates DNS when IPs actually change
- DNS verification after updates
- Rate limiting and retry with exponential backoff
- Optional health endpoints for Kubernetes

## Quick Start

### Using Environment Variables Only

The simplest way to run - no config file needed:

```bash
docker run --rm \
  -e OPNSENSE_URL=https://opnsense.local/api \
  -e OPNSENSE_API_KEY='your-key' \
  -e OPNSENSE_API_SECRET='your-secret' \
  -e OPNSENSE_INTERFACES='wan:igb0' \
  -e OPNSENSE_VERIFY_SSL=false \
  -e HCLOUD_TOKEN='your-token' \
  -e HETZNER_ZONE=example.com \
  -e RECORDS='home:wan' \
  -e DRY_RUN=true \
  ghcr.io/ginsys/opnsense-dyndns-hetzner:main \
  --once --log-level debug
```

### Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `OPNSENSE_URL` | Yes | OPNsense API base URL | `https://192.168.1.1/api` |
| `OPNSENSE_API_KEY` | Yes | API key | |
| `OPNSENSE_API_SECRET` | Yes | API secret | |
| `OPNSENSE_INTERFACES` | Yes | Interface mappings (logical:opnsense) | `wan:igb0,backup:igb1` |
| `OPNSENSE_VERIFY_SSL` | No | Verify SSL certs (default: true) | `false` |
| `HCLOUD_TOKEN` | Yes | Hetzner Cloud API token | |
| `HETZNER_ZONE` | Yes | DNS zone to manage | `example.com` |
| `HETZNER_TTL` | No | TTL in seconds (default: 300) | `300` |
| `RECORDS` | Yes | Record definitions | `home:wan,server:wan+backup` |
| `INTERVAL` | No | Check interval seconds (default: 300) | `300` |
| `DRY_RUN` | No | Don't make changes (default: false) | `true` |
| `HEALTH_PORT` | No | HTTP health endpoint port | `8080` |
| `VERIFY_DELAY` | No | Seconds before DNS verification | `2.0` |

**Interface format**: `logical_name:opnsense_interface_name` - use the actual interface name from OPNsense (e.g., `igb0`, `em0`), not the friendly name.

**Records format**: `hostname:interface1+interface2` - multiple interfaces create multiple A records.

## Configuration

### Configuration File (Alternative)

For more complex setups, use a YAML config file:

```yaml
opnsense:
  url: "https://opnsense.local/api"
  key: "${OPNSENSE_API_KEY}"        # From environment variable
  secret: "${OPNSENSE_API_SECRET}"  # From environment variable
  verify_ssl: true                  # Set false for self-signed certs
  interfaces:
    wan: "igb0"       # logical name -> OPNsense interface name
    backup: "igb1"

hetzner:
  token: "${HCLOUD_TOKEN}"          # Hetzner Cloud API token
  zone: "example.com"
  ttl: 300

settings:
  interval: 300       # seconds between checks
  dry_run: false
  health_port: null   # Set to 8080 to enable health endpoints
  verify_delay: 2.0   # seconds to wait before DNS verification

records:
  - hostname: office
    interfaces: [backup]          # Single interface -> 1 A record
  - hostname: server
    interfaces: [wan, backup]     # Both interfaces -> 2 A records
```

Run with config file:

```bash
docker run --rm \
  -v ./config.yaml:/etc/opnsense-dyndns-hetzner/config.yaml:ro \
  -e OPNSENSE_API_KEY='your-key' \
  -e OPNSENSE_API_SECRET='your-secret' \
  -e HCLOUD_TOKEN='your-token' \
  ghcr.io/ginsys/opnsense-dyndns-hetzner:main
```

### Finding OPNsense Interface Names

To find the correct interface names for your OPNsense configuration:

#### Option 1: Via OPNsense API

```bash
curl -k -u "API_KEY:API_SECRET" \
  https://opnsense.local/api/diagnostics/interface/getInterfaceConfig \
  | jq 'keys'
```

This returns the actual interface names:
```json
["igb0", "igb1", "igb2", "lo0", "ovpns1"]
```

#### Option 2: Via OPNsense Web UI

1. Go to **Interfaces > Overview**
2. Note the **Device** column (e.g., `igb0`, `em0`)

#### Option 3: Run with Debug Logging

If you use the wrong interface name, the tool will show available interfaces:

```json
{"logical_name": "wan", "opnsense_name": "wan", "available_interfaces": ["igb0", "igb1", "lo0"], "event": "Interface not found in OPNsense", "level": "warning"}
```

## Deployment

### Kubernetes

1. Create the namespace and secret:

```bash
kubectl create namespace opnsense-dyndns-hetzner

kubectl create secret generic opnsense-dyndns-hetzner-secrets \
  --namespace opnsense-dyndns-hetzner \
  --from-literal=OPNSENSE_API_KEY='your-key' \
  --from-literal=OPNSENSE_API_SECRET='your-secret' \
  --from-literal=HCLOUD_TOKEN='your-token'
```

2. Edit `k8s/config.yaml` with your settings

3. Apply with kustomize:

```bash
kubectl apply -k k8s/
```

### Local Development

Using the Makefile:

```bash
# Create virtual environment and install dependencies
make venv

# Activate (or use mise for auto-activation)
source .venv/bin/activate

# Run all checks
make check

# Run with example config
make run
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Docker

```bash
# Build locally
make build

# Or pull from registry
docker pull ghcr.io/ginsys/opnsense-dyndns-hetzner:main
```

## CLI Options

```
usage: odh [-h] [--config CONFIG] [--dry-run]
           [--log-level {debug,info,warning,error}] [--once]

Dynamic DNS updater for Hetzner Cloud DNS using OPNsense WAN IPs

options:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to configuration file (optional if using environment variables)
  --dry-run             Don't make changes, just log what would be done
  --log-level {debug,info,warning,error}
                        Logging level (default: info)
  --once                Run once and exit (don't loop)
```

## How It Works

1. **Query OPNsense**: Fetches current IP addresses for configured WAN interfaces via the OPNsense REST API
2. **Query Hetzner DNS**: Fetches current A records for each configured hostname
3. **Compare**: Checks if current DNS records match desired IPs
4. **Update if needed**: Creates/updates/deletes A records to match desired state using RRSet operations
5. **Verify**: Queries Hetzner authoritative nameservers to confirm changes propagated
6. **Sleep**: Waits for the configured interval before repeating

### Features

#### Rate Limiting

API requests are rate-limited to 30 requests per minute to avoid hitting Hetzner API limits.

#### Retry with Backoff

Transient API failures (429, 5xx) are automatically retried with exponential backoff up to 3 times.

#### DNS Verification

After each update, the tool queries Hetzner's authoritative nameservers directly to verify the changes have propagated:
- `helium.ns.hetzner.de`
- `hydrogen.ns.hetzner.com`
- `oxygen.ns.hetzner.com`

#### Health Endpoints

When `health_port` is configured, the following endpoints are available:

| Endpoint | Purpose | Success | Failure |
|----------|---------|---------|---------|
| `/healthz` | Liveness probe | 200 OK | - |
| `/readyz` | Readiness probe | 200 OK (APIs reachable) | 503 Service Unavailable |

### Logging

Output is JSON-formatted for easy parsing:

```json
{"zone": "example.com", "interval": 300, "dry_run": false, "event": "Starting opnsense-dyndns-hetzner", "level": "info"}
{"hostname": "test", "current": [], "desired": ["1.2.3.4"], "event": "Syncing A records", "level": "info"}
{"hostname": "test", "ips": ["1.2.3.4"], "event": "Created A record", "level": "info"}
```

Log levels:
- **DEBUG**: Detailed API calls, skipped updates when no changes needed
- **INFO**: Update cycles, DNS record changes, startup/shutdown
- **WARNING**: Missing interfaces, DNS verification mismatches
- **ERROR**: API failures

## API Setup

### OPNsense API Setup

1. Go to **System > Access > Users**
2. Create a new user (or edit existing)
3. Generate an API key pair
4. Go to **System > Access > Groups**
5. Ensure the user has the `Diagnostics: Interface` privilege

### Hetzner Cloud API Setup

1. Go to [Hetzner Cloud Console](https://console.hetzner.cloud/)
2. Select your project
3. Go to **Security > API Tokens**
4. Create a new token with read/write permissions

**Note**: This tool uses the new Hetzner Cloud API (`hcloud`), not the legacy DNS console API (`dns.hetzner.com`).

## Development

### Running Tests

```bash
make venv
make check   # runs lint, typecheck, and tests
```

Or individually:

```bash
make lint       # ruff check
make typecheck  # mypy
make test       # pytest
```

### Code Formatting

```bash
make format
```

## License

MIT
