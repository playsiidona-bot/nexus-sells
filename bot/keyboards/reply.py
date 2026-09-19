from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.services.i18n import t


def get_main_menu(lang: str = "am", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Generate main reply keyboard."""
    buttons = [
        [KeyboardButton(text=t("menu_catalog", lang)), KeyboardButton(text=t("menu_cart", lang))],
        [KeyboardButton(text=t("menu_wallet", lang)), KeyboardButton(text=t("menu_orders", lang))],
        [KeyboardButton(text=t("menu_referral", lang)), KeyboardButton(text=t("menu_support", lang))],
        [KeyboardButton(text=t("menu_language", lang))]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=t("menu_admin", lang))])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_language_menu() -> ReplyKeyboardMarkup:
    """Language selection keyboard."""
    buttons = [
        [KeyboardButton(text="🇪🇹 አማርኛ (Amharic)"), KeyboardButton(text="🇬🇧 English")],
        [KeyboardButton(text="🔙 Back / ተመለስ")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
