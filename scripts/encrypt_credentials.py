"""One-shot: .env'den credential oku → derive et → encrypt et → data/credentials.enc yaz.

Credential değerleri EKRANA BASILMAZ.
Sadece başarı/hata durumu raporlanır.
Çalıştır: python scripts/encrypt_credentials.py
"""

import sys
import os

# Project root'u path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv


def main():
    # 1. .env oku
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        print("HATA: .env dosyasi bulunamadi")
        return False

    # .env formatı esnek parse — KEY=VALUE veya "Label value" her ikisi de çalışır
    pk = ''
    rk = ''

    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Standart KEY=VALUE formatı
            if '=' in line:
                key, _, val = line.partition('=')
                key = key.strip().upper()
                val = val.strip()
                if key == 'PRIVATE_KEY' and val:
                    pk = val
                elif key == 'RELAYER_KEY' and val:
                    rk = val
            else:
                # "Label value" formatı (Not Defteri düzenlemesi)
                low = line.lower()
                parts = line.split(None, 2)  # max 3 parça
                if len(parts) >= 2:
                    if low.startswith('private key'):
                        pk = parts[-1].strip()
                    elif low.startswith('relayer api key'):
                        rk = parts[-1].strip()
                    elif low.startswith('relayer_key'):
                        rk = parts[-1].strip()

    if not pk:
        print("HATA: PRIVATE_KEY bulunamadi")
        return False
    if not rk:
        print("HATA: RELAYER_KEY bulunamadi")
        return False

    print(f"[1/4] .env okundu: PRIVATE_KEY={len(pk)} char, RELAYER_KEY={len(rk)} char")

    # 2. 0x prefix normalize
    if not pk.startswith('0x'):
        pk = '0x' + pk

    # 3. Funder address derive
    try:
        from eth_account import Account
        funder = Account.from_key(pk).address
        print(f"[2/4] Funder address derive: {funder[:6]}****{funder[-4:]}")
    except Exception as e:
        print(f"HATA: Funder derive basarisiz: {type(e).__name__}")
        return False

    # 4. API credential derive
    try:
        from py_clob_client.client import ClobClient
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=137,
            signature_type=2,
            funder=funder,
        )
        derived = client.create_or_derive_api_creds()
        api_key = derived.api_key
        api_secret = derived.api_secret
        api_passphrase = derived.api_passphrase
        print(f"[3/4] API creds derive: api_key={api_key[:8]}****, secret=****, passphrase=****")
    except Exception as e:
        print(f"HATA: API credential derive basarisiz: {type(e).__name__}")
        return False

    # 5. Credential objesi olustur + encrypt
    try:
        from backend.auth_clients.credential_store import Credentials
        from backend.persistence.credential_persistence import save_encrypted, has_encrypted_file

        creds = Credentials(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            private_key=pk,
            funder_address=funder,
            relayer_key=rk,
        )

        save_encrypted(creds)

        if has_encrypted_file():
            print("[4/4] Encrypted credential kaydedildi: data/credentials.enc")
        else:
            print("HATA: Encrypted dosya olusturulamadi")
            return False
    except Exception as e:
        print(f"HATA: Encryption basarisiz: {type(e).__name__}")
        return False

    # 6. Verify — decrypt edip kontrol
    try:
        from backend.persistence.credential_persistence import load_encrypted
        restored = load_encrypted()
        if restored and restored.private_key and restored.relayer_key:
            checks = {
                'has_trading': restored.has_trading_credentials(),
                'has_signing': restored.has_signing_credentials(),
                'has_relayer': restored.has_relayer_credentials(),
            }
            print(f"\nVERIFY: {checks}")
            if all(checks.values()):
                print("BASARILI: Tum credential alanlari sifrelendi ve dogrulandi.")
                return True
            else:
                print(f"UYARI: Bazi alanlar eksik: {[k for k,v in checks.items() if not v]}")
                return False
        else:
            print("HATA: Decrypt sonrasi credential bos")
            return False
    except Exception as e:
        print(f"HATA: Verify basarisiz: {type(e).__name__}")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
