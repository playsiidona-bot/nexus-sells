import time
from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

RATE_LIMIT_DELAY = 0.5  # half second throttle


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self):
        self.last_requests: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            now = time.time()
            last_time = self.last_requests.get(user_id, 0.0)
            if now - last_time < RATE_LIMIT_DELAY:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⚠️ Please slow down!", show_alert=False)
                    except Exception:
                        pass
                return None
            self.last_requests[user_id] = now

        return await handler(event, data)
