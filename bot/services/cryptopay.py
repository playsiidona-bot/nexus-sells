import logging
import aiohttp
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CryptoPayAPIError(Exception):
    """Exception raised when CryptoPay API returns an error."""
    def __init__(self, code: int, name: str, message: Optional[str] = None):
        self.code = code
        self.name = name
        self.message = message or name
        super().__init__(f"CryptoPay API Error [{code}]: {name} - {self.message}")


class CryptoPayClient:
    """
    Async client for Telegram's @CryptoBot API (https://pay.crypt.bot/api).
    Allows creating invoices (fiat USD / crypto USDT, TON, BTC, etc.) and checking payment status.
    """

    def __init__(self, api_token: str, base_url: str = "https://pay.crypt.bot/api"):
        self.api_token = (api_token or "").strip()
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, params: Optional[Dict[str, Any]] = None, is_post: bool = True) -> Dict[str, Any]:
        if not self.api_token:
            raise CryptoPayAPIError(401, "TOKEN_MISSING", "CRYPTO_PAY_TOKEN is not configured in .env")

        session = await self.get_session()
        url = f"{self.base_url}/{method}"
        headers = {
            "Crypto-Pay-API-Token": self.api_token,
            "Content-Type": "application/json"
        }

        try:
            if is_post:
                async with session.post(url, json=params or {}, headers=headers) as resp:
                    resp_json = await resp.json()
            else:
                async with session.get(url, params=params or {}, headers=headers) as resp:
                    resp_json = await resp.json()
        except Exception as e:
            logger.error(f"CryptoPay network request failed: {e}")
            raise CryptoPayAPIError(500, "NETWORK_ERROR", str(e))

        if not resp_json.get("ok", False):
            error_data = resp_json.get("error", {})
            code = error_data.get("code", 0)
            name = error_data.get("name", "UNKNOWN_ERROR")
            raise CryptoPayAPIError(code, name, str(error_data))

        return resp_json.get("result", {})

    async def get_me(self) -> Dict[str, Any]:
        """Test API credentials and return CryptoBot app info."""
        return await self._request("getMe", is_post=False)

    async def create_invoice(
        self,
        amount: float,
        fiat_currency: str = "USD",
        accepted_assets: str = "USDT,TON,BTC,LTC,ETH,TRX",
        description: Optional[str] = None,
        payload: Optional[str] = None,
        expires_in: int = 1800
    ) -> Dict[str, Any]:
        """
        Create a new CryptoBot invoice.
        Accepts fiat amount (e.g. 10.00 USD) and allows customer to pay in accepted crypto assets.
        """
        params = {
            "currency_type": "fiat",
            "fiat": fiat_currency.upper(),
            "amount": f"{amount:.2f}",
            "accepted_assets": accepted_assets,
            "expires_in": expires_in,
        }
        if description:
            params["description"] = description
        if payload:
            params["payload"] = payload

        return await self._request("createInvoice", params, is_post=True)

    async def get_invoice(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch invoice details by ID.
        Status values: 'active', 'paid', 'expired'.
        """
        params = {"invoice_ids": str(invoice_id)}
        res = await self._request("getInvoices", params, is_post=False)
        items = res.get("items", [])
        return items[0] if items else None
