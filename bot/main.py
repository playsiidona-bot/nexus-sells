import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from bot.config import BOT_TOKEN, PORT
from bot.database.session import init_db
from bot.middleware.anti_flood import AntiFloodMiddleware
from bot.middleware.force_join import ForceJoinMiddleware
from bot.web.server import start_health_check_server

# Import Handlers
from bot.handlers.user.start import router as start_router
from bot.handlers.user.catalog import router as catalog_router
from bot.handlers.user.cart import router as cart_router
from bot.handlers.user.wallet import router as wallet_router
from bot.handlers.user.orders import router as orders_router
from bot.handlers.user.referral import router as referral_router
from bot.handlers.admin.main import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Please set BOT_TOKEN in .env.")
        sys.exit(1)

    logger.info("Initializing Nexus Hub Bot...")

    # 1. Initialize Database
    await init_db()

    # 2. Start Cloud Keep-Alive Web Server
    start_health_check_server(PORT)

    # 3. Setup Bot & Dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # 4. Register Middlewares
    dp.message.outer_middleware(AntiFloodMiddleware())
    dp.callback_query.outer_middleware(AntiFloodMiddleware())
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    # 5. Register Routers
    dp.include_router(start_router)
    dp.include_router(catalog_router)
    dp.include_router(cart_router)
    dp.include_router(wallet_router)
    dp.include_router(orders_router)
    dp.include_router(referral_router)
    dp.include_router(admin_router)

    logger.info("Nexus Hub Bot is now running and polling for updates!")

    try:
        masked_token = f"{BOT_TOKEN[:6]}...{BOT_TOKEN[-4:]}" if len(BOT_TOKEN) > 10 else "***"
        logger.info(f"Connecting to Telegram with token {masked_token}...")
        me = await bot.get_me()
        logger.info(f"Bot connected successfully as @{me.username} ({me.first_name})!")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        if "unauthorized" in str(e).lower():
            logger.error(
                "❌ FATAL: Telegram returned 'Unauthorized' (401)! "
                "The BOT_TOKEN in Render Environment variables is invalid or revoked. "
                "Please get the correct token from @BotFather in Telegram and update BOT_TOKEN in Render Dashboard -> Environment."
            )
        else:
            logger.error(f"Error while running bot: {e}")
        sys.exit(1)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
