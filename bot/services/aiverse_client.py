import logging
from typing import Dict, Any, Optional, List
import httpx
from bot.config import AIVERSE_API_KEY, AIVERSE_BASE_URL

logger = logging.getLogger(__name__)


class AIVerseClient:
    """Client for AIVerse Hub Supplier REST API."""

    def __init__(self, api_key: str = AIVERSE_API_KEY, base_url: str = AIVERSE_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def _post(self, action: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "API key not configured"}

        payload = {"key": self.api_key, "action": action}
        if data:
            payload.update(data)

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.post(f"{self.base_url}/api/v2", json=payload)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"HTTP {resp.status_code}: {resp.text[:100]}"}
            except Exception as e:
                logger.error(f"AIVerse API error on action '{action}': {e}")
                return {"error": str(e)}

    async def get_balance(self) -> Dict[str, Any]:
        """Fetch supplier account balance."""
        return await self._post("balance")

    async def get_services(self) -> List[Dict[str, Any]]:
        """Fetch all available supplier services and rates."""
        res = await self._post("services")
        if isinstance(res, list):
            return res
        return []

    async def create_order(self, service_id: str, link: str, quantity: int = 1) -> Dict[str, Any]:
        """Place an order with the supplier."""
        return await self._post("add", {
            "service": service_id,
            "link": link,
            "quantity": quantity
        })

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Check order fulfillment status."""
        return await self._post("status", {"order": order_id})


aiverse_client = AIVerseClient()
