import uuid
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, update, delete, func
from bot.database.session import async_session
from bot.database.models import (
    User, Category, Product, ProductStock, CartItem, Order, PromoCode, PaymentReceipt, Review,
    RestockSubscription, SupportTicket, BotSetting
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

async def get_all_categories(active_only: bool = False) -> List[Category]:
    async with async_session() as session:
        stmt = select(Category)
        if active_only:
            stmt = stmt.where(Category.is_active == True)
        stmt = stmt.order_by(Category.display_order, Category.id)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def get_category_by_id(category_id: int) -> Optional[Category]:
    async with async_session() as session:
        stmt = select(Category).where(Category.id == category_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def update_category(
    category_id: int,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    display_order: Optional[int] = None
) -> Optional[Category]:
    async with async_session() as session:
        stmt = select(Category).where(Category.id == category_id).with_for_update()
        cat = (await session.execute(stmt)).scalar_one_or_none()
        if not cat:
            return None
        if name is not None:
            cat.name = name
        if is_active is not None:
            cat.is_active = is_active
        if display_order is not None:
            cat.display_order = display_order
        await session.commit()
        await session.refresh(cat)
        return cat


async def delete_category(category_id: int) -> bool:
    async with async_session() as session:
        stmt = delete(Category).where(Category.id == category_id)
        await session.execute(stmt)
        await session.commit()
        return True


async def create_category(name: str, icon: str = "📦") -> Category:
    async with async_session() as session:
        cat = Category(name=name, icon=icon, is_active=True)
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return cat


async def get_products_by_category(category_id: int, active_only: bool = True) -> List[Product]:
    async with async_session() as session:
        stmt = select(Product).where(Product.category_id == category_id)
        if active_only:
            stmt = stmt.where(Product.is_active == True)
        stmt = stmt.order_by(Product.id)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def get_all_products(limit: int = 50, active_only: bool = True) -> List[Product]:
    async with async_session() as session:
        stmt = select(Product)
        if active_only:
            stmt = stmt.where(Product.is_active == True)
        stmt = stmt.order_by(Product.id).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def get_product_by_id(product_id: int) -> Optional[Product]:
    async with async_session() as session:
        stmt = select(Product).where(Product.id == product_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def update_product_details(
    product_id: int,
    name: Optional[str] = None,
    price: Optional[Decimal] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[Product]:
    """Admin update for standard product properties."""
    async with async_session() as session:
        stmt = select(Product).where(Product.id == product_id).with_for_update()
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            return None
        if name is not None:
            product.name = name
        if price is not None:
            product.price = price
        if description is not None:
            product.description = description
        if is_active is not None:
            product.is_active = is_active
        await session.commit()
        await session.refresh(product)
        return product


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
    import re
    async with async_session() as session:
        added = 0
        for item in items:
            sub_items = [x.strip() for x in re.split(r'[\n,]+', str(item)) if x.strip()]
            for val in sub_items:
                stock = ProductStock(product_id=product_id, value=val, is_infinity=is_infinity)
                session.add(stock)
                added += 1
        await session.commit()
        return added


# =====================================================================
# API PRODUCTS & ADMIN REVIEW STAGING
# =====================================================================

async def sync_aiverse_products(services: List[Dict[str, Any]], default_markup: Decimal = Decimal("1.25")) -> Dict[str, int]:
    """
    Sync products from AIVerse Hub into the database.
    CRITICAL: Any new products imported from the API are set with is_active = False
    so that the Admin must review, adjust price/details, and approve before users can see them.
    """
    async with async_session() as session:
        # Ensure a default category exists for imported API services
        cat_stmt = select(Category).where(Category.name.in_(["API Services", "Digital Subscriptions", "ዲጂታል አገልግሎቶች"]))
        default_cat = (await session.execute(cat_stmt)).scalars().first()
        if not default_cat:
            default_cat = Category(name="Digital Subscriptions", icon="🌐", display_order=99)
            session.add(default_cat)
            await session.commit()
            await session.refresh(default_cat)

        created_count = 0
        updated_count = 0

        for s in services:
            sid = str(s.get("service_id", "")).strip()
            if not sid:
                continue

            name = str(s.get("name", f"Service {sid}")).strip()
            cost = Decimal(str(s.get("price", "0.00")))
            stock = int(s.get("stock", 0))

            prod_stmt = select(Product).where(
                Product.delivery_type == "api",
                Product.service_id == sid
            )
            existing = (await session.execute(prod_stmt)).scalar_one_or_none()

            if existing:
                # Update wholesale cost and live stock, but PRESERVE admin's custom price, name and is_active approval state
                existing.wholesale_price = cost
                existing.api_stock = stock
                updated_count += 1
            else:
                # NEW item from API: created as INACTIVE (Pending Admin Review)
                # Keep customer description clean without supplier IDs or wholesale costs!
                suggested_retail = (cost * default_markup).quantize(Decimal("0.01"))
                needs_input = any(w in name.lower() for w in ["username", "telegram", "uid", "link", "channel", "boost", "account", "profile"])
                placeholder = "@username" if ("telegram" in name.lower() or "username" in name.lower()) else "Target Account / ID"

                new_prod = Product(
                    category_id=default_cat.id,
                    name=name,
                    description="Official digital activation service with automated instant delivery.",
                    price=suggested_retail,
                    wholesale_price=cost,
                    api_stock=stock,
                    delivery_type="api",
                    service_id=sid,
                    requires_input=needs_input,
                    input_placeholder=placeholder,
                    is_active=False  # MUST be reviewed & approved by admin first!
                )
                session.add(new_prod)
                created_count += 1

        await session.commit()
        return {"created": created_count, "updated": updated_count}


async def create_product(
    category_id: int,
    name: str,
    price: Decimal,
    description: str = "",
    delivery_type: str = "stock",
    requires_input: bool = False,
    input_placeholder: str = "@username",
    input_label: str = "Target Account / Username",
    service_id: Optional[str] = None,
    wholesale_price: Optional[Decimal] = None,
    is_active: bool = True
) -> Product:
    """Create a new manual or API product in the database."""
    async with async_session() as session:
        prod = Product(
            category_id=category_id,
            name=name,
            description=description,
            price=price,
            delivery_type=delivery_type,
            requires_input=requires_input,
            input_placeholder=input_placeholder,
            input_label=input_label,
            service_id=service_id,
            wholesale_price=wholesale_price or Decimal("0.00"),
            is_active=is_active
        )
        session.add(prod)
        await session.commit()
        await session.refresh(prod)
        return prod


async def get_pending_api_products(limit: int = 50) -> List[Product]:
    """Fetch API products that require admin review and approval."""
    async with async_session() as session:
        stmt = select(Product).where(
            Product.delivery_type == "api",
            Product.is_active == False
        ).order_by(Product.id.desc()).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def get_approved_api_products(limit: int = 50) -> List[Product]:
    """Fetch API products that have been approved and published."""
    async with async_session() as session:
        stmt = select(Product).where(
            Product.delivery_type == "api",
            Product.is_active == True
        ).order_by(Product.id.desc()).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def update_api_product_review(
    product_id: int,
    price: Optional[Decimal] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    requires_input: Optional[bool] = None,
    input_placeholder: Optional[str] = None
) -> Optional[Product]:
    """Admin adjustments: change retail price, name, category, input requirements, or approve/hide."""
    async with async_session() as session:
        stmt = select(Product).where(Product.id == product_id).with_for_update()
        product = (await session.execute(stmt)).scalar_one_or_none()
        if not product:
            return None

        if price is not None:
            product.price = price
        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if category_id is not None:
            product.category_id = category_id
        if is_active is not None:
            product.is_active = is_active
        if requires_input is not None:
            product.requires_input = requires_input
        if input_placeholder is not None:
            product.input_placeholder = input_placeholder

        await session.commit()
        await session.refresh(product)
        return product


async def delete_product(product_id: int) -> bool:
    async with async_session() as session:
        stmt = delete(Product).where(Product.id == product_id)
        await session.execute(stmt)
        await session.commit()
        return True


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
                "requires_input": product.requires_input,
                "input_placeholder": product.input_placeholder,
                "input_label": product.input_label,
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
    promo_code_str: Optional[str] = None,
    customer_inputs: Optional[Dict[int, str]] = None
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
                    delivered_payload = f"Access Details: {inf_stock.value}"
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
                    delivered_payload = "\n".join([f"Key: <code>{k}</code>" for k in keys])
            else:
                from bot.services.aiverse_client import aiverse_client
                api_res = await aiverse_client.create_order(
                    service_id=str(product.service_id),
                    quantity=ci.quantity
                )
                if not api_res.get("success", False):
                    err_msg = api_res.get("error", "Delivery failed. Please contact support.")
                    await session.rollback()
                    return False, f"Delivery Notice: {err_msg}", []

                prods_delivered = api_res.get("products", [])
                if prods_delivered:
                    codes_str = "\n".join([f"<code>{p}</code>" for p in prods_delivered])
                    delivered_payload = f"Digital License / Credentials:\n{codes_str}"
                else:
                    delivered_payload = f"Order Ref: <code>{api_res.get('order_id', 'N/A')}</code>\nStatus: Activated Successfully"

            item_price = (Decimal(str(product.sale_price or product.price)) * ci.quantity).quantize(Decimal("0.01"))
            c_input = (customer_inputs or {}).get(product.id)

            new_order = Order(
                order_code=order_code,
                user_id=user_id,
                product_name=product.name,
                quantity=ci.quantity,
                total_price=item_price,
                currency=BASE_CURRENCY,
                delivered_data=delivered_payload,
                customer_input=c_input,
                status="completed"
            )
            session.add(new_order)
            delivered_orders.append({
                "order_code": order_code,
                "product_name": product.name,
                "quantity": ci.quantity,
                "price": item_price,
                "delivered_data": delivered_payload,
                "customer_input": c_input
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
) -> PaymentReceipt:
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
        await session.refresh(receipt)
        return receipt


async def get_payment_receipt_by_id(receipt_id: int) -> Optional[PaymentReceipt]:
    async with async_session() as session:
        stmt = select(PaymentReceipt).where(PaymentReceipt.id == receipt_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


async def update_payment_receipt(receipt_id: int, status: str, amount: Optional[Decimal] = None) -> Optional[PaymentReceipt]:
    async with async_session() as session:
        stmt = select(PaymentReceipt).where(PaymentReceipt.id == receipt_id)
        res = await session.execute(stmt)
        receipt = res.scalar_one_or_none()
        if not receipt:
            return None
        receipt.status = status
        if amount is not None:
            receipt.amount = amount
        await session.commit()
        await session.refresh(receipt)
        return receipt


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


# =====================================================================
# DYNAMIC BOT SETTINGS & CUSTOMIZATION
# =====================================================================

_SETTINGS_CACHE: Dict[str, str] = {}


async def get_setting(key: str, default: str = "") -> str:
    """Retrieve dynamic bot setting from cache/database."""
    if key in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[key]

    async with async_session() as session:
        stmt = select(BotSetting.value).where(BotSetting.key == key)
        val = (await session.execute(stmt)).scalar_one_or_none()
        if val is not None:
            _SETTINGS_CACHE[key] = val
            return val
        return default


async def set_setting(key: str, value: str, description: str = "") -> bool:
    """Set or update dynamic bot setting and bust cache."""
    async with async_session() as session:
        stmt = select(BotSetting).where(BotSetting.key == key)
        setting = (await session.execute(stmt)).scalar_one_or_none()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            session.add(BotSetting(key=key, value=value, description=description))
        await session.commit()
        _SETTINGS_CACHE[key] = value
        return True


async def get_all_settings() -> Dict[str, str]:
    """Retrieve all customized settings."""
    async with async_session() as session:
        stmt = select(BotSetting)
        rows = (await session.execute(stmt)).scalars().all()
        res = {}
        for r in rows:
            res[r.key] = r.value
            _SETTINGS_CACHE[r.key] = r.value
        return res


# =====================================================================
# USER MANAGEMENT & CONTROLLING
# =====================================================================

async def get_users_paged(page: int = 1, per_page: int = 10, search: Optional[str] = None) -> Tuple[List[User], int]:
    """Retrieve paginated users with optional search."""
    async with async_session() as session:
        base_query = select(User)
        count_query = select(func.count(User.telegram_id))

        if search:
            search_str = search.strip()
            if search_str.isdigit():
                cond = (User.telegram_id == int(search_str)) | (User.username.ilike(f"%{search_str}%"))
            else:
                clean = search_str.lstrip("@")
                cond = User.username.ilike(f"%{clean}%") | User.first_name.ilike(f"%{clean}%")
            base_query = base_query.where(cond)
            count_query = count_query.where(cond)

        total = (await session.execute(count_query)).scalar() or 0
        offset = max(0, (page - 1) * per_page)
        stmt = base_query.order_by(User.created_at.desc()).offset(offset).limit(per_page)
        res = await session.execute(stmt)
        return list(res.scalars().all()), total


async def set_user_ban_status(user_id: int, is_banned: bool) -> Optional[User]:
    """Toggle or set user ban status."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return None
        user.is_banned = is_banned
        await session.commit()
        await session.refresh(user)
        return user


async def adjust_user_balance(user_id: int, delta: Decimal) -> Tuple[bool, Decimal]:
    """Add or deduct user balance atomically."""
    async with async_session() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            return False, Decimal("0.00")
        current = Decimal(str(user.balance or 0.00))
        new_bal = current + delta
        if new_bal < Decimal("0.00"):
            new_bal = Decimal("0.00")
        user.balance = new_bal
        await session.commit()
        return True, new_bal


async def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Retrieve user order count, total expenditure, and referral count."""
    async with async_session() as session:
        order_count = (await session.execute(
            select(func.count(Order.id)).where(Order.user_id == user_id)
        )).scalar() or 0
        total_spent = (await session.execute(
            select(func.sum(Order.total_price)).where(Order.user_id == user_id)
        )).scalar() or Decimal("0.00")
        referral_count = (await session.execute(
            select(func.count(User.telegram_id)).where(User.referrer_id == user_id)
        )).scalar() or 0
        return {
            "order_count": order_count,
            "total_spent": total_spent,
            "referral_count": referral_count
        }


