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
        for col_def in ["wholesale_price NUMERIC(12, 2) DEFAULT 0.00", "api_stock INTEGER DEFAULT 0"]:
            try:
                await conn.execute(text(f"ALTER TABLE products ADD COLUMN {col_def}"))
            except Exception:
                pass
    logger.info("Database initialized successfully.")
