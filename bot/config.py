import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Telegram Core
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
]
if OWNER_ID and OWNER_ID not in ADMIN_IDS:
    ADMIN_IDS.append(OWNER_ID)

SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "support").replace("@", "")

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///nexus_hub.db")

# Ethiopian Payments
BASE_CURRENCY: str = os.getenv("BASE_CURRENCY", "ETB")
TELEBIRR_RECEIVER_PHONE: str = os.getenv("TELEBIRR_RECEIVER_PHONE", "0900000000")
TELEBIRR_RECEIVER_NAME: str = os.getenv("TELEBIRR_RECEIVER_NAME", "Nexus Hub")
CBE_ACCOUNT_NUMBER: str = os.getenv("CBE_ACCOUNT_NUMBER", "1000000000000")
CBE_ACCOUNT_NAME: str = os.getenv("CBE_ACCOUNT_NAME", "Nexus Hub")
MIN_DEPOSIT_AMOUNT: float = float(os.getenv("MIN_DEPOSIT_AMOUNT", "20"))
MAX_DEPOSIT_AMOUNT: float = float(os.getenv("MAX_DEPOSIT_AMOUNT", "50000"))

# Supplier API
AIVERSE_API_KEY: str = os.getenv("AIVERSE_API_KEY", "")
AIVERSE_BASE_URL: str = os.getenv("AIVERSE_BASE_URL", "https://aiversehub.store").rstrip("/")

# Global Payments
STARS_RATE_ETB: float = float(os.getenv("STARS_RATE_ETB", "25.0"))
CRYPTO_PAY_TOKEN: str = os.getenv("CRYPTO_PAY_TOKEN", "")

# Referral
REFERRAL_PERCENT: float = float(os.getenv("REFERRAL_PERCENT", "5.0"))

# Channel
FORCE_JOIN_CHANNEL: str = os.getenv("FORCE_JOIN_CHANNEL", "").strip()
FORCE_JOIN_CHANNELS: List[str] = [
    c.strip() for c in os.getenv("FORCE_JOIN_CHANNELS", FORCE_JOIN_CHANNEL).split(",") if c.strip()
]
LOGS_CHANNEL_ID: str = os.getenv("LOGS_CHANNEL_ID", "").strip()
REVIEWS_CHANNEL_ID: str = os.getenv("REVIEWS_CHANNEL_ID", "").strip()

# Web Server
PORT: int = int(os.getenv("PORT", "8080"))
SECRET_KEY: str = os.getenv("SECRET_KEY", "nexus-secret-key-change-me")
