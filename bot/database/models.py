from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Numeric, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), default="Customer")
    language = Column(String(10), default="en")  # "en" or "am"
    balance = Column(Numeric(12, 2), default=0.00, nullable=False)
    referrer_id = Column(BigInteger, nullable=True, index=True)
    is_banned = Column(Boolean, default=False)
    role = Column(String(32), default="user")  # "user", "admin", "owner"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user")
    reviews = relationship("Review", back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False)
    icon = Column(String(16), default="📦")
    display_order = Column(Integer, default=0)

    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")
    price = Column(Numeric(12, 2), nullable=False)
    sale_price = Column(Numeric(12, 2), nullable=True)
    delivery_type = Column(String(32), default="stock")  # "stock" (local keys) or "api" (AIVerse Hub)
    service_id = Column(String(64), nullable=True)  # AIVerse Hub service ID if delivery_type == "api"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    category = relationship("Category", back_populates="products")
    stock_items = relationship("ProductStock", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")


class ProductStock(Base):
    __tablename__ = "product_stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(Text, nullable=False)  # License key, credentials, or link
    is_infinity = Column(Boolean, default=False)
    is_used = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="stock_items")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_code = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    product_name = Column(String(256), nullable=False)
    quantity = Column(Integer, default=1)
    total_price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="ETB")
    delivered_data = Column(Text, nullable=True)  # Keys, accounts, or details
    status = Column(String(32), default="completed")  # "completed", "pending", "failed"
    api_order_id = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="orders")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    discount_type = Column(String(16), default="percent")  # "percent" or "fixed"
    discount_value = Column(Numeric(10, 2), nullable=False)
    max_uses = Column(Integer, default=100)
    current_uses = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)  # "telebirr", "cbe", "stars", "crypto"
    transaction_id = Column(String(128), unique=True, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="ETB")
    sender_name = Column(String(128), nullable=True)
    status = Column(String(32), default="approved")  # "approved", "pending", "rejected"
    raw_details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1 to 5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="reviews")
    product = relationship("Product", back_populates="reviews")


class RestockSubscription(Base):
    __tablename__ = "restock_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_code = Column(String(32), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_name = Column(String(256), nullable=False)
    issue_description = Column(Text, nullable=False)
    status = Column(String(32), default="open")  # "open", "replaced", "refunded", "rejected"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key = Column(String(64), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(String(256), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


