from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.i18n import t
from bot.database.models import Category, Product
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL


def categories_keyboard(categories: List[Category], lang: str = "en") -> InlineKeyboardMarkup:
    """Clean, emoji-free category selection buttons."""
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=f"[ {cat.name} ]", callback_data=f"cat_{cat.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="[ View All Products ]", callback_data="cat_all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(products: List[Product], cat_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Clean product list buttons."""
    buttons = []
    for p in products:
        price_val = p.sale_price or p.price
        price_display = f"{CURRENCY_SYMBOL}{price_val:.2f}"
        buttons.append([InlineKeyboardButton(text=f"{p.name} — {price_display}", callback_data=f"prod_{p.id}")])
    buttons.append([InlineKeyboardButton(text="< Back to Categories", callback_data="catalog_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_keyboard(product_id: int, stock_count: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Clean product detail view keyboard."""
    buttons = []
    if stock_count > 0:
        buttons.append([
            InlineKeyboardButton(text="[ Instant Buy ]", callback_data=f"buy_now_{product_id}"),
            InlineKeyboardButton(text="[ + Add to Cart ]", callback_data=f"cart_add_{product_id}")
        ])
    else:
        btn_notify_text = "Notify When Available" if lang == "en" else "ስቶክ ሲገባ አሳውቀኝ"
        buttons.append([
            InlineKeyboardButton(text=f"[ {btn_notify_text} ]", callback_data=f"notify_restock_{product_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="Reviews & Ratings", callback_data=f"reviews_{product_id}"),
        InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_action_keyboard(order_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    btn_report = "Report Issue" if lang == "en" else "ቅሬታ አቅርብ"
    btn_review = "Rate & Review" if lang == "en" else "ደረጃ ስጥ"
    buttons = [
        [
            InlineKeyboardButton(text=f"[ {btn_review} ]", callback_data=f"rate_order_{order_id}"),
            InlineKeyboardButton(text=f"[ {btn_report} ]", callback_data=f"report_issue_{order_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rating_stars_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Emoji-free rating score selection."""
    buttons = [
        [
            InlineKeyboardButton(text="1/5", callback_data=f"star_{order_id}_1"),
            InlineKeyboardButton(text="2/5", callback_data=f"star_{order_id}_2"),
            InlineKeyboardButton(text="3/5", callback_data=f"star_{order_id}_3"),
            InlineKeyboardButton(text="4/5", callback_data=f"star_{order_id}_4"),
            InlineKeyboardButton(text="5/5", callback_data=f"star_{order_id}_5"),
        ],
        [InlineKeyboardButton(text="< Cancel", callback_data="close_view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_ticket_keyboard(ticket_code: str) -> InlineKeyboardMarkup:
    """Admin support ticket actions."""
    buttons = [
        [
            InlineKeyboardButton(text="Replace Key", callback_data=f"adm_replace_{ticket_code}"),
            InlineKeyboardButton(text="Refund Balance", callback_data=f"adm_refund_{ticket_code}")
        ],
        [
            InlineKeyboardButton(text="Reject Issue", callback_data=f"adm_reject_{ticket_code}"),
            InlineKeyboardButton(text="Dismiss", callback_data=f"adm_ignore_{ticket_code}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_keyboard(cart_items: List[Dict[str, Any]], lang: str = "en") -> InlineKeyboardMarkup:
    """In-place updatable cart controls."""
    buttons = []
    for item in cart_items:
        cid = item["cart_id"]
        qty = item["quantity"]
        name = item["name"][:16]
        buttons.append([
            InlineKeyboardButton(text="[ - ]", callback_data=f"cart_dec_{cid}"),
            InlineKeyboardButton(text=f"{name} x{qty}", callback_data=f"cart_info_{cid}"),
            InlineKeyboardButton(text="[ + ]", callback_data=f"cart_inc_{cid}"),
            InlineKeyboardButton(text="[ x ]", callback_data=f"cart_del_{cid}")
        ])

    if cart_items:
        buttons.append([InlineKeyboardButton(text="[ Proceed to Checkout ]", callback_data="cart_checkout")])
        buttons.append([InlineKeyboardButton(text="[ Clear Cart ]", callback_data="cart_clear")])

    buttons.append([InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_methods_keyboard(lang: str = "en", show_local: bool = True) -> InlineKeyboardMarkup:
    """Sleek international deposit gateway menu."""
    buttons = [
        [
            InlineKeyboardButton(text="OxaPay (0.4% Fee / Instant)", callback_data="dep_oxapay"),
            InlineKeyboardButton(text="Cryptomus (USDT & Crypto)", callback_data="dep_cryptomus")
        ],
        [
            InlineKeyboardButton(text="NOWPayments (300+ Coins)", callback_data="dep_nowpayments"),
            InlineKeyboardButton(text="CryptoBot (Telegram In-App)", callback_data="dep_crypto")
        ],
        [
            InlineKeyboardButton(text="Telegram Stars", callback_data="dep_stars")
        ]
    ]
    if show_local:
        buttons.append([
            InlineKeyboardButton(text="Telebirr (Ethiopia)", callback_data="dep_telebirr"),
            InlineKeyboardButton(text="CBE Bank (Ethiopia)", callback_data="dep_cbe")
        ])
    buttons.append([InlineKeyboardButton(text="< Close", callback_data="close_view")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def crypto_invoice_keyboard(pay_url: str, invoice_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Pay via @CryptoBot ]", url=pay_url)],
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_crypto_{invoice_id}")],
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def oxapay_invoice_keyboard(pay_url: str, track_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open OxaPay Checkout ]", url=pay_url)],
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_oxapay_{track_id}")],
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cryptomus_invoice_keyboard(pay_url: str, uuid: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open Cryptomus Checkout ]", url=pay_url)],
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_cryptomus_{uuid}")],
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def nowpayments_invoice_keyboard(pay_url: str, payment_id: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open NOWPayments Checkout ]", url=pay_url)],
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_nowpayments_{payment_id}")],
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ + Product ]", callback_data="adm_add_prod"),
         InlineKeyboardButton(text="[ + Category ]", callback_data="adm_add_cat")],
        [InlineKeyboardButton(text="[ + Stock Keys ]", callback_data="adm_add_stock"),
         InlineKeyboardButton(text="[ + Promo Code ]", callback_data="adm_add_promo")],
        [InlineKeyboardButton(text="[ Store Settings ]", callback_data="adm_settings"),
         InlineKeyboardButton(text="[ Broadcast ]", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="[ Sales Analytics ]", callback_data="adm_stats")],
        [InlineKeyboardButton(text="< Close Admin", callback_data="close_view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_settings_keyboard(maintenance_on: bool = False) -> InlineKeyboardMarkup:
    m_status = "ENABLED (Click to Disable)" if maintenance_on else "DISABLED (Click to Enable)"
    buttons = [
        [
            InlineKeyboardButton(text="Edit Welcome Card", callback_data="adm_set_welcome"),
            InlineKeyboardButton(text="Edit Store Rules", callback_data="adm_set_rules")
        ],
        [
            InlineKeyboardButton(text="Edit Telebirr Info", callback_data="adm_set_telebirr"),
            InlineKeyboardButton(text="Edit CBE Account", callback_data="adm_set_cbe")
        ],
        [
            InlineKeyboardButton(text="Set Force Join Channel", callback_data="adm_set_fjoin"),
            InlineKeyboardButton(text="Set Review Channel", callback_data="adm_set_revchan")
        ],
        [
            InlineKeyboardButton(text=f"Maintenance Mode: {m_status}", callback_data="adm_toggle_maint")
        ],
        [InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
