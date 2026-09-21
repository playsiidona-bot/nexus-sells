import logging
import aiohttp
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class OxaPayClient:
    """
    Async client for OxaPay Crypto Gateway (https://oxapay.com).
    Low fee (0.4%), Non-custodial, No-KYC payment gateway.
    """

    BASE_URL = "https://api.oxapay.com/merchants"

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
        currency: str = "USD",
        order_id: Optional[str] = None,
        description: Optional[str] = None,
        life_time: int = 60
    ) -> Dict[str, Any]:
        """
        Create a new payment link on OxaPay.
        Returns: {'result': 100, 'message': 'success', 'trackId': 123456, 'payLink': 'https://...'}
        """
        session = await self.get_session()
        payload = {
            "merchant": self.api_key,
            "amount": amount,
            "currency": currency.upper(),
            "lifeTime": life_time,
            "orderId": order_id or f"order_{amount}",
            "description": description or "Wallet Top-up"
        }

        try:
            async with session.post(f"{self.BASE_URL}/request", json=payload) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"OxaPay create_invoice error: {e}")
            return {"result": 0, "message": str(e)}

    async def inquiry_payment(self, track_id: int) -> Dict[str, Any]:
        """
        Inquire payment status by trackId.
        Statuses: 'Paid', 'Waiting', 'Expired', 'Rejected'.
        """
        session = await self.get_session()
        payload = {
            "merchant": self.api_key,
            "trackId": int(track_id)
        }

        try:
            async with session.post(f"{self.BASE_URL}/inquiry", json=payload) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"OxaPay inquiry error: {e}")
            return {"result": 0, "status": "Error", "message": str(e)}
