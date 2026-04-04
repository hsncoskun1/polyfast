"""Tests for structured logging and credential masking."""

import json
import logging
import pytest

from backend.logging_config.filters import mask_string, mask_dict, CredentialMaskingFilter
from backend.logging_config.formatters import JsonFormatter, HumanFormatter
from backend.logging_config.service import setup_logging, get_logger, log_event


class TestCredentialMasking:
    """Tests for credential masking filter."""

    def test_mask_api_key_in_string(self):
        text = 'api_key="f649cb77-2283-dbf3-510d-f8a3dafade63"'
        result = mask_string(text)
        assert "f649cb77-2283-dbf3-510d-f8a3dafade63" not in result
        assert "****" in result

    def test_mask_secret_in_string(self):
        text = "secret=VSlmx75F7clayZpaDs1r2YWDPx5XJHKTcBwBgY45e5A="
        result = mask_string(text)
        assert "VSlmx75F7clay" not in result
        assert "****" in result

    def test_mask_private_key_in_string(self):
        text = 'private_key: "79f6a2c64bbeee82affa2098d74dddd8babb39ce2527dab2451c9ea49e8559fe"'
        result = mask_string(text)
        assert "79f6a2c64bbeee82" not in result
        assert "****" in result

    def test_mask_ethereum_address(self):
        text = "funder=0x7e3bacaa4e7563ff2343e48019120504028ee306"
        result = mask_string(text)
        assert "0x7e3bacaa4e7563ff2343e48019120504028ee306" not in result

    def test_mask_dict_sensitive_fields(self):
        data = {
            "api_key": "f649cb77-2283-dbf3-510d-f8a3dafade63",
            "username": "trader1",
            "private_key": "79f6a2c64bbeee82affa2098d74dddd8",
        }
        result = mask_dict(data)
        assert "f649cb77-2283" not in result["api_key"]
        assert "****" in result["api_key"]
        assert result["username"] == "trader1"  # non-sensitive preserved
        assert "****" in result["private_key"]

    def test_mask_nested_dict(self):
        data = {
            "credentials": {
                "api_key": "secret-value-here",
                "passphrase": "another-secret",
            },
            "config": {"port": 8000},
        }
        result = mask_dict(data)
        assert "****" in result["credentials"]["api_key"]
        assert "****" in result["credentials"]["passphrase"]
        assert result["config"]["port"] == 8000

    def test_non_sensitive_string_unchanged(self):
        text = "Discovery found 5 new events in crypto category"
        assert mask_string(text) == text

    def test_filter_masks_log_record(self):
        f = CredentialMaskingFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg='Connecting with api_key="my-secret-key-12345"',
            args=None, exc_info=None,
        )
        f.filter(record)
        assert "my-secret-key-12345" not in record.msg
        assert "****" in record.msg


class TestFormatters:
    """Tests for JSON and human formatters."""

    def test_json_formatter_produces_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="polyfast.test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=None, exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["severity"] == "INFO"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_json_formatter_includes_entity(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="polyfast.test", level=logging.INFO, pathname="", lineno=0,
            msg="Order placed", args=None, exc_info=None,
        )
        record.entity_type = "order"
        record.entity_id = "ord-123"
        output = formatter.format(record)
        data = json.loads(output)
        assert data["entity_type"] == "order"
        assert data["entity_id"] == "ord-123"

    def test_human_formatter_output(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="polyfast.test", level=logging.WARNING, pathname="", lineno=0,
            msg="Connection lost", args=None, exc_info=None,
        )
        record.entity_type = "rtds"
        record.entity_id = ""
        output = formatter.format(record)
        assert "WARNING" in output
        assert "Connection lost" in output
        assert "[rtds]" in output


class TestLoggerService:
    """Tests for logger setup and usage."""

    def test_setup_logging_creates_logger(self):
        setup_logging(level="DEBUG", fmt="json", mask_credentials=True)
        logger = get_logger("test")
        assert logger.name == "polyfast.test"

    def test_log_event_with_entity(self, capfd):
        setup_logging(level="DEBUG", fmt="human", mask_credentials=True)
        logger = get_logger("test_event")
        log_event(logger, logging.INFO, "Test event", entity_type="discovery", entity_id="evt-1")
        captured = capfd.readouterr()
        assert "Test event" in captured.out

    def test_credential_masking_in_log_output(self, capfd):
        setup_logging(level="DEBUG", fmt="human", mask_credentials=True)
        logger = get_logger("test_mask")
        logger.info('Using api_key="f649cb77-2283-dbf3-510d-f8a3dafade63"')
        captured = capfd.readouterr()
        assert "f649cb77-2283-dbf3-510d-f8a3dafade63" not in captured.out
        assert "****" in captured.out
