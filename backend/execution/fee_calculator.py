"""Fee calculator — Polymarket taker fee hesaplama.

Formul: fee = C x feeRate x p x (1 - p)
- C = shares
- feeRate = base_fee_bps / 10000 (crypto: 1000 bps = 0.10)
- p = fiyat (0-1)

Onemli:
- Buy tarafinda fee SHARES olarak tahsil edilir
- Sell tarafinda fee USDC olarak tahsil edilir
- fee_rate HARDCODE EDILMEZ — dinamik cekilmeli
- Ama PositionRecord'a islem anindaki fee_rate yazilir (sonradan degisse bile eski accounting bozulmaz)

Kaynak: https://docs.polymarket.com/trading/fees
"""

# Default crypto fee rate — GUARD ONLY.
# Production'da dinamik cekilmeli (fee_rate_bps endpoint).
# Polymarket crypto 5M Up/Down: base_fee=1000 bps = 0.10
# Endpoint: GET /fee-rate?token_id=X -> {"base_fee": 1000}
# Paper mode guard — live'da SDK otomatik çeker
DEFAULT_CRYPTO_FEE_RATE = 0.10


class FeeCalculator:
    """Polymarket taker fee hesaplayici.

    fee = C × feeRate × p × (1 - p)
    """

    def __init__(self, fee_rate: float = DEFAULT_CRYPTO_FEE_RATE):
        self._fee_rate = fee_rate

    @property
    def fee_rate(self) -> float:
        return self._fee_rate

    def set_fee_rate(self, rate: float) -> None:
        """Fee rate guncelle (dinamik cekim sonrasi)."""
        self._fee_rate = rate

    def calculate_buy_fee_shares(self, shares: float, price: float) -> float:
        """Buy order fee — shares cinsinden.

        Args:
            shares: Brut share miktari (gross_fill_shares)
            price: Fill fiyati (0-1)

        Returns:
            Fee shares (bu kadar share dusuluyor)
        """
        return shares * self._fee_rate * price * (1.0 - price)

    def calculate_sell_fee_usdc(self, shares: float, price: float) -> float:
        """Sell order fee — USDC cinsinden.

        Args:
            shares: Net share miktari (net_position_shares)
            price: Exit fill fiyati (0-1)

        Returns:
            Fee USDC (bu kadar USDC dusuluyor)
        """
        return shares * self._fee_rate * price * (1.0 - price)

    def calculate_entry(
        self, requested_usd: float, fill_price: float
    ) -> dict:
        """Entry (buy) icin tum fee-aware hesaplama.

        Returns:
            Dict with: gross_fill_shares, entry_fee_shares,
            net_position_shares, fee_rate
        """
        gross_shares = requested_usd / fill_price
        fee_shares = self.calculate_buy_fee_shares(gross_shares, fill_price)
        net_shares = gross_shares - fee_shares

        return {
            "gross_fill_shares": round(gross_shares, 8),
            "entry_fee_shares": round(fee_shares, 8),
            "net_position_shares": round(net_shares, 8),
            "fee_rate": self._fee_rate,
        }

    def calculate_exit(
        self, net_shares: float, exit_price: float
    ) -> dict:
        """Exit (sell) icin tum fee-aware hesaplama.

        Returns:
            Dict with: exit_gross_usdc, actual_exit_fee_usdc, net_exit_usdc
        """
        gross_usdc = net_shares * exit_price
        fee_usdc = self.calculate_sell_fee_usdc(net_shares, exit_price)
        net_usdc = gross_usdc - fee_usdc

        return {
            "exit_gross_usdc": round(gross_usdc, 8),
            "actual_exit_fee_usdc": round(fee_usdc, 8),
            "net_exit_usdc": round(net_usdc, 8),
        }

    def estimate_exit(
        self, net_shares: float, current_price: float
    ) -> dict:
        """Acik pozisyon icin tahmini exit hesaplama.

        Returns:
            Dict with: gross_position_value, estimated_exit_fee_usdc,
            net_exit_value_estimate
        """
        gross_value = net_shares * current_price
        est_fee = self.calculate_sell_fee_usdc(net_shares, current_price)
        net_value = gross_value - est_fee

        return {
            "gross_position_value": round(gross_value, 8),
            "estimated_exit_fee_usdc": round(est_fee, 8),
            "net_exit_value_estimate": round(net_value, 8),
        }
