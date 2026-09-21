from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.i18n import t
from bot.database.models import Category, Product


def categories_keyboard(categories: List[Category], lang: str = "am") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=f"{cat.icon} {cat.name}", callback_data=f"cat_{cat.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(products: List[Product], cat_id: int, lang: str = "am") -> InlineKeyboardMarkup:
    buttons = []
    for p in products:
        price_display = f"{p.sale_price or p.price} ETB"
        buttons.append([InlineKeyboardButton(text=f"📦 {p.name} — {price_display}", callback_data=f"prod_{p.id}")])
    buttons.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data="catalog_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_keyboard(product_id: int, stock_count: int, lang: str = "am") -> InlineKeyboardMarkup:
    buttons = []
    if stock_count > 0:
        buttons.append([
            InlineKeyboardButton(text=t("btn_buy_now", lang), callback_data=f"buy_now_{product_id}"),
            InlineKeyboardButton(text=t("btn_add_cart", lang), callback_data=f"cart_add_{product_id}")
        ])
    else:
        # Out of stock: Show Restock Alert button
        btn_notify_text = "🔔 ዕቃው ሲገባ አሳውቀኝ (Notify Me)" if lang == "am" else "🔔 Notify Me When In Stock"
        buttons.append([
            InlineKeyboardButton(text=btn_notify_text, callback_data=f"notify_restock_{product_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="⭐ Reviews", callback_data=f"reviews_{product_id}"),
        InlineKeyboardButton(text=t("btn_back", lang), callback_data="catalog_home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_action_keyboard(order_id: int, lang: str = "am") -> InlineKeyboardMarkup:
    btn_report = "⚠️ ቅሬታ አቅርብ (Report)" if lang == "am" else "⚠️ Report"
    btn_review = "⭐ ደረጃ ስጥ (Rate)" if lang == "am" else "⭐ Rate & Review"
    buttons = [
        [
            InlineKeyboardButton(text=btn_review, callback_data=f"rate_order_{order_id}"),
            InlineKeyboardButton(text=btn_report, callback_data=f"report_issue_{order_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rating_stars_keyboard(order_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="⭐ 1", callback_data=f"star_{order_id}_1"),
            InlineKeyboardButton(text="⭐ 2", callback_data=f"star_{order_id}_2"),
            InlineKeyboardButton(text="⭐ 3", callback_data=f"star_{order_id}_3"),
            InlineKeyboardButton(text="⭐ 4", callback_data=f"star_{order_id}_4"),
            InlineKeyboardButton(text="⭐ 5", callback_data=f"star_{order_id}_5"),
        ],
        [InlineKeyboardButton(text="✖️ ዝጋ / Close", callback_data="close_view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_ticket_keyboard(ticket_code: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🔄 Replace Key (ቀይር)", callback_data=f"adm_replace_{ticket_code}"),
            InlineKeyboardButton(text="💰 Refund (መልስ)", callback_data=f"adm_refund_{ticket_code}")
        ],
        [
            InlineKeyboardButton(text="❌ Reject (ውድቅ)", callback_data=f"adm_reject_{ticket_code}"),
            InlineKeyboardButton(text="🙈 ችላ በል (Ignore)", callback_data=f"adm_ignore_{ticket_code}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_keyboard(cart_items: List[Dict[str, Any]], lang: str = "am") -> InlineKeyboardMarkup:
    buttons = []
    for item in cart_items:
        cid = item["cart_id"]
        qty = item["quantity"]
        name = item["name"][:15]
        buttons.append([
            InlineKeyboardButton(text=f"➖", callback_data=f"cart_dec_{cid}"),
            InlineKeyboardButton(text=f"{name} (x{qty})", callback_data=f"cart_info_{cid}"),
            InlineKeyboardButton(text=f"➕", callback_data=f"cart_inc_{cid}"),
            InlineKeyboardButton(text=f"❌", callback_data=f"cart_del_{cid}")
        ])

    if cart_items:
        buttons.append([InlineKeyboardButton(text=t("btn_checkout", lang), callback_data="cart_checkout")])
        buttons.append([InlineKeyboardButton(text=t("btn_clear_cart", lang), callback_data="cart_clear")])

    buttons.append([InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_view")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_methods_keyboard(lang: str = "en", show_local: bool = True) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="💎 CryptoBot (USDT, TON, BTC)", callback_data="dep_crypto")
        ],
        [
            InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="dep_stars")
        ]
    ]
    if show_local:
        buttons.append([
            InlineKeyboardButton(text=t("pay_telebirr", lang), callback_data="dep_telebirr"),
            InlineKeyboardButton(text=t("pay_cbe", lang), callback_data="dep_cbe")
        ])
    buttons.append([InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_view")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def crypto_invoice_keyboard(pay_url: str, invoice_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💳 Pay with @CryptoBot", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Check Payment", callback_data=f"check_crypto_{invoice_id}")],
        [InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📦 Add Product", callback_data="adm_add_prod"),
         InlineKeyboardButton(text="🏷️ Add Category", callback_data="adm_add_cat")],
        [InlineKeyboardButton(text="➕ Add Stock Keys", callback_data="adm_add_stock"),
         InlineKeyboardButton(text="🎟️ Create Promo", callback_data="adm_add_promo")],
        [InlineKeyboardButton(text="⚙️ Customization & Settings", callback_data="adm_settings"),
         InlineKeyboardButton(text="📢 Broadcast Message", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Real-Time Analytics", callback_data="adm_stats")],
        [InlineKeyboardButton(text="✖️ Close Admin", callback_data="close_view")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_settings_keyboard(maintenance_on: bool = False) -> InlineKeyboardMarkup:
    m_icon = "🔴 Enabled (Turn OFF)" if maintenance_on else "⚪ Disabled (Turn ON)"
    buttons = [
        [
            InlineKeyboardButton(text="📝 Edit Welcome Text", callback_data="adm_set_welcome"),
            InlineKeyboardButton(text="📜 Edit Rules/About", callback_data="adm_set_rules")
        ],
        [
            InlineKeyboardButton(text="📱 Edit Telebirr Number", callback_data="adm_set_telebirr"),
            InlineKeyboardButton(text="🏦 Edit CBE Account", callback_data="adm_set_cbe")
        ],
        [
            InlineKeyboardButton(text="📢 Set Force Join Channel", callback_data="adm_set_fjoin"),
            InlineKeyboardButton(text="🌟 Set Review Channel", callback_data="adm_set_revchan")
        ],
        [
            InlineKeyboardButton(text=f"🛠️ Maintenance Mode: {m_icon}", callback_data="adm_toggle_maint")
        ],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="adm_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

