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
    get_product_by_id, get_setting, set_setting
)
from bot.keyboards.inline import admin_main_keyboard, admin_settings_keyboard
from bot.config import (
    ADMIN_IDS, OWNER_ID, BASE_CURRENCY, TELEBIRR_RECEIVER_PHONE,
    TELEBIRR_RECEIVER_NAME, CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME,
    FORCE_JOIN_CHANNEL, REVIEWS_CHANNEL_ID
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


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == OWNER_ID


@router.message(F.text.in_(["[ Admin Suite ]", "Admin Suite", "[ የአስተዳዳሪ ክፍል ]", "⚙️ አስተዳዳሪ (Admin)", "⚙️ Admin Suite"]))
@router.message(Command("admin"))
async def open_admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    text = (
        "⚙️ <b>Nexus Hub Admin Suite</b>\n\n"
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
        "📊 <b>Nexus Hub Real-Time Analytics:</b>\n\n"
        f"👥 የተመዘገቡ ተጠቃሚዎች፡ <b>{users_count}</b>\n"
        f"📦 ጠቅላላ የተሸጡ ትዕዛዞች፡ <b>{orders_count}</b>\n"
        f"💰 ጠቅላላ የሽያጭ ገቢ፡ <b>{revenue} {BASE_CURRENCY}</b>\n"
        f"🛍️ ንቁ ዕቃዎች (Products)፡ <b>{products_count}</b>\n"
        f"🔑 የሚገኙ የቁልፎች ክምችት (Stock Keys)፡ <b>{active_stock}</b>"
    )
    await call.message.edit_text(stats_text, reply_markup=admin_main_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "adm_add_cat")
async def start_add_category(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.answer("📝 እባክዎ የአዲሱን ምድብ (Category) ስም እና Icon ያስገቡ:\n<i>ለምሳሌ፡ 🎮 Gaming Accounts</i>", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_cat_name)
    await call.answer()


@router.message(AdminStates.waiting_cat_name)
async def process_cat_name(message: Message, state: FSMContext):
    cat_name = message.text.strip()
    if cat_name:
        await create_category(name=cat_name)
        await message.answer(f"✅ ምድብ <b>{cat_name}</b> በተሳካ ሁኔታ ተፈጥሯል!", parse_mode="HTML")
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

