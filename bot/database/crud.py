import uuid
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, update, delete, func
from bot.database.session import async_session
from bot.database.models import (
    User, Category, Product, ProductStock, CartItem, Order, PromoCode, PaymentReceipt, Review,
    RestockSubscription, SupportTicket
)
from bot.config import ADMIN_IDS, OWNER_ID, REFERRAL_PERCENT, BASE_CURRENCY


async def get_or_create_user(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: str = "Customer",
    referrer_id: Optional[int] = None
) -> User:
    """Fetch existing user or register new user."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()

        if user:
            # Update username if changed
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            await session.commit()
            return user

        # Determine role
        role = "owner" if telegram_id == OWNER_ID else ("admin" if telegram_id in ADMIN_IDS else "user")
        valid_referrer = referrer_id if (referrer_id and referrer_id != telegram_id) else None

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            role=role,
            referrer_id=valid_referrer,
            balance=Decimal("0.00")
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def set_user_language(telegram_id: int, language: str) -> bool:
    async with async_session() as session:
        stmt = update(User).where(User.telegram_id == telegram_id).values(language=language)
        await session.execute(stmt)
        await session.commit()
        return True


async def get_user_by_id(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def add_user_balance(telegram_id: int, amount: Decimal) -> Tuple[bool, Decimal]:
    """Atomically add balance to user."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == telegram_id).with_for_update()
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return False, Decimal("0.00")

        user.balance = Decimal(str(user.balance)) + Decimal(str(amount))
        new_balance = user.balance
        await session.commit()
        return True, new_balance


# =====================================================================
# CATALOG & PRODUCTS
# =====================================================================

async def get_all_categories() -> List[Category]:
    async with async_session() as session:
        stmt = select(Category).order_by(Category.display_order, Category.id)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def create_category(name: str, icon: str = "📦") -> Category:
    async with async_session() as session:
        cat = Category(name=name, icon=icon)
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return cat


async def get_products_by_category(category_id: int) -> List[Product]:
    async with async_session() as session:
        stmt = select(Product).where(
            Product.category_id == category_id,
            Product.is_active == True
        ).order_by(Product.id)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def get_product_by_id(product_id: int) -> Optional[Product]:
    async with async_session() as session:
        stmt = select(Product).where(Product.id == product_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def get_product_stock_count(product_id: int) -> int:
    """Return available stock units or 999 for API/Infinity items."""
    async with async_session() as session:
        product = (await session.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
        if not product:
            return 0
        if product.delivery_type == "api":
            return 999  # External API available

        # Check infinity stock
        inf_stmt = select(func.count(ProductStock.id)).where(
            ProductStock.product_id == product_id,
            ProductStock.is_infinity == True
        )
        if (await session.execute(inf_stmt)).scalar() > 0:
            return 999

        count_stmt = select(func.count(ProductStock.id)).where(
            ProductStock.product_id == product_id,
            ProductStock.is_used == False
        )
        return int((await session.execute(count_stmt)).scalar() or 0)


async def add_product_stock_items(product_id: int, items: List[str], is_infinity: bool = False) -> int:
    async with async_session() as session:
        added = 0
        for item in items:
            val = item.strip()
            if val:
                stock = ProductStock(product_id=product_id, value=val, is_infinity=is_infinity)
                session.add(stock)
                added += 1
        await session.commit()
        return added


# =====================================================================
# CART OPERATIONS
# =====================================================================

async def get_cart(user_id: int) -> List[Dict[str, Any]]:
    async with async_session() as session:
        stmt = select(CartItem, Product).join(Product, CartItem.product_id == Product.id).where(
            CartItem.user_id == user_id
        )
        res = await session.execute(stmt)
        items = []
        for cart_item, product in res.all():
            unit_price = Decimal(str(product.sale_price or product.price))
            total_price = unit_price * cart_item.quantity
            items.append({
                "cart_id": cart_item.id,
                "product_id": product.id,
                "name": product.name,
                "quantity": cart_item.quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "delivery_type": product.delivery_type,
            })
        return items


async def add_to_cart(user_id: int, product_id: int, quantity: int = 1) -> bool:
    async with async_session() as session:
        stmt = select(CartItem).where(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        )
        item = (await session.execute(stmt)).scalar_one_or_none()
        if item:
            item.quantity += quantity
        else:
            session.add(CartItem(user_id=user_id, product_id=product_id, quantity=quantity))
        await session.commit()
        return True


async def update_cart_qty(cart_id: int, quantity: int) -> bool:
    async with async_session() as session:
        if quantity <= 0:
            await session.execute(delete(CartItem).where(CartItem.id == cart_id))
        else:
            await session.execute(update(CartItem).where(CartItem.id == cart_id).values(quantity=quantity))
        await session.commit()
        return True


async def clear_cart(user_id: int) -> bool:
    async with async_session() as session:
        await session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await session.commit()
        return True


# =====================================================================
# ORDERS & CHECKOUT
# =====================================================================

async def checkout_cart_atomic(
    user_id: int,
    promo_code_str: Optional[str] = None
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Atomically purchases all items in the user's cart.
    Returns: (success, message, list_of_delivered_orders)
    """
    async with async_session() as session:
        # Lock user
        user_stmt = select(User).where(User.telegram_id == user_id).with_for_update()
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        if not user:
            return False, "user_not_found", []

        cart_stmt = select(CartItem, Product).join(Product, CartItem.product_id == Product.id).where(
            CartItem.user_id == user_id
        )
        cart_rows = (await session.execute(cart_stmt)).all()
        if not cart_rows:
            return False, "cart_empty", []

        # Calculate total price
        subtotal = Decimal("0.00")
        for ci, p in cart_rows:
            effective_price = Decimal(str(p.sale_price or p.price))
            subtotal += effective_price * ci.quantity

        discount = Decimal("0.00")
        if promo_code_str:
            promo_stmt = select(PromoCode).where(
                PromoCode.code == promo_code_str.upper(),
                PromoCode.is_active == True
            ).with_for_update()
            promo = (await session.execute(promo_stmt)).scalar_one_or_none()
            if promo and promo.current_uses < promo.max_uses:
                if promo.discount_type == "percent":
                    discount = (subtotal * Decimal(str(promo.discount_value)) / Decimal("100")).quantize(Decimal("0.01"))
                else:
                    discount = min(Decimal(str(promo.discount_value)), subtotal)
                promo.current_uses += 1

        total_due = max(subtotal - discount, Decimal("0.00"))
        if Decimal(str(user.balance)) < total_due:
            return False, "insufficient_balance", []

        # Deduct balance
        user.balance = Decimal(str(user.balance)) - total_due

        delivered_orders = []
        for ci, product in cart_rows:
            order_code = f"NX-{uuid.uuid4().hex[:8].upper()}"
            delivered_payload = ""

            if product.delivery_type == "stock":
                # Check infinity
                inf_stock = (await session.execute(
                    select(ProductStock).where(
                        ProductStock.product_id == product.id,
                        ProductStock.is_infinity == True
                    )
                )).scalar_one_or_none()

                if inf_stock:
                    delivered_payload = f"🔗 {inf_stock.value}"
                else:
                    # Pick limited rows
                    stock_rows = (await session.execute(
                        select(ProductStock).where(
                            ProductStock.product_id == product.id,
                            ProductStock.is_used == False
                        ).limit(ci.quantity).with_for_update()
                    )).scalars().all()

                    if len(stock_rows) < ci.quantity:
                        # Stock shortage
                        await session.rollback()
                        return False, f"out_of_stock: {product.name}", []

                    keys = []
                    for s in stock_rows:
                        s.is_used = True
                        keys.append(s.value)
                    delivered_payload = "\n".join([f"🔑 <code>{k}</code>" for k in keys])
            else:
                delivered_payload = f"⚡ Service ID: {product.service_id} (API Fulfilled)"

            item_price = (Decimal(str(product.sale_price or product.price)) * ci.quantity).quantize(Decimal("0.01"))

            new_order = Order(
                order_code=order_code,
                user_id=user_id,
                product_name=product.name,
                quantity=ci.quantity,
                total_price=item_price,
                currency=BASE_CURRENCY,
                delivered_data=delivered_payload,
                status="completed"
            )
            session.add(new_order)
            delivered_orders.append({
                "order_code": order_code,
                "product_name": product.name,
                "quantity": ci.quantity,
                "price": item_price,
                "delivered_data": delivered_payload
            })

        # Clear cart
        await session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await session.commit()
        return True, "success", delivered_orders


async def get_user_orders(user_id: int, limit: int = 10) -> List[Order]:
    async with async_session() as session:
        stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


# =====================================================================
# RECEIPTS & REVIEWS
# =====================================================================

async def check_transaction_exists(transaction_id: str) -> bool:
    async with async_session() as session:
        stmt = select(PaymentReceipt.id).where(PaymentReceipt.transaction_id == transaction_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None


async def save_payment_receipt(
    user_id: int,
    provider: str,
    transaction_id: str,
    amount: Decimal,
    sender_name: str = "",
    raw_details: str = "",
    status: str = "approved"
) -> bool:
    async with async_session() as session:
        receipt = PaymentReceipt(
            user_id=user_id,
            provider=provider,
            transaction_id=transaction_id,
            amount=amount,
            sender_name=sender_name,
            raw_details=raw_details,
            status=status
        )
        session.add(receipt)
        await session.commit()
        return True


async def add_review(user_id: int, product_id: int, rating: int, comment: str = "") -> bool:
    async with async_session() as session:
        rev = Review(user_id=user_id, product_id=product_id, rating=rating, comment=comment)
        session.add(rev)
        await session.commit()
        return True


async def get_product_reviews(product_id: int, limit: int = 5) -> List[Review]:
    async with async_session() as session:
        stmt = select(Review).where(Review.product_id == product_id).order_by(Review.id.desc()).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


# =====================================================================
# RESTOCK NOTIFICATIONS & SUPPORT TICKETS
# =====================================================================

async def subscribe_restock(user_id: int, product_id: int) -> bool:
    """Subscribe user to restock alert for a product."""
    async with async_session() as session:
        stmt = select(RestockSubscription).where(
            RestockSubscription.user_id == user_id,
            RestockSubscription.product_id == product_id
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return False  # Already subscribed
        session.add(RestockSubscription(user_id=user_id, product_id=product_id))
        await session.commit()
        return True


async def get_and_clear_restock_subscribers(product_id: int) -> List[int]:
    """Retrieve all subscribed user IDs for a product and delete the subscriptions."""
    async with async_session() as session:
        stmt = select(RestockSubscription.user_id).where(RestockSubscription.product_id == product_id)
        user_ids = list((await session.execute(stmt)).scalars().all())
        if user_ids:
            await session.execute(delete(RestockSubscription).where(RestockSubscription.product_id == product_id))
            await session.commit()
        return user_ids


async def get_order_by_id(order_id: int) -> Optional[Order]:
    async with async_session() as session:
        stmt = select(Order).where(Order.id == order_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def create_support_ticket(
    user_id: int,
    order_id: int,
    product_name: str,
    issue_description: str
) -> SupportTicket:
    async with async_session() as session:
        ticket_code = f"TCK-{uuid.uuid4().hex[:6].upper()}"
        ticket = SupportTicket(
            ticket_code=ticket_code,
            user_id=user_id,
            order_id=order_id,
            product_name=product_name,
            issue_description=issue_description,
            status="open"
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)
        return ticket


async def get_ticket_by_code(ticket_code: str) -> Optional[SupportTicket]:
    async with async_session() as session:
        stmt = select(SupportTicket).where(SupportTicket.ticket_code == ticket_code)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def replace_key_for_ticket(ticket_code: str) -> Tuple[bool, str, Optional[str]]:
    """
    Finds a new available key for the ticket's product, delivers it, and closes the ticket.
    Returns (success, message, new_key_value)
    """
    async with async_session() as session:
        ticket_stmt = select(SupportTicket).where(SupportTicket.ticket_code == ticket_code).with_for_update()
        ticket = (await session.execute(ticket_stmt)).scalar_one_or_none()
        if not ticket or ticket.status != "open":
            return False, "ticket_not_open", None

        # Fetch product
        prod_stmt = select(Product).where(Product.name == ticket.product_name)
        prod = (await session.execute(prod_stmt)).scalars().first()
        if not prod:
            return False, "product_not_found", None

        # Pick next unused stock key
        stock_stmt = select(ProductStock).where(
            ProductStock.product_id == prod.id,
            ProductStock.is_used == False
        ).limit(1).with_for_update()
        stock = (await session.execute(stock_stmt)).scalar_one_or_none()
        if not stock:
            return False, "no_replacement_stock_available", None

        stock.is_used = True
        ticket.status = "replaced"
        new_key = stock.value
        await session.commit()
        return True, "key_replaced", new_key


async def refund_ticket(ticket_code: str) -> Tuple[bool, str, Decimal]:
    """
    Refunds the order cost back to the user's wallet balance.
    Returns (success, message, refunded_amount)
    """
    async with async_session() as session:
        ticket_stmt = select(SupportTicket).where(SupportTicket.ticket_code == ticket_code).with_for_update()
        ticket = (await session.execute(ticket_stmt)).scalar_one_or_none()
        if not ticket or ticket.status != "open":
            return False, "ticket_not_open", Decimal("0.00")

        order_stmt = select(Order).where(Order.id == ticket.order_id)
        order = (await session.execute(order_stmt)).scalar_one_or_none()
        if not order:
            return False, "order_not_found", Decimal("0.00")

        refund_amount = Decimal(str(order.total_price))

        # Add to user balance
        user_stmt = select(User).where(User.telegram_id == ticket.user_id).with_for_update()
        user = (await session.execute(user_stmt)).scalar_one_or_none()
        if not user:
            return False, "user_not_found", Decimal("0.00")

        user.balance = Decimal(str(user.balance)) + refund_amount
        ticket.status = "refunded"
        await session.commit()
        return True, "refunded_successfully", refund_amount


async def reject_ticket(ticket_code: str) -> bool:
    async with async_session() as session:
        ticket_stmt = select(SupportTicket).where(SupportTicket.ticket_code == ticket_code).with_for_update()
        ticket = (await session.execute(ticket_stmt)).scalar_one_or_none()
        if not ticket or ticket.status != "open":
            return False
        ticket.status = "rejected"
        await session.commit()
        return True

