import logging
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text
from bot.config import DATABASE_URL
from bot.database.models import Base

logger = logging.getLogger(__name__)


def build_engine(raw_url: str):
    url = (raw_url or "sqlite+aiosqlite:///nexus_hub.db").strip().strip('"').strip("'")
    engine_kwargs = {"echo": False}

    if "sqlite" in url:
        if not url.startswith("sqlite+aiosqlite://"):
            url = re.sub(r"^sqlite:\/\/", "sqlite+aiosqlite://", url)
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL / Supabase
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        # Clean query parameters incompatible with asyncpg (e.g., sslmode=require)
        try:
            parsed = urlparse(url)
            query_dict = parse_qs(parsed.query)
            query_dict.pop("sslmode", None)
            query_dict.pop("ssl", None)
            query_dict.pop("channel_binding", None)
            new_query = urlencode(query_dict, doseq=True)
            url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
        except Exception:
            pass

        # Configure SSL context and statement cache for Supabase / PgBouncer pooler
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        is_pooler = ":6543" in url or "pooler.supabase.com" in url
        connect_args = {
            "ssl": ssl_ctx,
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0
        }
        engine_kwargs["connect_args"] = connect_args
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 300

        if is_pooler:
            # Supabase Transaction Pooler (port 6543) requires NullPool
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

    return create_async_engine(url, **engine_kwargs)


engine = build_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    """Create all tables if they don't exist and run safe schema updates."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        product_cols = [
            ("wholesale_price", "NUMERIC(12, 2) DEFAULT 0.00"),
            ("api_stock", "INTEGER DEFAULT 0"),
            ("requires_input", "BOOLEAN DEFAULT FALSE"),
            ("input_placeholder", "VARCHAR(128) DEFAULT '@username'"),
            ("input_label", "VARCHAR(256) DEFAULT 'Target Account / Username'")
        ]
        for col_name, col_def in product_cols:
            try:
                await conn.execute(text(f"ALTER TABLE products ADD COLUMN {col_name} {col_def}"))
            except Exception:
                pass

        try:
            await conn.execute(text("ALTER TABLE orders ADD COLUMN customer_input TEXT"))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE categories ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE payment_receipts ADD COLUMN receipt_url TEXT"))
        except Exception:
            pass

        try:
            await conn.execute(text(
                "UPDATE products SET description = 'Official digital activation service with automated instant delivery.' "
                "WHERE description LIKE '%Supplier ID%' OR description LIKE '%Wholesale Cost%'"
            ))
        except Exception:
            pass

    logger.info("Database initialized successfully.")
