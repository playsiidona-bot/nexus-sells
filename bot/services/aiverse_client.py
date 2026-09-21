import logging
from typing import Dict, Any, Optional, List
import httpx
from bot.config import AIVERSE_API_KEY, AIVERSE_BASE_URL

logger = logging.getLogger(__name__)


class AIVerseClient:
    """
    Official REST API client for AIVerse Hub (https://aiversehub.store/docs).
    Authentication uses the 'X-API-Key' HTTP header.
    """

    def __init__(self, api_key: str = AIVERSE_API_KEY, base_url: str = AIVERSE_BASE_URL):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://aiversehub.store").rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    async def get_me(self) -> Dict[str, Any]:
        """
        Fetch supplier account details and wallet balance.
        GET /api/v1/me -> {"chat_id": int, "first_name": str, "wallet_balance": float}
        """
        if not self.api_key:
            return {"error": "AIVERSE_API_KEY not configured"}

        url = f"{self.base_url}/api/v1/me"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"HTTP {resp.status_code}: {resp.text[:120]}"}
            except Exception as e:
                logger.error(f"AIVerse get_me error: {e}")
                return {"error": str(e)}

    async def get_products(self) -> Dict[str, Any]:
        """
        Fetch supplier products with live wholesale prices and available stock.
        GET /api/v1/products -> {"services": [{"service_id": str, "name": str, "price": float, "stock": int}]}
        """
        if not self.api_key:
            return {"error": "AIVERSE_API_KEY not configured", "services": []}

        url = f"{self.base_url}/api/v1/products"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "services" in data:
                        return data
                    elif isinstance(data, list):
                        return {"services": data}
                    return {"services": []}
                return {"error": f"HTTP {resp.status_code}: {resp.text[:120]}", "services": []}
            except Exception as e:
                logger.error(f"AIVerse get_products error: {e}")
                return {"error": str(e), "services": []}

    async def create_order(self, service_id: str, quantity: int = 1) -> Dict[str, Any]:
        """
        Place an order with automated wallet debit and instant key/account delivery.
        POST /api/v1/order -> {"service_id": str, "quantity": int}
        Response: {"success": bool, "order_id": str, "products": ["key1", ...], "total_cost": float}
        """
        if not self.api_key:
            return {"success": False, "error": "AIVERSE_API_KEY not configured"}

        url = f"{self.base_url}/api/v1/order"
        payload = {
            "service_id": str(service_id),
            "quantity": int(quantity)
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=self._headers())
                if resp.status_code in (200, 201):
                    return resp.json()
                err_text = resp.text[:150]
                logger.error(f"AIVerse order creation failed: {resp.status_code} - {err_text}")
                return {"success": False, "error": f"HTTP {resp.status_code}: {err_text}"}
            except Exception as e:
                logger.error(f"AIVerse order creation error: {e}")
                return {"success": False, "error": str(e)}

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Retrieve order status and delivered credentials.
        GET /api/v1/order/{order_id}
        """
        if not self.api_key:
            return {"error": "AIVERSE_API_KEY not configured"}

        url = f"{self.base_url}/api/v1/order/{order_id}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"HTTP {resp.status_code}: {resp.text[:120]}"}
            except Exception as e:
                logger.error(f"AIVerse get_order error: {e}")
                return {"error": str(e)}

    async def get_orders(self, page: int = 1, limit: int = 50) -> Dict[str, Any]:
        """
        Retrieve order history.
        GET /api/v1/orders
        """
        if not self.api_key:
            return {"orders": []}

        url = f"{self.base_url}/api/v1/orders?page={page}&limit={limit}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"orders": []}
            except Exception as e:
                logger.error(f"AIVerse get_orders error: {e}")
                return {"orders": []}

    async def get_stats(self) -> Dict[str, Any]:
        """
        Retrieve supplier account statistics.
        GET /api/v1/stats
        """
        if not self.api_key:
            return {"error": "AIVERSE_API_KEY not configured"}

        url = f"{self.base_url}/api/v1/stats"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"HTTP {resp.status_code}: {resp.text[:120]}"}
            except Exception as e:
                logger.error(f"AIVerse get_stats error: {e}")
                return {"error": str(e)}


aiverse_client = AIVerseClient()
