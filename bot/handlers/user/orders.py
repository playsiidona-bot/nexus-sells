from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database.crud import (
    get_user_orders, get_user_by_id, get_order_by_id, create_support_ticket
)
from bot.keyboards.inline import order_action_keyboard, admin_ticket_keyboard
from bot.config import ADMIN_IDS, OWNER_ID, LOGS_CHANNEL_ID

router = Router()


class ReportIssueStates(StatesGroup):
    waiting_issue_text = State()


@router.message(F.text.in_(["📦 የገዟቸው ዕቃዎች", "📦 My Orders"]))
async def view_orders(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "am"

    orders = await get_user_orders(message.from_user.id, limit=5)
    if not orders:
        text = "እስካሁን የገዙት ዕቃ የለም።" if lang == "am" else "You have no purchase history yet."
        await message.answer(text)
        return

    title = "📦 <b>የቅርብ ጊዜ ትዕዛዞችዎ (Recent Orders):</b>" if lang == "am" else "📦 <b>Your Recent Orders:</b>"
    await message.answer(title, parse_mode="HTML")

    for o in orders:
        order_text = (
            f"📦 <b>{o.product_name}</b> (x{o.quantity})\n"
            f"🆔 Order Code: <code>{o.order_code}</code>\n"
            f"💵 Price: <b>{o.total_price} {o.currency}</b>\n"
            f"{o.delivered_data or ''}"
        )
        kb = order_action_keyboard(o.id, lang)
        await message.answer(order_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("report_issue_"))
async def start_report_issue(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "am"
    order_id = int(call.data.split("_")[2])

    order = await get_order_by_id(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    await state.update_data(order_id=order.id, product_name=order.product_name)
    await state.set_state(ReportIssueStates.waiting_issue_text)

    prompt = (
        f"⚠️ <b>ስለ ትዕዛዝ #{order.order_code} ({order.product_name}) ያለብዎትን ችግር ይግለጹ፡</b>\n\n"
        "<i>ለምሳሌ፡ ቁልፉ አልሰራም፣ አካውንቱ ሎግ-ኢን አላለኝም፣ ወዘተ...</i>"
        if lang == "am" else
        f"⚠️ <b>Describe your issue for order #{order.order_code} ({order.product_name}):</b>\n\n"
        "<i>e.g. The license key is invalid, account is locked, etc...</i>"
    )
    await call.message.answer(prompt, parse_mode="HTML")
    await call.answer()


@router.message(ReportIssueStates.waiting_issue_text)
async def submit_issue_report(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "am"

    data = await state.get_data()
    order_id = data.get("order_id")
    product_name = data.get("product_name")
    issue_desc = (message.text or "").strip()

    if not issue_desc or not order_id:
        await message.answer("⚠️ እባክዎ ችግሩን በዝርዝር ይጻፉ።")
        return

    # Create ticket
    ticket = await create_support_ticket(
        user_id=user_id,
        order_id=order_id,
        product_name=product_name,
        issue_description=issue_desc
    )

    user_ack = (
        f"✅ <b>ቅሬታዎ ተመዝግቧል!</b>\n\n"
        f"🎫 የቲኬት ቁጥር (Ticket Code)፡ <code>{ticket.ticket_code}</code>\n"
        f"📦 ዕቃ፡ <b>{product_name}</b>\n\n"
        "የድጋፍ ሰጪ ቡድናችን ጉዳዩን ተመልክቶ ወዲያውኑ አዲስ ቁልፍ ይልክልዎታል ወይም ክፍያዎን ወደ ዋሌትዎ ይመልሳል!"
        if lang == "am" else
        f"✅ <b>Your issue has been reported!</b>\n\n"
        f"🎫 Ticket Code: <code>{ticket.ticket_code}</code>\n"
        f"📦 Product: <b>{product_name}</b>\n\n"
        "Our support team will review it shortly to issue a replacement key or refund your balance."
    )
    await message.answer(user_ack, parse_mode="HTML")
    await state.clear()

    # Send Admin Action Alert
    admin_alert = (
        f"🚨 <b>NEW SUPPORT TICKET / ISSUE REPORT</b>\n\n"
        f"🎫 Ticket: <code>{ticket.ticket_code}</code>\n"
        f"👤 User: <code>{user_id}</code> (@{message.from_user.username or 'N/A'})\n"
        f"📦 Product: <b>{product_name}</b> (Order ID: #{order_id})\n"
        f"📝 Problem: <i>{issue_desc}</i>\n\n"
        f"👇 Action:"
    )
    admin_kb = admin_ticket_keyboard(ticket.ticket_code)

    for admin_id in set(ADMIN_IDS + ([OWNER_ID] if OWNER_ID else [])):
        try:
            await message.bot.send_message(admin_id, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass

    if LOGS_CHANNEL_ID:
        try:
            await message.bot.send_message(LOGS_CHANNEL_ID, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass
