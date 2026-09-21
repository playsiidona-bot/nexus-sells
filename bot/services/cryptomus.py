import json
import base64
import hashlib
import logging
import aiohttp
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CryptomusClient:
    """
    Async client for Cryptomus Payment Gateway (https://cryptomus.com).
    Instant crypto payments, auto-convert to USDT, robust webhook & API support.
    """

    BASE_URL = "https://api.cryptomus.com/v1"

    def __init__(self, merchant_id: str, payment_key: str):
        self.merchant_id = (merchant_id or "").strip()
        self.payment_key = (payment_key or "").strip()
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

    def _generate_sign(self, data_json: str) -> str:
        """Generate Cryptomus MD5 signature: md5(base64(json) + payment_key)."""
        encoded_payload = base64.b64encode(data_json.encode("utf-8")).decode("utf-8")
        sign_str = f"{encoded_payload}{self.payment_key}"
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    async def create_payment(
        self,
        amount: float,
        order_id: str,
        currency: str = "USD",
        lifetime: int = 3600
    ) -> Dict[str, Any]:
        """
        Create a new Cryptomus payment invoice.
        Returns: {'state': 0, 'result': {'uuid': '...', 'order_id': '...', 'amount': '...', 'url': 'https://pay.cryptomus.com/pay/...'}}
        """
        session = await self.get_session()
        payload_dict = {
            "amount": f"{amount:.2f}",
            "currency": currency.upper(),
            "order_id": str(order_id),
            "lifetime": lifetime,
            "is_payment_multiple": True
        }
        payload_json = json.dumps(payload_dict)
        signature = self._generate_sign(payload_json)

        headers = {
            "merchant": self.merchant_id,
            "sign": signature,
            "Content-Type": "application/json"
        }

        try:
            async with session.post(f"{self.BASE_URL}/payment", data=payload_json, headers=headers) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"Cryptomus create_payment error: {e}")
            return {"state": 1, "message": str(e)}

    async def get_payment_info(self, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check Cryptomus payment status by UUID or order_id.
        Statuses: 'paid', 'paid_over', 'process', 'wrong_amount', 'cancel', 'system_fail'.
        """
        session = await self.get_session()
        payload_dict = {}
        if uuid:
            payload_dict["uuid"] = uuid
        if order_id:
            payload_dict["order_id"] = str(order_id)

        payload_json = json.dumps(payload_dict)
        signature = self._generate_sign(payload_json)

        headers = {
            "merchant": self.merchant_id,
            "sign": signature,
            "Content-Type": "application/json"
        }

        try:
            async with session.post(f"{self.BASE_URL}/payment/info", data=payload_json, headers=headers) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"Cryptomus get_payment_info error: {e}")
            return {"state": 1, "message": str(e)}
