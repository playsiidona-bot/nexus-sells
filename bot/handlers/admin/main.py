from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from bot.database.session import async_session
from bot.database.models import User, Product, Order, Category, ProductStock, SupportTicket
from bot.database.crud import (
    create_category, add_product_stock_items, get_and_clear_restock_subscribers,
    get_ticket_by_code, replace_key_for_ticket, refund_ticket, reject_ticket,
    get_product_by_id, get_setting, set_setting, sync_aiverse_products,
    get_pending_api_products, get_approved_api_products, update_api_product_review,
    delete_product, get_all_categories, create_product
)
from bot.keyboards.inline import (
    admin_main_keyboard, admin_settings_keyboard, admin_api_menu_keyboard,
    admin_pending_api_list_keyboard, admin_api_item_review_keyboard,
    admin_categories_select_keyboard, admin_api_keys_keyboard,
    admin_add_prod_category_keyboard, admin_add_prod_skip_desc_keyboard,
    admin_add_prod_delivery_keyboard, admin_add_prod_input_keyboard
)
from bot.services.aiverse_client import aiverse_client
from bot.config import (
    ADMIN_IDS, OWNER_ID, BASE_CURRENCY, CURRENCY_SYMBOL, TELEBIRR_RECEIVER_PHONE,
    TELEBIRR_RECEIVER_NAME, CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME,
    FORCE_JOIN_CHANNEL, REVIEWS_CHANNEL_ID,
    AIVERSE_API_KEY, CRYPTO_PAY_TOKEN, OXAPAY_API_KEY,
    CRYPTOMUS_PAYMENT_KEY, CRYPTOMUS_MERCHANT_ID, NOWPAYMENTS_API_KEY
)

router = Router()


class AdminStates(StatesGroup):
    waiting_cat_name = State()
    waiting_stock_prod_id = State()
    waiting_stock_keys = State()
    waiting_broadcast_text = State()
    waiting_welcome_text = State()
    waiting_rules_text = State()
    waiting_telebirr = State()
    waiting_cbe = State()
    waiting_fjoin = State()
    waiting_revchan = State()
    waiting_api_price = State()
    waiting_api_name = State()
    # Dynamic API keys configuration
    waiting_api_key_val = State()
    # Add Product flow states
    waiting_new_prod_name = State()
    waiting_new_prod_desc = State()
    waiting_new_prod_price = State()
    waiting_new_prod_placeholder = State()
    waiting_new_prod_inf_val = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_ID


@router.message(F.text.in_(["Admin Suite", "የአስተዳዳሪ ክፍል", "[ Admin Suite ]", "[ የአስተዳዳሪ ክፍል ]", "⚙️ አስተዳዳሪ (Admin)", "⚙️ Admin Suite"]))
@router.message(Command("admin"))
async def open_admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = (
        "<b>Nexus Hub Admin Suite</b>\n"
        "────────────────────────\n"
        "የቦቱን ዕቃዎች፣ ክምችት፣ ማስታወቂያዎችና አጠቃላይ ስታትስቲክስ ከዚህ ማስተዳደር ይችላሉ።"
    )
    await message.answer(text, reply_markup=admin_main_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "adm_stats")
async def show_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True)
        return

    async with async_session() as session:
        users_count = (await session.execute(select(func.count(User.telegram_id)))).scalar() or 0
        orders_count = (await session.execute(select(func.count(Order.id)))).scalar() or 0
        revenue = (await session.execute(select(func.sum(Order.total_price)))).scalar() or Decimal("0.00")
        products_count = (await session.execute(select(func.count(Product.id)))).scalar() or 0
        active_stock = (await session.execute(
            select(func.count(ProductStock.id)).where(ProductStock.is_used == False)
        )).scalar() or 0

    stats_text = (
        "<b>Nexus Hub Real-Time Analytics:</b>\n"
        "────────────────────────\n"
        f"• የተመዘገቡ ተጠቃሚዎች፡ <b>{users_count}</b>\n"
        f"• ጠቅላላ የተሸጡ ትዕዛዞች፡ <b>{orders_count}</b>\n"
        f"• ጠቅላላ የሽያጭ ገቢ፡ <b>{CURRENCY_SYMBOL}{revenue:.2f} {BASE_CURRENCY}</b>\n"
        f"• ንቁ ዕቃዎች (Products)፡ <b>{products_count}</b>\n"
        f"• የሚገኙ የቁልፎች ክምችት (Stock Keys)፡ <b>{active_stock}</b>"
    )
    await call.message.edit_text(stats_text, reply_markup=admin_main_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_add_cat")
async def start_add_category(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("እባክዎ የአዲሱን ምድብ (Category) ስም ያስገቡ:\n<i>ለምሳሌ፡ Gaming Accounts</i>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_cat_name)
    await call.answer()


@router.message(AdminStates.waiting_cat_name)
async def process_cat_name(message: Message, state: FSMContext):
    cat_name = message.text.strip()
    if cat_name:
        await create_category(name=cat_name)
        await message.answer(f"ምድብ <b>{cat_name}</b> በተሳካ ሁኔታ ተፈጥሯል!", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_add_stock")
async def start_add_stock(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    async with async_session() as session:
        prods = (await session.execute(select(Product))).scalars().all()
    if not prods:
        await call.answer("ምንም ዕቃ አልተገኘም!", show_alert=True)
        return

    prod_list = "\n".join([f"ID: <code>{p.id}</code> - {p.name}" for p in prods[:20]])
    await call.message.answer(
        f"🔑 <b>Stock ለመጨመር የዕቃውን ID ያስገቡ፡</b>\n\n{prod_list}\n\nየዕቃውን ID ይላኩ፡",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_stock_prod_id)
    await call.answer()


@router.message(AdminStates.waiting_stock_prod_id)
async def process_stock_prod_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ እባክዎ ትክክለኛ የዕቃ ቁጥር (ID) ያስገቡ።")
        return
    prod_id = int(message.text)
    await state.update_data(prod_id=prod_id)
    await message.answer(
        "📝 አሁን ላይሰንሶቹን/ቁልፎቹን በአንድ መስመር አንድ በማድረግ ይላኩ (Batch paste):\n\n"
        "<i>ለምሳሌ፡\nKEY1-AAAA-BBBB\nKEY2-CCCC-DDDD</i>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_stock_keys)


@router.message(AdminStates.waiting_stock_keys)
async def process_stock_keys(message: Message, state: FSMContext):
    data = await state.get_data()
    prod_id = data.get("prod_id")
    lines = [x.strip() for x in message.text.split("\n") if x.strip()]
    if lines and prod_id:
        added = await add_product_stock_items(prod_id, lines)
        product = await get_product_by_id(prod_id)
        prod_name = product.name if product else f"Product #{prod_id}"

        # Notify waiting subscribers!
        subscribers = await get_and_clear_restock_subscribers(prod_id)
        notified = 0
        restock_msg = (
            f"🎉 <b>ዕቃው አሁን ገብቷል! (Back in Stock!)</b>\n\n"
            f"ይፈልጉት የነበረው <b>{prod_name}</b> አሁን በክምችት ላይ ይገኛል!\n"
            "አሁኑኑ በቦቱ ካታሎግ ገብተው ማዘዝ ይችላሉ።"
        )
        for uid in subscribers:
            try:
                await message.bot.send_message(uid, restock_msg, parse_mode="HTML")
                notified += 1
            except Exception:
                pass

        reply = f"✅ <b>{added}</b> ቁልፎች ወደ <b>{prod_name}</b> ተጨምረዋል!"
        if notified > 0:
            reply += f"\n📢 ለ <b>{notified}</b> ተጠቃሚዎች የክምችት ማሳወቂያ (Restock Alert) ተልኳል!"
        await message.answer(reply, parse_mode="HTML")
    await state.clear()


# =====================================================================
# TICKET RESOLUTION HANDLERS
# =====================================================================

@router.callback_query(F.data.startswith("adm_replace_"))
async def admin_replace_key(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True)
        return

    ticket_code = call.data.replace("adm_replace_", "")
    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket.status != "open":
        await call.answer("Ticket is not open or already resolved.", show_alert=True)
        return

    success, msg, new_key = await replace_key_for_ticket(ticket_code)
    if not success:
        await call.answer(f"❌ Failed: {msg}", show_alert=True)
        return

    # Notify User with new key
    user_msg = (
        f"✅ <b>አዲስ ቁልፍ ተልኮልዎታል! (Replacement Key)</b>\n\n"
        f"ስለ ትኬትዎ <code>{ticket_code}</code> ጉዳይ ተመልክተን አዲስ ቁልፍ ልከንልዎታል:\n"
        f"🔑 <code>{new_key}</code>\n\n"
        "ለደረሰብዎ መጉላላት ከልብ ይቅርታ እንጠይቃለን!"
    )
    try:
        await call.bot.send_message(ticket.user_id, user_msg, parse_mode="HTML")
    except Exception:
        pass

    await call.message.edit_text(
        f"{call.message.html_text}\n\n✅ <b>RESOLVED: Key Replaced and delivered to user!</b>",
        parse_mode="HTML"
    )
    await call.answer("Key Replaced & Sent!", show_alert=False)


@router.callback_query(F.data.startswith("adm_refund_"))
async def admin_refund_ticket(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True)
        return

    ticket_code = call.data.replace("adm_refund_", "")
    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket.status != "open":
        await call.answer("Ticket is not open or already resolved.", show_alert=True)
        return

    success, msg, refund_amount = await refund_ticket(ticket_code)
    if not success:
        await call.answer(f"❌ Failed: {msg}", show_alert=True)
        return

    # Notify User
    user_msg = (
        f"💰 <b>ክፍያዎ ወደ ዋሌትዎ ተመላሽ ተደርጓል! (Refunded)</b>\n\n"
        f"ስለ ትኬትዎ <code>{ticket_code}</code> የ <b>{refund_amount} {BASE_CURRENCY}</b> ተመላሽ ወደ ዋሌትዎ ገብቷል!\n\n"
        "ለደረሰብዎ ችግር ይቅርታ እንጠይቃለን።"
    )
    try:
        await call.bot.send_message(ticket.user_id, user_msg, parse_mode="HTML")
    except Exception:
        pass

    await call.message.edit_text(
        f"{call.message.html_text}\n\n💰 <b>RESOLVED: {refund_amount} {BASE_CURRENCY} refunded to user wallet!</b>",
        parse_mode="HTML"
    )
    await call.answer("Refunded successfully!", show_alert=False)


@router.callback_query(F.data.startswith("adm_reject_"))
async def admin_reject_ticket(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True)
        return

    ticket_code = call.data.replace("adm_reject_", "")
    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket.status != "open":
        await call.answer("Ticket is not open or already resolved.", show_alert=True)
        return

    await reject_ticket(ticket_code)

    # Notify User
    user_msg = (
        f"❌ <b>ቅሬታዎ ውድቅ ተደርጓል (Ticket Rejected)</b>\n\n"
        f"ስለ ትኬትዎ <code>{ticket_code}</code> ጉዳይ ተመርምሮ ውድቅ ተደርጓል።\n"
        "ተጨማሪ ማብራሪያ ካለዎት እባክዎ ደንበኞች አገልግሎትን ያነጋግሩ።"
    )
    try:
        await call.bot.send_message(ticket.user_id, user_msg, parse_mode="HTML")
    except Exception:
        pass

    await call.message.edit_text(
        f"{call.message.html_text}\n\n❌ <b>REJECTED: Ticket closed.</b>",
        parse_mode="HTML"
    )
    await call.answer("Ticket Rejected", show_alert=False)


@router.callback_query(F.data.startswith("adm_ignore_"))
async def admin_ignore_ticket(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True)
        return

    await call.message.edit_text(
        f"{call.message.html_text}\n\n🙈 <b>ችላ ተብሏል (Dismissed)</b>",
        parse_mode="HTML"
    )
    await call.answer("ችላ ተብሏል (Dismissed)", show_alert=False)




@router.callback_query(F.data == "adm_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📢 ለሁሉም ተጠቃሚዎች የሚላከውን መልእክት እዚህ ይጻፉ/ይላኩ:")
    await state.set_state(AdminStates.waiting_broadcast_text)
    await call.answer()


@router.message(AdminStates.waiting_broadcast_text)
async def process_broadcast_message(message: Message, state: FSMContext):
    text_to_send = message.html_text or message.text
    async with async_session() as session:
        users = (await session.execute(select(User.telegram_id))).scalars().all()

    sent = 0
    progress = await message.answer("🚀 መልእክቱ እየተላከ ነው...")
    for uid in users:
        try:
            await message.bot.send_message(uid, text_to_send, parse_mode="HTML")
            sent += 1
        except Exception:
            pass

    await progress.edit_text(f"✅ ማስታወቂያው ለ <b>{sent}/{len(users)}</b> ተጠቃሚዎች ተልኳል!", parse_mode="HTML")
    await state.clear()


# =====================================================================
# IN-CHAT BOT SETTINGS & CUSTOMIZATION
# =====================================================================

@router.callback_query(F.data == "adm_main_menu")
async def back_to_admin_main(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    text = "⚙️ <b>Nexus Hub Admin Suite</b>\n\nየቦቱን ዕቃዎች፣ ክምችት፣ ማስታወቂያዎችና አጠቃላይ ስታትስቲክስ ከዚህ ማስተዳደር ይችላሉ።"
    await call.message.edit_text(text, reply_markup=admin_main_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_settings")
async def open_settings_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    maint = await get_setting("maintenance_mode", "0") == "1"
    kb = admin_settings_keyboard(maintenance_on=maint)
    text = (
        "⚙️ <b>Bot Settings & UI Customization:</b>\n\n"
        "ከዚህ ክፍል የቦቱን ጽሁፎች፣ የክፍያ ስልኮች፣ የማስገደጃና የሪቪው ቻናሎችን ሳያጠፉ በቅጽበት ማስተካከል ይችላሉ።"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_toggle_maint")
async def toggle_maintenance(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    curr = await get_setting("maintenance_mode", "0")
    new_val = "0" if curr == "1" else "1"
    await set_setting("maintenance_mode", new_val, "Toggle maintenance mode")

    kb = admin_settings_keyboard(maintenance_on=(new_val == "1"))
    status_label = "🔴 በርቷል (ON)" if new_val == "1" else "⚪ ጠፍቷል (OFF)"
    await call.message.edit_text(
        f"🛠️ <b>Maintenance Mode: {status_label}</b>\n\nሁኔታው በተሳካ ሁኔታ ተቀይሯል።",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await call.answer(f"Maintenance: {status_label}", show_alert=False)


@router.callback_query(F.data == "adm_set_welcome")
async def start_set_welcome(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📝 አዲሱን የቦቱን <b>የመግቢያ መልእክት (Welcome Text)</b> ይላኩ:\n<i>(HTML tags መጠቀም ይችላሉ)</i>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_welcome_text)
    await call.answer()


@router.message(AdminStates.waiting_welcome_text)
async def process_welcome_text(message: Message, state: FSMContext):
    new_text = message.html_text or message.text
    await set_setting("welcome_text", new_text, "Custom welcome message")
    await message.answer("✅ <b>የመግቢያ መልእክቱ በተሳካ ሁኔታ ተቀይሯል!</b>", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_set_rules")
async def start_set_rules(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📜 አዲሱን <b>የቦቱ ደንቦችና መመሪያ (Rules/About Us)</b> ይላኩ:", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_rules_text)
    await call.answer()


@router.message(AdminStates.waiting_rules_text)
async def process_rules_text(message: Message, state: FSMContext):
    new_text = message.html_text or message.text
    await set_setting("rules_text", new_text, "Custom rules")
    await message.answer("✅ <b>የቦቱ መመሪያ ጽሁፍ በተሳካ ሁኔታ ተቀይሯል!</b>", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_set_telebirr")
async def start_set_telebirr(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📱 አዲሱን የቴሌብር <b>ስልክ ቁጥር እና ስም</b> በዚህ ፎርማት ይላኩ:\n<code>0912345678, Nexus Digital</code>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_telebirr)
    await call.answer()


@router.message(AdminStates.waiting_telebirr)
async def process_telebirr(message: Message, state: FSMContext):
    text = message.text.strip()
    await set_setting("telebirr_account", text, "Telebirr account details")
    await message.answer(f"✅ የቴሌብር መረጃ ወደ <code>{text}</code> ተቀይሯል!", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_set_cbe")
async def start_set_cbe(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("🏦 አዲሱን የ CBE <b>የሒሳብ ቁጥር እና ስም</b> በዚህ ፎርማት ይላኩ:\n<code>1000123456789, Nexus Digital</code>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_cbe)
    await call.answer()


@router.message(AdminStates.waiting_cbe)
async def process_cbe(message: Message, state: FSMContext):
    text = message.text.strip()
    await set_setting("cbe_account", text, "CBE account details")
    await message.answer(f"✅ የ CBE መረጃ ወደ <code>{text}</code> ተቀይሯል!", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_set_fjoin")
async def start_set_fjoin(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📢 ተጠቃሚዎች ግዴታ እንዲቀላቀሉ የሚፈልጉትን <b>የቻናል ዩዘርኔም (ወይም ID)</b> ይላኩ:\n<i>(ከአንድ በላይ ከሆነ በኮማ ይለዩ፡ @channel1, @channel2)</i>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_fjoin)
    await call.answer()


@router.message(AdminStates.waiting_fjoin)
async def process_fjoin(message: Message, state: FSMContext):
    text = message.text.strip()
    await set_setting("force_join_channels", text, "Required force join channels")
    await message.answer(f"✅ Force Join ቻናሎች ወደ <b>{text}</b> ተቀይረዋል!", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_set_revchan")
async def start_set_revchan(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("🌟 የደንበኞች ሪቪው (Reviews) የሚለጠፍበትን <b>የቻናል ዩዘርኔም ወይም ID</b> ይላኩ:\n<i>ለምሳሌ፡ @nexus_reviews ወይም -1001234567890</i>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_revchan)
    await call.answer()


@router.message(AdminStates.waiting_revchan)
async def process_revchan(message: Message, state: FSMContext):
    text = message.text.strip()
    await set_setting("reviews_channel_id", text, "Customer reviews channel")
    await message.answer(f"✅ Review Channel ወደ <b>{text}</b> ተቀይሯል! አዳዲስ ሪቪውዎች እዚህ ቻናል ላይ ይለጠፋሉ።", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "adm_home")
async def back_to_admin_home(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    text = (
        "<b>Nexus Hub Admin Suite</b>\n"
        "────────────────────────\n"
        "የቦቱን ዕቃዎች፣ ክምችት፣ API ምርቶችና አጠቃላይ ስታትስቲክስ ከዚህ ማስተዳደር ይችላሉ።"
    )
    await call.message.edit_text(text, reply_markup=admin_main_keyboard(), parse_mode="HTML")
    await call.answer()


# =====================================================================
# API PRODUCT REVIEW, APPROVAL & PRICE ADJUSTMENT
# =====================================================================

@router.callback_query(F.data == "adm_api_menu")
async def open_api_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pending = await get_pending_api_products(100)
    approved = await get_approved_api_products(100)
    kb = admin_api_menu_keyboard(len(pending), len(approved))
    text = (
        "<b>SUPPLIER API & PRODUCT REVIEW CENTER</b>\n"
        "────────────────────────\n"
        "All products from external APIs (AIVerseHub) are staged here.\n\n"
        "<blockquote>• <b>Admin Review Policy:</b> Any product imported from the API remains hidden until you inspect, adjust pricing, and explicitly approve it.\n"
        f"• <b>Pending Review:</b> <code>{len(pending)} items</code>\n"
        f"• <b>Active in Store:</b> <code>{len(approved)} items</code></blockquote>\n\n"
        "Select an action below:"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_api_bal")
async def check_api_balance(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    res = await aiverse_client.get_me()
    if "error" in res:
        await call.answer(f"API Error: {res['error']}", show_alert=True)
        return
    bal = res.get("wallet_balance", 0.0)
    name = res.get("first_name", "AIVerse User")
    await call.answer(f"AIVerse Account ({name}): Balance = ${bal:.2f}", show_alert=True)


@router.callback_query(F.data == "adm_api_sync")
async def sync_api_catalog(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.answer("Fetching catalog from AIVerseHub API...", show_alert=False)
    data = await aiverse_client.get_products()
    services = data.get("services", [])
    if not services:
        err = data.get("error", "No services returned from supplier API")
        await call.answer(f"Sync failed: {err}", show_alert=True)
        return

    res = await sync_aiverse_products(services)
    pending = await get_pending_api_products(100)
    approved = await get_approved_api_products(100)
    kb = admin_api_menu_keyboard(len(pending), len(approved))
    text = (
        "<b>AIVERSEHUB CATALOG SYNC COMPLETE</b>\n"
        "────────────────────────\n"
        f"<blockquote>• <b>Total Services Fetched:</b> <code>{len(services)}</code>\n"
        f"• <b>New Items Staged for Review:</b> <code>{res['created']}</code>\n"
        f"• <b>Existing Items Updated:</b> <code>{res['updated']}</code></blockquote>\n\n"
        "<i>All new services are staged as <b>Pending Review</b> (hidden from users) until you approve them.</i>"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_api_pending")
async def view_pending_api_products(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    pending = await get_pending_api_products(50)
    if not pending:
        await call.answer("No pending API products requiring review.", show_alert=True)
        return

    kb = admin_pending_api_list_keyboard(pending, is_pending=True)
    text = (
        "<b>PENDING API PRODUCTS (NEED REVIEW)</b>\n"
        "────────────────────────\n"
        "These items were fetched from the API and are <b>hidden from customers</b>.\n"
        "Tap an item below to inspect, set custom retail pricing, assign category, and approve:"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_api_active")
async def view_active_api_products(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    active = await get_approved_api_products(50)
    if not active:
        await call.answer("No active API products in store.", show_alert=True)
        return

    kb = admin_pending_api_list_keyboard(active, is_pending=False)
    text = (
        "<b>ACTIVE STORE API PRODUCTS</b>\n"
        "────────────────────────\n"
        "These API items are currently live and purchasable by customers in the catalog.\n"
        "Tap an item to modify price or deactivate:"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("adm_api_inspect_"))
async def inspect_api_product(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    status_tag = "ACTIVE IN STORE" if product.is_active else "PENDING REVIEW (HIDDEN)"
    cost = product.wholesale_price or Decimal("0.00")
    margin = product.price - cost
    margin_percent = ((margin / cost) * 100) if cost > 0 else 0
    input_str = f"Required ({product.input_placeholder or '@username'})" if product.requires_input else "Not Required"

    text = (
        f"<b>API PRODUCT INSPECTION & REVIEW</b>\n"
        f"────────────────────────\n"
        f"<blockquote>• <b>Title:</b> {product.name}\n"
        f"• <b>Supplier Service ID:</b> <code>{product.service_id}</code>\n"
        f"• <b>Wholesale Cost:</b> <code>${cost:.2f}</code>\n"
        f"• <b>Current Retail Price:</b> <code>${product.price:.2f}</code>\n"
        f"• <b>Your Profit Margin:</b> <code>+${margin:.2f} (+{margin_percent:.1f}%)</code>\n"
        f"• <b>Live API Stock:</b> <code>{product.api_stock}</code>\n"
        f"• <b>Customer Input:</b> <code>{input_str}</code>\n"
        f"• <b>Status:</b> <b>{status_tag}</b></blockquote>\n\n"
        f"<i>Adjust pricing, customer input requirement, or details below:</i>"
    )
    kb = admin_api_item_review_keyboard(product)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("adm_api_toggle_"))
async def toggle_api_approval(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    new_active = not product.is_active
    await update_api_product_review(prod_id, is_active=new_active)
    msg = "Product published to store catalog!" if new_active else "Product hidden from store catalog."
    await call.answer(msg, show_alert=True)

    call.data = f"adm_api_inspect_{prod_id}"
    await inspect_api_product(call)


@router.callback_query(F.data.startswith("adm_api_toggleinput_"))
async def toggle_api_required_input(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    new_val = not product.requires_input
    await update_api_product_review(prod_id, requires_input=new_val)
    status_str = "Customer input requirement: ENABLED" if new_val else "Customer input requirement: DISABLED"
    await call.answer(status_str, show_alert=False)

    call.data = f"adm_api_inspect_{prod_id}"
    await inspect_api_product(call)


@router.callback_query(F.data.startswith("adm_api_setprice_"))
async def prompt_set_api_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    product = await get_product_by_id(prod_id)
    if not product:
        await call.answer("Product not found", show_alert=True)
        return

    await state.update_data(prod_id=prod_id)
    await state.set_state(AdminStates.waiting_api_price)
    cost = product.wholesale_price or Decimal("0.00")
    await call.message.answer(
        f"<b>SET CUSTOM RETAIL PRICE</b>\n"
        f"────────────────────────\n"
        f"• Product: <b>{product.name}</b>\n"
        f"• Wholesale Cost: <code>${cost:.2f}</code>\n\n"
        f"Send the new retail price in USD (e.g. <code>4.99</code> or <code>12.50</code>):",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(AdminStates.waiting_api_price)
async def process_set_api_price(message: Message, state: FSMContext):
    data = await state.get_data()
    prod_id = data.get("prod_id")
    try:
        new_price = Decimal(message.text.strip().replace("$", ""))
        if new_price <= 0:
            raise ValueError()
    except Exception:
        await message.answer("Please enter a valid numeric price (e.g. 9.99).")
        return

    await update_api_product_review(prod_id, price=new_price)
    await state.clear()
    await message.answer(f"Retail price updated to <b>${new_price:.2f}</b>!", parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_api_setname_"))
async def prompt_set_api_name(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    await state.update_data(prod_id=prod_id)
    await state.set_state(AdminStates.waiting_api_name)
    await call.message.answer("Send the customized display title for this product:", parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_api_name)
async def process_set_api_name(message: Message, state: FSMContext):
    data = await state.get_data()
    prod_id = data.get("prod_id")
    new_name = message.text.strip()
    if new_name and prod_id:
        await update_api_product_review(prod_id, name=new_name)
        await message.answer(f"Title updated to <b>{new_name}</b>!", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("adm_api_setcat_"))
async def prompt_set_api_cat(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    categories = await get_all_categories()
    kb = admin_categories_select_keyboard(categories, prod_id)
    await call.message.edit_text("Select category to assign this product to:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("adm_api_assigncat_"))
async def process_assign_api_cat(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    prod_id = int(parts[3])
    cat_id = int(parts[4])
    await update_api_product_review(prod_id, category_id=cat_id)
    await call.answer("Category updated!", show_alert=True)
    call.data = f"adm_api_inspect_{prod_id}"
    await inspect_api_product(call)


@router.callback_query(F.data.startswith("adm_api_del_"))
async def process_delete_api_prod(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    prod_id = int(call.data.split("_")[3])
    await delete_product(prod_id)
    await call.answer("Product deleted from staging.", show_alert=True)
    await view_pending_api_products(call)


# =====================================================================
# ADD PRODUCT FLOW (STEP-BY-STEP)
# =====================================================================

@router.callback_query(F.data == "adm_add_prod")
async def start_add_product(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    categories = await get_all_categories()
    if not categories:
        await call.answer("Please create at least one category first (+ Category).", show_alert=True)
        return

    kb = admin_add_prod_category_keyboard(categories)
    text = (
        "<b>ADD NEW PRODUCT (STEP 1/5)</b>\n"
        "────────────────────────\n"
        "Select the category for this new product:"
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("adm_addprod_cat_"))
async def process_addprod_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    cat_id = int(call.data.replace("adm_addprod_cat_", ""))
    await state.update_data(new_cat_id=cat_id)
    await state.set_state(AdminStates.waiting_new_prod_name)
    text = (
        "<b>ADD NEW PRODUCT (STEP 2/5)</b>\n"
        "────────────────────────\n"
        "Enter the product title / name:\n"
        "<i>Example: Telegram Premium (3 Months) or Steam Wallet $10</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_new_prod_name)
async def process_addprod_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Please enter a valid product title:")
        return
    await state.update_data(new_prod_name=name)
    await state.set_state(AdminStates.waiting_new_prod_desc)
    text = (
        "<b>ADD NEW PRODUCT (STEP 3/5)</b>\n"
        "────────────────────────\n"
        f"Product: <b>{name}</b>\n\n"
        "Send the product description, or tap <b>Skip Description</b> below:"
    )
    await message.answer(text, reply_markup=admin_add_prod_skip_desc_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "adm_addprod_skip_desc")
async def process_addprod_skip_desc(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_prod_desc="")
    await state.set_state(AdminStates.waiting_new_prod_price)
    text = (
        "<b>ADD NEW PRODUCT (STEP 4/5)</b>\n"
        "────────────────────────\n"
        f"Enter the selling price in {BASE_CURRENCY} (e.g. <code>9.99</code> or <code>250</code>):"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_new_prod_desc)
async def process_addprod_desc(message: Message, state: FSMContext):
    desc = message.html_text or message.text
    await state.update_data(new_prod_desc=desc)
    await state.set_state(AdminStates.waiting_new_prod_price)
    text = (
        "<b>ADD NEW PRODUCT (STEP 4/5)</b>\n"
        "────────────────────────\n"
        f"Enter the selling price in {BASE_CURRENCY} (e.g. <code>9.99</code> or <code>250</code>):"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(AdminStates.waiting_new_prod_price)
async def process_addprod_price(message: Message, state: FSMContext):
    raw = message.text.strip().replace("$", "").replace("ETB", "").replace(CURRENCY_SYMBOL, "")
    try:
        price = Decimal(raw)
        if price <= 0:
            raise ValueError()
    except Exception:
        await message.answer("Please enter a valid numeric price (e.g. <code>9.99</code> or <code>150</code>):", parse_mode="HTML")
        return

    await state.update_data(new_prod_price=str(price))
    text = (
        "<b>ADD NEW PRODUCT (STEP 5/5)</b>\n"
        "────────────────────────\n"
        "Select the delivery method for this product:\n\n"
        "• <b>Stock / License Keys:</b> Specific codes or accounts pulled from inventory.\n"
        "• <b>Unlimited Link / Instructions:</b> A permanent link, guide, or invite delivered automatically."
    )
    await message.answer(text, reply_markup=admin_add_prod_delivery_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "adm_addprod_deliv_stock")
async def process_addprod_deliv_stock(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_deliv_type="stock")
    text = (
        "<b>CUSTOMER INPUT REQUIREMENT</b>\n"
        "────────────────────────\n"
        "Does this product require custom customer input upon purchase?\n\n"
        "<i>(For example: customer's Telegram @username, player UID, account email, or profile link)</i>"
    )
    await call.message.edit_text(text, reply_markup=admin_add_prod_input_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_addprod_deliv_inf")
async def process_addprod_deliv_inf(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_deliv_type="stock_infinity")
    await state.set_state(AdminStates.waiting_new_prod_inf_val)
    text = (
        "<b>UNLIMITED DELIVERY CONTENT</b>\n"
        "────────────────────────\n"
        "Send the permanent link, credentials, or instructions that every customer receives after purchase:"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_new_prod_inf_val)
async def process_addprod_inf_val(message: Message, state: FSMContext):
    inf_val = message.text.strip()
    if not inf_val:
        await message.answer("Please send the link or instructions to be delivered:")
        return
    await state.update_data(new_inf_val=inf_val)
    text = (
        "<b>CUSTOMER INPUT REQUIREMENT</b>\n"
        "────────────────────────\n"
        "Does this product require custom customer input upon purchase?\n\n"
        "<i>(For example: customer's Telegram @username, player UID, account email, or profile link)</i>"
    )
    await message.answer(text, reply_markup=admin_add_prod_input_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "adm_addprod_input_yes")
async def process_addprod_input_yes(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_requires_input=True)
    await state.set_state(AdminStates.waiting_new_prod_placeholder)
    text = (
        "<b>SET CUSTOMER INPUT PROMPT</b>\n"
        "────────────────────────\n"
        "Enter the placeholder or instruction text shown to the customer.\n\n"
        "<i>Examples:</i>\n"
        "• <code>@username</code>\n"
        "• <code>Telegram Username</code>\n"
        "• <code>Player ID / UID</code>\n"
        "• <code>Account Email</code>\n"
        "• <code>Channel Link</code>"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_new_prod_placeholder)
async def process_addprod_placeholder(message: Message, state: FSMContext):
    placeholder = message.text.strip() or "@username"
    await state.update_data(new_input_placeholder=placeholder)
    await finalize_new_product(message, state)


@router.callback_query(F.data == "adm_addprod_input_no")
async def process_addprod_input_no(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.update_data(new_requires_input=False, new_input_placeholder="")
    await finalize_new_product(call.message, state)
    await call.answer()


async def finalize_new_product(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("new_cat_id")
    name = data.get("new_prod_name")
    desc = data.get("new_prod_desc", "")
    price = Decimal(data.get("new_prod_price", "0.00"))
    deliv_type = data.get("new_deliv_type", "stock")
    requires_input = data.get("new_requires_input", False)
    placeholder = data.get("new_input_placeholder", "@username")
    inf_val = data.get("new_inf_val", "")

    product = await create_product(
        category_id=cat_id,
        name=name,
        description=desc,
        price=price,
        delivery_type="stock",
        requires_input=requires_input,
        input_placeholder=placeholder,
        is_active=True
    )

    if deliv_type == "stock_infinity" and inf_val:
        await add_product_stock_items(product.id, [inf_val], is_infinity=True)

    input_tag = f"Required ({placeholder})" if requires_input else "None"
    deliv_tag = "Unlimited Shared Link" if deliv_type == "stock_infinity" else "Inventory Keys"

    text = (
        "<b>PRODUCT CREATED SUCCESSFULLY</b>\n"
        "────────────────────────\n"
        f"• <b>Title:</b> {product.name}\n"
        f"• <b>Price:</b> {CURRENCY_SYMBOL}{product.price:.2f} {BASE_CURRENCY}\n"
        f"• <b>Delivery Type:</b> {deliv_tag}\n"
        f"• <b>Customer Input:</b> {input_tag}\n"
        f"• <b>Status:</b> Active in Store\n\n"
        "You can add inventory keys now or return to Admin Suite:"
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+ Add Stock Keys Now", callback_data="adm_add_stock", style="success")],
        [InlineKeyboardButton(text="< Back to Admin", callback_data="adm_home", style="primary")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


# =====================================================================
# DYNAMIC API KEYS & GATEWAY SETTINGS
# =====================================================================

@router.callback_query(F.data == "adm_api_keys")
async def open_api_keys_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    aiverse_key = await get_setting("aiverse_api_key", AIVERSE_API_KEY)
    cryptobot_tok = await get_setting("crypto_pay_token", CRYPTO_PAY_TOKEN)
    oxapay_key = await get_setting("oxapay_api_key", OXAPAY_API_KEY)
    nowpay_key = await get_setting("nowpayments_api_key", NOWPAYMENTS_API_KEY)
    cryptomus_key = await get_setting("cryptomus_payment_key", CRYPTOMUS_PAYMENT_KEY)
    cryptomus_mid = await get_setting("cryptomus_merchant_id", CRYPTOMUS_MERCHANT_ID)

    def mask(val: str) -> str:
        if not val:
            return "Not Set"
        if len(val) <= 6:
            return "***"
        return f"{val[:3]}...{val[-3:]}"

    text = (
        "<b>PAYMENT & SUPPLIER API CONFIGURATION</b>\n"
        "────────────────────────\n"
        "Manage gateway credentials dynamically without restarting the bot:\n\n"
        f"• <b>AIVerseHub Key:</b> <code>{mask(aiverse_key)}</code>\n"
        f"• <b>CryptoBot Token:</b> <code>{mask(cryptobot_tok)}</code>\n"
        f"• <b>OxaPay Key:</b> <code>{mask(oxapay_key)}</code>\n"
        f"• <b>NOWPayments Key:</b> <code>{mask(nowpay_key)}</code>\n"
        f"• <b>Cryptomus Key:</b> <code>{mask(cryptomus_key)}</code>\n"
        f"• <b>Cryptomus Merchant ID:</b> <code>{mask(cryptomus_mid)}</code>\n\n"
        "Tap a button below to update its credentials:"
    )
    await call.message.edit_text(text, reply_markup=admin_api_keys_keyboard(), parse_mode="HTML")
    await call.answer()


KEY_NAME_MAP = {
    "adm_key_aiverse": ("aiverse_api_key", "AIVerseHub API Key"),
    "adm_key_cryptobot": ("crypto_pay_token", "CryptoBot Token"),
    "adm_key_oxapay": ("oxapay_api_key", "OxaPay API Key"),
    "adm_key_nowpayments": ("nowpayments_api_key", "NOWPayments API Key"),
    "adm_key_cryptomus_key": ("cryptomus_payment_key", "Cryptomus Payment Key"),
    "adm_key_cryptomus_mid": ("cryptomus_merchant_id", "Cryptomus Merchant ID"),
}


@router.callback_query(F.data.in_(KEY_NAME_MAP.keys()))
async def prompt_set_api_key(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    setting_key, friendly_title = KEY_NAME_MAP[call.data]
    current_val = await get_setting(setting_key, "")
    masked = f"{current_val[:3]}...{current_val[-3:]}" if current_val else "Not Configured"

    await state.update_data(target_key=setting_key, target_title=friendly_title)
    await state.set_state(AdminStates.waiting_api_key_val)

    text = (
        f"<b>CONFIGURE {friendly_title.upper()}</b>\n"
        "────────────────────────\n"
        f"Current Value: <code>{masked}</code>\n\n"
        "Send the new API credential / token below:\n"
        "<i>(Send 'clear' to remove the key, or /cancel to abort)</i>"
    )
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.waiting_api_key_val)
async def process_save_api_key(message: Message, state: FSMContext):
    data = await state.get_data()
    target_key = data.get("target_key")
    target_title = data.get("target_title", "API Key")

    val = message.text.strip()
    if val.lower() == "/cancel":
        await state.clear()
        await message.answer("Cancelled.")
        return

    save_val = "" if val.lower() == "clear" else val
    await set_setting(target_key, save_val, f"Configured {target_title}")

    # If AIVerseHub key was changed, refresh client immediately
    if target_key == "aiverse_api_key":
        aiverse_client.api_key = save_val

    await state.clear()
    status_str = "cleared" if not save_val else "saved successfully"
    text = (
        f"<b>{target_title.upper()} UPDATED</b>\n"
        "────────────────────────\n"
        f"The credential has been {status_str} and is now active in memory and database."
    )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="< Back to API Keys", callback_data="adm_api_keys", style="primary")],
        [InlineKeyboardButton(text="< Admin Suite", callback_data="adm_home", style="danger")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_test_aiverse")
async def test_aiverse_connection(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    await call.answer("Testing connection to AIVerseHub...", show_alert=False)
    res = await aiverse_client.get_me()
    if "error" in res:
        await call.answer(f"Connection Failed: {res['error']}", show_alert=True)
        return

    bal = res.get("wallet_balance", 0.0)
    first_name = res.get("first_name", "Supplier Account")
    await call.answer(f"Success! Connected to {first_name} | Balance: ${bal:.2f}", show_alert=True)


