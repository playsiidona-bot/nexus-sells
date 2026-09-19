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
    REVIEWS_CHANNEL_ID, get_channel_list
)

router = Router()


class ReportIssueStates(StatesGroup):
    waiting_issue_text = State()


class ReviewStates(StatesGroup):
    waiting_review_comment = State()


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

    log_channels = get_channel_list(ORDERS_CHANNEL_ID or LOGS_CHANNEL_ID)
    for ch in log_channels:
        try:
            await message.bot.send_message(ch, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception:
            pass


# =====================================================================
# CUSTOMER REVIEW & RATING (POSTS TO REVIEW CHANNEL)
# =====================================================================

@router.callback_query(F.data.startswith("rate_order_"))
async def start_rate_order(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "am"
    order_id = int(call.data.split("_")[2])

    order = await get_order_by_id(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    text = (
        f"⭐ <b>ለዕቃው ደረጃ ይስጡ (Rate {order.product_name}):</b>\n\n"
        "ከ 1 እስከ 5 ኮከብ ይምረጡ፡"
        if lang == "am" else
        f"⭐ <b>Rate your order for {order.product_name}:</b>\n\n"
        "Select your rating from 1 to 5 stars:"
    )
    await call.message.answer(text, reply_markup=rating_stars_keyboard(order_id), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("star_"))
async def select_rating_stars(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "am"

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
        f"🌟 <b>{stars} ኮከብ መርጠዋል!</b>\n\n"
        "ስለ አግልግሎቱ ያለዎትን አስተያየት እዚህ ይጻፉ (ወይም ያለ አስተያየት ለማጠናቀቅ <b>'skip'</b> ይበሉ)፡"
        if lang == "am" else
        f"🌟 <b>You selected {stars} stars!</b>\n\n"
        "Please type your review comment (or send <b>'skip'</b> to finish):"
    )
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(ReviewStates.waiting_review_comment)
async def process_review_comment(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "am"

    data = await state.get_data()
    order_id = data.get("order_id")
    product_name = data.get("product_name")
    stars = data.get("stars", 5)

    comment_text = (message.text or "").strip()
    if comment_text.lower() in ("skip", "ዝለል", "-"):
        comment_text = "Verified Customer Purchase ✅"

    # Save to database
    # (using order_id as product_id placeholder or order lookup)
    order = await get_order_by_id(order_id)
    if order:
        await add_review(user_id, order.id, stars, comment_text)

    ack = "🙏 <b>እናመሰግናለን! አስተያየትዎ በተሳካ ሁኔታ ተመዝግቧል።</b>" if lang == "am" else "🙏 <b>Thank you! Your review has been published.</b>"
    await message.answer(ack, parse_mode="HTML")
    await state.clear()

    # BROADCAST TO REVIEW CHANNEL(S)!
    rev_channel_raw = await get_setting("reviews_channel_id", REVIEWS_CHANNEL_ID)
    rev_targets = get_channel_list(rev_channel_raw)
    if rev_targets:
        first_name = message.from_user.first_name or "Customer"
        star_emojis = "⭐" * stars
        review_card = (
            f"🌟 <b>NEW VERIFIED CUSTOMER REVIEW</b> 🌟\n\n"
            f"📦 <b>Product:</b> {product_name}\n"
            f"⭐ <b>Rating:</b> {star_emojis} ({stars}/5)\n"
            f"💬 <b>Feedback:</b> <i>\"{comment_text}\"</i>\n\n"
            f"👤 <b>Customer:</b> {first_name} (ID: <code>****{str(user_id)[-4:]}</code>)\n"
            f"✅ <i>Verified Purchase via Nexus Hub Bot</i>"
        )
        for target in rev_targets:
            try:
                await message.bot.send_message(target, review_card, parse_mode="HTML")
            except Exception:
                pass

