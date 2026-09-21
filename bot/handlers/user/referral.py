from aiogram import Router, F
from aiogram.types import Message
from bot.database.crud import get_user_by_id
from bot.services.i18n import t
from bot.config import REFERRAL_PERCENT

router = Router()


@router.message(F.text.in_(["Affiliate Program", "የግብዣ ፕሮግራም", "[ Affiliate Program ]", "[ የግብዣ ፕሮግራም ]", "👥 Referral Link", "👥 የግብዣ ሊንክ (Referral)"]))
async def show_referral(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"

    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"

    text = t("referral_info", lang, percent=REFERRAL_PERCENT, link=ref_link)
    await message.answer(text, parse_mode="HTML")
