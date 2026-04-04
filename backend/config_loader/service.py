"""Config loader — reads YAML config, validates with Pydantic, provides singleton access."""

from pathlib import Path

import yaml

from backend.config_loader.schema import AppConfig

_DEFAULT_CONFIG_PATH = Path("config/default.yaml")

_config: AppConfig | None = None


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate configuration from YAML file.

    Args:
        path: Path to YAML config file. Defaults to config/default.yaml.

    Returns:
        Validated AppConfig instance.

    Raises:
        FileNotFoundError: If config file does not exist.
        yaml.YAMLError: If YAML is malformed.
        pydantic.ValidationError: If config values fail validation.
    """
    config_path = path or _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    config = AppConfig(**raw)

    global _config
    _config = config

    return config


def get_config() -> AppConfig:
    """Get the current loaded config. Raises if not loaded yet."""
    if _config is None:
        raise RuntimeError("Config not loaded. Call load_config() first.")
    return _config


def reset_config() -> None:
    """Reset config state. For testing only."""
    global _config
    _config = None
