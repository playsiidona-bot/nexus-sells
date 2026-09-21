import json
import logging
from decimal import Decimal
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database.crud import (
    get_user_by_id, add_user_balance, check_transaction_exists,
    save_payment_receipt, get_setting, is_payment_link_or_txn_used,
    record_used_payment_link
)
from bot.keyboards.inline import (
    deposit_methods_keyboard, crypto_invoice_keyboard,
    oxapay_invoice_keyboard, cryptomus_invoice_keyboard, nowpayments_invoice_keyboard,
    usdt_deposit_keyboard
)
from bot.services.i18n import t
from bot.services.verifier import (
    verify_payment_receipt, verify_receipt_url,
    payment_flood_protector, extract_and_normalize_payment_input
)
from bot.services.cryptopay import CryptoPayClient, CryptoPayAPIError
from bot.services.oxapay import OxaPayClient
from bot.services.cryptomus import CryptomusClient
from bot.services.nowpayments import NOWPaymentsClient
from bot.config import (
    BASE_CURRENCY, CURRENCY_SYMBOL, CRYPTO_PAY_TOKEN, STARS_RATE_USD,
    OXAPAY_API_KEY, CRYPTOMUS_MERCHANT_ID, CRYPTOMUS_PAYMENT_KEY, NOWPAYMENTS_API_KEY,
    TELEBIRR_RECEIVER_PHONE, TELEBIRR_RECEIVER_NAME,
    CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME, MIN_DEPOSIT_AMOUNT, MAX_DEPOSIT_AMOUNT,
    REFERRAL_PERCENT, LOGS_CHANNEL_ID, PAYMENTS_CHANNEL_ID, get_channel_list
)

logger = logging.getLogger(__name__)
router = Router()


class DepositStates(StatesGroup):
    waiting_crypto_amount = State()
    waiting_oxapay_amount = State()
    waiting_cryptomus_amount = State()
    waiting_nowpayments_amount = State()
    waiting_stars_amount = State()
    waiting_receipt = State()
    waiting_usdt_txid = State()


@router.message(Command("wallet"))
@router.message(Command("balance"))
@router.message(Command("ዋሌት"))
@router.message(F.text.in_(["Balance & Deposit", "ዋሌት / ሒሳብ", "[ Balance & Deposit ]", "[ ዋሌት / ሒሳብ ]", "💳 ዋሌት / ሒሳብ", "💳 Wallet / Balance", "💳 Balance / Top-Up"]))
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

    active_crypto_token = await get_setting("crypto_pay_token", CRYPTO_PAY_TOKEN)
    if not active_crypto_token:
        await message.answer(
            "<b>Crypto payments are temporarily in maintenance.</b>\nPlease contact support or choose another payment method.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    client = CryptoPayClient(active_crypto_token)
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
        await message.answer(f"Failed to generate invoice: {e.message}. Please try again later.")
        await state.clear()
        return
    finally:
        await client.close()

    invoice_id = invoice.get("invoice_id")
    bot_invoice_url = invoice.get("bot_invoice_url") or invoice.get("mini_app_invoice_url") or invoice.get("pay_url")

    card_text = (
        f"<b>Crypto Invoice Generated</b>\n\n"
        f"Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"Invoice ID: <code>#{invoice_id}</code>\n"
        f"Valid for: <b>30 Minutes</b>\n\n"
        f"1. Click the button below to pay via <b>@CryptoBot</b> with USDT, TON, BTC, or LTC.\n"
        f"2. After payment completes, return here and click <b>Check Payment</b>."
    ) if lang == "en" else (
        f"<b>የክሪፕቶ ደረሰኝ ተዘጋጅቷል</b>\n\n"
        f"መጠን፡ <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"የደረሰኝ ቁጥር፡ <code>#{invoice_id}</code>\n"
        f"የሚቆይበት ጊዜ፡ <b>30 ደቂቃ</b>\n\n"
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
        await call.answer("This invoice has already been credited to your balance!", show_alert=True)
        return

    active_crypto_token = await get_setting("crypto_pay_token", CRYPTO_PAY_TOKEN)
    client = CryptoPayClient(active_crypto_token)
    try:
        invoice = await client.get_invoice(invoice_id)
    except Exception as e:
        await call.answer("Could not reach CryptoBot API. Please try again in a moment.", show_alert=True)
        return
    finally:
        await client.close()

    if not invoice:
        await call.answer("Invoice not found or expired.", show_alert=True)
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
# 2. OXAPAY INTEGRATION (#1)
# =====================================================================

@router.callback_query(F.data == "dep_oxapay")
async def start_oxapay_deposit(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prompt = (
        f"⚡ <b>Deposit via OxaPay (0.4% Fee / Instant)</b>\n\n"
        f"Fast, non-custodial crypto checkout supporting <b>USDT (TRC20, TON, BEP20), BTC, LTC, TRX</b> and more.\n\n"
        f"Enter the amount in <b>{BASE_CURRENCY}</b> to deposit:\n"
        f"• Minimum: <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b>\n"
        f"• Maximum: <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>\n\n"
        f"<i>Reply with the amount (e.g., <code>10</code> or <code>50</code>):</i>"
    )
    await state.set_state(DepositStates.waiting_oxapay_amount)
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_oxapay_amount)
async def process_oxapay_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    raw_text = (message.text or "").strip().replace("$", "")
    try:
        amount = Decimal(raw_text)
    except Exception:
        await message.answer("⚠️ Please enter a valid numerical amount (e.g. <code>10</code>):")
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)) or amount > Decimal(str(MAX_DEPOSIT_AMOUNT)):
        await message.answer(f"⚠️ Amount must be between <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b> and <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>.", parse_mode="HTML")
        return

    active_oxapay_key = await get_setting("oxapay_api_key", OXAPAY_API_KEY)
    if not active_oxapay_key:
        await message.answer("<b>OxaPay is not configured yet.</b>\nPlease choose another payment method or contact support.", parse_mode="HTML")
        await state.clear()
        return

    client = OxaPayClient(active_oxapay_key)
    order_ref = f"ox_{user_id}_{int(amount*100)}"
    res = await client.create_invoice(
        amount=float(amount),
        currency=BASE_CURRENCY,
        order_id=order_ref,
        description=f"Nexus Store Top-up {user_id}"
    )
    await client.close()

    if res.get("result") != 100 or not res.get("payLink"):
        err = res.get("message", "Unable to create invoice")
        await message.answer(f"Failed to create OxaPay invoice: {err}")
        await state.clear()
        return

    track_id = res.get("trackId")
    pay_link = res.get("payLink")

    card_text = (
        f"<b>OxaPay Crypto Invoice Generated</b>\n\n"
        f"Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"Track ID: <code>#{track_id}</code>\n"
        f"Valid for: <b>60 Minutes</b>\n\n"
        f"1. Click the button below to open the OxaPay payment page.\n"
        f"2. Pay with USDT, BTC, TON, LTC, or your preferred cryptocurrency.\n"
        f"3. Return here and tap <b>Check Payment</b> to instantly credit your balance."
    )
    kb = oxapay_invoice_keyboard(pay_link, track_id, lang)
    await message.answer(card_text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("check_oxapay_"))
async def check_oxapay_status(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    track_id = int(call.data.split("_")[2])
    txn_ref = f"oxapay_{track_id}"

    if await check_transaction_exists(txn_ref):
        await call.answer("This invoice was already credited to your wallet!", show_alert=True)
        return

    active_oxapay_key = await get_setting("oxapay_api_key", OXAPAY_API_KEY)
    client = OxaPayClient(active_oxapay_key)
    res = await client.inquiry_payment(track_id)
    await client.close()

    status = (res.get("status") or "").lower()
    if status == "paid":
        amount_paid = Decimal(str(res.get("amount", "0.00")))
        ok, new_balance = await add_user_balance(user_id, amount_paid)
        if not ok:
            await call.answer("❌ Error crediting balance. Please contact support.", show_alert=True)
            return

        await save_payment_receipt(
            user_id=user_id,
            provider="oxapay",
            transaction_id=txn_ref,
            amount=amount_paid,
            sender_name=f"OxaPay #{track_id}",
            raw_details=json.dumps(res)
        )

        if user and user.referrer_id and REFERRAL_PERCENT > 0:
            bonus = (amount_paid * Decimal(str(REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
            if bonus > 0:
                await add_user_balance(user.referrer_id, bonus)

        success_card = (
            f"🎉 <b>OxaPay Payment Confirmed!</b>\n\n"
            f"💵 Amount Credited: <b>+{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 New Balance: <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>\n"
            f"🆔 Transaction ID: <code>{txn_ref}</code>"
        )
        await call.message.edit_text(success_card, parse_mode="HTML")
        await call.answer("🎉 Payment Confirmed!", show_alert=False)

        targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
        for ch in targets:
            try:
                await call.bot.send_message(
                    ch,
                    f"⚡ <b>New OxaPay Deposit Confirmed!</b>\n\n"
                    f"👤 User: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
                    f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
                    f"🆔 Track ID: <code>#{track_id}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif status in ["waiting", "pending"]:
        await call.answer("⏳ Payment not detected on blockchain yet. Please complete the transfer and check again.", show_alert=True)
    elif status == "expired":
        await call.answer("❌ This invoice has expired. Please create a new deposit.", show_alert=True)
    else:
        await call.answer(f"Status: {res.get('status', 'Waiting')}. Awaiting blockchain confirmation.", show_alert=True)


# =====================================================================
# 3. CRYPTOMUS INTEGRATION (#2)
# =====================================================================

@router.callback_query(F.data == "dep_cryptomus")
async def start_cryptomus_deposit(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prompt = (
        f"🪙 <b>Deposit via Cryptomus (Auto-Convert & Multi-Coin)</b>\n\n"
        f"Fast multi-currency crypto processing with automatic conversion to USDT.\n\n"
        f"Enter the amount in <b>{BASE_CURRENCY}</b> to deposit:\n"
        f"• Minimum: <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b>\n"
        f"• Maximum: <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>\n\n"
        f"<i>Reply with the amount (e.g., <code>15</code> or <code>50</code>):</i>"
    )
    await state.set_state(DepositStates.waiting_cryptomus_amount)
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_cryptomus_amount)
async def process_cryptomus_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    raw_text = (message.text or "").strip().replace("$", "")
    try:
        amount = Decimal(raw_text)
    except Exception:
        await message.answer("⚠️ Please enter a valid numerical amount (e.g. <code>15</code>):")
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)) or amount > Decimal(str(MAX_DEPOSIT_AMOUNT)):
        await message.answer(f"⚠️ Amount must be between <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b> and <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>.", parse_mode="HTML")
        return

    active_cm_mid = await get_setting("cryptomus_merchant_id", CRYPTOMUS_MERCHANT_ID)
    active_cm_key = await get_setting("cryptomus_payment_key", CRYPTOMUS_PAYMENT_KEY)
    if not active_cm_mid or not active_cm_key:
        await message.answer("<b>Cryptomus is not configured yet.</b>\nPlease choose another payment method or contact support.", parse_mode="HTML")
        await state.clear()
        return

    client = CryptomusClient(active_cm_mid, active_cm_key)
    order_id = f"cm_{user_id}_{int(amount*100)}"
    res = await client.create_payment(
        amount=float(amount),
        order_id=order_id,
        currency=BASE_CURRENCY
    )
    await client.close()

    result_data = res.get("result", {})
    pay_url = result_data.get("url")
    uuid = result_data.get("uuid")

    if res.get("state") != 0 or not pay_url:
        err = res.get("message", "Unable to create payment")
        await message.answer(f"Failed to create Cryptomus payment: {err}")
        await state.clear()
        return

    card_text = (
        f"<b>Cryptomus Payment Invoice Generated</b>\n\n"
        f"Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"Payment UUID: <code>{uuid}</code>\n"
        f"Valid for: <b>60 Minutes</b>\n\n"
        f"1. Click the button below to open Cryptomus secure checkout.\n"
        f"2. Pay with USDT, BTC, ETH, TON, or your selected cryptocurrency.\n"
        f"3. Return here and tap <b>Check Payment</b> to credit your balance instantly."
    )
    kb = cryptomus_invoice_keyboard(pay_url, uuid, lang)
    await message.answer(card_text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("check_cryptomus_"))
async def check_cryptomus_status(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    uuid = call.data.replace("check_cryptomus_", "")
    txn_ref = f"cryptomus_{uuid}"

    if await check_transaction_exists(txn_ref):
        await call.answer("This payment was already credited to your wallet!", show_alert=True)
        return

    active_cm_mid = await get_setting("cryptomus_merchant_id", CRYPTOMUS_MERCHANT_ID)
    active_cm_key = await get_setting("cryptomus_payment_key", CRYPTOMUS_PAYMENT_KEY)
    client = CryptomusClient(active_cm_mid, active_cm_key)
    res = await client.get_payment_info(uuid=uuid)
    await client.close()

    result_data = res.get("result", {})
    status = (result_data.get("status") or "").lower()

    if status in ["paid", "paid_over"]:
        amount_paid = Decimal(str(result_data.get("amount", "0.00")))
        ok, new_balance = await add_user_balance(user_id, amount_paid)
        if not ok:
            await call.answer("❌ Error crediting balance. Please contact support.", show_alert=True)
            return

        await save_payment_receipt(
            user_id=user_id,
            provider="cryptomus",
            transaction_id=txn_ref,
            amount=amount_paid,
            sender_name=f"Cryptomus {uuid[:8]}",
            raw_details=json.dumps(res)
        )

        if user and user.referrer_id and REFERRAL_PERCENT > 0:
            bonus = (amount_paid * Decimal(str(REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
            if bonus > 0:
                await add_user_balance(user.referrer_id, bonus)

        success_card = (
            f"🎉 <b>Cryptomus Payment Confirmed!</b>\n\n"
            f"💵 Amount Credited: <b>+{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 New Balance: <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>\n"
            f"🆔 Transaction ID: <code>{txn_ref}</code>"
        )
        await call.message.edit_text(success_card, parse_mode="HTML")
        await call.answer("🎉 Payment Confirmed!", show_alert=False)

        targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
        for ch in targets:
            try:
                await call.bot.send_message(
                    ch,
                    f"🪙 <b>New Cryptomus Deposit Confirmed!</b>\n\n"
                    f"👤 User: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
                    f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
                    f"🆔 UUID: <code>{uuid}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif status in ["process", "check"]:
        await call.answer("⏳ Payment detected, waiting for blockchain confirmations. Check again shortly.", show_alert=True)
    elif status in ["cancel", "system_fail"]:
        await call.answer("❌ Payment was canceled or failed. Please create a new invoice.", show_alert=True)
    else:
        await call.answer(f"Status: {status or 'Awaiting Payment'}. Check again after paying.", show_alert=True)


# =====================================================================
# 4. NOWPAYMENTS INTEGRATION (#3)
# =====================================================================

@router.callback_query(F.data == "dep_nowpayments")
async def start_nowpayments_deposit(call: CallbackQuery, state: FSMContext):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    prompt = (
        f"🌍 <b>Deposit via NOWPayments (300+ Cryptos)</b>\n\n"
        f"Non-custodial global payment supporting over 300 coins and tokens.\n\n"
        f"Enter the amount in <b>{BASE_CURRENCY}</b> to deposit:\n"
        f"• Minimum: <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b>\n"
        f"• Maximum: <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>\n\n"
        f"<i>Reply with the amount (e.g., <code>20</code> or <code>100</code>):</i>"
    )
    await state.set_state(DepositStates.waiting_nowpayments_amount)
    await call.message.edit_text(prompt, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_nowpayments_amount)
async def process_nowpayments_amount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    raw_text = (message.text or "").strip().replace("$", "")
    try:
        amount = Decimal(raw_text)
    except Exception:
        await message.answer("⚠️ Please enter a valid numerical amount (e.g. <code>20</code>):")
        return

    if amount < Decimal(str(MIN_DEPOSIT_AMOUNT)) or amount > Decimal(str(MAX_DEPOSIT_AMOUNT)):
        await message.answer(f"⚠️ Amount must be between <b>{CURRENCY_SYMBOL}{MIN_DEPOSIT_AMOUNT:.2f}</b> and <b>{CURRENCY_SYMBOL}{MAX_DEPOSIT_AMOUNT:.2f}</b>.", parse_mode="HTML")
        return

    active_np_key = await get_setting("nowpayments_api_key", NOWPAYMENTS_API_KEY)
    if not active_np_key:
        await message.answer("<b>NOWPayments is not configured yet.</b>\nPlease choose another payment method or contact support.", parse_mode="HTML")
        await state.clear()
        return

    client = NOWPaymentsClient(active_np_key)
    order_ref = f"np_{user_id}_{int(amount*100)}"
    res = await client.create_invoice(
        amount=float(amount),
        currency=BASE_CURRENCY,
        order_id=order_ref,
        description=f"Nexus Store Top-up {user_id}"
    )
    await client.close()

    invoice_url = res.get("invoice_url")
    payment_id = res.get("id")

    if not invoice_url or not payment_id:
        err = res.get("message", "Unable to generate invoice")
        await message.answer(f"Failed to create NOWPayments invoice: {err}")
        await state.clear()
        return

    card_text = (
        f"<b>NOWPayments Invoice Generated</b>\n\n"
        f"Amount: <b>{CURRENCY_SYMBOL}{amount:.2f} {BASE_CURRENCY}</b>\n"
        f"Invoice ID: <code>{payment_id}</code>\n\n"
        f"1. Click the button below to open the NOWPayments page.\n"
        f"2. Select from 300+ cryptocurrencies to complete payment.\n"
        f"3. Return here and tap <b>Check Payment</b> to credit your balance."
    )
    kb = nowpayments_invoice_keyboard(invoice_url, payment_id, lang)
    await message.answer(card_text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("check_nowpayments_"))
async def check_nowpayments_status(call: CallbackQuery):
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    payment_id = call.data.replace("check_nowpayments_", "")
    txn_ref = f"nowpayments_{payment_id}"

    if await check_transaction_exists(txn_ref):
        await call.answer("This invoice has already been credited to your wallet!", show_alert=True)
        return

    active_np_key = await get_setting("nowpayments_api_key", NOWPAYMENTS_API_KEY)
    client = NOWPaymentsClient(active_np_key)
    res = await client.get_payment_status(payment_id)
    await client.close()

    status = (res.get("payment_status") or "").lower()
    if status in ["finished", "confirmed"]:
        amount_paid = Decimal(str(res.get("price_amount", "0.00")))
        ok, new_balance = await add_user_balance(user_id, amount_paid)
        if not ok:
            await call.answer("❌ Error crediting balance. Please contact support.", show_alert=True)
            return

        await save_payment_receipt(
            user_id=user_id,
            provider="nowpayments",
            transaction_id=txn_ref,
            amount=amount_paid,
            sender_name=f"NOWPayments #{payment_id}",
            raw_details=json.dumps(res)
        )

        if user and user.referrer_id and REFERRAL_PERCENT > 0:
            bonus = (amount_paid * Decimal(str(REFERRAL_PERCENT)) / Decimal("100")).quantize(Decimal("0.01"))
            if bonus > 0:
                await add_user_balance(user.referrer_id, bonus)

        success_card = (
            f"🎉 <b>NOWPayments Payment Confirmed!</b>\n\n"
            f"💵 Amount Credited: <b>+{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
            f"💰 New Balance: <b>{CURRENCY_SYMBOL}{new_balance:.2f} {BASE_CURRENCY}</b>\n"
            f"🆔 Transaction ID: <code>{txn_ref}</code>"
        )
        await call.message.edit_text(success_card, parse_mode="HTML")
        await call.answer("🎉 Payment Confirmed!", show_alert=False)

        targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
        for ch in targets:
            try:
                await call.bot.send_message(
                    ch,
                    f"🌍 <b>New NOWPayments Deposit Confirmed!</b>\n\n"
                    f"👤 User: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
                    f"💵 Amount: <b>{CURRENCY_SYMBOL}{amount_paid:.2f} {BASE_CURRENCY}</b>\n"
                    f"🆔 Payment ID: <code>{payment_id}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif status in ["waiting", "confirming", "sending"]:
        await call.answer(f"⏳ Payment Status: {status.title()}. Awaiting network confirmation.", show_alert=True)
    elif status in ["failed", "expired"]:
        await call.answer("❌ Payment was not completed or has expired.", show_alert=True)
    else:
        await call.answer("⏳ Status: Awaiting Payment. Tap again once transaction is sent.", show_alert=True)


# =====================================================================
# 5. TELEGRAM STARS PAYMENT INTEGRATION
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

    # 1. Flood protection check
    is_flooding, flood_reason, wait_seconds = payment_flood_protector.check_flood(user_id, lang=lang)
    if is_flooding:
        await message.answer(flood_reason, parse_mode="HTML")
        return

    raw_text = (message.text or "").strip()
    norm_url, detected_provider, candidate_txn_id, orig_url = extract_and_normalize_payment_input(raw_text)

    data = await state.get_data()
    expected_provider = data.get("provider") or detected_provider

    if not norm_url or (detected_provider == "unknown" and not expected_provider):
        await message.answer(
            "እባክዎ ትክክለኛ የባንክ ደረሰኝ ሊንክ (SMS Link) ወይም የግብይት ቁጥር (Transaction ID) ያስገቡ።"
            if lang == "am" else
            "Please send a valid bank receipt URL (SMS link) or Transaction Reference ID."
        )
        return

    # 2. Duplicate check before making outbound requests
    is_used, duplicate_reason = await is_payment_link_or_txn_used(norm_url, candidate_txn_id)
    if is_used:
        payment_flood_protector.record_failure(user_id)
        await message.answer(
            duplicate_reason or (t("receipt_duplicate", lang) if lang == "am" else "This receipt link or transaction has already been used."),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # 3. Record attempt in flood tracker
    payment_flood_protector.record_attempt(user_id)

    # 4. Fetch dynamic receiver configuration from database or config
    custom_tele = await get_setting("telebirr_account")
    phone = TELEBIRR_RECEIVER_PHONE
    if custom_tele and "," in custom_tele:
        phone = custom_tele.split(",", 1)[0].strip()
    elif custom_tele:
        phone = custom_tele.strip()

    custom_cbe = await get_setting("cbe_account")
    account = CBE_ACCOUNT_NUMBER
    if custom_cbe and "," in custom_cbe:
        account = custom_cbe.split(",", 1)[0].strip()
    elif custom_cbe:
        account = custom_cbe.strip()

    status_msg = await message.answer(t("verifying_receipt", lang), parse_mode="HTML")

    # 5. Run Auto-Verifier Engine
    res = await verify_payment_receipt(
        raw_input=raw_text,
        expected_provider=expected_provider,
        expected_telebirr=phone,
        expected_cbe=account,
        min_amount=MIN_DEPOSIT_AMOUNT
    )

    if not res.get("valid"):
        payment_flood_protector.record_failure(user_id)
        err = res.get("message") or "Invalid Receipt"
        await status_msg.edit_text(t("receipt_failed", lang, reason=err), parse_mode="HTML")
        await state.clear()
        return

    # 6. Verification successful!
    payment_flood_protector.record_success(user_id)

    final_txn_id = res["txn_id"]
    final_amount = Decimal(str(res["amount"]))
    final_provider = res["provider"]
    final_norm_url = res["normalized_url"]

    # Final concurrency race-condition check
    is_used_final, _ = await is_payment_link_or_txn_used(final_norm_url, final_txn_id)
    if is_used_final:
        await status_msg.edit_text(t("receipt_duplicate", lang), parse_mode="HTML")
        await state.clear()
        return

    ok, new_balance = await add_user_balance(user_id, final_amount)
    if not ok:
        await status_msg.edit_text("የዳታቤዝ ስህተት አጋጥሟል። እባክዎ ድጋፍ ሰጪ ያነጋግሩ።" if lang == "am" else "Database error. Please contact support.")
        await state.clear()
        return

    # Permanently save consumed link & receipt to prevent reuse
    await record_used_payment_link(
        user_id=user_id,
        provider=final_provider,
        normalized_url=final_norm_url,
        original_url=raw_text,
        transaction_id=final_txn_id,
        amount=final_amount
    )

    await save_payment_receipt(
        user_id=user_id,
        provider=final_provider,
        transaction_id=final_txn_id,
        amount=final_amount,
        sender_name=res.get("sender_name", ""),
        raw_details=str(res),
        status="approved",
        receipt_url=final_norm_url
    )

    await status_msg.edit_text(
        t("receipt_success", lang, amount=final_amount, currency=BASE_CURRENCY, txn_id=final_txn_id, new_balance=new_balance),
        parse_mode="HTML"
    )

    # Optional channel notifications
    log_text = (
        f"<b>Local Deposit Approved ({final_provider.upper()})</b>\n"
        f"User: <code>{user_id}</code>\n"
        f"Amount: <code>+{final_amount} {BASE_CURRENCY}</code>\n"
        f"Txn ID: <code>{final_txn_id}</code>\n"
        f"Link: <code>{final_norm_url}</code>"
    )
    if PAYMENTS_CHANNEL_ID:
        try:
            await message.bot.send_message(PAYMENTS_CHANNEL_ID, log_text, parse_mode="HTML")
        except Exception:
            pass

    await state.clear()


# =====================================================================
# REFRESH & NAVIGATION HANDLERS
# =====================================================================

@router.callback_query(F.data == "refresh_wallet")
async def refresh_wallet_view(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    balance = user.balance if user else Decimal("0.00")

    show_local = bool(TELEBIRR_RECEIVER_PHONE or CBE_ACCOUNT_NUMBER)
    text = t("wallet_title", lang, balance=balance, currency=BASE_CURRENCY, user_id=call.from_user.id)
    kb = deposit_methods_keyboard(lang=lang, show_local=show_local)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Balance refreshed" if lang == "en" else "ሒሳብ ታድሷል")


@router.callback_query(F.data == "back_to_deposit")
async def back_to_deposit_view(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"
    balance = user.balance if user else Decimal("0.00")

    show_local = bool(TELEBIRR_RECEIVER_PHONE or CBE_ACCOUNT_NUMBER)
    text = t("wallet_title", lang, balance=balance, currency=BASE_CURRENCY, user_id=call.from_user.id)
    kb = deposit_methods_keyboard(lang=lang, show_local=show_local)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "close_view")
async def close_view_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


# =====================================================================
# DIRECT USDT PAYMENTS (POLYGON & BEP-20)
# =====================================================================

@router.callback_query(F.data == "dep_usdt_polygon")
async def dep_usdt_polygon(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    address = await get_setting("usdt_polygon_address", "0xYourPolygonUSDTAddressHere")
    text = (
        "<b>DEPOSIT USDT (POLYGON NETWORK)</b>\n"
        "────────────────────────\n"
        "Send USDT on the <b>Polygon (PoS) network</b> to the official store address below:\n\n"
        f"<code>{address}</code>\n\n"
        "• Network: <b>Polygon (PoS / MATIC)</b>\n"
        "• Minimum Deposit: <b>$1.00</b>\n"
        "• Once sent, tap the button below and paste your <b>Transaction Hash (TXID)</b> for rapid verification."
        if lang == "en" else
        "<b>USDT በPOLYGON መረብ አስገባ</b>\n"
        "────────────────────────\n"
        "USDT በ <b>Polygon (PoS) network</b> ወደዚህ አድራሻ ይላኩ፡\n\n"
        f"<code>{address}</code>\n\n"
        "• ኔትወርክ፡ <b>Polygon (PoS)</b>\n"
        "• ዝቅተኛ ተቀማጭ፡ <b>$1.00</b>\n"
        "• ገንዘቡን ከላኩ በኋላ ከታች ያለውን ቁልፍ በመንካት <b>የትራንዛክሽን Hash (TXID)</b> ያስገቡ።"
    )
    kb = usdt_deposit_keyboard("polygon", lang)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "dep_usdt_bep20")
async def dep_usdt_bep20(call: CallbackQuery):
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    address = await get_setting("usdt_bep20_address", "0xYourBEP20USDTAddressHere")
    text = (
        "<b>DEPOSIT USDT (BEP-20 / BSC)</b>\n"
        "────────────────────────\n"
        "Send USDT on the <b>BNB Smart Chain (BEP-20)</b> to the official store address below:\n\n"
        f"<code>{address}</code>\n\n"
        "• Network: <b>BNB Smart Chain (BEP-20)</b>\n"
        "• Minimum Deposit: <b>$1.00</b>\n"
        "• Once sent, tap the button below and paste your <b>Transaction Hash (TXID)</b> for rapid verification."
        if lang == "en" else
        "<b>USDT በBEP-20 (BSC) መረብ አስገባ</b>\n"
        "────────────────────────\n"
        "USDT በ <b>BNB Smart Chain (BEP-20)</b> ወደዚህ አድራሻ ይላኩ፡\n\n"
        f"<code>{address}</code>\n\n"
        "• ኔትወርክ፡ <b>BNB Smart Chain (BEP-20)</b>\n"
        "• ዝቅተኛ ተቀማጭ፡ <b>$1.00</b>\n"
        "• ገንዘቡን ከላኩ በኋላ ከታች ያለውን ቁልፍ በመንካት <b>የትራንዛክሽን Hash (TXID)</b> ያስገቡ።"
    )
    kb = usdt_deposit_keyboard("bep20", lang)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("usdt_submit_"))
async def start_usdt_txid_submission(call: CallbackQuery, state: FSMContext):
    network = call.data.replace("usdt_submit_", "")
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    await state.set_state(DepositStates.waiting_usdt_txid)
    await state.update_data(network=network)

    prompt = (
        f"<b>SUBMIT USDT TRANSACTION HASH ({network.upper()})</b>\n"
        "────────────────────────\n"
        "Please paste the full transaction hash (TXID) of your transfer:\n\n"
        "<i>Example: <code>0x7f9a12bc45...</code></i>"
        if lang == "en" else
        f"<b>የትራንዛክሽን HASH (TXID) አስገባ ({network.upper()})</b>\n"
        "────────────────────────\n"
        "እባክዎ የላኩበትን ሙሉ የትራንዛክሽን Hash (TXID) ይላኩ፡\n\n"
        "<i>ምሳሌ፡ <code>0x7f9a12bc45...</code></i>"
    )
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="< Cancel", callback_data="back_to_deposit", style="danger")]
    ])
    await call.message.edit_text(prompt, reply_markup=cancel_kb, parse_mode="HTML")
    await call.answer()


@router.message(DepositStates.waiting_usdt_txid)
async def process_usdt_txid(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    txid = (message.text or "").strip()
    if len(txid) < 10:
        await message.answer("Please send a valid transaction hash (TXID).")
        return

    data = await state.get_data()
    network = data.get("network", "usdt")
    await state.clear()

    if await check_transaction_exists(txid):
        await message.answer("This transaction hash has already been submitted or processed.")
        return

    receipt = await save_payment_receipt(
        user_id=user_id,
        provider=f"usdt_{network}",
        transaction_id=txid,
        amount=Decimal("0.00"),
        sender_name=f"USDT ({network.upper()})",
        raw_details=f"User @{message.from_user.username or 'N/A'} submitted TXID for {network.upper()}",
        status="pending"
    )

    success_msg = (
        "<b>TRANSACTION RECEIVED</b>\n"
        "────────────────────────\n"
        f"Your USDT ({network.upper()}) transaction hash has been submitted:\n"
        f"<code>{txid}</code>\n\n"
        "Our team will verify the blockchain confirmation shortly. Your balance will update automatically upon verification."
        if lang == "en" else
        "<b>ትራንዛክሽኑ ደርሷል</b>\n"
        "────────────────────────\n"
        f"የ USDT ({network.upper()}) የትራንዛክሽን Hash ተልኳል፡\n"
        f"<code>{txid}</code>\n\n"
        "ቡድናችን በብሎክቼይን ላይ እንደተረጋገጠ ሒሳብዎን ወዲያውኑ ይጨምራል።"
    )
    await message.answer(success_msg, parse_mode="HTML")

    targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
    receipt_id = receipt.id if hasattr(receipt, "id") else 0
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Approve Deposit", callback_data=f"adm_usdt_appr_{receipt_id}", style="success"),
            InlineKeyboardButton(text="Reject Deposit", callback_data=f"adm_usdt_rej_{receipt_id}", style="danger")
        ]
    ])
    admin_alert = (
        "<b>NEW USDT DEPOSIT SUBMISSION</b>\n"
        "────────────────────────\n"
        f"Receipt ID: <code>#{receipt_id}</code>\n"
        f"User: <code>{user_id}</code> (@{message.from_user.username or 'N/A'})\n"
        f"Network: <b>{network.upper()}</b>\n"
        f"TXID: <code>{txid}</code>\n\n"
        "Tap 'Approve Deposit' to verify and credit amount, or 'Reject Deposit' to decline."
    )
    for ch in targets:
        try:
            await message.bot.send_message(ch, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send USDT deposit alert to channel {ch}: {e}")


# =====================================================================
# VERIFY PAYMENT WITHOUT HASH (MANUAL CHECK)
# =====================================================================

@router.callback_query(F.data.startswith("usdt_nohash_"))
async def prompt_usdt_nohash_verification(call: CallbackQuery):
    network = call.data.replace("usdt_nohash_", "")
    user = await get_user_by_id(call.from_user.id)
    lang = user.language if user else "en"

    address = await get_setting(f"usdt_{network}_address", "Configured Address")

    text = (
        f"<b>VERIFY USDT TRANSFER ({network.upper()}) WITHOUT HASH</b>\n"
        "────────────────────────\n"
        f"If you transferred USDT on <b>{network.upper()}</b> to:\n"
        f"<code>{address}</code>\n"
        "but do not have or cannot copy the transaction hash, you can submit a manual verification request.\n\n"
        "Our team will check our wallet for incoming transfers and credit your balance.\n\n"
        "Tap <b>Confirm Verification Request</b> to notify administrators:"
        if lang == "en" else
        f"<b>የUSDT ዝውውር ({network.upper()}) ያለ HASH ማረጋገጫ</b>\n"
        "────────────────────────\n"
        f"በ <b>{network.upper()}</b> ወደዚህ አድራሻ፡\n\n"
        f"<code>{address}</code>\n\n"
        "ገንዘብ ልከው የትራንዛክሽን hash ማግኘት ካልቻሉ፣ ያለ hash የማረጋገጫ ጥያቄ ማቅረብ ይችላሉ።\n\n"
        "አስተዳዳሪዎቻችን የዋሌት ገቢዎችን በመፈተሽ ሒሳብዎን ይጨምራሉ።\n\n"
        "<b>ማረጋገጫውን ላክ</b> የሚለውን ቁልፍ ይጫኑ፡"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Confirm Verification Request" if lang == "en" else "ማረጋገጫውን ላክ",
            callback_data=f"usdt_confirm_nohash_{network}",
            style="success"
        )],
        [InlineKeyboardButton(
            text="< Back" if lang == "en" else "< ተመለስ",
            callback_data=f"dep_usdt_{network}",
            style="danger"
        )]
    ])
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("usdt_confirm_nohash_"))
async def process_usdt_nohash_confirm(call: CallbackQuery):
    network = call.data.replace("usdt_confirm_nohash_", "")
    user_id = call.from_user.id
    user = await get_user_by_id(user_id)
    lang = user.language if user else "en"

    import time
    fake_txid = f"nohash_{user_id}_{int(time.time())}"
    receipt = await save_payment_receipt(
        user_id=user_id,
        provider=f"usdt_{network}_manual",
        transaction_id=fake_txid,
        amount=Decimal("0.00"),
        sender_name=f"USDT Manual ({network.upper()})",
        raw_details=f"User @{call.from_user.username or 'N/A'} requested manual check on {network.upper()}",
        status="pending"
    )

    receipt_id = receipt.id if hasattr(receipt, "id") else 0
    ref_text = "Refresh Balance" if lang == "en" else "ሒሳብ አድስ"
    back_text = "< Back to Deposit" if lang == "en" else "< ወደ ክፍያ ተመለስ"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=ref_text, callback_data="refresh_wallet", style="primary"),
            InlineKeyboardButton(text=back_text, callback_data="back_to_deposit", style="danger")
        ]
    ])

    user_text = (
        f"<b>VERIFICATION REQUEST SUBMITTED</b>\n"
        "────────────────────────\n"
        f"• Reference: <code>#{receipt_id}</code>\n"
        f"• Network: <b>{network.upper()}</b>\n"
        f"• Method: <b>Manual Blockchain Inspection</b>\n\n"
        "Your request has been delivered to store administrators. We will check our wallet for incoming transfers and credit your balance shortly."
        if lang == "en" else
        f"<b>የማረጋገጫ ጥያቄ ቀርቧል</b>\n"
        "────────────────────────\n"
        f"• መለያ ቁጥር፡ <code>#{receipt_id}</code>\n"
        f"• ኔትወርክ፡ <b>{network.upper()}</b>\n"
        f"• አይነት፡ <b>ቀጥታ የዋሌት ማረጋገጫ</b>\n\n"
        "ጥያቄዎ ለአስተዳዳሪዎች ደርሷል። ገቢ የተደረገው ገንዘብ በዋሌታችን እንደተረጋገጠ ሒሳብዎ ወዲያውኑ ይሞላል።"
    )
    try:
        await call.message.edit_text(user_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer("Request sent to admin", show_alert=False)

    # Admin Channel notification with Approve / Reject buttons
    targets = get_channel_list(PAYMENTS_CHANNEL_ID or LOGS_CHANNEL_ID)
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Approve Deposit", callback_data=f"adm_usdt_appr_{receipt_id}", style="success"),
            InlineKeyboardButton(text="Reject Deposit", callback_data=f"adm_usdt_rej_{receipt_id}", style="danger")
        ]
    ])
    admin_alert = (
        "<b>MANUAL USDT DEPOSIT REQUEST (NO TXID)</b>\n"
        "────────────────────────\n"
        f"Receipt ID: <code>#{receipt_id}</code>\n"
        f"User: <code>{user_id}</code> (@{call.from_user.username or 'N/A'})\n"
        f"Network: <b>{network.upper()}</b>\n"
        "Notice: <i>Customer transferred without TXID hash. Please check your incoming transfers on blockchain explorer for this customer.</i>\n\n"
        "Tap 'Approve Deposit' to enter amount and credit balance, or 'Reject Deposit' to decline."
    )
    for ch in targets:
        try:
            await call.bot.send_message(ch, admin_alert, reply_markup=admin_kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send manual USDT deposit alert to channel {ch}: {e}")
