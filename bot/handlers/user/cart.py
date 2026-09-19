from typing import Any
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.database.crud import (
    get_cart, update_cart_qty, clear_cart, checkout_cart_atomic, get_user_by_id
)
from bot.keyboards.inline import cart_keyboard
from bot.services.i18n import t
from bot.config import BASE_CURRENCY, ORDERS_CHANNEL_ID, LOGS_CHANNEL_ID, get_channel_list

router = Router()


async def render_cart_view(user_id: int) -> tuple[str, Any]:
    user = await get_user_by_id(user_id)
    lang = user.language if user else "am"

    items = await get_cart(user_id)
    if not items:
        return t("cart_empty", lang), cart_keyboard([], lang)

    items_text = []
    total = Decimal("0.00")
    for i, it in enumerate(items, 1):
        items_text.append(f"{i}. <b>{it['name']}</b> x{it['quantity']} — <code>{it['total_price']} {BASE_CURRENCY}</code>")
        total += it["total_price"]

    body = "\n".join(items_text)
    text = t("cart_title", lang, items=body, total=total, currency=BASE_CURRENCY)
    kb = cart_keyboard(items, lang)
    return text, kb


@router.message(F.text.in_(["🛒 የእኔ ዘንቢል (Cart)", "🛒 My Cart"]))
async def view_cart_message(message: Message):
    text, kb = await render_cart_view(message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


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


@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "am"

    success, msg, orders = await checkout_cart_atomic(user_id)

    if not success:
        if msg == "insufficient_balance":
            cart_items = await get_cart(user_id)
            total = sum(x["total_price"] for x in cart_items)
            err_text = t("insufficient_balance", lang, price=total, balance=user.balance, currency=BASE_CURRENCY)
            await call.answer(err_text, show_alert=True)
        elif "out_of_stock" in msg:
            await call.answer(f"⚠️ {msg}", show_alert=True)
        else:
            await call.answer(f"❌ Error: {msg}", show_alert=True)
        return

    # Build delivery receipt
    order_details = []
    for o in orders:
        order_details.append(
            f"📦 <b>{o['product_name']}</b> (x{o['quantity']})\n"
            f"🆔 Order Code: <code>{o['order_code']}</code>\n"
            f"💵 Price: <code>{o['price']} {BASE_CURRENCY}</code>\n"
            f"{o['delivered_data']}\n"
        )

    receipt = t("checkout_success", lang, orders="\n".join(order_details))
    await call.message.edit_text(receipt, parse_mode="HTML")
    await call.answer("🎉 Order Completed!", show_alert=False)

    # Log to channel(s)
    order_targets = get_channel_list(ORDERS_CHANNEL_ID or LOGS_CHANNEL_ID)
    if order_targets:
        log_msg = (
            f"🛒 <b>NEW ORDER COMPLETED</b>\n\n"
            f"👤 Customer: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
            f"📦 Items:\n" + "\n".join([f" • {o['product_name']} (x{o['quantity']}) - {o['price']} {BASE_CURRENCY}" for o in orders])
        )
        for ch in order_targets:
            try:
                await call.bot.send_message(ch, log_msg, parse_mode="HTML")
            except Exception:
                pass
