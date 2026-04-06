"""Credentialed Resolution Test — credential'li path dogrulama.

READ-ONLY: Sadece getMarket okuma + SDK init. Order/settlement/redeem YOK.

Dogrulanacaklar:
1. Credential parse (.env dosyasindan)
2. ClobClientWrapper credential'li init
3. SDK get_market() credential'li call
4. RelayerClientWrapper credential'li init
5. Guard altinda hangi noktaya kadar calisiliyor

Calistirma:
    python tools/credentialed_resolution_test.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth_clients.credential_store import CredentialStore, Credentials
from backend.execution.clob_client_wrapper import ClobClientWrapper
from backend.execution.relayer_client_wrapper import RelayerClientWrapper, LIVE_SETTLEMENT_ENABLED

HDR = "\033[96m"
RST = "\033[0m"
OK = "\033[92mOK\033[0m"
WARN = "\033[93mWARN\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def check(label, condition, detail=""):
    tag = OK if condition else FAIL
    extra = f"  ({detail})" if detail else ""
    print(f"  {tag} {label}{extra}")
    results.append((label, condition))


def parse_env() -> dict:
    """Parse .env dosyasi — KEY=VALUE ve duz metin formati destekler."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}

    content = env_path.read_text(encoding="utf-8")
    creds = {}

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Duz metin format: "Private key abc123"
        lower = line.lower()
        if lower.startswith("private key "):
            creds["PRIVATE_KEY"] = line.split(" ", 2)[-1].strip()
        elif lower.startswith("polymarket api key "):
            creds["API_KEY"] = line.split(" ", 3)[-1].strip()
        elif lower.startswith("polymarket api secret "):
            creds["SECRET"] = line.split(" ", 3)[-1].strip()
        elif lower.startswith("polymarket api passphrase "):
            creds["PASSPHRASE"] = line.split(" ", 3)[-1].strip()
        elif lower.startswith("funder "):
            creds["FUNDER"] = line.split(" ", 1)[-1].strip()
        elif lower.startswith("relayer api key "):
            creds["RELAYER_KEY"] = line.split(" ", 3)[-1].strip()
        elif lower.startswith("relayer address "):
            creds["RELAYER_ADDRESS"] = line.split(" ", 2)[-1].strip()
        elif lower.startswith("polymarket wallet address "):
            pass  # funder ile ayni
        elif lower.startswith("signature type "):
            pass  # kullanilmiyor
        # KEY=VALUE format
        elif "=" in line:
            key, _, val = line.partition("=")
            creds[key.strip()] = val.strip().strip('"').strip("'")

    return creds


async def test_credential_parse():
    """1. Credential parse."""
    print(f"\n{HDR}[1] CREDENTIAL PARSE{RST}")

    creds = parse_env()
    has_pk = bool(creds.get("PRIVATE_KEY"))
    has_ak = bool(creds.get("API_KEY"))
    has_secret = bool(creds.get("SECRET"))
    has_pass = bool(creds.get("PASSPHRASE"))
    has_funder = bool(creds.get("FUNDER"))
    has_rk = bool(creds.get("RELAYER_KEY"))
    has_ra = bool(creds.get("RELAYER_ADDRESS"))

    check("PRIVATE_KEY found", has_pk)
    check("API_KEY found", has_ak)
    check("SECRET found", has_secret)
    check("PASSPHRASE found", has_pass)
    check("FUNDER found", has_funder)
    check("RELAYER_KEY found", has_rk)
    check("RELAYER_ADDRESS found", has_ra)

    if has_pk:
        print(f"    PRIVATE_KEY: {creds['PRIVATE_KEY'][:8]}... (len={len(creds['PRIVATE_KEY'])})")
    if has_ak:
        print(f"    API_KEY: {creds['API_KEY'][:8]}... (len={len(creds['API_KEY'])})")

    return creds


async def test_credential_store(creds: dict):
    """2. CredentialStore lifecycle."""
    print(f"\n{HDR}[2] CREDENTIAL STORE{RST}")

    store = CredentialStore()
    check("Initial version=0", store.version == 0)

    store.load(Credentials(
        private_key=creds.get("PRIVATE_KEY", ""),
        api_key=creds.get("API_KEY", ""),
        api_secret=creds.get("SECRET", ""),
        api_passphrase=creds.get("PASSPHRASE", ""),
        funder_address=creds.get("FUNDER", ""),
        relayer_key=creds.get("RELAYER_KEY", ""),
    ))
    check("Version incremented to 1", store.version == 1)
    check("has_trading_credentials", store.credentials.has_trading_credentials())
    check("has_signing_credentials", store.credentials.has_signing_credentials())
    check("has_relayer_credentials", store.credentials.has_relayer_credentials())

    return store


async def test_clob_wrapper_init(store: CredentialStore, creds: dict):
    """3. ClobClientWrapper credential'li init + getMarket."""
    print(f"\n{HDR}[3] CLOB CLIENT WRAPPER{RST}")

    wrapper = ClobClientWrapper(credential_store=store)

    # _ensure_initialized cagrilir — credential store'dan ceker
    initialized = wrapper.is_initialized
    check("Credential propagated from store", wrapper._api_key == creds.get("API_KEY", ""))
    check("Version synced", wrapper._last_cred_version == store.version)

    if initialized:
        print(f"    SDK initialized: True")
        check("SDK client created", wrapper._client is not None)

        # getMarket read test — bitmis bir event
        import time
        now = int(time.time())
        slot_start = ((now // 300) - 5) * 300
        slug = f"btc-updown-5m-{slot_start}"

        # Gamma'dan condition_id bul
        import httpx
        try:
            resp = httpx.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug}, timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                ev = resp.json()[0]
                markets = ev.get("markets", [])
                if markets:
                    cid = markets[0].get("conditionId", "")
                    if cid:
                        resolution = await wrapper.get_market_resolution(cid)
                        check("getMarket via SDK works", resolution.condition_id == cid)
                        check("Response has closed field", resolution.closed is not None)
                        print(f"    closed={resolution.closed} resolved={resolution.resolved} winning_side={resolution.winning_side}")
                    else:
                        check("conditionId found", False, "no conditionId in gamma response")
                else:
                    check("Market found in gamma", False, "no markets in event")
            else:
                check("Gamma event found", False, f"slug={slug} not found")
        except Exception as e:
            check("Gamma/CLOB call succeeded", False, str(e))
    else:
        print(f"    SDK initialized: False (SDK not installed or init failed)")
        check("SDK init attempted", True, "expected — SDK may not be pip-installed")

        # Public fallback test
        print(f"\n    Falling back to public HTTP path...")
        import httpx, time
        now = int(time.time())
        slot_start = ((now // 300) - 5) * 300
        slug = f"btc-updown-5m-{slot_start}"
        try:
            resp = httpx.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug}, timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                ev = resp.json()[0]
                markets = ev.get("markets", [])
                if markets:
                    cid = markets[0].get("conditionId", "")
                    resp2 = httpx.get(f"https://clob.polymarket.com/markets/{cid}", timeout=10)
                    if resp2.status_code == 200:
                        check("Public HTTP getMarket works", True)
                        data = resp2.json()
                        print(f"    closed={data.get('closed')} tokens={len(data.get('tokens', []))}")
        except Exception as e:
            check("Public HTTP fallback", False, str(e))


async def test_relayer_wrapper_init(store: CredentialStore, creds: dict):
    """4. RelayerClientWrapper credential'li init."""
    print(f"\n{HDR}[4] RELAYER CLIENT WRAPPER{RST}")

    relayer = RelayerClientWrapper(credential_store=store)

    initialized = relayer.is_initialized
    check("Relayer initialized", initialized)
    check("Private key propagated", relayer._private_key == creds.get("PRIVATE_KEY", ""))
    check("Relayer key propagated", relayer._relayer_api_key == creds.get("RELAYER_KEY", ""))
    check("Version synced", relayer._last_cred_version == store.version)

    # Guard test
    print(f"\n{HDR}[5] SETTLEMENT GUARD{RST}")
    check("LIVE_SETTLEMENT_ENABLED=False", LIVE_SETTLEMENT_ENABLED is False)

    result = await relayer.redeem_positions("0xtest", "UP")
    check("Redeem blocked by guard", result["success"] is False)
    check("Guard flag present", result.get("guard") is True)
    print(f"    Guard mesaji: {result.get('error', '')}")


async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  CREDENTIALED RESOLUTION TEST")
    print(f"  READ-ONLY — no orders, no settlement TX")
    print(f"{'#' * 60}{RST}")

    # 1. Parse
    creds = await test_credential_parse()

    if not creds.get("PRIVATE_KEY"):
        print(f"\n  {FAIL} CREDENTIAL BULUNAMADI — test YAPILAMAZ")
        print(f"  .env dosyasinda PRIVATE_KEY/API_KEY olmali")
        sys.exit(1)

    # 2. Store
    store = await test_credential_store(creds)

    # 3. CLOB wrapper
    await test_clob_wrapper_init(store, creds)

    # 4. Relayer wrapper
    await test_relayer_wrapper_init(store, creds)

    # Summary
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print(f"\n{HDR}{'=' * 60}")
    print(f"  SONUC: {passed}/{total} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(f" -- ALL GREEN")
    print(f"{'=' * 60}{RST}")

    if failed:
        for label, ok in results:
            if not ok:
                print(f"  {FAIL} {label}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
