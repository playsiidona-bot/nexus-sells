import html
import logging
from typing import Any
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.database.crud import (
    get_cart, update_cart_qty, clear_cart, checkout_cart_atomic, get_user_by_id, get_or_create_user
)
from bot.keyboards.inline import cart_keyboard, insufficient_balance_keyboard, deposit_methods_keyboard
from bot.services.i18n import t
from bot.config import BASE_CURRENCY, CURRENCY_SYMBOL, ORDERS_CHANNEL_ID, LOGS_CHANNEL_ID, get_channel_list

logger = logging.getLogger(__name__)
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


async def send_or_edit(event_message: Message, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """
    Safely deliver message whether event_message originated from a callback query or a customer text message.
    Automatically handles edit vs send, and falls back to plain text if HTML formatting causes an entity error.
    """
    try:
        if event_message.from_user and event_message.from_user.is_bot:
            await event_message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return
    except Exception:
        pass

    try:
        await event_message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await event_message.answer(text, reply_markup=reply_markup, parse_mode=None)
        except Exception as exc:
            logger.error(f"Failed to send response message: {exc}")


@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = "en"

    items = await get_cart(user_id)
    if not items:
        await call.answer(t("cart_empty", lang), show_alert=True)
        return

    # Check for products requiring customer input
    items_needing_input = [it for it in items if it.get("requires_input")]
    fsm_data = await state.get_data()
    customer_inputs = fsm_data.get("customer_inputs", {})

    pending_item = next(
        (it for it in items_needing_input if it["product_id"] not in customer_inputs and str(it["product_id"]) not in customer_inputs),
        None
    )
    if pending_item:
        await state.update_data(pending_prod_id=pending_item["product_id"])
        await state.set_state(CheckoutStates.waiting_customer_input)
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{html.escape(pending_item['name'])}</b>\n\n"
            f"Please send your <b>{html.escape(placeholder)}</b> in reply to this message:\n"
            f"<i>(Example: @myusername or your profile link / ID)</i>"
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
    user = await get_or_create_user(
        telegram_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name or "Customer"
    )

    input_val = (message.text or message.caption or "").strip()
    if not input_val:
        await message.answer("Please send the required information (such as your Telegram username, player ID, or link):")
        return

    data = await state.get_data()
    prod_id = data.get("pending_prod_id")
    customer_inputs = data.get("customer_inputs", {})
    if prod_id is not None:
        customer_inputs[prod_id] = input_val
        customer_inputs[str(prod_id)] = input_val
        try:
            customer_inputs[int(prod_id)] = input_val
        except (ValueError, TypeError):
            pass
    await state.update_data(customer_inputs=customer_inputs)

    items = await get_cart(user_id)
    if not items:
        await state.clear()
        await message.answer("Your cart is empty. Please choose products from the catalog.")
        return

    items_needing_input = [it for it in items if it.get("requires_input")]
    pending_item = next(
        (it for it in items_needing_input if it["product_id"] not in customer_inputs and str(it["product_id"]) not in customer_inputs),
        None
    )

    if pending_item:
        await state.update_data(pending_prod_id=pending_item["product_id"])
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{html.escape(pending_item['name'])}</b>\n\n"
            f"Please enter your <b>{html.escape(placeholder)}</b>:"
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
    lang = "en"

    try:
        success, msg, orders = await checkout_cart_atomic(user_id, customer_inputs=customer_inputs)
    except Exception as e:
        logger.error(f"Error during checkout execution: {e}", exc_info=True)
        await state.clear()
        err_msg = (
            "<b>ORDER PROCESSING NOTICE</b>\n"
            "────────────────────────\n"
            f"An error occurred while processing your order: {html.escape(str(e))}\n\n"
            "Please contact customer support."
        )
        await send_or_edit(event_message, err_msg)
        return

    await state.clear()

    if not success:
        if msg == "insufficient_balance":
            total = sum(x["total_price"] for x in items)
            user_fresh = await get_user_by_id(user_id)
            current_bal = user_fresh.balance if user_fresh else Decimal("0.00")
            err_text = t("insufficient_balance", lang, price=f"{CURRENCY_SYMBOL}{total:.2f}", balance=f"{CURRENCY_SYMBOL}{current_bal:.2f}", currency="")
            kb = insufficient_balance_keyboard(lang)
            await send_or_edit(event_message, err_text, reply_markup=kb)
        elif msg.startswith("out_of_stock"):
            prod_name = msg.replace("out_of_stock:", "").strip()
            err_text = (
                "<b>OUT OF STOCK</b>\n"
                "────────────────────────\n"
                f"Sorry, <b>{html.escape(prod_name)}</b> is currently out of stock.\n"
                "Please update your cart or choose another item."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Clear Cart", callback_data="cart_clear", style="danger")],
                [InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="primary")]
            ])
            await send_or_edit(event_message, err_text, reply_markup=kb)
        else:
            err_text = (
                "<b>ORDER NOTICE</b>\n"
                "────────────────────────\n"
                f"{html.escape(msg)}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="primary")]
            ])
            await send_or_edit(event_message, err_text, reply_markup=kb)
        return

    # Build clean delivery receipt - 100% white-labeled without supplier references
    order_details = []
    for o in orders:
        c_in = o.get("customer_input")
        escaped_cin = html.escape(str(c_in)) if c_in else ""
        input_line = f"• Provided Target: <code>{escaped_cin}</code>\n" if c_in else ""
        escaped_prod_name = html.escape(str(o['product_name']))
        escaped_payload = html.escape(str(o.get('delivered_data') or ''))
        order_details.append(
            f"<b>{escaped_prod_name}</b> (x{o['quantity']})\n"
            f"• Order Code: <code>{html.escape(str(o['order_code']))}</code>\n"
            f"• Price: <code>{CURRENCY_SYMBOL}{o['price']:.2f}</code>\n"
            f"{input_line}"
            f"• Delivered Details:\n<code>{escaped_payload}</code>\n"
        )

    receipt = t("checkout_success", lang, orders="\n".join(order_details))
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="< Back to Catalog", callback_data="catalog_home", style="primary")]
    ])
    await send_or_edit(event_message, receipt, reply_markup=back_kb)

    # Log to channel(s)
    order_targets = get_channel_list(ORDERS_CHANNEL_ID or LOGS_CHANNEL_ID)
    if order_targets:
        items_summary = []
        for o in orders:
            c_in = o.get("customer_input")
            c_tag = f" [Target: {html.escape(str(c_in))}]" if c_in else ""
            items_summary.append(f"  - {html.escape(str(o['product_name']))} (x{o['quantity']}) — {CURRENCY_SYMBOL}{o['price']:.2f}{c_tag}")

        log_msg = (
            "<b>NEW ORDER COMPLETED</b>\n"
            "────────────────────────\n"
            f"• Customer: <code>{user_id}</code>\n"
            "• Items:\n" + "\n".join(items_summary)
        )
        for ch in order_targets:
            try:
                await bot.send_message(ch, log_msg, parse_mode="HTML")
            except Exception:
                pass


@router.callback_query(F.data == "dep_from_cart")
async def handle_dep_from_cart(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = "en"
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
    lang = "en"
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
    pending_item = next(
        (it for it in items_needing_input if it["product_id"] not in customer_inputs and str(it["product_id"]) not in customer_inputs),
        None
    )

    if pending_item:
        await state.set_state(CheckoutStates.waiting_customer_input)
        await state.update_data(pending_prod_id=pending_item["product_id"])
        placeholder = pending_item.get("input_placeholder") or "@username"
        prompt = (
            "<b>REQUIRED CUSTOMER INFORMATION</b>\n"
            "────────────────────────\n"
            f"Product: <b>{html.escape(pending_item['name'])}</b>\n\n"
            f"Please enter your <b>{html.escape(placeholder)}</b>:"
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="< Cancel Checkout", callback_data="cart_cancel_checkout", style="danger")]
        ])
        await call.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
        await call.answer()
        return

    await execute_checkout(call.message, call.bot, user, items, customer_inputs, state)
    await call.answer("Purchase completed!", show_alert=False)


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_([
    "Products Catalog", "Shopping Cart", "Balance & Deposit", "Order History",
    "Affiliate Program", "Customer Support", "Admin Suite", "< Back", "English"
]))
async def unhandled_user_input_fallback(message: Message, state: FSMContext):
    """
    Forgiving handler: If a user sends a username, link, or text without explicitly
    being in FSM state, check if their cart has a product awaiting input and seamlessly process it.
    """
    current_state = await state.get_state()
    if current_state:
        return

    items = await get_cart(message.from_user.id)
    if not items:
        return

    items_needing_input = [it for it in items if it.get("requires_input")]
    if items_needing_input:
        first_item = items_needing_input[0]
        await state.set_state(CheckoutStates.waiting_customer_input)
        await state.update_data(pending_prod_id=first_item["product_id"])
        await process_checkout_customer_input(message, state)
