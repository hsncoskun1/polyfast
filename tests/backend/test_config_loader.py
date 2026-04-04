"""Tests for config loader and schema validation."""

import pytest
from pathlib import Path
import tempfile
import yaml

from backend.config_loader.service import load_config, get_config, reset_config
from backend.config_loader.schema import AppConfig


@pytest.fixture(autouse=True)
def clean_config():
    """Reset config state before each test."""
    reset_config()
    yield
    reset_config()


def _write_yaml(data: dict, tmp_path: Path) -> Path:
    """Write a dict as YAML to a temp file and return the path."""
    p = tmp_path / "test_config.yaml"
    with open(p, "w") as f:
        yaml.dump(data, f)
    return p


def test_load_default_config():
    """Default config file loads and validates successfully."""
    config = load_config(Path("config/default.yaml"))
    assert isinstance(config, AppConfig)
    assert config.server.port == 8000
    assert config.trading.min_amount_usd == 5.0


def test_get_config_after_load():
    """get_config returns the loaded config."""
    load_config(Path("config/default.yaml"))
    config = get_config()
    assert config.server.host == "127.0.0.1"


def test_get_config_before_load_raises():
    """get_config raises RuntimeError if config not loaded."""
    with pytest.raises(RuntimeError, match="Config not loaded"):
        get_config()


def test_config_file_not_found():
    """Loading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config(Path("nonexistent.yaml"))


def test_time_rule_min_must_be_less_than_max(tmp_path):
    """Time rule rejects min_seconds >= max_seconds."""
    data = {
        "trading": {
            "entry_rules": {
                "time": {"min_seconds": 200, "max_seconds": 100}
            }
        }
    }
    with pytest.raises(Exception, match="min_seconds.*must be < max_seconds"):
        load_config(_write_yaml(data, tmp_path))


def test_price_rule_min_must_be_less_than_max(tmp_path):
    """Price rule rejects min_price >= max_price."""
    data = {
        "trading": {
            "entry_rules": {
                "price": {"min_price": 0.90, "max_price": 0.10}
            }
        }
    }
    with pytest.raises(Exception, match="min_price.*must be < max_price"):
        load_config(_write_yaml(data, tmp_path))


def test_invalid_log_level(tmp_path):
    """Invalid log level is rejected."""
    data = {"logging": {"level": "TRACE"}}
    with pytest.raises(Exception):
        load_config(_write_yaml(data, tmp_path))


def test_invalid_force_sell_combinator(tmp_path):
    """Force sell combinator must be 'all' or 'any'."""
    data = {
        "trading": {
            "exit_rules": {
                "force_sell": {"combinator": "maybe"}
            }
        }
    }
    with pytest.raises(Exception):
        load_config(_write_yaml(data, tmp_path))


def test_port_out_of_range(tmp_path):
    """Server port must be 1-65535."""
    data = {"server": {"port": 99999}}
    with pytest.raises(Exception):
        load_config(_write_yaml(data, tmp_path))


def test_empty_yaml_loads_defaults(tmp_path):
    """An empty YAML file should produce valid defaults."""
    p = tmp_path / "empty.yaml"
    p.write_text("")
    config = load_config(p)
    assert config.server.port == 8000
    assert config.trading.entry_rules.time.enabled is True


def test_partial_override(tmp_path):
    """Partial config overrides only specified values."""
    data = {"server": {"port": 9999}}
    config = load_config(_write_yaml(data, tmp_path))
    assert config.server.port == 9999
    assert config.server.host == "127.0.0.1"  # default preserved
