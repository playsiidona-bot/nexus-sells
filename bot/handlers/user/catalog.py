from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.crud import (
    get_all_categories, get_products_by_category, get_all_products, get_product_by_id,
    get_product_stock_count, add_to_cart, get_user_by_id, subscribe_restock,
    get_product_reviews, get_cart
)
from bot.keyboards.inline import categories_keyboard, products_keyboard, product_detail_keyboard, cart_keyboard
from bot.services.i18n import t
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL

router = Router()


@router.message(F.text.in_(["Products Catalog", "የዕቃዎች ካታሎግ", "[ Products Catalog ]", "[ የዕቃዎች ካታሎግ ]", "🛍️ Products Catalog", "🛍️ የዕቃዎች ካታሎግ"]))
async def open_catalog(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"

    categories = await get_all_categories()
    if not categories:
        await message.answer(t("empty_catalog", lang))
        return

    kb = categories_keyboard(categories, lang)
    await message.answer(t("catalog_title", lang), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "catalog_home")
async def back_to_catalog(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    categories = await get_all_categories()
    kb = categories_keyboard(categories, lang)
    await call.message.edit_text(t("catalog_title", lang), reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "cat_all")
async def open_all_products(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    products = await get_all_products()
    if not products:
        await call.answer(t("empty_catalog", lang), show_alert=True)
        return

    kb = products_keyboard(products, cat_id=0, lang=lang)
    header = (
        "<b>ALL AVAILABLE PRODUCTS</b>\n"
        "────────────────────────\n"
        "Select an item below to view specifications and purchase:"
        if lang == "en" else
        "<b>ሁሉም የሚገኙ ዕቃዎች</b>\n"
        "────────────────────────\n"
        "ዝርዝሩን ለማየት ከታች ይምረጡ፡"
    )
    await call.message.edit_text(header, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("cat_"))
async def open_category(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    cat_id = int(call.data.split("_")[1])
    products = await get_products_by_category(cat_id)

    if not products:
        await call.answer(t("empty_catalog", lang), show_alert=True)
        return

    kb = products_keyboard(products, cat_id, lang)
    header = (
        "<b>PRODUCTS IN CATEGORY</b>\n"
        "────────────────────────\n"
        "Select an item below to view specifications and purchase:"
        if lang == "en" else
        "<b>በምድቡ ውስጥ ያሉ ዕቃዎች</b>\n"
        "────────────────────────\n"
        "ዝርዝሩን ለማየት ከታች ይምረጡ፡"
    )
    await call.message.edit_text(header, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("prod_"))
async def open_product(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prod_id = int(call.data.split("_")[1])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    stock = await get_product_stock_count(prod_id)
    stock_display = (
        "Instant Delivery" if (stock >= 999 or product.delivery_type == "api")
        else (f"{stock} units" if stock > 0 else "Out of Stock")
    )

    price_str = f"<b>{CURRENCY_SYMBOL}{product.price:.2f}</b>"
    if product.sale_price:
        price_str = f"<s>{CURRENCY_SYMBOL}{product.price:.2f}</s> <b>{CURRENCY_SYMBOL}{product.sale_price:.2f}</b> (Sale)"

    text = t("product_view", lang,
             name=product.name,
             description=product.description or "No description provided.",
             price=price_str,
             currency="",
             stock=stock_display)

    kb = product_detail_keyboard(prod_id, stock, lang)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("cart_add_"))
async def add_item_to_cart(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prod_id = int(call.data.split("_")[2])
    await add_to_cart(call.from_user.id, prod_id, quantity=1)
    await call.answer(t("added_to_cart", lang), show_alert=False)


@router.callback_query(F.data.startswith("buy_now_"))
async def handle_buy_now(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prod_id = int(call.data.split("_")[2])
    await add_to_cart(call.from_user.id, prod_id, quantity=1)

    items = await get_cart(call.from_user.id)
    total = sum(it["total_price"] for it in items)
    items_text = [
        f"{i}. <b>{it['name']}</b> x{it['quantity']} — <code>{CURRENCY_SYMBOL}{it['total_price']:.2f}</code>"
        for i, it in enumerate(items, 1)
    ]
    body = "\n".join(items_text)
    text = t("cart_title", lang, items=body, total=f"{CURRENCY_SYMBOL}{total:.2f}", currency="")
    kb = cart_keyboard(items, lang)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("Item added to checkout", show_alert=False)


@router.callback_query(F.data.startswith("reviews_"))
async def handle_product_reviews(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prod_id = int(call.data.split("_")[1])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    reviews = await get_product_reviews(prod_id, limit=5)
    if not reviews:
        text = (
            f"<b>REVIEWS & RATINGS: {product.name}</b>\n"
            f"────────────────────────\n"
            f"No reviews have been posted for this product yet."
        )
    else:
        rev_lines = []
        for r in reviews:
            score_bar = f"{r.rating}/5"
            rev_lines.append(f"• <b>{score_bar}</b> <i>\"{r.comment or 'Verified Purchase'}\"</i>")
        rev_body = "\n".join(rev_lines)
        text = (
            f"<b>CUSTOMER REVIEWS: {product.name}</b>\n"
            f"────────────────────────\n"
            f"{rev_body}"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="< Back to Product", callback_data=f"prod_{prod_id}", style="primary")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("notify_restock_"))
async def handle_notify_restock(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    prod_id = int(call.data.split("_")[2])

    ok = await subscribe_restock(call.from_user.id, prod_id)
    if ok:
        msg = "ተመዝግበዋል! ዕቃው በክምችት ሲገባ ወዲያውኑ መልእክት ይደርሶታል።" if lang == "am" else "Subscribed! You will be notified instantly when this item is back in stock."
    else:
        msg = "አስቀድመው ለዚህ ዕቃ ተመዝግበዋል።" if lang == "am" else "You are already subscribed to restock alerts for this item."

    await call.answer(msg, show_alert=True)
