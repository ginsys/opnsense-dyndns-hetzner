"""Configuration loading and validation."""

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class OPNsenseConfig(BaseModel):
    """OPNsense API configuration."""

    url: str = Field(description="Base URL for OPNsense API (e.g., https://opnsense.local/api)")
    key: str = Field(description="API key")
    secret: str = Field(description="API secret")
    interfaces: dict[str, str] = Field(
        description="Mapping of logical names to OPNsense interface names"
    )


class HetznerConfig(BaseModel):
    """Hetzner Cloud DNS configuration."""

    token: str = Field(description="Hetzner Cloud API token")
    zone: str = Field(description="DNS zone name (e.g., example.com)")
    ttl: int = Field(default=300, description="TTL for DNS records in seconds")


class SettingsConfig(BaseModel):
    """Application settings."""

    interval: int = Field(default=300, description="Interval between checks in seconds")
    dry_run: bool = Field(default=False, description="If true, don't make changes")


class RecordConfig(BaseModel):
    """DNS record configuration."""

    hostname: str = Field(description="Hostname (without zone suffix)")
    interfaces: list[str] = Field(description="List of interface logical names")


class Config(BaseModel):
    """Root configuration."""

    opnsense: OPNsenseConfig
    hetzner: HetznerConfig
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    records: list[RecordConfig]


def _substitute_env_vars(value: str) -> str:
    """Substitute ${VAR_NAME} patterns with environment variables."""
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' not set")
        return env_value

    return pattern.sub(replacer, value)


def _process_env_vars(obj: object) -> object:
    """Recursively process environment variable substitution in a data structure."""
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    elif isinstance(obj, dict):
        return {k: _process_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_process_env_vars(item) for item in obj]
    return obj


def load_config(path: Path) -> Config:
    """Load and validate configuration from a YAML file."""
    with path.open() as f:
        raw_config = yaml.safe_load(f)

    # Substitute environment variables
    processed_config = _process_env_vars(raw_config)

    return Config.model_validate(processed_config)
