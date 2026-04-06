"""ClobClientWrapper — py-clob-client SDK wrapper.

SDK sorumlulukları:
- Auth (private key + API creds)
- Balance okuma (get_balance_allowance)
- Fee rate okuma (neg_risk endpoint)
- Market resolution okuma (getMarket) — v0.6.8
- Order gönderme (create_and_post_order) — v0.5.3'te KAPALI

Fee rate authoritative path (öncelik sırası):
1. SDK neg_risk_fee_rate_bps → token bazlı authoritative
2. Market endpoint fee_rate_bps → fallback
3. DEFAULT_CRYPTO_FEE_RATE → SADECE paper mode guard

Bu surumde order gonderme TEKNIK GUARD ile KAPALI:
- LIVE_ORDER_ENABLED = False
- Bu flag True yapılmadan gerçek order çıkamaz
- Yanlışlıkla canlı order riski SIFIR
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.logging_config.service import get_logger, log_event

logger = get_logger("execution.clob_wrapper")


@dataclass
class MarketResolution:
    """Market resolution durumu — wrapper seviyesinde uretilir.

    Settlement katmani ham API cevabina bagli kalmaz,
    bu model uzerinden calisir.

    Kavram ayrimi:
    - closed: market kapandi, islem yapilamaz
    - resolved: closed + kazanan taraf belli (winner bilgisi mevcut)
    - winning_side: "UP" veya "DOWN" (resolved=True ise dolu)

    Not: "redeemable" bu modelde YOK.
    Redeemable = resolved + shares > 0, bu bot tarafli uygulama karari,
    Polymarket'ten gelen kesin alan degil.
    """
    condition_id: str
    closed: bool = False
    resolved: bool = False       # closed + winner bilgisi mevcut
    winning_side: str = ""       # "UP" veya "DOWN", resolved=True ise dolu
    raw_response: dict | None = None  # debug/log icin ham API cevabi

# TEKNIK GUARD — bu False oldukca gercek order CIKMAZ
LIVE_ORDER_ENABLED = False


class ClobClientWrapper:
    """py-clob-client SDK wrapper.

    Credential lifecycle (v0.7.0):
    - CredentialStore referansi alir (tercihen)
    - Her islemde _ensure_initialized() ile credential version kontrol edilir
    - Credential degistiyse SDK reinitialize edilir
    - Eski credential ile sessiz calisma engellenir

    Backward compat: string params ile de olusturulabilir (test/paper icin).
    """

    def __init__(
        self,
        private_key: str = "",
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
        chain_id: int = 137,
        credential_store=None,
    ):
        self._credential_store = credential_store
        # Fallback: direkt string params (backward compat / test)
        self._private_key = private_key
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._chain_id = chain_id
        self._client = None
        self._initialized = False
        self._last_cred_version: int = -1

    def _ensure_initialized(self) -> None:
        """Credential version kontrol et, degistiyse reinitialize."""
        if self._credential_store is None:
            return  # string params mode — version tracking yok

        current_version = self._credential_store.version
        if current_version == self._last_cred_version:
            return  # degismemis

        # Credential degisti — reinitialize
        creds = self._credential_store.credentials
        self._private_key = creds.private_key
        self._api_key = creds.api_key
        self._api_secret = creds.api_secret
        self._api_passphrase = creds.api_passphrase

        if self._initialized:
            log_event(
                logger, logging.WARNING,
                f"Credential change detected (v{self._last_cred_version} -> v{current_version}) "
                f"— reinitializing SDK",
                entity_type="execution",
                entity_id="cred_change",
            )

        self._last_cred_version = current_version
        self.initialize()

    def initialize(self) -> bool:
        """SDK client olustur. Credentials varsa gercek SDK, yoksa simulated."""
        if self._private_key and self._api_key:
            try:
                from py_clob_client.client import ClobClient
                self._client = ClobClient(
                    host="https://clob.polymarket.com",
                    key=self._private_key,
                    chain_id=self._chain_id,
                    creds={
                        "apiKey": self._api_key,
                        "secret": self._api_secret,
                        "passphrase": self._api_passphrase,
                    },
                )
                self._initialized = True
                log_event(
                    logger, logging.INFO,
                    "CLOB SDK client initialized (real credentials)",
                    entity_type="execution",
                    entity_id="sdk_init",
                )
                return True
            except Exception as e:
                log_event(
                    logger, logging.WARNING,
                    f"CLOB SDK init failed: {e} — running without SDK",
                    entity_type="execution",
                    entity_id="sdk_init_error",
                )
                self._initialized = False
                return False
        else:
            log_event(
                logger, logging.INFO,
                "CLOB SDK: no credentials — paper mode only",
                entity_type="execution",
                entity_id="sdk_no_creds",
            )
            self._initialized = False
            return False

    @property
    def is_initialized(self) -> bool:
        self._ensure_initialized()
        return self._initialized

    # ─── Balance ───

    async def get_balance(self) -> dict | None:
        """CLOB SDK ile balance cek.

        Returns:
            {"available": float, "total": float} veya None.
        """
        self._ensure_initialized()
        if not self._initialized or self._client is None:
            return None

        try:
            # SDK call: get_balance_allowance
            result = self._client.get_balance_allowance()
            if result is not None:
                balance = float(result.get("balance", 0))
                return {"available": balance, "total": balance}
        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Balance fetch failed: {e}",
                entity_type="execution",
                entity_id="balance_error",
            )
        return None

    # ─── Fee Rate ───

    async def get_fee_rate(self, token_id: str) -> float | None:
        """Fee rate cek — authoritative path.

        Oncelik:
        1. neg_risk endpoint (token bazli)
        2. market endpoint (fallback)
        """
        self._ensure_initialized()
        if not self._initialized or self._client is None:
            return None

        try:
            # SDK veya direct API call
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                # 1. neg_risk endpoint
                resp = await client.get(
                    f"https://clob.polymarket.com/neg-risk/markets/{token_id}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    rate = data.get("neg_risk_fee_rate")
                    if rate is not None:
                        return float(rate)
                    bps = data.get("fee_rate_bps")
                    if bps is not None:
                        return int(bps) / 10000.0

                # 2. market endpoint fallback
                resp2 = await client.get(
                    f"https://clob.polymarket.com/markets/{token_id}"
                )
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    bps2 = data2.get("fee_rate_bps")
                    if bps2 is not None:
                        return int(bps2) / 10000.0

        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Fee rate fetch failed: {e}",
                entity_type="execution",
                entity_id="fee_rate_error",
            )
        return None

    # ─── Market Resolution ───

    async def get_market_resolution(self, condition_id: str) -> MarketResolution:
        """Market resolution durumunu sorgula.

        CLOB API getMarket(condition_id) ile:
        - Market closed mi
        - Winner belli mi (tokens[].winner)
        - Kazanan taraf (UP/DOWN)

        SDK yoksa veya API erisimsiz ise bos MarketResolution doner.
        """
        self._ensure_initialized()
        result = MarketResolution(condition_id=condition_id)

        if not self._initialized or self._client is None:
            return result

        try:
            # SDK call: get_market(condition_id)
            market = self._client.get_market(condition_id)
            if market is None:
                return result

            result.raw_response = market if isinstance(market, dict) else None
            market_data = market if isinstance(market, dict) else {}

            # closed kontrolu
            result.closed = bool(market_data.get("closed", False))

            if result.closed:
                # Winner kontrolu — tokens listesinde winner=True olan
                tokens = market_data.get("tokens", [])
                for token in tokens:
                    if token.get("winner", False):
                        outcome = token.get("outcome", "").upper()
                        if outcome in ("UP", "DOWN"):
                            result.resolved = True
                            result.winning_side = outcome
                        break

            if result.resolved:
                log_event(
                    logger, logging.INFO,
                    f"Market resolved: {condition_id} -> {result.winning_side} wins",
                    entity_type="resolution",
                    entity_id=condition_id,
                )
            elif result.closed:
                log_event(
                    logger, logging.WARNING,
                    f"Market closed but winner not found: {condition_id}",
                    entity_type="resolution",
                    entity_id=condition_id,
                )

        except Exception as e:
            log_event(
                logger, logging.WARNING,
                f"Market resolution check failed: {condition_id} — {e}",
                entity_type="resolution",
                entity_id=condition_id,
            )

        return result

    # ─── Order (TEKNIK GUARD ILE KAPALI) ───

    async def send_market_fok_order(
        self,
        token_id: str,
        side: str,
        amount_usd: float,
    ) -> dict | None:
        """Market FOK order gonder.

        TEKNIK GUARD: LIVE_ORDER_ENABLED = False oldukca CALISMAZ.
        Gercek order CIKMAZ.
        """
        self._ensure_initialized()
        if not LIVE_ORDER_ENABLED:
            log_event(
                logger, logging.WARNING,
                "LIVE ORDER BLOCKED — LIVE_ORDER_ENABLED = False",
                entity_type="execution",
                entity_id="order_blocked",
            )
            return None

        if not self._initialized or self._client is None:
            return None

        # TODO: gercek SDK order gonderme
        # order = self._client.create_and_post_order(...)
        # return {"order_id": ..., "fill_price": ..., "status": ...}

        return None
