import logging
from typing import Dict, Any, Callable, Awaitable, List
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import FORCE_JOIN_CHANNELS, ADMIN_IDS, OWNER_ID
from bot.database.crud import get_setting

logger = logging.getLogger(__name__)


class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        bot = data.get("bot")
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        is_admin_user = user_id in ADMIN_IDS or user_id == OWNER_ID

        # 1. Maintenance Mode check
        maintenance_active = await get_setting("maintenance_mode", "0") == "1"
        if maintenance_active and not is_admin_user:
            maint_msg = (
                "🛠️ <b>ቦቱ በአሁኑ ሰዓት በማሻሻያ ላይ ይገኛል (Under Maintenance)</b>\n\n"
                "አዳዲስ አገልግሎቶችን እያካተትን ስለሆነ እባክዎ ጥቂት ቆይተው እንደገና ይሞክሩ።\n\n"
                "<i>The bot is currently undergoing scheduled maintenance. Please check back shortly.</i>"
            )
            if isinstance(event, Message):
                await event.answer(maint_msg, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.message.answer(maint_msg, parse_mode="HTML")
                await event.answer()
            return None

        # 2. Force Join check
        raw_channels = await get_setting("force_join_channels", "")
        channels: List[str] = [c.strip() for c in raw_channels.split(",") if c.strip()] if raw_channels else FORCE_JOIN_CHANNELS

        if not channels or is_admin_user or not user_id:
            return await handler(event, data)

        unjoined_buttons = []
        for ch in channels:
            try:
                member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
                if member.status in ("left", "kicked"):
                    # Resolve safe URL
                    link = None
                    if str(ch).startswith("@"):
                        link = f"https://t.me/{str(ch).lstrip('@')}"
                    else:
                        try:
                            chat_info = await bot.get_chat(ch)
                            if chat_info.username:
                                link = f"https://t.me/{chat_info.username}"
                            elif chat_info.invite_link:
                                link = chat_info.invite_link
                            else:
                                created_link = await bot.create_chat_invite_link(ch)
                                link = created_link.invite_link
                        except Exception:
                            pass

                    if link:
                        unjoined_buttons.append([InlineKeyboardButton(text=f"📢 Join Channel", url=link)])
            except Exception as e:
                # If bot cannot check membership (not admin or invalid ID), gracefully bypass
                logger.warning(f"Force join bypass for channel {ch}: {e}")

        if unjoined_buttons:
            unjoined_buttons.append([InlineKeyboardButton(text="🔄 Verify / አረጋግጥ", callback_data="check_join")])
            msg_text = (
                "📢 <b>Join Our Official Channel to Continue</b>\n\n"
                "Please join our required community channel below, then click <b>Verify</b> to access the store.\n\n"
                "<i>⚠️ ቦቱን ለመጠቀም እባክዎ መጀመሪያ ቻናላችንን ይቀላቀሉ።</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=unjoined_buttons)
            if isinstance(event, Message):
                await event.answer(msg_text, reply_markup=kb, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                if event.data == "check_join":
                    await event.answer("⚠️ You have not joined all channels yet! Please join to continue.", show_alert=True)
                else:
                    await event.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
                    await event.answer()
            return None

        return await handler(event, data)
