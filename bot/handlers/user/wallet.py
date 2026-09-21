import json
import logging
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.crud import (
    get_user_by_id, add_user_balance, check_transaction_exists,
    save_payment_receipt, get_setting
)
from bot.keyboards.inline import deposit_methods_keyboard, crypto_invoice_keyboard
from bot.services.i18n import t
from bot.services.verifier import verify_receipt_url
from bot.services.cryptopay import CryptoPayClient, CryptoPayAPIError
from bot.config import (
    BASE_CURRENCY, CURRENCY_SYMBOL, CRYPTO_PAY_TOKEN, STARS_RATE_USD,
    TELEBIRR_RECEIVER_PHONE, TELEBIRR_RECEIVER_NAME,
    CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME, MIN_DEPOSIT_AMOUNT, MAX_DEPOSIT_AMOUNT,
    REFERRAL_PERCENT, LOGS_CHANNEL_ID, PAYMENTS_CHANNEL_ID, get_channel_list
)

logger = logging.getLogger(__name__)
router = Router()


class DepositStates(StatesGroup):
    waiting_crypto_amount = State()
    waiting_stars_amount = State()
    waiting_receipt = State()


@router.message(F.text.in_(["💳 ዋሌት / ሒሳብ", "💳 Wallet / Balance", "💳 Balance / Top-Up"]))
async def view_wallet(message: Message):
    user = await get_user_by_id(message.from_user.id)
    lang = user.language if user else "en"
    balance = user.balance if user else Decimal("0.00")

    show_local = bool(TELEBIRR_RECEIVER_PHONE or CBE_ACCOUNT_NUMBER)
    text = t("wallet_title", lang, balance=balance, currency=BASE_CURRENCY, user_id=message.from_user.id)
    kb = deposit_methods_keyboard(lang=lang, show_local=show_local)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# =====================================================================
# 1. CRYPTOBOT (@CryptoBot / CryptoPay) INTEGRATION
# =====================================================================

@router.callback_query(F.data == "dep_crypto")
async def start_crypto_deposit(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prompt = (
        f"💎 <b>Deposit with Cryptocurrency (@CryptoBot)</b>\n\n"
        f"We accept <b>USDT, TON, BTC, LTC, ETH, TRX</b> and more with instant automated confirmation.\n\n"
        f"Enter the amount in <b>{BASE_CURRENCY}</b> to deposit:\n"
        f"• Minimum: <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b>\n"
        f"• Maximum: <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>\n\n"
        f"<i>Reply with the amount (e.g., <code>10</code> or <code>25.50</code>):</i>"
    ) if lang == "en" else (
        f"💎 <b>በክሪፕቶ ከረንሲ ይክፈሉ (@CryptoBot)</b>\n\n"
        f"በ <b>USDT, TON, BTC, LTC, ETH, TRX</b> ወዲያውኑ ሒሳብዎን መሙላት ይችላሉ።\n\n"
        f"መሙላት የሚፈልጉትን መጠን በ <b>{BASE_CURRENCY}</b> ያስገቡ፡\n"
        f"• ዝቅተኛ፡ <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b>\n"
        f"• ከፍተኛ፡ <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>\n\n"
        f"<i>ምሳሌ፡ <code>10</code> ወይም <code>25.50</code> ብለው ይላኩ፡</i>"
    )

    await state.set_state(DepositStates.waiting_crypto_amount)
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_crypto_amount)
async def process_crypto_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    raw_text = (message.text or "").strip().replace("$", "")
    try:
        amount = Decimal(raw_text)
    except Exception:
        await message.answer("⚠️ Please enter a valid numerical amount (e.g. <code>10</code> or <code>25.00</code>):")
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)) or amount > Decimal(str(MAX_DEPOSIT_AMOUNT)):
        await message.answer(
            f"⚠️ Amount must be between <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b> and <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>.",
            parse_mode="HTML"
        )
        return

    if not CRYPTO_PAY_TOKEN:
        await message.answer(
            "⚠️ <b>Crypto payments are temporarily in maintenance.</b>\nPlease contact support or choose another payment method.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    client = CryptoPayClient(CRYPTO_PAY_TOKEN)
    try:
        invoice = await client.create_invoice(
            amount=float(amount),
            fiat_currency=BASE_CURRENCY if BASE_CURRENCY in ["USD", "EUR", "RUB"] else "USD",
            description=f"Nexus Store Top-up for user {user_id}",
            payload=f"topup:{user_id}:{amount}",
            expires_in=1800
        )
    except CryptoPayAPIError as e:
        logger.error(f"CryptoPay API Error: {e}")
        await message.answer(f"❌ Failed to generate invoice: {e.message}. Please try again later.")
        await state.clear()
        return
    finally:
        await client.close()

    invoice_id = invoice.get("invoice_id")
    bot_invoice_url = invoice.get("bot_invoice_url") or invoice.get("mini_app_invoice_url") or invoice.get("pay_url")

    card_text = (
        f"💎 <b>Crypto Invoice Generated</b>\n\n"
        f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"🆔 Invoice ID: <code>#{invoice_id}</code>\n"
        f"⏳ Valid for: <b>30 Minutes</b>\n\n"
        f"1. Click the button below to pay via <b>@CryptoBot</b> with USDT, TON, BTC, or LTC.\n"
        f"2. After payment completes, return here and click <b>Check Payment</b>."
    ) if lang == "en" else (
        f"💎 <b>የክሪፕቶ ደረሰኝ ተዘጋጅቷል</b>\n\n"
        f"💵 መጠን፡ <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"🆔 የደረሰኝ ቁጥር፡ <code>#{invoice_id}</code>\n"
        f"⏳ የሚቆይበት ጊዜ፡ <b>30 ደቂቃ</b>\n\n"
        f"1. ከታች ባለው ማስፈንጠሪያ @CryptoBot ላይ ክፍያዎን በ USDT, TON ወይም BTC ይፈጽሙ።\n"
        f"2. ክፍያውን እንደጨረሱ <b>Check Payment</b> የሚለውን ይጫኑ።"
    )

    kb = crypto_invoice_keyboard(bot_invoice_url, invoice_id, lang)
    await message.answer(card_text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_status(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    invoice_id = int(call.data.split("_")[2])
    txn_ref = f"crypto_{invoice_id}"

    # Already redeemed?
    if await check_transaction_exists(txn_ref):
        await call.answer("✅ This invoice has already been credited to your balance!", show_alert=True)
        return

    client = CryptoPayClient(CRYPTO_PAY_TOKEN)
    try:
        invoice = await client.get_invoice(invoice_id)
    except Exception as e:
        await call.answer("⚠️ Could not reach CryptoBot API. Please try again in a moment.", show_alert=True)
        return
    finally:
        await client.close()

    if not invoice:
        await call.answer("❌ Invoice not found or expired.", show_alert=True)
        return

    status = invoice.get("status")
    if status == "paid":
        amount_paid = Decimal(str(invoice.get("amount", "0.00")))
        # Atomic balance credit
        ok, new_balance = await add_user_balance(user_id, amount_paid)
        if not ok:
            await call.answer("❌ Database error crediting balance. Please contact support.", show_alert=True)
            return

        # Record receipt
        await save_payment_receipt(
            user_id=user_id,
            provider="cryptopay",
            transaction_id=txn_ref,
            amount=amount_paid,
            sender_name=f"CryptoBot #{invoice_id}",
            raw_details=json.dumps(invoice)
        )

        # Referral bonus
        if user and user.referrer_id and REFERRAL_PERCENT > 0:
            bonus = (amount_paid * Decimal(str(REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
            if bonus > 0:
                await add_user_balance(user.referrer_id, bonus)
                try:
                    await call.bot.send_message(
                        user.referrer_id,
                        f"🎁 <b>Referral Commission Earned!</b>\n\nA user you referred made a deposit. <b>+{CURRENCY_SYMBOL}{bonus}</b> has been credited to your wallet!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        success_card = (
            f"🎉 <b>Crypto Payment Confirmed!</b>\n\n"
            f"💵 Amount Credited: <b>+{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 New Balance: <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>\n"
            f"🆔 Transaction ID: <code>{txn_ref}</code>\n\n"
            f"You can now browse products and make purchases!"
        ) if lang == "en" else (
            f"🎉 <b>የክሪፕቶ ክፍያዎ በተሳካ ሁኔታ ተረጋግጧል!</b>\n\n"
            f"💵 የገባው መጠን፡ <b>+{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 አዲሱ ቀሪ ሒሳብ፡ <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>\n"
            f"🆔 መለያ፡ <code>{txn_ref}</code>\n\n"
            f"አሁን ወደ ካታሎግ በመሄድ የፈለጉትን ዕቃ መግዛት ይችላሉ!"
        )
        await call.message.edit_text(success_card, parse_mode="HTML")
        await call.answer("🎉 Payment Successful!", show_alert=False)

        # Broadcast to channel(s)
        targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
        for ch in targets:
            try:
                await call.bot.send_message(
                    ch,
                    f"💎 <b>New Crypto Deposit Confirmed!</b>\n\n"
                    f"👤 User: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
                    f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
                    f"🏦 Provider: CryptoBot\n"
                    f"🆔 Invoice: <code>#{invoice_id}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif status == "active":
        await call.answer(
            "⏳ Payment not detected yet. Please complete the transfer in @CryptoBot and click check again.",
            show_alert=True
        )
    elif status == "expired":
        await call.answer("❌ This invoice has expired. Please initiate a new deposit.", show_alert=True)
    else:
        await call.answer(f"Status: {status}. Awaiting payment.", show_alert=True)


# =====================================================================
# 2. TELEGRAM STARS PAYMENT INTEGRATION
# =====================================================================

@router.callback_query(F.data == "dep_stars")
async def start_stars_deposit(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prompt = (
        f"⭐ <b>Deposit with Telegram Stars</b>\n\n"
        f"Pay natively inside Telegram using your Telegram Stars balance or in-app purchase.\n\n"
        f"Enter the amount in <b>{BASE_CURRENCY}</b> to deposit (Min: {CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT}):"
    ) if lang == "en" else (
        f"⭐ <b>በቴሌግራም ስታርስ (Stars) ይክፈሉ</b>\n\n"
        f"በቀጥታ በቴሌግራም ስታርስ ሒሳብዎን ይሙሉ\n\n"
        f"መሙላት የሚፈልጉትን መጠን በ <b>{BASE_CURRENCY}</b> ያስገቡ (ዝቅተኛ: {CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT}):"
    )

    await state.set_state(DepositStates.waiting_stars_amount)
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_stars_amount)
async def process_stars_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    raw_text = (message.text or "").strip().replace("$", "")
    try:
        amount = Decimal(raw_text)
    except Exception:
        await message.answer("⚠️ Please enter a valid numerical amount (e.g. <code>5</code> or <code>10</code>):")
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)):
        await message.answer(f"⚠️ Minimum deposit is {CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}.")
        return

    # Calculate Stars needed (e.g., $1 = 50 Stars at $0.02/Star)
    stars_count = max(1, int(round(float(amount) / STARS_RATE_USD)))

    prices = [LabeledPrice(label=f"Deposit {CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}", amount=stars_count)]
    payload = json.dumps({"user_id": user_id, "amount": str(amount), "type": "stars_deposit"})

    try:
        await message.bot.send_invoice(
            chat_id=user_id,
            title="Nexus Store Balance Top-Up",
            description=f"Top-up {CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY} to your Nexus account balance.",
            payload=payload,
            provider_token="",  # Telegram Stars uses empty provider_token
            currency="XTR",
            prices=prices
        )
    except Exception as e:
        logger.error(f"Stars invoice failed: {e}")
        await message.answer(f"❌ Failed to create Stars invoice: {e}")

    await state.clear()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment_info = message.successful_payment
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    try:
        payload_data = json.loads(payment_info.invoice_payload)
        amount = Decimal(payload_data.get("amount", "0.00"))
    except Exception:
        amount = Decimal(str(payment_info.total_amount * STARS_RATE_USD))

    txn_id = f"stars_{payment_info.telegram_payment_charge_id}"

    if await check_transaction_exists(txn_id):
        return

    ok, new_balance = await add_user_balance(user_id, amount)
    if ok:
        await save_payment_receipt(
            user_id=user_id,
            provider="telegram_stars",
            transaction_id=txn_id,
            amount=amount,
            sender_name=f"Stars ({payment_info.total_amount} XTR)",
            raw_details=str(payment_info)
        )

        ack = (
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"⭐ Paid: <b>{payment_info.total_amount} Stars</b>\n"
            f"💵 Credited: <b>+{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 New Balance: <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>"
        )
        await message.answer(ack, parse_mode="HTML")

        # Channel notification
        targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
        for ch in targets:
            try:
                await message.bot.send_message(
                    ch,
                    f"⭐ <b>New Telegram Stars Deposit!</b>\n\n"
                    f"👤 User: <code>{user_id}</code> (@{message.from_user.username or 'N/A'})\n"
                    f"⭐ Stars: {payment_info.total_amount} XTR\n"
                    f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
                    f"🆔 Txn: <code>{txn_id}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass


# =====================================================================
# 3. LOCAL ETHIOPIAN PAYMENTS (TELEBIRR & CBE)
# =====================================================================

@router.callback_query(F.data == "dep_telebirr")
async def dep_telebirr(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    custom_tele = await get_setting("telebirr_account")
    phone = TELEBIRR_RECEIVER_PHONE
    name = TELEBIRR_RECEIVER_NAME
    if custom_tele and "," in custom_tele:
        parts = [p.strip() for p in custom_tele.split(",", 1)]
        phone = parts[0]
        name = parts[1]
    elif custom_tele:
        phone = custom_tele

    text = t("telebirr_instructions", lang, phone=phone, name=name, min=MIN_DEPOSIT_AMOUNT)
    await state.set_state(DepositStates.waiting_receipt)
    await state.update_data(provider="telebirr")
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "dep_cbe")
async def dep_cbe(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    custom_cbe = await get_setting("cbe_account")
    account = CBE_ACCOUNT_NUMBER
    name = CBE_ACCOUNT_NAME
    if custom_cbe and "," in custom_cbe:
        parts = [p.strip() for p in custom_cbe.split(",", 1)]
        account = parts[0]
        name = parts[1]
    elif custom_cbe:
        account = custom_cbe

    text = t("cbe_instructions", lang, account=account, name=name, min=MIN_DEPOSIT_AMOUNT)
    await state.set_state(DepositStates.waiting_receipt)
    await state.update_data(provider="cbe")
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_receipt)
async def process_receipt_submission(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    raw_text = (message.text or "").strip()
    if not raw_text.startswith("http"):
        await message.answer("⚠️ Please send the full bank receipt URL (e.g. starting with https://).")
        return

    status_msg = await message.answer(t("verifying_receipt", lang))
    res = await verify_receipt_url(raw_text)

    if not res.get("valid"):
        err = res.get("message", "Invalid Receipt")
        await status_msg.edit_text(t("receipt_failed", lang, reason=err), parse_mode="HTML")
        await state.clear()
        return

    txn_id = res.get("txn_id")
    amount = Decimal(str(res.get("amount", 0.0)))
    provider = res.get("provider", "bank")

    if await check_transaction_exists(txn_id):
        await status_msg.edit_text(t("receipt_duplicate", lang), parse_mode="HTML")
        await state.clear()
        return

    ok, new_balance = await add_user_balance(user_id, amount)
    if not ok:
        await status_msg.edit_text("❌ Database error. Please contact support.")
        await state.clear()
        return

    await save_payment_receipt(
        user_id=user_id,
        provider=provider,
        transaction_id=txn_id,
        amount=amount,
        sender_name=res.get("recipientName", ""),
        raw_details=str(res)
    )

    await status_msg.edit_text(
        t("receipt_success", lang, amount=amount, currency=BASE_CURRENCY, txn_id=txn_id, new_balance=new_balance),
        parse_mode="HTML"
    )
    await state.clear()
