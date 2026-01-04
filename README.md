# opnsense-dyndns-hetzner

Dynamic DNS updater for Hetzner Cloud DNS using OPNsense WAN interface IPs.

## Overview

This tool queries OPNsense for WAN interface IP addresses and updates A records in Hetzner Cloud DNS. It supports:

- Multiple interfaces with logical names
- Multiple A records per hostname (for redundancy)
- Configurable update interval
- Dry-run mode for testing
- Only updates DNS when IPs actually change

## Configuration

### Configuration File

```yaml
opnsense:
  url: "https://opnsense.local/api"
  key: "${OPNSENSE_API_KEY}"        # From environment variable
  secret: "${OPNSENSE_API_SECRET}"  # From environment variable
  interfaces:
    telenet: "wan"      # logical name -> OPNsense interface name
    telenet2: "opt1"

hetzner:
  token: "${HETZNER_DNS_TOKEN}"     # From environment variable
  zone: "example.com"
  ttl: 300

settings:
  interval: 300    # seconds between checks
  dry_run: false

records:
  - hostname: office
    interfaces: [telenet2]          # Single interface -> 1 A record
  - hostname: server
    interfaces: [telenet, telenet2] # Both interfaces -> 2 A records
```

### Finding OPNsense Interface Names

To find the correct interface names for your OPNsense configuration:

#### Option 1: Via OPNsense Web UI

1. Go to **Interfaces > Overview**
2. Note the interface identifiers (e.g., `wan`, `lan`, `opt1`, `opt2`)

#### Option 2: Via OPNsense API

```bash
curl -u "API_KEY:API_SECRET" \
  https://opnsense.local/api/diagnostics/interface/getInterfaceConfig \
  | jq 'keys'
```

This will return a list like:
```json
["lan", "lo0", "opt1", "wan"]
```

#### Option 3: Via OPNsense Shell

```bash
# SSH into OPNsense
ifconfig -l
# or
cat /conf/config.xml | grep -A5 "<interfaces>"
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
  --from-literal=HETZNER_DNS_TOKEN='your-token'
```

2. Edit `k8s/config.yaml` with your settings

3. Apply with kustomize:

```bash
kubectl apply -k k8s/
```

### Local Development

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. Set environment variables:

```bash
export OPNSENSE_API_KEY='your-key'
export OPNSENSE_API_SECRET='your-secret'
export HETZNER_DNS_TOKEN='your-token'
```

3. Run:

```bash
# Single run
odh --config config.yaml --once

# Dry run (no changes)
odh --config config.yaml --once --dry-run

# With debug logging
odh --config config.yaml --once --log-level debug

# Continuous mode
odh --config config.yaml
```

### Docker

```bash
# Build
docker build -t opnsense-dyndns-hetzner .

# Run
docker run -v ./config.yaml:/etc/opnsense-dyndns-hetzner/config.yaml \
  -e OPNSENSE_API_KEY='your-key' \
  -e OPNSENSE_API_SECRET='your-secret' \
  -e HETZNER_DNS_TOKEN='your-token' \
  opnsense-dyndns-hetzner
```

## CLI Options

```
usage: odh [-h] --config CONFIG [--dry-run]
           [--log-level {debug,info,warning,error}] [--once]

Dynamic DNS updater for Hetzner Cloud DNS using OPNsense WAN IPs

options:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
                        Path to configuration file
  --dry-run             Don't make changes, just log what would be done
  --log-level {debug,info,warning,error}
                        Logging level (default: info)
  --once                Run once and exit (don't loop)
```

## How It Works

1. **Query OPNsense**: Fetches current IP addresses for configured WAN interfaces via the OPNsense REST API
2. **Query Hetzner DNS**: Fetches current A records for each configured hostname
3. **Compare**: Checks if current DNS records match desired IPs
4. **Update if needed**: Creates/updates/deletes A records to match desired state
5. **Sleep**: Waits for the configured interval before repeating

### Logging

- **DEBUG**: Logs when no changes are needed (skipped updates)
- **INFO**: Logs when DNS records are created, updated, or deleted
- **WARNING**: Logs missing interfaces or configuration issues
- **ERROR**: Logs API failures

## OPNsense API Setup

1. Go to **System > Access > Users**
2. Create a new user (or edit existing)
3. Generate an API key pair
4. Go to **System > Access > Groups**
5. Ensure the user has the `Diagnostics: Interface` privilege

## Hetzner Cloud DNS API Setup

1. Go to [Hetzner DNS Console](https://dns.hetzner.com/)
2. Click on your profile > API Tokens
3. Create a new token with read/write permissions

## License

MIT
