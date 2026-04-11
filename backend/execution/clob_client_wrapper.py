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

# TEKNIK GUARD — True ise gercek order CIKABILIR
# Cift kilit: paper_mode=False ile birlikte olmali
# v0.9.2: ilk controlled live test icin acildi
LIVE_ORDER_ENABLED = True


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
        signature_type: int = 0,
        credential_store=None,
    ):
        self._credential_store = credential_store
        # Fallback: direkt string params (backward compat / test)
        self._private_key = private_key
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._chain_id = chain_id
        self._signature_type = signature_type
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
        pk = creds.private_key
        if pk and not pk.startswith("0x"):
            pk = "0x" + pk
        self._private_key = pk
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
                from py_clob_client.clob_types import ApiCreds

                # Funder address: credential store'dan veya private key'den derive
                funder = None
                if self._credential_store:
                    funder = self._credential_store.credentials.funder_address or None

                # ApiCreds objesi — dict değil (SDK uyumluluğu)
                api_creds = ApiCreds(
                    api_key=self._api_key,
                    api_secret=self._api_secret,
                    api_passphrase=self._api_passphrase,
                )

                self._client = ClobClient(
                    host="https://clob.polymarket.com",
                    key=self._private_key,
                    chain_id=self._chain_id,
                    creds=api_creds,
                    signature_type=self._signature_type,
                    funder=funder,
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
                # Plaintext credential sızdırmamak için sadece error tipi logla
                log_event(
                    logger, logging.WARNING,
                    f"CLOB SDK init failed: {type(e).__name__} — running without SDK",
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
            # SDK call: get_balance_allowance (explicit params — SDK bug workaround)
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
                signature_type=self._signature_type,
            )
            result = self._client.get_balance_allowance(params)
            if result is not None:
                raw = int(result.get("balance", 0))
                usd = raw / 1_000_000  # USDC 6 decimals
                return {"available": usd, "total": usd}
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
        amount: float,
    ) -> dict | None:
        """Market FOK order gonder.

        TEKNIK GUARD: LIVE_ORDER_ENABLED = False oldukca CALISMAZ.

        Args:
            token_id: Outcome token ID.
            side: "BUY" veya "SELL".
            amount: BUY=USD tutar, SELL=share sayisi.

        Returns:
            {"status": "matched"|"not_matched"|"error",
             "order_id": str, "fee_rate_bps": int,
             "making_amount": float, "taking_amount": float}
            veya None (guard/init fail).

        FOK retry politikasi:
            - matched → fill, retry YOK
            - not_matched → reject, retry YOK
            - network timeout → tek kisa retry (3s bekle)
            - ayni order tekrar deneme YOK (duplicate guard caller'da)
        """
        self._ensure_initialized()

        if not LIVE_ORDER_ENABLED:
            log_event(
                logger, logging.WARNING,
                "LIVE ORDER BLOCKED — LIVE_ORDER_ENABLED=False",
                entity_type="execution",
                entity_id="order_blocked",
            )
            return None

        if not self._initialized or self._client is None:
            log_event(
                logger, logging.ERROR,
                "Order rejected: SDK client not initialized",
                entity_type="execution",
                entity_id="order_not_init",
            )
            return None

        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        sdk_side = BUY if side.upper() == "BUY" else SELL

        args = MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=sdk_side,
            order_type=OrderType.FOK,
            # fee_rate_bps=0 → SDK __resolve_fee_rate ile endpoint'ten otomatik ceker
        )

        # Attempt 1 + tek transient retry
        last_error = None
        for attempt in range(2):
            try:
                # SDK: create signed order + auto fee resolve
                signed_order = self._client.create_market_order(args)

                # SDK: post to CLOB — response = dict
                response = self._client.post_order(signed_order, orderType=OrderType.FOK)

                # Response parse
                if isinstance(response, dict):
                    success = response.get("success", False)
                    status = response.get("status", "")
                    order_id = response.get("orderID", "")
                    error_msg = response.get("errorMsg", "")

                    # makingAmount/takingAmount: fixed-math 6 decimals string
                    making_raw = response.get("makingAmount", "0")
                    taking_raw = response.get("takingAmount", "0")
                    making = int(making_raw) / 1_000_000 if making_raw else 0
                    taking = int(taking_raw) / 1_000_000 if taking_raw else 0

                    # SDK order'a yazdigi fee_rate_bps'yi kaydet (accounting icin)
                    fee_bps = getattr(args, 'fee_rate_bps', 0) or 0

                    if success and status == "matched":
                        log_event(
                            logger, logging.INFO,
                            f"FOK MATCHED: {side} token={token_id[:16]}... "
                            f"making={making:.6f} taking={taking:.6f} "
                            f"fee_bps={fee_bps} order={order_id[:12]}...",
                            entity_type="execution",
                            entity_id=order_id,
                        )
                        return {
                            "status": "matched",
                            "order_id": order_id,
                            "fee_rate_bps": fee_bps,
                            "making_amount": making,
                            "taking_amount": taking,
                        }

                    # Not matched veya hata
                    reason = error_msg or f"status={status}" or "unknown"
                    log_event(
                        logger, logging.WARNING,
                        f"FOK NOT MATCHED: {side} {reason} order={order_id}",
                        entity_type="execution",
                        entity_id="order_not_matched",
                    )
                    return {
                        "status": "not_matched",
                        "order_id": order_id,
                        "error": reason,
                        "fee_rate_bps": fee_bps,
                    }

                # Response dict degil — beklenmeyen format
                log_event(
                    logger, logging.ERROR,
                    f"Unexpected SDK response type: {type(response).__name__}",
                    entity_type="execution",
                    entity_id="order_unexpected",
                )
                return {"status": "error", "error": f"unexpected response: {type(response).__name__}"}

            except Exception as e:
                last_error = e
                err_name = type(e).__name__
                err_msg = str(e)[:100]

                # Transient network error → tek retry (attempt 0'da)
                if attempt == 0 and self._is_transient_error(e):
                    log_event(
                        logger, logging.WARNING,
                        f"FOK transient error (retry 1): {err_name}: {err_msg}",
                        entity_type="execution",
                        entity_id="order_retry",
                    )
                    import asyncio
                    await asyncio.sleep(3)
                    continue

                # Non-transient veya retry tukendi
                log_event(
                    logger, logging.ERROR,
                    f"FOK FAILED: {err_name}: {err_msg}",
                    entity_type="execution",
                    entity_id="order_failed",
                )
                return {"status": "error", "error": f"{err_name}: {err_msg}"}

        # Retry tukendi
        return {"status": "error", "error": f"exhausted retries: {last_error}"}

    @staticmethod
    def _is_transient_error(e: Exception) -> bool:
        """Network timeout / connection error mi? Retry edilebilir mi?"""
        import httpx
        transient_types = (
            TimeoutError,
            ConnectionError,
            OSError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
        )
        return isinstance(e, transient_types)
