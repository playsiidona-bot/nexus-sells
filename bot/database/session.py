import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from bot.config import DATABASE_URL
from bot.database.models import Base

logger = logging.getLogger(__name__)

# Handle SQLite vs PostgreSQL arguments
engine_kwargs = {"echo": False}
if "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


from sqlalchemy import text

async def init_db():
    """Create all tables if they don't exist and run safe schema updates."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        product_cols = [
            "wholesale_price NUMERIC(12, 2) DEFAULT 0.00",
            "api_stock INTEGER DEFAULT 0",
            "requires_input BOOLEAN DEFAULT 0",
            "input_placeholder VARCHAR(128) DEFAULT '@username'",
            "input_label VARCHAR(256) DEFAULT 'Target Account / Username'"
        ]
        for col_def in product_cols:
            try:
                await conn.execute(text(f"ALTER TABLE products ADD COLUMN {col_def}"))
            except Exception:
                pass

        try:
            await conn.execute(text("ALTER TABLE orders ADD COLUMN customer_input TEXT"))
        except Exception:
            pass

        try:
            await conn.execute(text("ALTER TABLE categories ADD COLUMN is_active BOOLEAN DEFAULT 1"))
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
