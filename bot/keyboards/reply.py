from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.services.i18n import t


def get_main_menu(lang: str = "en", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Generate styled main reply keyboard using Telegram 4 button colors (Blue, Green, Red, Default)."""
    buttons = [
        [
            KeyboardButton(text=t("menu_catalog", lang), style="primary"),    # Blue (ሰማያዊ)
            KeyboardButton(text=t("menu_cart", lang), style="success")        # Green (አረንጓዴ)
        ],
        [
            KeyboardButton(text=t("menu_wallet", lang), style="success"),     # Green (አረንጓዴ)
            KeyboardButton(text=t("menu_orders", lang))                       # Default (ያለቀለም)
        ],
        [
            KeyboardButton(text=t("menu_referral", lang), style="primary"),   # Blue (ሰማያዊ)
            KeyboardButton(text=t("menu_support", lang))                      # Default (ያለቀለም)
        ],
        [
            KeyboardButton(text=t("menu_language", lang))                     # Default (ያለቀለም)
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=t("menu_admin", lang), style="danger")])  # Red (ቀይ)

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_language_menu() -> ReplyKeyboardMarkup:
    """Styled language selection keyboard."""
    buttons = [
        [
            KeyboardButton(text="English", style="primary"),             # Blue (ሰማያዊ)
            KeyboardButton(text="Amharic (አማርኛ)", style="success")       # Green (አረንጓዴ)
        ],
        [
            KeyboardButton(text="< Back", style="danger")                # Red (ቀይ)
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
