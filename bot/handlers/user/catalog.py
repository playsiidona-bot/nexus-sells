from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.database.crud import (
    get_all_categories, get_products_by_category, get_product_by_id,
    get_product_stock_count, add_to_cart, get_user_by_id, subscribe_restock
)
from bot.keyboards.inline import categories_keyboard, products_keyboard, product_detail_keyboard
from bot.services.i18n import t
from bot.config import BASE_CURRENCY

router = Router()


@router.message(F.text.in_(["🛍️ የዕቃዎች ካታሎግ", "🛍️ Products Catalog"]))
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
    await call.message.edit_text("📂 <b>የተመረጡ ዕቃዎች (Products):</b>\n\nዕቃውን ለመመልከት ከታች ይምረጡ፡", reply_markup=kb, parse_mode="HTML")
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
    stock_display = "⚡ Instant Available" if (stock >= 999 or product.delivery_type == "api") else (f"{stock} units" if stock > 0 else "❌ Out of Stock")

    price_str = f"<b>{product.price} {BASE_CURRENCY}</b>"
    if product.sale_price:
        price_str = f"<s>{product.price}</s> <b>{product.sale_price} {BASE_CURRENCY}</b> 🔥"

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
    await call.answer(t("added_to_cart", lang), show_alert=True)


@router.callback_query(F.data.startswith("notify_restock_"))
async def handle_notify_restock(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    prod_id = int(call.data.split("_")[2])

    ok = await subscribe_restock(call.from_user.id, prod_id)
    if ok:
        msg = "✅ <b>ተመዝግበዋል!</b> ዕቃው በክምችት ሲገባ ወዲያውኑ መልእክት ይደርሶታል።" if lang == "am" else "✅ <b>Subscribed!</b> You will be notified instantly when this item is back in stock."
    else:
        msg = "ℹ️ አስቀድመው ለዚህ ዕቃ ተመዝግበዋል።" if lang == "am" else "ℹ️ You are already subscribed to restock alerts for this item."

    await call.answer(msg, show_alert=True)

