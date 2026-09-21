from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.i18n import t
from bot.database.models import Category, Product
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL


def categories_keyboard(categories: List[Category], lang: str = "en") -> InlineKeyboardMarkup:
    """Category selection buttons with Telegram styles (primary/success/danger/default)."""
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=f"[ {cat.name} ]", callback_data=f"cat_{cat.id}", style="primary"))  # Blue
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="[ View All Products ]", callback_data="cat_all", style="success")])  # Green
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(products: List[Product], cat_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Product list buttons."""
    buttons = []
    for p in products:
        price_val = p.sale_price or p.price
        price_display = f"{CURRENCY_SYMBOL}{price_val:.2f}"
        buttons.append([InlineKeyboardButton(text=f"{p.name} — {price_display}", callback_data=f"prod_{p.id}")])  # Default (ያለቀለም)
    buttons.append([InlineKeyboardButton(text="< Back to Categories", callback_data="catalog_home", style="danger")])  # Red
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_keyboard(product_id: int, stock_count: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Product detail view with colored action buttons."""
    buttons = []
    if stock_count > 0:
        buttons.append([
            InlineKeyboardButton(text="[ Instant Buy ]", callback_data=f"buy_now_{product_id}", style="success"),  # Green (አረንጓዴ)
            InlineKeyboardButton(text="[ + Add to Cart ]", callback_data=f"cart_add_{product_id}", style="primary")  # Blue (ሰማያዊ)
        ])
    else:
        btn_notify_text = "Notify When Available" if lang == "en" else "ስቶክ ሲገባ አሳውቀኝ"
        buttons.append([
            InlineKeyboardButton(text=f"[ {btn_notify_text} ]", callback_data=f"notify_restock_{product_id}", style="primary")  # Blue
        ])

    buttons.append([
        InlineKeyboardButton(text="Reviews & Ratings", callback_data=f"reviews_{product_id}"),  # Default (ያለቀለም)
        InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="danger")  # Red (ቀይ)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_action_keyboard(order_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    btn_report = "Report Issue" if lang == "en" else "ቅሬታ አቅርብ"
    btn_review = "Rate & Review" if lang == "en" else "ደረጃ ስጥ"
    buttons = [
        [
            InlineKeyboardButton(text=f"[ {btn_review} ]", callback_data=f"rate_order_{order_id}", style="success"),  # Green (አረንጓዴ)
            InlineKeyboardButton(text=f"[ {btn_report} ]", callback_data=f"report_issue_{order_id}", style="danger")   # Red (ቀይ)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rating_stars_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Emoji-free rating score selection with gradient 4-color styling."""
    buttons = [
        [
            InlineKeyboardButton(text="1/5", callback_data=f"star_{order_id}_1", style="danger"),   # Red (ቀይ)
            InlineKeyboardButton(text="2/5", callback_data=f"star_{order_id}_2", style="danger"),   # Red (ቀይ)
            InlineKeyboardButton(text="3/5", callback_data=f"star_{order_id}_3"),                   # Default (ያለቀለም)
            InlineKeyboardButton(text="4/5", callback_data=f"star_{order_id}_4", style="primary"),  # Blue (ሰማያዊ)
            InlineKeyboardButton(text="5/5", callback_data=f"star_{order_id}_5", style="success"),  # Green (አረንጓዴ)
        ],
        [InlineKeyboardButton(text="< Cancel", callback_data="close_view", style="danger")]         # Red (ቀይ)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_ticket_keyboard(ticket_code: str) -> InlineKeyboardMarkup:
    """Admin support ticket actions with clear semantic colors."""
    buttons = [
        [
            InlineKeyboardButton(text="Replace Key", callback_data=f"adm_replace_{ticket_code}", style="success"),  # Green (አረንጓዴ)
            InlineKeyboardButton(text="Refund Balance", callback_data=f"adm_refund_{ticket_code}", style="primary") # Blue (ሰማያዊ)
        ],
        [
            InlineKeyboardButton(text="Reject Issue", callback_data=f"adm_reject_{ticket_code}", style="danger"),  # Red (ቀይ)
            InlineKeyboardButton(text="Dismiss", callback_data=f"adm_ignore_{ticket_code}")                         # Default (ያለቀለም)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_keyboard(cart_items: List[Dict[str, Any]], lang: str = "en") -> InlineKeyboardMarkup:
    """In-place updatable cart controls with button colors."""
    buttons = []
    for item in cart_items:
        cid = item["cart_id"]
        qty = item["quantity"]
        name = item["name"][:16]
        buttons.append([
            InlineKeyboardButton(text="[ - ]", callback_data=f"cart_dec_{cid}", style="danger"),   # Red (ቀይ)
            InlineKeyboardButton(text=f"{name} x{qty}", callback_data=f"cart_info_{cid}"),         # Default (ያለቀለም)
            InlineKeyboardButton(text="[ + ]", callback_data=f"cart_inc_{cid}", style="success"),  # Green (አረንጓዴ)
            InlineKeyboardButton(text="[ x ]", callback_data=f"cart_del_{cid}", style="danger")    # Red (ቀይ)
        ])

    if cart_items:
        buttons.append([InlineKeyboardButton(text="[ Proceed to Checkout ]", callback_data="cart_checkout", style="success")])  # Green
        buttons.append([InlineKeyboardButton(text="[ Clear Cart ]", callback_data="cart_clear", style="danger")])                 # Red

    buttons.append([InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="primary")])              # Blue
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_methods_keyboard(lang: str = "en", show_local: bool = True) -> InlineKeyboardMarkup:
    """Sleek international deposit gateway menu with 4 Telegram colors."""
    buttons = [
        [
            InlineKeyboardButton(text="OxaPay (0.4% Fee / Instant)", callback_data="dep_oxapay", style="success"),  # Green (አረንጓዴ)
            InlineKeyboardButton(text="Cryptomus (USDT & Crypto)", callback_data="dep_cryptomus", style="primary")  # Blue (ሰማያዊ)
        ],
        [
            InlineKeyboardButton(text="NOWPayments (300+ Coins)", callback_data="dep_nowpayments", style="primary"), # Blue (ሰማያዊ)
            InlineKeyboardButton(text="CryptoBot (Telegram In-App)", callback_data="dep_crypto", style="primary")   # Blue (ሰማያዊ)
        ],
        [
            InlineKeyboardButton(text="Telegram Stars", callback_data="dep_stars", style="primary")                  # Blue (ሰማያዊ)
        ]
    ]
    if show_local:
        buttons.append([
            InlineKeyboardButton(text="Telebirr (Ethiopia)", callback_data="dep_telebirr", style="success"),        # Green (አረንጓዴ)
            InlineKeyboardButton(text="CBE Bank (Ethiopia)", callback_data="dep_cbe", style="primary")             # Blue (ሰማያዊ)
        ])
    buttons.append([InlineKeyboardButton(text="< Close", callback_data="close_view", style="danger")])             # Red (ቀይ)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def crypto_invoice_keyboard(pay_url: str, invoice_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Pay via @CryptoBot ]", url=pay_url, style="success")],                        # Green
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_crypto_{invoice_id}", style="primary")],  # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                    # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def oxapay_invoice_keyboard(pay_url: str, track_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open OxaPay Checkout ]", url=pay_url, style="success")],                     # Green
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_oxapay_{track_id}", style="primary")],   # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cryptomus_invoice_keyboard(pay_url: str, uuid: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open Cryptomus Checkout ]", url=pay_url, style="success")],                   # Green
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_cryptomus_{uuid}", style="primary")],  # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def nowpayments_invoice_keyboard(pay_url: str, payment_id: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ Open NOWPayments Checkout ]", url=pay_url, style="success")],                 # Green
        [InlineKeyboardButton(text="[ Refresh Payment Status ]", callback_data=f"check_nowpayments_{payment_id}", style="primary")], # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="[ + Product ]", callback_data="adm_add_prod", style="primary"),
         InlineKeyboardButton(text="[ + Category ]", callback_data="adm_add_cat", style="primary")],
        [InlineKeyboardButton(text="[ + Stock Keys ]", callback_data="adm_add_stock", style="primary"),
         InlineKeyboardButton(text="[ + Promo Code ]", callback_data="adm_add_promo", style="primary")],
        [InlineKeyboardButton(text="[ Store Settings ]", callback_data="adm_settings"),                             # Default
         InlineKeyboardButton(text="[ Broadcast ]", callback_data="adm_broadcast", style="danger")],                # Red
        [InlineKeyboardButton(text="[ Sales Analytics ]", callback_data="adm_stats", style="success")],            # Green
        [InlineKeyboardButton(text="< Close Admin", callback_data="close_view", style="danger")]                    # Red
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
            InlineKeyboardButton(text=f"Maintenance Mode: {m_status}", callback_data="adm_toggle_maint", style="danger")  # Red
        ],
        [InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="primary")]                         # Blue
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
