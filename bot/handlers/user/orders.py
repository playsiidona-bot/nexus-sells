from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database.crud import (
    get_user_orders, get_user_by_id, get_order_by_id, create_support_ticket,
    add_review, get_setting
)
from bot.keyboards.inline import order_action_keyboard, admin_ticket_keyboard, rating_stars_keyboard
from bot.config import (
    ADMIN_IDS, OWNER_ID, LOGS_CHANNEL_ID, ORDERS_CHANNEL_ID,
    REVIEWS_CHANNEL_ID, CURRENCY_SYMBOL, get_channel_list
)

router = Router()


class ReportIssueStates(StatesGroup):
    waiting_issue_text = State()


class ReviewStates(StatesGroup):
    waiting_review_comment = State()


@router.message(F.text.in_(["[ Order History ]", "Order History", "[ የገዟቸው ዕቃዎች ]", "📦 My Orders", "📦 የገዟቸው ዕቃዎች"]))
async def view_orders(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"

    orders = await get_user_orders(message.from_user.id, limit=5)
    if not orders:
        text = (
            "<b>ORDER HISTORY</b>\n"
            "────────────────────────\n"
            "You have no purchase history yet."
            if lang == "en" else
            "<b>የግዢ ታሪክ</b>\n"
            "────────────────────────\n"
            "እስካሁን የገዙት ዕቃ የለም።"
        )
        await message.answer(text, parse_mode="HTML")
        return

    title = (
        "<b>RECENT ORDERS</b>\n"
        "────────────────────────\n"
        "Your recent transactions and delivered keys:"
        if lang == "en" else
        "<b>የቅርብ ጊዜ ትዕዛዞችዎ</b>\n"
        "────────────────────────\n"
        "የገዟቸው ዕቃዎችና የቁልፍ መረጃዎች፡"
    )
    await message.answer(title, parse_mode="HTML")

    for o in orders:
        order_text = (
            f"<b>{o.product_name}</b> (x{o.quantity})\n"
            f"• Order Code: <code>{o.order_code}</code>\n"
            f"• Total Paid: <code>{CURRENCY_SYMBOL}{o.total_price:.2f}</code>\n"
            f"• Delivered Key / Data:\n<code>{o.delivered_data or 'Fulfilled'}</code>"
        )
        kb = order_action_keyboard(o.id, lang)
        await message.answer(order_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("report_issue_"))
async def start_report_issue(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    order_id = int(call.data.split("_")[2])

    order = await get_order_by_id(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    await state.update_data(order_id=order.id, product_name=order.product_name)
    await state.set_state(ReportIssueStates.waiting_issue_text)

    prompt = (
        f"<b>REPORT ISSUE: #{order.order_code} ({order.product_name})</b>\n"
        f"────────────────────────\n"
        f"Please describe the problem you encountered in detail:\n"
        f"<i>(e.g. key invalid, account locked, activation error)</i>"
        if lang == "en" else
        f"<b>ስለ ትዕዛዝ #{order.order_code} ({order.product_name}) ቅሬታ ማቅረቢያ</b>\n"
        f"────────────────────────\n"
        f"ያጋጠመዎትን ችግር በዝርዝር ይጻፉ፡\n"
        f"<i>(ለምሳሌ፡ ቁልፉ አልሰራም፣ አካውንቱ አልከፈተም ወዘተ)</i>"
    )
    await call.message.answer(prompt, parse_mode="HTML")
    await call.answer()


@router.message(ReportIssueStates.waiting_issue_text)
async def submit_issue_report(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    data = await state.get_data()
    order_id = data.get("order_id")
    product_name = data.get("product_name")
    issue_desc = (message.text or "").strip()

    if not issue_desc or not order_id:
        await message.answer("Please provide detailed description of the issue.")
        return

    ticket = await create_support_ticket(
        user_id=user_id,
        order_id=order_id,
        product_name=product_name,
        issue_description=issue_desc
    )

    user_ack = (
        f"<b>TICKET SUBMITTED SUCCESSFULLY</b>\n"
        f"────────────────────────\n"
        f"• Ticket Code: <code>{ticket.ticket_code}</code>\n"
        f"• Product: <b>{product_name}</b>\n\n"
        f"Support desk has received your ticket. A replacement key or refund will be processed promptly."
        if lang == "en" else
        f"<b>ቅሬታዎ በተሳካ ሁኔታ ተመዝግቧል</b>\n"
        f"────────────────────────\n"
        f"• የቲኬት ቁጥር፡ <code>{ticket.ticket_code}</code>\n"
        f"• ዕቃ፡ <b>{product_name}</b>\n\n"
        f"የድጋፍ ሰጪ ቡድናችን ጉዳዩን ተመልክቶ አዲስ ቁልፍ ወይም ተመላሽ ሒሳብ ይሰጥዎታል!"
    )
    await message.answer(user_ack, parse_mode="HTML")
    await state.clear()

    admin_alert = (
        f"<b>SUPPORT TICKET: ISSUE REPORTED</b>\n"
        f"────────────────────────\n"
        f"• Ticket: <code>{ticket.ticket_code}</code>\n"
        f"• User: <code>{user_id}</code> (@{message.from_user.username or 'N/A'})\n"
        f"• Product: <b>{product_name}</b> (Order ID: #{order_id})\n"
        f"• Problem:\n<blockquote>{issue_desc}</blockquote>\n"
        f"Select resolution action below:"
    )
    admin_kb = admin_ticket_keyboard(ticket.ticket_code)

    for admin_id in set(ADMIN_IDS + ([OWNER_ID] if OWNER_ID else [])):
        try:
            await message.bot.send_message(admin_id, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass

    log_channels = get_channel_list(ORDERS_CHANNEL_ID or LOGS_CHANNEL_ID)
    for ch in log_channels:
        try:
            await message.bot.send_message(ch, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("rate_order_"))
async def start_rate_order(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    order_id = int(call.data.split("_")[2])

    order = await get_order_by_id(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    text = (
        f"<b>RATE YOUR PURCHASE: {order.product_name}</b>\n"
        f"────────────────────────\n"
        f"Select your rating score:"
        if lang == "en" else
        f"<b>ለዕቃው ደረጃ ይስጡ፡ {order.product_name}</b>\n"
        f"────────────────────────\n"
        f"ደረጃዎን ከታች ይምረጡ፡"
    )
    await call.message.edit_text(text, reply_markup=rating_stars_keyboard(order_id), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("star_"))
async def select_rating_stars(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    parts = call.data.split("_")
    order_id = int(parts[1])
    stars = int(parts[2])

    order = await get_order_by_id(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    await state.update_data(
        order_id=order.id,
        product_name=order.product_name,
        stars=stars
    )
    await state.set_state(ReviewStates.waiting_review_comment)

    prompt = (
        f"<b>Rating Selected: [{stars}/5]</b>\n"
        f"────────────────────────\n"
        f"Please type your review comment (or send <b>'skip'</b> to complete):"
        if lang == "en" else
        f"<b>የመረጡት ደረጃ፡ [{stars}/5]</b>\n"
        f"────────────────────────\n"
        f"አስተያየትዎን ይጻፉ (ወይም ያለ አስተያየት ለማጠናቀቅ <b>'skip'</b> ይበሉ)፡"
    )
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(ReviewStates.waiting_review_comment)
async def process_review_comment(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    data = await state.get_data()
    order_id = data.get("order_id")
    product_name = data.get("product_name")
    stars = data.get("stars", 5)

    comment_text = (message.text or "").strip()
    if comment_text.lower() in ("skip", "ዝለል", "-"):
        comment_text = "Verified Customer Purchase"

    order = await get_order_by_id(order_id)
    if order:
        await add_review(user_id, order.id, stars, comment_text)

    ack = (
        "<b>THANK YOU!</b>\n"
        "────────────────────────\n"
        "Your review has been verified and published."
        if lang == "en" else
        "<b>እናመሰግናለን!</b>\n"
        "────────────────────────\n"
        "አስተያየትዎ በተሳካ ሁኔታ ተመዝግቧል።"
    )
    await message.answer(ack, parse_mode="HTML")
    await state.clear()

    rev_channel_raw = await get_setting("reviews_channel_id", REVIEWS_CHANNEL_ID)
    rev_targets = get_channel_list(rev_channel_raw)
    if rev_targets:
        first_name = message.from_user.first_name or "Customer"
        review_card = (
            f"<b>VERIFIED CUSTOMER REVIEW</b>\n"
            f"────────────────────────\n"
            f"• Product: <b>{product_name}</b>\n"
            f"• Rating: <b>[{stars}/5]</b>\n"
            f"• Feedback: <i>\"{comment_text}\"</i>\n"
            f"• Customer: {first_name} (ID: <code>****{str(user_id)[-4:]}</code>)\n"
            f"• Status: Verified Purchase"
        )
        for target in rev_targets:
            try:
                await message.bot.send_message(target, review_card, parse_mode="HTML")
            except Exception:
                pass
