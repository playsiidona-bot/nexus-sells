import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from bot.database.crud import get_or_create_user, set_user_language, get_user_by_id
from bot.keyboards.reply import get_main_menu, get_language_menu
from bot.services.i18n import t
from bot.config import ADMIN_IDS, OWNER_ID, SUPPORT_USERNAME

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name or "Customer"

    # Check for referral parameter
    referrer_id = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        param = args[1].strip()
        if param.startswith("ref_"):
            ref_str = param.replace("ref_", "")
            if ref_str.isdigit():
                referrer_id = int(ref_str)

    user = await get_or_create_user(
        telegram_id=user_id,
        username=username,
        first_name=first_name,
        referrer_id=referrer_id
    )

    lang = user.language or "am"
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID

    welcome_text = t("welcome", lang)
    reply_kb = get_main_menu(lang=lang, is_admin=is_admin)

    await message.answer(welcome_text, reply_markup=reply_kb, parse_mode="HTML")


@router.message(F.text.in_(["🌐 ቋንቋ / Language", "Language / ቋንቋ"]))
async def select_language(message: Message):
    await message.answer("🌐 ቋንቋ ይምረጡ / Choose your language:", reply_markup=get_language_menu())


@router.message(F.text == "🇪🇹 አማርኛ (Amharic)")
async def set_lang_am(message: Message):
    user_id = message.from_user.id
    await set_user_language(user_id, "am")
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID
    await message.answer("✅ ቋንቋው ወደ <b>አማርኛ</b> ተቀይሯል!", reply_markup=get_main_menu("am", is_admin), parse_mode="HTML")


@router.message(F.text == "🇬🇧 English")
async def set_lang_en(message: Message):
    user_id = message.from_user.id
    await set_user_language(user_id, "en")
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID
    await message.answer("✅ Language switched to <b>English</b>!", reply_markup=get_main_menu("en", is_admin), parse_mode="HTML")


@router.message(F.text.in_(["🔙 Back / ተመለስ"]))
async def back_to_main(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "am"
    is_admin = message.from_user.id in ADMIN_IDS or message.from_user.id == OWNER_ID
    await message.answer(t("welcome", lang), reply_markup=get_main_menu(lang, is_admin), parse_mode="HTML")


@router.message(F.text.in_(["💬 የደንበኞች አገልግሎት", "💬 Customer Support"]))
async def support_info(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "am"
    text = (
        f"💬 <b>የደንበኞች አገልግሎት (Support):</b>\n\n"
        f"ማንኛውም ጥያቄ ወይም እርዳታ ሲፈልጉ በ @{SUPPORT_USERNAME} ያነጋግሩን።"
        if lang == "am" else
        f"💬 <b>Customer Support:</b>\n\n"
        f"For any inquiries or assistance, please contact @{SUPPORT_USERNAME}."
    )
    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "close_view")
async def close_message(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        await call.answer()


@router.callback_query(F.data == "check_join")
async def check_channel_join(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("✅ እናመሰግናለን! አሁን ቦቱን መጠቀም ይችላሉ።\nለመጀመር /start ይጫኑ።")
    await call.answer()
