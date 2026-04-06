"""CREDENTIALED CLAIM/REDEEM E2E — uctan uca tek akis dogrulamasi.

Gercek credential ile tam zincir:
1. Credential parse + CredentialStore yukle
2. ClobClientWrapper credential'li init
3. Position ac (paper fill)
4. Position kapat (EXPIRY — token elde, redeem gerekli)
5. SettlementOrchestrator: getMarket() GERCEK API ile resolved kontrol
6. Resolved ise: ClaimRecord olustur
7. Paper redeem execute (gercek TX yok — guard kapali)
8. Balance guncelleme
9. Pending claim temizlenmis mi
10. Idempotent: ikinci settlement skip

GERCEK PARA HAREKETI YOK — paper mode + guard.
AMA: getMarket() GERCEK API call ile resolved bilgisi alinir.

Calistirma:
    python tools/credentialed_claim_redeem_e2e.py
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth_clients.credential_store import CredentialStore, Credentials
from backend.execution.clob_client_wrapper import ClobClientWrapper
from backend.execution.relayer_client_wrapper import RelayerClientWrapper, LIVE_SETTLEMENT_ENABLED
from backend.execution.position_tracker import PositionTracker
from backend.execution.position_record import PositionState
from backend.execution.balance_manager import BalanceManager
from backend.execution.claim_manager import ClaimManager, ClaimOutcome, ClaimStatus
from backend.execution.close_reason import CloseReason
from backend.orchestrator.settlement import SettlementOrchestrator

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
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}
    content = env_path.read_text(encoding="utf-8")
    creds = {}
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
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
    return creds


async def find_resolved_event(clob: ClobClientWrapper) -> tuple[str, str]:
    """Bitmis ve resolved bir 5M event bul. condition_id + winning_side dondur."""
    import httpx

    now = int(time.time())
    for i in range(2, 30):
        slot_start = ((now // 300) - i) * 300
        slug = f"btc-updown-5m-{slot_start}"

        try:
            resp = httpx.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug}, timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                ev = resp.json()[0]
                markets = ev.get("markets", [])
                for mk in markets:
                    cid = mk.get("conditionId", "")
                    if cid:
                        resolution = await clob.get_market_resolution(cid)
                        if resolution.resolved:
                            return cid, resolution.winning_side
        except Exception:
            continue

    return "", ""


async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  CREDENTIALED CLAIM/REDEEM E2E")
    print(f"  Gercek API + Paper Redeem — Tek Akis")
    print(f"{'#' * 60}{RST}")

    # ═══════════════════════════════════════════════
    # STEP 1: Credential parse + store
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 1] CREDENTIAL PARSE + STORE{RST}")
    creds = parse_env()
    has_creds = bool(creds.get("PRIVATE_KEY") and creds.get("API_KEY"))
    check("Credentials found", has_creds)

    if not has_creds:
        print(f"\n  {FAIL} CREDENTIAL BULUNAMADI — e2e YAPILAMAZ")
        sys.exit(1)

    store = CredentialStore()
    store.load(Credentials(
        private_key=creds.get("PRIVATE_KEY", ""),
        api_key=creds.get("API_KEY", ""),
        api_secret=creds.get("SECRET", ""),
        api_passphrase=creds.get("PASSPHRASE", ""),
        funder_address=creds.get("FUNDER", ""),
        relayer_key=creds.get("RELAYER_KEY", ""),
    ))
    check("CredentialStore loaded (version=1)", store.version == 1)

    # ═══════════════════════════════════════════════
    # STEP 2: ClobClientWrapper credential'li init
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 2] CLOB CLIENT INIT{RST}")
    clob = ClobClientWrapper(credential_store=store)
    sdk_ready = clob.is_initialized
    check("SDK initialized via credential_store", sdk_ready)

    if not sdk_ready:
        print(f"  {FAIL} SDK init basarisiz — e2e devam edemez")
        sys.exit(1)

    # ═══════════════════════════════════════════════
    # STEP 3: Resolved event bul (GERCEK API)
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 3] RESOLVED EVENT BUL (GERCEK API){RST}")
    condition_id, winning_side = await find_resolved_event(clob)
    check("Resolved event found", bool(condition_id), f"cid={condition_id[:20]}...")
    check("Winning side determined", winning_side in ("UP", "DOWN"), f"winner={winning_side}")

    if not condition_id:
        print(f"  {FAIL} Resolved event bulunamadi — e2e devam edemez")
        sys.exit(1)

    # ═══════════════════════════════════════════════
    # STEP 4: Execution layer kur
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 4] EXECUTION LAYER{RST}")
    tracker = PositionTracker()
    balance = BalanceManager()
    balance.update(available=100.0)
    claim_mgr = ClaimManager(balance, paper_mode=True)
    relayer = RelayerClientWrapper(credential_store=store)

    settlement = SettlementOrchestrator(
        tracker, claim_mgr, relayer,
        paper_mode=True,
        clob_client=clob,  # GERCEK API — getMarket credential'li
    )

    check("PositionTracker created", True)
    check("BalanceManager: $100.00", balance.available_balance == 100.0)
    check("ClaimManager paper_mode=True", claim_mgr._paper_mode is True)
    check("RelayerWrapper initialized", relayer.is_initialized)
    check("Settlement clob_client set", settlement._clob is not None)

    # ═══════════════════════════════════════════════
    # STEP 5: Position ac + EXPIRY ile kapat
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 5] POSITION OPEN + EXPIRY CLOSE{RST}")
    pos = tracker.create_pending("BTC", "UP", condition_id, "tok_test", 5.0)
    tracker.confirm_fill(pos.position_id, fill_price=0.85)
    check("Position opened", pos.is_open)
    check("Position side=UP", pos.side == "UP")

    # EXPIRY ile kapat — token elde, redeem gerekli
    tracker.request_close(pos.position_id, CloseReason.EXPIRY)
    tracker.confirm_close(pos.position_id, exit_fill_price=0.0)  # satis yok
    check("Position closed (EXPIRY)", pos.is_closed)
    check("was_sold=False (token elde)", pos.was_sold is False)
    check("needs_redeem=True", pos.needs_redeem is True)

    # ═══════════════════════════════════════════════
    # STEP 6: Settlement — GERCEK getMarket + paper redeem
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 6] SETTLEMENT (GERCEK getMarket + PAPER REDEEM){RST}")
    before_balance = balance.available_balance
    settled = await settlement.process_settlements()
    check("Settlement processed", settled == 1, f"settled={settled}")

    # getMarket GERCEK API'den mi geldi?
    check("Resolution method: api", settlement._last_resolution_method == "api",
          f"method={settlement._last_resolution_method}")

    # Winner cache kontrol
    cached = settlement._winner_cache.get(condition_id)
    check("Winner cached from API", cached == winning_side, f"cached={cached}")

    # ═══════════════════════════════════════════════
    # STEP 7: ClaimRecord kontrol
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 7] CLAIM RECORD{RST}")
    claims = claim_mgr.get_claims_by_position(pos.position_id)
    check("ClaimRecord created", len(claims) == 1)

    if claims:
        c = claims[0]
        check("claim_status=SUCCESS", c.claim_status == ClaimStatus.SUCCESS)
        check("claimed_at set", c.claimed_at is not None)
        check("condition_id matches", c.condition_id == condition_id)

        # Winning/losing outcome
        pos_won = pos.side == winning_side
        if pos_won:
            check("Outcome: REDEEMED_WON", c.outcome == ClaimOutcome.REDEEMED_WON)
            check("Claimed amount > 0", c.claimed_amount_usdc > 0, f"${c.claimed_amount_usdc:.4f}")
            check("Balance increased", balance.available_balance > before_balance,
                  f"${before_balance:.2f} -> ${balance.available_balance:.2f}")
        else:
            check("Outcome: REDEEMED_LOST", c.outcome == ClaimOutcome.REDEEMED_LOST)
            check("Claimed amount = $0", c.claimed_amount_usdc == 0.0)
            check("Balance unchanged", balance.available_balance == before_balance)

    # ═══════════════════════════════════════════════
    # STEP 8: Pending temizlenmis mi
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 8] PENDING STATE{RST}")
    check("No pending claims", claim_mgr.has_pending_claims() is False)
    check("No pending settlements", settlement.has_pending_settlements() is False)

    # ═══════════════════════════════════════════════
    # STEP 9: Idempotent — ikinci settlement skip
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 9] IDEMPOTENT{RST}")
    balance_before_retry = balance.available_balance
    settled2 = await settlement.process_settlements()
    check("Second settlement: 0 (skip)", settled2 == 0)
    check("Balance unchanged", balance.available_balance == balance_before_retry)

    # ═══════════════════════════════════════════════
    # STEP 10: Guard kontrolu
    # ═══════════════════════════════════════════════
    print(f"\n{HDR}[STEP 10] GUARD STATUS{RST}")
    check("LIVE_SETTLEMENT_ENABLED=False", LIVE_SETTLEMENT_ENABLED is False)
    check("Paper mode redeem (no real TX)", True, "gercek para hareketi YOK")

    # ═══════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════
    total = len(results)
    passed = sum(1 for _, ok in results if ok)
    failed = total - passed

    print(f"\n{HDR}{'=' * 60}")
    print(f"  CLAIM/REDEEM E2E SONUC: {passed}/{total}", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(f" -- ALL GREEN")

    print(f"\n  AKIS OZETI:")
    print(f"    Credential: .env'den parse edildi")
    print(f"    SDK init: credential_store -> ClobClientWrapper")
    print(f"    getMarket: GERCEK API (credentialed SDK)")
    print(f"    Resolved: {condition_id[:20]}... winner={winning_side}")
    print(f"    Redeem: PAPER (gercek TX yok, guard kapali)")
    print(f"    Balance: ${before_balance:.2f} -> ${balance.available_balance:.2f}")
    print(f"    Pending: temizlendi")
    print(f"    Idempotent: ikinci settlement skip")
    print(f"{'=' * 60}{RST}")

    if failed:
        for label, ok in results:
            if not ok:
                print(f"  {FAIL} {label}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
