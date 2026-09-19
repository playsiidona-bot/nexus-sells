from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.database.crud import (
    get_user_by_id, add_user_balance, check_transaction_exists,
    save_payment_receipt
)
from bot.keyboards.inline import deposit_methods_keyboard
from bot.services.i18n import t
from bot.services.verifier import verify_receipt_url
from bot.config import (
    BASE_CURRENCY, TELEBIRR_RECEIVER_PHONE, TELEBIRR_RECEIVER_NAME,
    CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME, MIN_DEPOSIT_AMOUNT,
    REFERRAL_PERCENT, LOGS_CHANNEL_ID
)

router = Router()


class DepositStates(StatesGroup):
    waiting_receipt = State()


@router.message(F.text.in_(["💳 ዋሌት / ሒሳብ", "💳 Wallet / Balance"]))
async def view_wallet(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "am"
    balance = user.balance if user else Decimal("0.00")

    text = t("wallet_title", lang, balance=balance, currency=BASE_CURRENCY, user_id=message.from_user.id)
    kb = deposit_methods_keyboard(lang)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "dep_telebirr")
async def dep_telebirr(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "am"

    text = t("telebirr_instructions", lang,
             phone=TELEBIRR_RECEIVER_PHONE,
             name=TELEBIRR_RECEIVER_NAME,
             min=MIN_DEPOSIT_AMOUNT)

    await state.set_state(DepositStates.waiting_receipt)
    await state.update_data(provider="telebirr")
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "dep_cbe")
async def dep_cbe(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "am"

    text = t("cbe_instructions", lang,
             account=CBE_ACCOUNT_NUMBER,
             name=CBE_ACCOUNT_NAME,
             min=MIN_DEPOSIT_AMOUNT)

    await state.set_state(DepositStates.waiting_receipt)
    await state.update_data(provider="cbe")
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_receipt)
async def process_receipt_submission(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "am"

    raw_text = (message.text or "").strip()
    if not raw_text.startswith("http"):
        # If user sent just text/transaction code
        await message.answer("⚠️ እባክዎ ሙሉውን የደረሰኝ ሊንክ (URL) ይላኩ።\nPlease send the full receipt URL.")
        return

    # Send verification indicator
    status_msg = await message.answer(t("verifying_receipt", lang))

    # Verify with server
    res = await verify_receipt_url(raw_text)

    if not res.get("valid"):
        err = res.get("message", "Invalid Receipt")
        await status_msg.edit_text(t("receipt_failed", lang, reason=err), parse_mode="HTML")
        await state.clear()
        return

    txn_id = res.get("txn_id")
    amount = Decimal(str(res.get("amount", 0.0)))
    provider = res.get("provider", "bank")

    # Check duplicate
    if await check_transaction_exists(txn_id):
        await status_msg.edit_text(t("receipt_duplicate", lang), parse_mode="HTML")
        await state.clear()
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)):
        await status_msg.edit_text(f"❌ የተላከው መጠን ከተፈቀደው ዝቅተኛ መጠን ({MIN_DEPOSIT_AMOUNT} {BASE_CURRENCY}) ያነሰ ነው።")
        await state.clear()
        return

    # Add balance atomically
    ok, new_balance = await add_user_balance(user_id, amount)
    if not ok:
        await status_msg.edit_text("❌ ዳታቤዝ ስህተት አጋጥሟል፤ እባክዎ ደንበኞች አገልግሎትን ያነጋግሩ።")
        await state.clear()
        return

    # Record receipt
    await save_payment_receipt(
        user_id=user_id,
        provider=provider,
        transaction_id=txn_id,
        amount=amount,
        sender_name=res.get("recipientName", ""),
        raw_details=str(res)
    )

    # Referral bonus
    if user and user.referrer_id and REFERRAL_PERCENT > 0:
        bonus = (amount * Decimal(str(REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
        if bonus > 0:
            await add_user_balance(user.referrer_id, bonus)
            try:
                await message.bot.send_message(
                    user.referrer_id,
                    f"🎁 <b>የግብዣ ቦነስ (Referral Bonus)!</b>\n\nየጋበዙት ተጠቃሚ ሒሳብ ስለሞላ <b>+{bonus} {BASE_CURRENCY}</b> ወደ ዋሌትዎ ገብቷል!",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # Success notification
    await status_msg.edit_text(
        t("receipt_success", lang, amount=amount, currency=BASE_CURRENCY, txn_id=txn_id, new_balance=new_balance),
        parse_mode="HTML"
    )
    await state.clear()

    # Log to channel if configured
    if LOGS_CHANNEL_ID:
        try:
            await message.bot.send_message(
                LOGS_CHANNEL_ID,
                f"💳 <b>New Deposit Verified!</b>\n\n"
                f"👤 User: <code>{user_id}</code> (@{message.from_user.username or 'N/A'})\n"
                f"💵 Amount: <b>{amount} {BASE_CURRENCY}</b>\n"
                f"🏦 Provider: {provider.upper()}\n"
                f"🆔 Txn ID: <code>{txn_id}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass
