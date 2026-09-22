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
        try:
            user_id = None
            bot = data.get("bot")
            if isinstance(event, Message) and event.from_user:
                user_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_id = event.from_user.id

            is_admin_user = user_id in ADMIN_IDS or user_id == OWNER_ID

            # 1. Maintenance Mode check
            try:
                maintenance_active = await get_setting("maintenance_mode", "0") == "1"
            except Exception:
                maintenance_active = False

            if maintenance_active and not is_admin_user:
                maint_msg = (
                    "<b>SYSTEM MAINTENANCE IN PROGRESS</b>\n"
                    "────────────────────────\n"
                    "The store network is currently undergoing scheduled maintenance. Please check back shortly.\n\n"
                    "<i>ቦቱ በአሁኑ ሰዓት በማሻሻያ ላይ ይገኛል፣ እባክዎ ጥቂት ቆይተው እንደገና ይሞክሩ።</i>"
                )
                if isinstance(event, Message):
                    await event.answer(maint_msg, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.message.answer(maint_msg, parse_mode="HTML")
                    await event.answer()
                return None

            # 2. Force Join check
            try:
                raw_channels = await get_setting("force_join_channels", "")
            except Exception:
                raw_channels = ""

            channels: List[str] = [c.strip() for c in raw_channels.split(",") if c.strip()] if raw_channels else FORCE_JOIN_CHANNELS

            if not channels or is_admin_user or not user_id:
                return await handler(event, data)

            unjoined_buttons = []
            for ch in channels:
                try:
                    member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
                    if member.status in ("left", "kicked"):
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
                            unjoined_buttons.append([InlineKeyboardButton(text="Join Required Channel", url=link)])
                except Exception as e:
                    logger.warning(f"Force join bypass for channel {ch}: {e}")

            if unjoined_buttons:
                unjoined_buttons.append([InlineKeyboardButton(text="Verify Membership / አረጋግጥ", callback_data="check_join")])
                msg_text = (
                    "<b>CHANNEL SUBSCRIPTION REQUIRED</b>\n"
                    "────────────────────────\n"
                    "Please subscribe to our community channel below, then click <b>Verify</b> to enter the store.\n\n"
                    "<i>ቦቱን ለመጠቀም እባክዎ መጀመሪያ ቻናላችንን ይቀላቀሉ።</i>"
                )
                kb = InlineKeyboardMarkup(inline_keyboard=unjoined_buttons)
                if isinstance(event, Message):
                    await event.answer(msg_text, reply_markup=kb, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    if event.data == "check_join":
                        await event.answer("Please join the required channel first before verifying.", show_alert=True)
                    else:
                        await event.message.answer(msg_text, reply_markup=kb, parse_mode="HTML")
                        await event.answer()
                return None

        except Exception as exc:
            logger.error(f"Error in ForceJoinMiddleware: {exc}", exc_info=True)

        return await handler(event, data)
