from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.i18n import t
from bot.database.models import Category, Product, User
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL


def categories_keyboard(categories: List[Category], lang: str = "en") -> InlineKeyboardMarkup:
    """Category selection buttons with blended colors and refresh button."""
    buttons = []
    row = []
    for i, cat in enumerate(categories):
        style = "primary" if i % 2 == 0 else "default"
        row.append(InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.id}", style=style))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    all_text = "View All Products" if lang == "en" else "ሁሉንም ዕቃዎች እይ"
    ref_text = "Refresh Catalog" if lang == "en" else "ካታሎግ አድስ"
    buttons.append([
        InlineKeyboardButton(text=all_text, callback_data="cat_all", style="success"),
        InlineKeyboardButton(text=ref_text, callback_data="refresh_catalog", style="primary")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(products: List[Product], cat_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Product list buttons with balanced color styling."""
    buttons = []
    for i, p in enumerate(products):
        price_val = p.sale_price or p.price
        price_display = f"{CURRENCY_SYMBOL}{price_val:.2f}"
        style = "primary" if i % 2 == 0 else "default"
        buttons.append([InlineKeyboardButton(text=f"{p.name} — {price_display}", callback_data=f"prod_{p.id}", style=style)])

    back_text = "< Back to Categories" if lang == "en" else "< ወደ ምድቦች ተመለስ"
    ref_text = "Refresh" if lang == "en" else "አድስ"
    buttons.append([
        InlineKeyboardButton(text=ref_text, callback_data=f"refresh_cat_{cat_id}", style="primary"),
        InlineKeyboardButton(text=back_text, callback_data="catalog_home", style="danger")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_keyboard(product_id: int, stock_count: int, lang: str = "en") -> InlineKeyboardMarkup:
    """Product detail view with colored action buttons."""
    buttons = []
    if stock_count > 0:
        buttons.append([
            InlineKeyboardButton(text="Instant Buy", callback_data=f"buy_now_{product_id}", style="success"),  # Green
            InlineKeyboardButton(text="+ Add to Cart", callback_data=f"cart_add_{product_id}", style="primary")  # Blue
        ])
    else:
        btn_notify_text = "Notify When Available" if lang == "en" else "ስቶክ ሲገባ አሳውቀኝ"
        buttons.append([
            InlineKeyboardButton(text=btn_notify_text, callback_data=f"notify_restock_{product_id}", style="primary")  # Blue
        ])

    buttons.append([
        InlineKeyboardButton(text="Reviews & Ratings", callback_data=f"reviews_{product_id}", style="primary"),
        InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="danger")  # Red
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_action_keyboard(order_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    btn_report = "Report Issue" if lang == "en" else "ቅሬታ አቅርብ"
    btn_review = "Rate & Review" if lang == "en" else "ደረጃ ስጥ"
    btn_refresh = "Refresh Orders" if lang == "en" else "ትዕዛዞችን አድስ"
    buttons = [
        [
            InlineKeyboardButton(text=btn_review, callback_data=f"rate_order_{order_id}", style="success"),  # Green
            InlineKeyboardButton(text=btn_report, callback_data=f"report_issue_{order_id}", style="danger")   # Red
        ],
        [InlineKeyboardButton(text=btn_refresh, callback_data="refresh_orders", style="primary")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rating_stars_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Rating score selection buttons."""
    buttons = [
        [
            InlineKeyboardButton(text="1/5", callback_data=f"star_{order_id}_1", style="danger"),   # Red
            InlineKeyboardButton(text="2/5", callback_data=f"star_{order_id}_2", style="danger"),   # Red
            InlineKeyboardButton(text="3/5", callback_data=f"star_{order_id}_3"),                   # Default
            InlineKeyboardButton(text="4/5", callback_data=f"star_{order_id}_4", style="primary"),  # Blue
            InlineKeyboardButton(text="5/5", callback_data=f"star_{order_id}_5", style="success"),  # Green
        ],
        [InlineKeyboardButton(text="< Cancel", callback_data="close_view", style="danger")]         # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_ticket_keyboard(ticket_code: str) -> InlineKeyboardMarkup:
    """Admin support ticket actions."""
    buttons = [
        [
            InlineKeyboardButton(text="Replace Key", callback_data=f"adm_replace_{ticket_code}", style="success"),  # Green
            InlineKeyboardButton(text="Refund Balance", callback_data=f"adm_refund_{ticket_code}", style="primary") # Blue
        ],
        [
            InlineKeyboardButton(text="Reject Issue", callback_data=f"adm_reject_{ticket_code}", style="danger"),  # Red
            InlineKeyboardButton(text="Dismiss", callback_data=f"adm_ignore_{ticket_code}")                         # Default
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_keyboard(cart_items: List[Dict[str, Any]], lang: str = "en") -> InlineKeyboardMarkup:
    """In-place updatable cart controls with refresh and balanced colors."""
    buttons = []
    for item in cart_items:
        cid = item["cart_id"]
        qty = item["quantity"]
        name = item["name"][:16]
        buttons.append([
            InlineKeyboardButton(text="-", callback_data=f"cart_dec_{cid}", style="danger"),       # Red
            InlineKeyboardButton(text=f"{name} x{qty}", callback_data=f"cart_info_{cid}"),         # Default
            InlineKeyboardButton(text="+", callback_data=f"cart_inc_{cid}", style="success"),      # Green
            InlineKeyboardButton(text="Delete", callback_data=f"cart_del_{cid}", style="danger")   # Red
        ])

    if cart_items:
        buttons.append([InlineKeyboardButton(text="Proceed to Checkout", callback_data="cart_checkout", style="success")])  # Green
        buttons.append([
            InlineKeyboardButton(text="Refresh Cart", callback_data="refresh_cart", style="primary"),                         # Blue
            InlineKeyboardButton(text="Clear Cart", callback_data="cart_clear", style="danger")                                # Red
        ])
    else:
        buttons.append([InlineKeyboardButton(text="Refresh Cart", callback_data="refresh_cart", style="primary")])

    buttons.append([InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="primary")])          # Blue
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def deposit_methods_keyboard(lang: str = "en", show_local: bool = True) -> InlineKeyboardMarkup:
    """USDT-only payment gateway menu (Polygon & BEP-20) without external branding."""
    poly_text = "Deposit USDT (Polygon Network)" if lang == "en" else "USDT አስገባ (Polygon / PoS)"
    bep_text = "Deposit USDT (BEP-20 / BSC)" if lang == "en" else "USDT አስገባ (BEP-20 / BSC)"
    ref_text = "Refresh Balance" if lang == "en" else "ሒሳብ አድስ"
    close_text = "< Close" if lang == "en" else "< ዝጋ"

    buttons = [
        [
            InlineKeyboardButton(text=poly_text, callback_data="dep_usdt_polygon", style="primary"),  # Blue
            InlineKeyboardButton(text=bep_text, callback_data="dep_usdt_bep20", style="success")     # Green
        ]
    ]
    if show_local:
        buttons.append([
            InlineKeyboardButton(text="Telebirr (Ethiopia)", callback_data="dep_telebirr", style="success"),        # Green
            InlineKeyboardButton(text="CBE Bank (Ethiopia)", callback_data="dep_cbe", style="primary")             # Blue
        ])
    buttons.append([
        InlineKeyboardButton(text=ref_text, callback_data="refresh_wallet", style="primary"),                       # Blue
        InlineKeyboardButton(text=close_text, callback_data="close_view", style="danger")                           # Red
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def usdt_deposit_keyboard(network: str, lang: str = "en") -> InlineKeyboardMarkup:
    """Direct USDT address payment screen with TXID submission and no-hash manual verification."""
    submit_text = "Submit Transaction Hash (TXID)" if lang == "en" else "የትራንዛክሽን Hash ላክ (TXID)"
    nohash_text = "I Paid (Verify Without Hash)" if lang == "en" else "ከፍያለሁ (ያለ Hash አረጋግጥ)"
    ref_text = "Refresh Balance" if lang == "en" else "ሒሳብ አድስ"
    back_text = "< Back to Deposit Methods" if lang == "en" else "< ወደ ክፍያ አማራጮች"

    buttons = [
        [InlineKeyboardButton(text=submit_text, callback_data=f"usdt_submit_{network}", style="success")],  # Green
        [InlineKeyboardButton(text=nohash_text, callback_data=f"usdt_nohash_{network}", style="primary")],  # Blue
        [
            InlineKeyboardButton(text=ref_text, callback_data="refresh_wallet", style="primary"),          # Blue
            InlineKeyboardButton(text=back_text, callback_data="back_to_deposit", style="danger")          # Red
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def insufficient_balance_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Updatable retry and top-up controls when order is rejected due to balance."""
    topup_text = "Deposit / Add Balance" if lang == "en" else "ሒሳብ ሙላ (Deposit)"
    retry_text = "Check Balance & Retry" if lang == "en" else "ሒሳብ አረጋግጥና እንደገና ይሞክሩ"
    back_text = "< Back to Cart" if lang == "en" else "< ወደ ዘንቢል ተመለስ"

    buttons = [
        [InlineKeyboardButton(text=topup_text, callback_data="dep_from_cart", style="success")],
        [
            InlineKeyboardButton(text=retry_text, callback_data="cart_retry_checkout", style="primary"),
            InlineKeyboardButton(text=back_text, callback_data="refresh_cart", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def crypto_invoice_keyboard(pay_url: str, invoice_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Pay via @CryptoBot", url=pay_url, style="success")],                        # Green
        [InlineKeyboardButton(text="Refresh Payment Status", callback_data=f"check_crypto_{invoice_id}", style="primary")],  # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                    # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def oxapay_invoice_keyboard(pay_url: str, track_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Open OxaPay Checkout", url=pay_url, style="success")],                     # Green
        [InlineKeyboardButton(text="Refresh Payment Status", callback_data=f"check_oxapay_{track_id}", style="primary")],   # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cryptomus_invoice_keyboard(pay_url: str, uuid: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Open Cryptomus Checkout", url=pay_url, style="success")],                   # Green
        [InlineKeyboardButton(text="Refresh Payment Status", callback_data=f"check_cryptomus_{uuid}", style="primary")],  # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def nowpayments_invoice_keyboard(pay_url: str, payment_id: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Open NOWPayments Checkout", url=pay_url, style="success")],                 # Green
        [InlineKeyboardButton(text="Refresh Payment Status", callback_data=f"check_nowpayments_{payment_id}", style="primary")], # Blue
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]                   # Red
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Admin dashboard with balanced primary, success, and danger buttons."""
    buttons = [
        [
            InlineKeyboardButton(text="+ Product", callback_data="adm_add_prod", style="primary"),
            InlineKeyboardButton(text="+ Category", callback_data="adm_add_cat", style="primary")
        ],
        [
            InlineKeyboardButton(text="Manage Products", callback_data="adm_prods_mgr", style="success"),
            InlineKeyboardButton(text="Manage Categories", callback_data="adm_cats_mgr", style="success")
        ],
        [
            InlineKeyboardButton(text="Manage Users", callback_data="adm_users_mgr", style="primary"),
            InlineKeyboardButton(text="+ Stock Keys", callback_data="adm_add_stock", style="primary")
        ],
        [
            InlineKeyboardButton(text="Review API Products", callback_data="adm_api_menu", style="primary"),
            InlineKeyboardButton(text="Store Settings", callback_data="adm_settings")
        ],
        [
            InlineKeyboardButton(text="Broadcast", callback_data="adm_broadcast", style="danger"),
            InlineKeyboardButton(text="Sales Analytics", callback_data="adm_stats", style="success")
        ],
        [InlineKeyboardButton(text="< Close Admin", callback_data="close_view", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_manager_keyboard(categories: List[Category]) -> InlineKeyboardMarkup:
    """Category list for edit, hide/show, and delete operations."""
    buttons = []
    for cat in categories:
        is_act = getattr(cat, "is_active", True)
        status_tag = "Active" if is_act else "Hidden"
        status_style = "primary" if is_act else "default"
        btn_text = f"{cat.name} ({status_tag})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_catdetail_{cat.id}", style=status_style)])

    buttons.append([
        InlineKeyboardButton(text="+ Add Category", callback_data="adm_add_cat", style="success"),
        InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="danger")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_detail_keyboard(category: Category) -> InlineKeyboardMarkup:
    """Category actions: edit name, toggle visibility, and delete."""
    is_act = getattr(category, "is_active", True)
    toggle_text = "Hide Category" if is_act else "Show Category"
    toggle_style = "danger" if is_act else "success"
    buttons = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"adm_cattoggle_{category.id}", style=toggle_style),
            InlineKeyboardButton(text="Edit Name", callback_data=f"adm_catedit_{category.id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="Delete Category", callback_data=f"adm_catdel_{category.id}", style="danger"),
            InlineKeyboardButton(text="< Back to Categories", callback_data="adm_cats_mgr", style="primary")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_manager_keyboard(products: List[Product]) -> InlineKeyboardMarkup:
    """Product list for editing, stock adding, hiding, and deleting."""
    buttons = []
    for p in products[:25]:
        status_tag = "Active" if p.is_active else "Hidden"
        status_style = "primary" if p.is_active else "default"
        price_display = f"{CURRENCY_SYMBOL}{p.price:.2f}"
        btn_text = f"{p.name[:18]} — {price_display} ({status_tag})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_proddetail_{p.id}", style=status_style)])

    buttons.append([
        InlineKeyboardButton(text="+ Add Product", callback_data="adm_add_prod", style="success"),
        InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="danger")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_detail_keyboard(product: Product) -> InlineKeyboardMarkup:
    """Product actions: edit title, price, description, toggle visibility, add stock, delete."""
    toggle_text = "Hide Product" if product.is_active else "Publish / Show Product"
    toggle_style = "danger" if product.is_active else "success"
    buttons = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"adm_prodtoggle_{product.id}", style=toggle_style),
            InlineKeyboardButton(text="+ Add Stock", callback_data=f"adm_prod_stock_{product.id}", style="success")
        ],
        [
            InlineKeyboardButton(text="Edit Title", callback_data=f"adm_prodedittitle_{product.id}", style="primary"),
            InlineKeyboardButton(text="Edit Price", callback_data=f"adm_prodeditprice_{product.id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="Edit Description", callback_data=f"adm_prodeditdesc_{product.id}", style="primary"),
            InlineKeyboardButton(text="Delete Product", callback_data=f"adm_proddel_{product.id}", style="danger")
        ],
        [InlineKeyboardButton(text="< Back to Products", callback_data="adm_prods_mgr", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_settings_keyboard(maintenance_on: bool = False) -> InlineKeyboardMarkup:
    m_status = "ENABLED (Click to Disable)" if maintenance_on else "DISABLED (Click to Enable)"
    buttons = [
        [
            InlineKeyboardButton(text="API Keys & Gateways", callback_data="adm_api_keys", style="primary"),
            InlineKeyboardButton(text="Configure USDT Wallets", callback_data="adm_usdt_wallets", style="success")
        ],
        [
            InlineKeyboardButton(text="Edit Welcome Card", callback_data="adm_set_welcome", style="primary"),
            InlineKeyboardButton(text="Edit Store Rules", callback_data="adm_set_rules", style="primary")
        ],
        [
            InlineKeyboardButton(text="Edit Telebirr Info", callback_data="adm_set_telebirr", style="success"),
            InlineKeyboardButton(text="Edit CBE Account", callback_data="adm_set_cbe", style="primary")
        ],
        [
            InlineKeyboardButton(text="Set Force Join Channel", callback_data="adm_set_fjoin"),
            InlineKeyboardButton(text="Set Review Channel", callback_data="adm_set_revchan")
        ],
        [
            InlineKeyboardButton(text=f"Maintenance Mode: {m_status}", callback_data="adm_toggle_maint", style="danger")
        ],
        [InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_usdt_wallets_keyboard() -> InlineKeyboardMarkup:
    """USDT address configuration keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="Set USDT (Polygon) Address", callback_data="adm_set_usdt_poly", style="primary"),
            InlineKeyboardButton(text="Set USDT (BEP-20) Address", callback_data="adm_set_usdt_bep20", style="success")
        ],
        [InlineKeyboardButton(text="< Back to Settings", callback_data="adm_settings", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_api_keys_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for managing external API keys and gateways."""
    buttons = [
        [
            InlineKeyboardButton(text="AIVerseHub Key", callback_data="adm_key_aiverse", style="primary"),
            InlineKeyboardButton(text="CryptoBot Token", callback_data="adm_key_cryptobot", style="primary"),
        ],
        [
            InlineKeyboardButton(text="OxaPay Key", callback_data="adm_key_oxapay", style="primary"),
            InlineKeyboardButton(text="NOWPayments Key", callback_data="adm_key_nowpayments", style="primary"),
        ],
        [
            InlineKeyboardButton(text="Cryptomus Key", callback_data="adm_key_cryptomus_key", style="primary"),
            InlineKeyboardButton(text="Cryptomus Merchant ID", callback_data="adm_key_cryptomus_mid", style="primary"),
        ],
        [
            InlineKeyboardButton(text="Test AIVerseHub Connection", callback_data="adm_test_aiverse", style="success"),
        ],
        [InlineKeyboardButton(text="< Back to Settings", callback_data="adm_settings", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_add_prod_category_keyboard(categories: List[Category]) -> InlineKeyboardMarkup:
    """Category picker for adding a new product."""
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=cat.name, callback_data=f"adm_addprod_cat_{cat.id}", style="primary"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="< Cancel", callback_data="adm_home", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_add_prod_skip_desc_keyboard() -> InlineKeyboardMarkup:
    """Option to skip description during product creation."""
    buttons = [
        [InlineKeyboardButton(text="Skip Description", callback_data="adm_addprod_skip_desc", style="primary")],
        [InlineKeyboardButton(text="< Cancel", callback_data="adm_home", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_add_prod_delivery_keyboard() -> InlineKeyboardMarkup:
    """Delivery type selection during product creation."""
    buttons = [
        [InlineKeyboardButton(text="Stock / License Keys", callback_data="adm_addprod_deliv_stock", style="primary")],
        [InlineKeyboardButton(text="Unlimited Link / Instructions", callback_data="adm_addprod_deliv_inf", style="primary")],
        [InlineKeyboardButton(text="< Cancel", callback_data="adm_home", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_add_prod_input_keyboard() -> InlineKeyboardMarkup:
    """Custom customer input requirement prompt during product creation."""
    buttons = [
        [InlineKeyboardButton(text="No, Standard Delivery", callback_data="adm_addprod_input_no", style="primary")],
        [InlineKeyboardButton(text="Yes, Requires Custom Input (@username, ID)", callback_data="adm_addprod_input_yes", style="success")],
        [InlineKeyboardButton(text="< Cancel", callback_data="adm_home", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_users_list_keyboard(users: List[User], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Paginated user management list."""
    buttons = []
    for u in users:
        ban_status = "Banned" if u.is_banned else "Active"
        ban_style = "danger" if u.is_banned else "primary"
        user_name = f"@{u.username}" if u.username else (u.first_name or f"User {u.telegram_id}")
        btn_text = f"{user_name[:14]} | {CURRENCY_SYMBOL}{u.balance:.2f} ({ban_status})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_usr_{u.telegram_id}_{page}", style=ban_style)])

    # Pagination navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="< Prev", callback_data=f"adm_usrpage_{page-1}", style="primary"))
    nav_row.append(InlineKeyboardButton(text=f"Page {page}/{max(1, total_pages)}", callback_data="adm_usr_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Next >", callback_data=f"adm_usrpage_{page+1}", style="primary"))
    buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="Find User by ID", callback_data="adm_usr_search", style="primary"),
        InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="danger")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_user_detail_keyboard(user: User, page: int = 1) -> InlineKeyboardMarkup:
    """User profile control panel: adjust balance, ban/unban, view orders."""
    ban_text = "Unban User" if user.is_banned else "Ban User"
    ban_style = "success" if user.is_banned else "danger"

    buttons = [
        [
            InlineKeyboardButton(text="Add / Deduct Balance", callback_data=f"adm_usradj_{user.telegram_id}_{page}", style="success"),
            InlineKeyboardButton(text=ban_text, callback_data=f"adm_usrban_{user.telegram_id}_{page}", style=ban_style)
        ],
        [
            InlineKeyboardButton(text="View User Orders", callback_data=f"adm_usrord_{user.telegram_id}_{page}", style="primary"),
            InlineKeyboardButton(text="< Back to Users", callback_data=f"adm_usrpage_{page}", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_api_menu_keyboard(pending_count: int = 0, approved_count: int = 0) -> InlineKeyboardMarkup:
    """Supplier API Management & Review Center."""
    pending_text = f"Pending Review ({pending_count})"
    pending_style = "danger" if pending_count > 0 else "primary"
    buttons = [
        [
            InlineKeyboardButton(text="Sync from AIVerseHub", callback_data="adm_api_sync", style="success"),
            InlineKeyboardButton(text="Check API Balance", callback_data="adm_api_bal", style="primary")
        ],
        [
            InlineKeyboardButton(text=pending_text, callback_data="adm_api_pending", style=pending_style),
            InlineKeyboardButton(text=f"Active in Store ({approved_count})", callback_data="adm_api_active", style="primary")
        ],
        [InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_pending_api_list_keyboard(products: List[Product], is_pending: bool = True) -> InlineKeyboardMarkup:
    """List API items for inspection and review."""
    buttons = []
    for p in products[:15]:
        status_tag = "Review" if not p.is_active else "Active"
        cost_str = f"${p.wholesale_price:.2f}" if p.wholesale_price else "$0.00"
        price_str = f"${p.price:.2f}"
        btn_text = f"{status_tag}: {p.name[:20]} | Cost: {cost_str} -> {price_str}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_api_inspect_{p.id}", style="primary")])

    buttons.append([InlineKeyboardButton(text="< Back to API Center", callback_data="adm_api_menu", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_api_item_review_keyboard(product: Product) -> InlineKeyboardMarkup:
    """Admin review & edit actions for a specific API product."""
    toggle_text = "Hide / Deactivate" if product.is_active else "Approve & Publish to Store"
    toggle_style = "danger" if product.is_active else "success"
    input_tag = f"Input Req: YES ({product.input_placeholder or '@username'})" if product.requires_input else "Input Req: NO"
    input_style = "success" if product.requires_input else "primary"
    buttons = [
        [InlineKeyboardButton(text=toggle_text, callback_data=f"adm_api_toggle_{product.id}", style=toggle_style)],
        [
            InlineKeyboardButton(text="Edit Retail Price", callback_data=f"adm_api_setprice_{product.id}", style="primary"),
            InlineKeyboardButton(text="Edit Title", callback_data=f"adm_api_setname_{product.id}", style="primary")
        ],
        [
            InlineKeyboardButton(text=input_tag, callback_data=f"adm_api_toggleinput_{product.id}", style=input_style),
            InlineKeyboardButton(text="Change Category", callback_data=f"adm_api_setcat_{product.id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="Delete Product", callback_data=f"adm_api_del_{product.id}", style="danger"),
            InlineKeyboardButton(text="< Back to Pending", callback_data="adm_api_pending", style="danger")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_categories_select_keyboard(categories: List[Category], product_id: int) -> InlineKeyboardMarkup:
    """Category picker for API product approval."""
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=cat.name, callback_data=f"adm_api_assigncat_{product_id}_{cat.id}", style="primary"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="< Cancel", callback_data=f"adm_api_inspect_{product_id}", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
