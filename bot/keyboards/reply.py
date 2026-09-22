from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.services.i18n import t


def get_main_menu(lang: str = "en", is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Clean, English-only layout without language toggles.
    """
    buttons = [
        [
            KeyboardButton(text="Products Catalog"),
            KeyboardButton(text="Shopping Cart")
        ],
        [
            KeyboardButton(text="Balance & Deposit"),
            KeyboardButton(text="Order History")
        ],
        [
            KeyboardButton(text="Affiliate Program"),
            KeyboardButton(text="Customer Support")
        ]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="Admin Suite")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_language_menu() -> ReplyKeyboardMarkup:
    """Styled language selection keyboard (English default)."""
    buttons = [
        [
            KeyboardButton(text="English")
        ],
        [
            KeyboardButton(text="< Back")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
