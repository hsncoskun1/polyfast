"""Encrypted credential persistence tests.

Coverage:
- encrypt/decrypt roundtrip
- machine key deterministic
- different key fails decrypt
- corrupted file fails gracefully
- missing file returns None
- no plaintext in encrypted file
- save/load cycle
- has_encrypted_file check
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.auth_clients.credential_store import Credentials
from backend.persistence.credential_persistence import (
    save_encrypted,
    load_encrypted,
    has_encrypted_file,
    _derive_key,
    _credentials_to_json,
    _json_to_credentials,
    _get_machine_identity,
)


def _test_creds() -> Credentials:
    return Credentials(
        api_key="test_api_key_123",
        api_secret="test_api_secret_456",
        api_passphrase="test_passphrase_789",
        private_key="0x" + "ab" * 32,
        funder_address="0x" + "cd" * 20,
        relayer_key="rlk_test_001",
    )


class TestEncryptDecryptRoundtrip:

    def test_roundtrip(self, tmp_path):
        """Encrypt → decrypt → aynı credential."""
        path = tmp_path / "creds.enc"
        creds = _test_creds()

        assert save_encrypted(creds, path) is True
        loaded = load_encrypted(path)

        assert loaded is not None
        assert loaded.api_key == creds.api_key
        assert loaded.api_secret == creds.api_secret
        assert loaded.api_passphrase == creds.api_passphrase
        assert loaded.private_key == creds.private_key
        assert loaded.funder_address == creds.funder_address
        assert loaded.relayer_key == creds.relayer_key

    def test_roundtrip_empty_fields(self, tmp_path):
        """Boş field'lar ile roundtrip."""
        path = tmp_path / "creds.enc"
        creds = Credentials(private_key="0x" + "ab" * 32)

        assert save_encrypted(creds, path) is True
        loaded = load_encrypted(path)

        assert loaded is not None
        assert loaded.private_key == creds.private_key
        assert loaded.api_key == ""
        assert loaded.relayer_key == ""


class TestMachineKey:

    def test_key_deterministic(self):
        """Aynı makinede aynı key üretilir."""
        key1 = _derive_key()
        key2 = _derive_key()
        assert key1 == key2

    def test_key_length(self):
        """Fernet key 44 bytes (base64 encoded 32 bytes)."""
        key = _derive_key()
        assert len(key) == 44

    def test_different_identity_different_key(self):
        """Farklı machine identity → farklı key."""
        key1 = _derive_key()
        with patch('backend.persistence.credential_persistence._get_machine_identity',
                   return_value="other-host|other-user|polyfast-credential-v1"):
            key2 = _derive_key()
        assert key1 != key2

    def test_machine_identity_not_empty(self):
        """Machine identity boş değil."""
        identity = _get_machine_identity()
        assert len(identity) > 10
        assert "|" in identity


class TestDecryptFailure:

    def test_different_machine_key_fails(self, tmp_path):
        """Farklı machine key ile decrypt → None."""
        path = tmp_path / "creds.enc"
        save_encrypted(_test_creds(), path)

        # Farklı key ile okuma dene
        with patch('backend.persistence.credential_persistence._derive_key',
                   return_value=b'A' * 44):  # Geçersiz Fernet key
            result = load_encrypted(path)
        # InvalidToken veya ValueError → None
        assert result is None

    def test_corrupted_file_returns_none(self, tmp_path):
        """Bozuk dosya → None, exception yok."""
        path = tmp_path / "creds.enc"
        path.write_bytes(b"corrupted data here!!!")
        result = load_encrypted(path)
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        """Boş dosya → None."""
        path = tmp_path / "creds.enc"
        path.write_bytes(b"")
        result = load_encrypted(path)
        assert result is None

    def test_missing_file_returns_none(self, tmp_path):
        """Dosya yok → None."""
        path = tmp_path / "nonexistent.enc"
        result = load_encrypted(path)
        assert result is None


class TestNoPlaintextInFile:

    def test_encrypted_file_no_plaintext(self, tmp_path):
        """Encrypted dosyada plaintext credential YOK."""
        path = tmp_path / "creds.enc"
        creds = _test_creds()
        save_encrypted(creds, path)

        raw = path.read_bytes()
        raw_str = raw.decode('latin-1')  # binary-safe decode

        # Plaintext değerler dosyada olmamalı
        assert "test_api_key_123" not in raw_str
        assert "test_api_secret_456" not in raw_str
        assert creds.private_key not in raw_str
        assert "rlk_test_001" not in raw_str

    def test_encrypted_file_not_json(self, tmp_path):
        """Encrypted dosya raw JSON değil."""
        path = tmp_path / "creds.enc"
        save_encrypted(_test_creds(), path)
        raw = path.read_bytes()
        try:
            json.loads(raw)
            assert False, "Encrypted dosya JSON olmamalı"
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Beklenen


class TestHasEncryptedFile:

    def test_exists(self, tmp_path):
        path = tmp_path / "creds.enc"
        save_encrypted(_test_creds(), path)
        assert has_encrypted_file(path) is True

    def test_not_exists(self, tmp_path):
        path = tmp_path / "nonexistent.enc"
        assert has_encrypted_file(path) is False


class TestSaveOverwrite:

    def test_second_save_overwrites(self, tmp_path):
        """İkinci save → dosya güncellenir."""
        path = tmp_path / "creds.enc"

        creds1 = Credentials(private_key="0x" + "11" * 32, relayer_key="rk1")
        creds2 = Credentials(private_key="0x" + "22" * 32, relayer_key="rk2")

        save_encrypted(creds1, path)
        save_encrypted(creds2, path)

        loaded = load_encrypted(path)
        assert loaded is not None
        assert loaded.private_key == "0x" + "22" * 32
        assert loaded.relayer_key == "rk2"


class TestJsonConversion:

    def test_to_json_and_back(self):
        creds = _test_creds()
        j = _credentials_to_json(creds)
        loaded = _json_to_credentials(j)
        assert loaded.api_key == creds.api_key
        assert loaded.private_key == creds.private_key
