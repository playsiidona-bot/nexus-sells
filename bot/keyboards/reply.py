from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.services.i18n import t


def get_main_menu(lang: str = "en", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Generate styled main reply keyboard using Telegram 4 button colors (Blue, Green, Red, Default).
    Clean, English-only layout without language toggles.
    """
    buttons = [
        [
            KeyboardButton(text="Products Catalog", style="primary"),    # Blue (primary)
            KeyboardButton(text="Shopping Cart", style="success")        # Green (success)
        ],
        [
            KeyboardButton(text="Balance & Deposit", style="success"),     # Green (success)
            KeyboardButton(text="Order History")                         # Default
        ],
        [
            KeyboardButton(text="Affiliate Program", style="primary"),   # Blue (primary)
            KeyboardButton(text="Customer Support")                      # Default
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="Admin Suite", style="danger")])  # Red (danger)

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_language_menu() -> ReplyKeyboardMarkup:
    """Styled language selection keyboard (English default)."""
    buttons = [
        [
            KeyboardButton(text="English", style="primary")
        ],
        [
            KeyboardButton(text="< Back", style="danger")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
