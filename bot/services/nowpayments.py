import logging
import aiohttp
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class NOWPaymentsClient:
    """
    Async client for NOWPayments Crypto Gateway (https://nowpayments.io).
    Non-custodial, 300+ cryptocurrencies, instant payout to merchant wallet.
    """

    BASE_URL = "https://api.nowpayments.io/v1"

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=25)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def create_invoice(
        self,
        amount: float,
        currency: str = "usd",
        order_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a NOWPayments invoice.
        Returns: {'id': '...', 'order_id': '...', 'invoice_url': 'https://nowpayments.io/payment/?iid=...'}
        """
        session = await self.get_session()
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "price_amount": amount,
            "price_currency": currency.lower(),
            "order_id": order_id or f"order_{amount}",
            "order_description": description or "Wallet Balance Top-Up"
        }

        try:
            async with session.post(f"{self.BASE_URL}/invoice", json=payload, headers=headers) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"NOWPayments create_invoice error: {e}")
            return {"message": str(e)}

    async def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Check payment status by payment_id.
        Statuses: 'finished' (success), 'waiting', 'confirming', 'confirmed', 'sending', 'failed', 'refunded', 'expired'.
        """
        session = await self.get_session()
        headers = {"x-api-key": self.api_key}

        try:
            async with session.get(f"{self.BASE_URL}/payment/{payment_id}", headers=headers) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"NOWPayments get_payment_status error: {e}")
            return {"payment_status": "error", "message": str(e)}
