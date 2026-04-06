"""getMarket() 5M Live Validation — gercek API response dogrulama.

READ-ONLY: Sadece getMarket okuma. Order/settlement/redeem cagrisi YOK.
Public endpoint: auth gerektirmez.

Dogrulanacak 3 madde:
1) closed / resolved ayrimi
2) winner/outcome normalizasyonu (raw string, format, whitespace)
3) condition_id -> market response eslesmesi

Birden fazla 5M event response'u gormek icin:
- Bitmis event'ler condition_id ile sorgulanir
- Farkli timing'lerde response karsilastirilir

Calistirma:
    python tools/live_getmarket_validation.py

Opsiyonel: condition_id parametresi
    python tools/live_getmarket_validation.py 0xABC123...
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HDR = "\033[96m"
RST = "\033[0m"
OK = "\033[92mOK\033[0m"
WARN = "\033[93mWARN\033[0m"
FAIL = "\033[91mFAIL\033[0m"

CLOB_BASE = "https://clob.polymarket.com"

# Validation path tracking
VALIDATION_PATH = "unknown"  # "credentialed_api" / "public_fallback" / "failed"


def check_credentials() -> dict | None:
    """API credential kontrol et (.env dosyasindan — KEY=VALUE ve duz metin)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    creds = {}

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
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
            elif "=" in line:
                key, _, val = line.partition("=")
                creds[key.strip()] = val.strip().strip('"').strip("'")

    # Ortam degiskenlerinden de kontrol et
    for key in ["POLY_API_KEY", "API_KEY", "PRIVATE_KEY"]:
        if os.environ.get(key):
            creds[key] = os.environ[key]

    api_key = creds.get("API_KEY") or ""
    private_key = creds.get("PRIVATE_KEY") or ""

    if api_key and private_key:
        return creds

    return None


async def fetch_market_credentialed(condition_id: str, creds: dict) -> dict | None:
    """SDK ile getMarket — credentialed path."""
    try:
        from py_clob_client.client import ClobClient
        client = ClobClient(
            host=CLOB_BASE,
            key=creds.get("PRIVATE_KEY", ""),
            chain_id=137,
            creds={
                "apiKey": creds.get("POLY_API_KEY") or creds.get("API_KEY", ""),
                "secret": creds.get("SECRET", ""),
                "passphrase": creds.get("PASSPHRASE", ""),
            },
        )
        market = client.get_market(condition_id)
        return market if isinstance(market, dict) else None
    except ImportError:
        print(f"  {WARN} py-clob-client SDK not installed — credentialed path unavailable")
        return None
    except Exception as e:
        print(f"  {WARN} Credentialed fetch failed: {e}")
        return None


async def fetch_market_public(condition_id: str) -> dict | None:
    """GET /markets/{condition_id} — public, auth gerektirmez."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{CLOB_BASE}/markets/{condition_id}")
            if resp.status_code == 200:
                return resp.json()
            print(f"  {FAIL} HTTP {resp.status_code} for {condition_id}")
            return None
    except Exception as e:
        print(f"  {FAIL} Public fetch error: {e}")
        return None


async def fetch_market(condition_id: str, creds: dict | None = None) -> dict | None:
    """getMarket — once credentialed, sonra public fallback."""
    global VALIDATION_PATH

    # 1. Credentialed path
    if creds:
        result = await fetch_market_credentialed(condition_id, creds)
        if result:
            VALIDATION_PATH = "credentialed_api"
            return result
        print(f"  {WARN} Credentialed path failed, falling back to public...")

    # 2. Public fallback
    result = await fetch_market_public(condition_id)
    if result:
        if not creds:
            VALIDATION_PATH = "public_fallback"
        else:
            VALIDATION_PATH = "public_fallback"  # credentialed failed, public worked
        return result

    VALIDATION_PATH = "failed"
    return None


async def fetch_recent_5m_events() -> list[dict]:
    """Gamma API'den son bitmis 5M crypto up/down event'leri bul."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Gamma API — public
            resp = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={
                    "closed": "true",
                    "limit": "20",
                    "order": "endDate",
                    "ascending": "false",
                },
            )
            if resp.status_code != 200:
                print(f"  {FAIL} Gamma API HTTP {resp.status_code}")
                return []

            markets = resp.json()
            # 5M crypto up/down filtrele
            results = []
            for m in markets:
                q = (m.get("question") or "").lower()
                slug = (m.get("slug") or "").lower()
                # 5-minute veya 5m iceren crypto up/down
                if ("5-minute" in q or "5m" in slug or "5min" in q) and \
                   ("up" in q or "down" in q) and \
                   any(c in q for c in ["btc", "eth", "sol", "doge", "xrp", "bnb", "bitcoin", "ether"]):
                    results.append(m)
                    if len(results) >= 5:
                        break
            return results
    except Exception as e:
        print(f"  {FAIL} Gamma fetch error: {e}")
        return []


def analyze_market(market: dict, label: str = "") -> dict:
    """Market response'u analiz et ve dogrulama sonucu uret."""
    header = f"  {label}" if label else ""
    print(f"\n{HDR}--- MARKET ANALYSIS {header} ---{RST}")

    analysis = {
        "condition_id": market.get("condition_id", ""),
        "question": market.get("question", "")[:80],
        "closed": market.get("closed"),
        "active": market.get("active"),
        "end_date_iso": market.get("end_date_iso", ""),
        "market_slug": market.get("market_slug", ""),
    }

    print(f"  condition_id: {analysis['condition_id']}")
    print(f"  question: {analysis['question']}")
    print(f"  closed: {analysis['closed']}")
    print(f"  active: {analysis['active']}")
    print(f"  end_date_iso: {analysis['end_date_iso']}")
    print(f"  market_slug: {analysis['market_slug']}")

    # ── 1) closed / resolved ayrimi ──
    is_closed = analysis["closed"]
    print(f"\n  [1] CLOSED/RESOLVED:")
    print(f"      closed={is_closed} (type={type(is_closed).__name__})")

    # ── 2) tokens + winner/outcome ──
    tokens = market.get("tokens", [])
    analysis["token_count"] = len(tokens)
    analysis["tokens"] = []

    print(f"\n  [2] TOKENS (count={len(tokens)}):")
    has_winner = False
    winning_side = ""

    for i, token in enumerate(tokens):
        raw_outcome = token.get("outcome")
        winner = token.get("winner")
        price = token.get("price")
        token_id = token.get("token_id", "")[:20]

        t_info = {
            "index": i,
            "raw_outcome": raw_outcome,
            "raw_outcome_type": type(raw_outcome).__name__,
            "raw_outcome_repr": repr(raw_outcome),
            "winner": winner,
            "winner_type": type(winner).__name__,
            "price": price,
            "token_id_prefix": token_id,
        }
        analysis["tokens"].append(t_info)

        # Normalizasyon kontrolu
        normalized = raw_outcome.upper().strip() if isinstance(raw_outcome, str) else str(raw_outcome)
        matches_expected = normalized in ("UP", "DOWN")

        tag = OK if matches_expected else WARN
        print(f"      token[{i}]:")
        print(f"        outcome: {tag} raw={repr(raw_outcome)} normalized={repr(normalized)}")
        print(f"        winner: {winner} (type={type(winner).__name__})")
        print(f"        price: {price}")
        print(f"        token_id: {token_id}...")

        # Whitespace / format kontrol
        if isinstance(raw_outcome, str):
            if raw_outcome != raw_outcome.strip():
                print(f"        {WARN} WHITESPACE detected in outcome!")
            if raw_outcome != raw_outcome.upper() and raw_outcome != raw_outcome.lower():
                print(f"        {WARN} Mixed case: {repr(raw_outcome)}")

        if winner is True:
            has_winner = True
            winning_side = normalized

    analysis["has_winner"] = has_winner
    analysis["winning_side"] = winning_side

    # ── 3) resolved = closed + winner ──
    resolved = is_closed is True and has_winner
    analysis["resolved"] = resolved

    print(f"\n  [3] RESOLUTION STATUS:")
    tag = OK if resolved else WARN
    print(f"      {tag} resolved={resolved} (closed={is_closed}, has_winner={has_winner})")
    if has_winner:
        print(f"      winning_side: {winning_side}")
    elif is_closed:
        print(f"      {WARN} Market CLOSED but NO WINNER found in tokens!")

    return analysis


async def main():
    print(f"\n{HDR}{'#' * 60}")
    print(f"  getMarket() 5M LIVE VALIDATION")
    print(f"  READ-ONLY — no orders, no settlement")
    print(f"{'#' * 60}{RST}")

    all_analyses = []

    # 0) Credential kontrolu
    print(f"\n{HDR}[CREDENTIAL CHECK]{RST}")
    creds = check_credentials()
    if creds:
        masked_key = creds.get("POLY_API_KEY", creds.get("API_KEY", ""))[:8] + "..."
        print(f"  {OK} API credentials found (key={masked_key})")
        print(f"  Validation path: CREDENTIALED API (once SDK, sonra public fallback)")
    else:
        print(f"  {WARN} API credentials NOT FOUND")
        print(f"  .env dosyasi kontrol edildi — POLY_API_KEY/PRIVATE_KEY bulunamadi")
        print(f"  Validation path: PUBLIC FALLBACK ONLY")
        print(f"  NOT: Credentialed path test EDILMEDI")

    # A) Kullanici condition_id verdiyse direkt sorgula
    if len(sys.argv) > 1:
        cid = sys.argv[1]
        print(f"\n{HDR}[USER SUPPLIED] condition_id: {cid}{RST}")
        market = await fetch_market(cid, creds)
        if market:
            analysis = analyze_market(market, "USER-SUPPLIED")
            all_analyses.append(analysis)
        else:
            print(f"  {FAIL} Market not found for {cid}")

    # B) Gamma API'den son bitmis 5M event'leri bul
    print(f"\n{HDR}[AUTO-DISCOVERY] Searching for recent closed 5M events...{RST}")
    events = await fetch_recent_5m_events()

    if not events:
        print(f"  {WARN} No recent 5M crypto up/down events found via Gamma API")

    for event in events[:3]:  # max 3 event
        cid = event.get("conditionId") or event.get("condition_id") or ""
        clob_ids = event.get("clobTokenIds") or []

        if not cid and clob_ids:
            print(f"\n  Gamma event: {event.get('question', '')[:60]}")
            print(f"  clobTokenIds: {clob_ids[:2]}")
            for tid in clob_ids[:1]:
                market = await fetch_market(tid, creds)
                if market:
                    analysis = analyze_market(market, f"GAMMA->{tid[:20]}")
                    all_analyses.append(analysis)
        elif cid:
            market = await fetch_market(cid, creds)
            if market:
                analysis = analyze_market(market, f"GAMMA->{cid[:20]}")
                all_analyses.append(analysis)

    # C) Summary
    print(f"\n{HDR}{'=' * 60}")
    print(f"  DOGRULAMA OZETI")
    print(f"{'=' * 60}{RST}")

    if not all_analyses:
        print(f"  {FAIL} Hicbir market response alinamadi")
        print(f"  Olasi nedenler:")
        print(f"    - API erisimsiz (network/proxy)")
        print(f"    - 5M event bulunamadi (piyasa kapali?)")
        print(f"    - Gamma API format degismis")
        sys.exit(1)

    # Ortak bulgular
    outcome_formats = set()
    winner_types = set()
    closed_values = set()
    resolved_count = 0

    for a in all_analyses:
        closed_values.add(str(a["closed"]))
        if a["resolved"]:
            resolved_count += 1
        for t in a["tokens"]:
            outcome_formats.add(t["raw_outcome_repr"])
            winner_types.add(t["winner_type"])

    print(f"\n  Validation path: {VALIDATION_PATH}")
    print(f"  Toplam market incelendi: {len(all_analyses)}")
    print(f"  Resolved: {resolved_count}/{len(all_analyses)}")
    print(f"\n  Outcome format'lari: {outcome_formats}")
    print(f"  Winner type'lari: {winner_types}")
    print(f"  Closed degerleri: {closed_values}")

    # Normalizasyon onerisi
    all_match_up_down = all(
        t["raw_outcome_repr"] in ("'Up'", "'Down'", "'UP'", "'DOWN'", "'up'", "'down'")
        for a in all_analyses for t in a["tokens"]
    )
    if all_match_up_down:
        print(f"\n  {OK} Tum outcome'lar Up/Down varyantlari — .upper() normalizasyonu YETERLI")
    else:
        print(f"\n  {WARN} Beklenmeyen outcome format'i tespit edildi — parsing guncellenmeli")

    # Raw response kaydet
    output_path = Path("tools/getmarket_responses.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_analyses, f, indent=2, default=str)
    print(f"\n  Raw analysis kaydedildi: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
