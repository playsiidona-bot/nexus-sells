import logging
from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import FORCE_JOIN_CHANNEL, ADMIN_IDS

logger = logging.getLogger(__name__)


class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not FORCE_JOIN_CHANNEL:
            return await handler(event, data)

        user_id = None
        bot = data.get("bot")
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if not user_id or user_id in ADMIN_IDS:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL, user_id=user_id)
            if member.status in ("left", "kicked"):
                channel_link = f"https://t.me/{FORCE_JOIN_CHANNEL.replace('@', '')}"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Join Official Channel", url=channel_link)],
                    [InlineKeyboardButton(text="🔄 Checked / አረጋግጥ", callback_data="check_join")]
                ])
                msg_text = (
                    "⚠️ <b>ቦቱን ለመጠቀም እባክዎ መጀመሪያ ቻናላችንን ይቀላቀሉ!</b>\n\n"
                    "Please join our official channel to continue using the bot."
                )
                if isinstance(event, Message):
                    await event.answer(msg_text, reply_markup=keyboard)
                elif isinstance(event, CallbackQuery):
                    await event.message.answer(msg_text, reply_markup=keyboard)
                    await event.answer()
                return None
        except Exception as e:
            logger.warning(f"Could not check channel membership for {FORCE_JOIN_CHANNEL}: {e}")

        return await handler(event, data)
