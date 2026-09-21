from typing import Any
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.crud import (
    get_cart, update_cart_qty, clear_cart, checkout_cart_atomic, get_user_by_id
)
from bot.keyboards.inline import cart_keyboard, insufficient_balance_keyboard, deposit_methods_keyboard
from bot.services.i18n import t
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL, ORDERS_CHANNEL_ID, LOGS_CHANNEL_ID, get_channel_list

router = Router()


async def render_cart_view(user_id: int) -> tuple[str, Any]:
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    items = await get_cart(user_id)
    if not items:
        return t("cart_empty", lang), cart_keyboard([], lang)

    items_text = []
    total = Decimal("0.00")
    for i, it in enumerate(items, 1):
        items_text.append(f"{i}. <b>{it['name']}</b> x{it['quantity']} — <code>{CURRENCY_SYMBOL}{it['total_price']:.2f}</code>")
        total += it["total_price"]

    body = "\n".join(items_text)
    text = t("cart_title", lang, items=body, total=f"{CURRENCY_SYMBOL}{total:.2f}", currency="")
    kb = cart_keyboard(items, lang)
    return text, kb


@router.message(Command("cart"))
@router.message(Command("ዘንቢል"))
@router.message(F.text.in_(["Shopping Cart", "የግዢ ዘንቢል", "[ Shopping Cart ]", "[ የግዢ ዘንቢል ]", "🛒 My Cart", "🛒 የእኔ ዘንቢል (Cart)"]))
async def view_cart_message(message: Message):
    text, kb = await render_cart_view(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_cart")
async def refresh_cart_cb(call: CallbackQuery):
    text, kb = await render_cart_view(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    await call.answer("Cart updated" if lang == "en" else "ዘንቢል ታድሷል")


@router.callback_query(F.data.startswith("cart_inc_"))
async def cart_inc(call: CallbackQuery):
    cid = int(call.data.split("_")[2])
    items = await get_cart(call.from_user.id)
    item = next((x for x in items if x["cart_id"] == cid), None)
    if item:
        await update_cart_qty(cid, item["quantity"] + 1)

    text, kb = await render_cart_view(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("cart_dec_"))
async def cart_dec(call: CallbackQuery):
    cid = int(call.data.split("_")[2])
    items = await get_cart(call.from_user.id)
    item = next((x for x in items if x["cart_id"] == cid), None)
    if item and item["quantity"] > 1:
        await update_cart_qty(cid, item["quantity"] - 1)
    elif item:
        await update_cart_qty(cid, 0)

    text, kb = await render_cart_view(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("cart_del_"))
async def cart_del(call: CallbackQuery):
    cid = int(call.data.split("_")[2])
    await update_cart_qty(cid, 0)
    text, kb = await render_cart_view(call.from_user.id)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "cart_clear")
async def cart_clear_all(call: CallbackQuery):
    await clear_cart(call.from_user.id)
    text, kb = await render_cart_view(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class CheckoutStates(StatesGroup):
    waiting_customer_input = State()


@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    items = await get_cart(user_id)
    if not items:
        await call.answer(t("cart_empty", lang), show_alert=True)
        return

    # Check for products requiring customer input
    items_needing_input = [it for it in items if it.get("requires_input")]
    fsm_data = await state.get_data()
    customer_inputs = fsm_data.get("customer_inputs", {})

    pending_item = next((it for it in items_needing_input if it["product_id"] not in customer_inputs), None)
    if pending_item:
        await state.update_data(pending_prod_id=pending_item["product_id"])
        await state.set_state(CheckoutStates.waiting_customer_input)
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{pending_item['name']}</b>\n\n"
            f"Please send your <b>{placeholder}</b> in reply to this message:\n"
            f"<i>(Example: @myusername or your player ID)</i>"
            if lang == "en" else
            "<b>ግዴታ የሚያስፈልግ መረጃ</b>\n"
            "────────────────────────\n"
            f"ዕቃ፡ <b>{pending_item['name']}</b>\n\n"
            f"እባክዎ ለዚህ ዕቃ የሚያስፈልገውን <b>{placeholder}</b> ይላኩ:\n"
            f"<i>(ለምሳሌ፡ @username ወይም የሂሳብ መለያ)</i>"
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="< Cancel Checkout", callback_data="cart_cancel_checkout", style="danger")]
        ])
        await call.message.answer(prompt, reply_markup=cancel_kb, parse_mode="HTML")
        await call.answer()
        return

    # All required inputs collected! Execute atomic purchase!
    await execute_checkout(call.message, call.bot, user, items, customer_inputs, state)
    await call.answer()


@router.message(CheckoutStates.waiting_customer_input)
async def process_checkout_customer_input(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    input_val = message.text.strip()
    if not input_val:
        await message.answer("Please enter the required information to continue:")
        return

    data = await state.get_data()
    prod_id = data.get("pending_prod_id")
    customer_inputs = data.get("customer_inputs", {})
    if prod_id:
        customer_inputs[prod_id] = input_val
    await state.update_data(customer_inputs=customer_inputs)

    items = await get_cart(user_id)
    items_needing_input = [it for it in items if it.get("requires_input")]
    pending_item = next((it for it in items_needing_input if it["product_id"] not in customer_inputs), None)

    if pending_item:
        await state.update_data(pending_prod_id=pending_item["product_id"])
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{pending_item['name']}</b>\n\n"
            f"Please enter your <b>{placeholder}</b>:"
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="< Cancel Checkout", callback_data="cart_cancel_checkout", style="danger")]
        ])
        await message.answer(prompt, reply_markup=cancel_kb, parse_mode="HTML")
        return

    # All collected! Execute atomic purchase
    await execute_checkout(message, message.bot, user, items, customer_inputs, state)


@router.callback_query(F.data == "cart_cancel_checkout")
async def cancel_checkout_flow(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await render_cart_view(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer("Checkout cancelled.")


async def execute_checkout(event_message: Message, bot, user, items: list, customer_inputs: dict, state: FSMContext):
    user_id = user.telegram_id
    lang = user.language or "en"

    success, msg, orders = await checkout_cart_atomic(user_id, customer_inputs=customer_inputs)
    await state.clear()

    if not success:
        if msg == "insufficient_balance":
            total = sum(x["total_price"] for x in items)
            user_fresh = await get_user_by_id(user_id)
            current_bal = user_fresh.balance if user_fresh else Decimal("0.00")
            err_text = t("insufficient_balance", lang, price=f"{CURRENCY_SYMBOL}{total:.2f}", balance=f"{CURRENCY_SYMBOL}{current_bal:.2f}", currency="")
            kb = insufficient_balance_keyboard(lang)
            try:
                await event_message.edit_text(err_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event_message.answer(err_text, reply_markup=kb, parse_mode="HTML")
        elif msg.startswith("out_of_stock"):
            prod_name = msg.replace("out_of_stock:", "").strip()
            err_text = (
                f"<b>ክምችት አልቋል (Out of Stock)</b>\n"
                f"────────────────────────\n"
                f"ይቅርታ፣ <b>{prod_name}</b> በአሁኑ ሰዓት በቂ ክምችት የለውም።\n"
                f"እባክዎ ዘንቢልዎን ያፅዱ ወይም ሌላ ዕቃ ይምረጡ።"
                if lang == "am" else
                f"<b>OUT OF STOCK</b>\n"
                f"────────────────────────\n"
                f"Sorry, <b>{prod_name}</b> is currently out of stock.\n"
                f"Please update your cart or choose another item."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="ዘንቢል አፅዳ" if lang == "am" else "Clear Cart", callback_data="cart_clear", style="danger")],
                [InlineKeyboardButton(text="< ወደ ካታሎግ" if lang == "am" else "< Back to Catalog", callback_data="catalog_home", style="primary")]
            ])
            try:
                await event_message.edit_text(err_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event_message.answer(err_text, reply_markup=kb, parse_mode="HTML")
        else:
            err_text = (
                f"<b>ትዕዛዙን ማጠናቀቅ አልተቻለም</b>\n"
                f"────────────────────────\n"
                f"{msg}"
                if lang == "am" else
                f"<b>Notice:</b> {msg}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="< ወደ ካታሎግ" if lang == "am" else "< Back to Catalog", callback_data="catalog_home", style="primary")]
            ])
            try:
                await event_message.edit_text(err_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await event_message.answer(err_text, reply_markup=kb, parse_mode="HTML")
        return

    # Build clean delivery receipt - 100% white-labeled without supplier references
    order_details = []
    for o in orders:
        c_in = o.get("customer_input")
        input_line = f"• Provided Target: <code>{c_in}</code>\n" if c_in else ""
        order_details.append(
            f"<b>{o['product_name']}</b> (x{o['quantity']})\n"
            f"• Order Code: <code>{o['order_code']}</code>\n"
            f"• Price: <code>{CURRENCY_SYMBOL}{o['price']:.2f}</code>\n"
            f"{input_line}"
            f"• Delivered Details:\n<code>{o['delivered_data']}</code>\n"
        )

    receipt = t("checkout_success", lang, orders="\n".join(order_details))
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="< ወደ ካታሎግ" if lang == "am" else "< Back to Catalog", callback_data="catalog_home", style="primary")]
    ])
    try:
        await event_message.edit_text(receipt, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        await event_message.answer(receipt, reply_markup=back_kb, parse_mode="HTML")

    # Log to channel(s)
    order_targets = get_channel_list(ORDERS_CHANNEL_ID or LOGS_CHANNEL_ID)
    if order_targets:
        items_summary = []
        for o in orders:
            c_in = o.get("customer_input")
            c_tag = f" [Target: {c_in}]" if c_in else ""
            items_summary.append(f"  - {o['product_name']} (x{o['quantity']}) — {CURRENCY_SYMBOL}{o['price']:.2f}{c_tag}")

        log_msg = (
            f"<b>NEW ORDER COMPLETED</b>\n"
            f"────────────────────────\n"
            f"• Customer: <code>{user_id}</code>\n"
            f"• Items:\n" + "\n".join(items_summary)
        )
        for ch in order_targets:
            try:
                await bot.send_message(ch, log_msg, parse_mode="HTML")
            except Exception:
                pass


@router.callback_query(F.data == "dep_from_cart")
async def handle_dep_from_cart(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    balance = user.balance if user else Decimal("0.00")
    text = t("wallet_title", lang, balance=balance, currency=BASE_CURRENCY, user_id=call.from_user.id)
    kb = deposit_methods_keyboard(lang=lang)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "cart_retry_checkout")
async def handle_retry_checkout(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    items = await get_cart(call.from_user.id)

    if not items:
        await call.answer("Cart is empty", show_alert=True)
        text, kb = await render_cart_view(call.from_user.id)
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        return

    total = sum(x["total_price"] for x in items)
    user_bal = user.balance if user else Decimal("0.00")

    if user_bal < total:
        err_text = t("insufficient_balance", lang, price=f"{CURRENCY_SYMBOL}{total:.2f}", balance=f"{CURRENCY_SYMBOL}{user_bal:.2f}", currency="")
        kb = insufficient_balance_keyboard(lang)
        try:
            await call.message.edit_text(err_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await call.answer(
            f"Balance checked: {CURRENCY_SYMBOL}{user_bal:.2f} — still needed {CURRENCY_SYMBOL}{(total - user_bal):.2f}",
            show_alert=True
        )
        return

    data = await state.get_data()
    customer_inputs = data.get("customer_inputs", {})
    items_needing_input = [it for it in items if it.get("requires_input")]
    pending_item = next((it for it in items_needing_input if it["product_id"] not in customer_inputs), None)

    if pending_item:
        await state.set_state(CheckoutStates.waiting_customer_input)
        await state.update_data(pending_prod_id=pending_item["product_id"])
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{pending_item['name']}</b>\n\n"
            f"Please enter your <b>{placeholder}</b>:"
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="< Cancel Checkout", callback_data="cart_cancel_checkout", style="danger")]
        ])
        await call.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
        await call.answer()
        return

    await execute_checkout(call.message, call.bot, user, items, customer_inputs, state)
    await call.answer("Purchase completed!", show_alert=False)
