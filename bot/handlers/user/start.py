import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from bot.database.crud import get_or_create_user, set_user_language, get_user_by_id, get_setting
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

    lang = user.language or "en"
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID

    custom_welcome = await get_setting("welcome_text")
    welcome_text = custom_welcome if custom_welcome else t("welcome", lang)
    reply_kb = get_main_menu(lang=lang, is_admin=is_admin)

    await message.answer(welcome_text, reply_markup=reply_kb, parse_mode="HTML")


@router.message(F.text.in_(["[ Language ]", "Language", "🌐 Language", "🌐 ቋንቋ / Language", "Language / ቋንቋ"]))
async def select_language(message: Message):
    await message.answer("Choose your display language / ቋንቋ ይምረጡ:", reply_markup=get_language_menu())


@router.message(F.text.in_(["Amharic (አማርኛ)", "🇪🇹 አማርኛ (Amharic)"]))
async def set_lang_am(message: Message):
    user_id = message.from_user.id
    await set_user_language(user_id, "am")
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID
    await message.answer("ቋንቋው ወደ <b>አማርኛ</b> ተቀይሯል!", reply_markup=get_main_menu("am", is_admin), parse_mode="HTML")


@router.message(F.text.in_(["English", "🇬🇧 English"]))
async def set_lang_en(message: Message):
    user_id = message.from_user.id
    await set_user_language(user_id, "en")
    is_admin = user_id in ADMIN_IDS or user_id == OWNER_ID
    await message.answer("Language set to <b>English</b>.", reply_markup=get_main_menu("en", is_admin), parse_mode="HTML")


@router.message(F.text.in_(["< Back", "🔙 Back / ተመለስ", "🔙 Back", "🔙 ተመለስ"]))
async def back_to_main(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"
    is_admin = message.from_user.id in ADMIN_IDS or message.from_user.id == OWNER_ID
    await message.answer(t("welcome", lang), reply_markup=get_main_menu(lang, is_admin), parse_mode="HTML")


@router.message(F.text.in_(["[ Customer Support ]", "[ Support ]", "Support", "💬 Customer Support", "💬 24/7 Support"]))
async def support_info(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"
    text = (
        f"<b>CUSTOMER SUPPORT</b>\n"
        f"────────────────────────\n"
        f"For orders, key issues, custom inquiries, or corporate sales:\n\n"
        f"<blockquote>• <b>Direct Telegram Support:</b> @{SUPPORT_USERNAME}\n"
        f"• <b>Availability:</b> 24/7 Automated Desk</blockquote>"
        if lang == "en" else
        f"<b>የደንበኞች አገልግሎት (Support)</b>\n"
        f"────────────────────────\n"
        f"ማንኛውም ጥያቄ ወይም እርዳታ ሲፈልጉ በ @{SUPPORT_USERNAME} ያነጋግሩን።"
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
    await call.message.answer("<b>እናመሰግናለን!</b> አሁን ቦቱን መጠቀም ይችላሉ።\nለመጀመር /start ይጫኑ።", parse_mode="HTML")
    await call.answer()
