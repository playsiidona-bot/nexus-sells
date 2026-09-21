import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import re

# Telegram Core
raw_token: str = os.getenv("BOT_TOKEN", "").strip()
token_match = re.search(r"(\d+:[A-Za-z0-9_-]+)", raw_token)
BOT_TOKEN: str = token_match.group(1) if token_match else raw_token

OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
ADMIN_IDS_RAW: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()
]
if OWNER_ID and OWNER_ID not in ADMIN_IDS:
    ADMIN_IDS.append(OWNER_ID)

SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "support").replace("@", "").strip()

# Database
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///nexus_hub.db")

# Base Store Currency (Default: USD for international digital commerce)
BASE_CURRENCY: str = os.getenv("BASE_CURRENCY", "USD").upper().strip()
CURRENCY_SYMBOL: str = "$" if BASE_CURRENCY == "USD" else f" {BASE_CURRENCY} "

# International & Global Payments
CRYPTO_PAY_TOKEN: str = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
STARS_RATE_USD: float = float(os.getenv("STARS_RATE_USD", "0.02"))  # 1 Telegram Star = $0.02 (50 Stars = $1.00)
MIN_DEPOSIT_AMOUNT: float = float(os.getenv("MIN_DEPOSIT_AMOUNT", "1.0" if BASE_CURRENCY == "USD" else "20"))
MAX_DEPOSIT_AMOUNT: float = float(os.getenv("MAX_DEPOSIT_AMOUNT", "5000.0" if BASE_CURRENCY == "USD" else "50000"))

# Local Payment Accounts (optional, enabled if configured)
TELEBIRR_RECEIVER_PHONE: str = os.getenv("TELEBIRR_RECEIVER_PHONE", os.getenv("TELEBIRR_NUMBER", "")).strip().strip('"')
TELEBIRR_RECEIVER_NAME: str = os.getenv("TELEBIRR_RECEIVER_NAME", os.getenv("TELEBIRR_NAME", "")).strip().strip('"')
CBE_ACCOUNT_NUMBER: str = os.getenv("CBE_ACCOUNT_NUMBER", os.getenv("CBE_ACCOUNT", "")).strip().strip('"')
CBE_ACCOUNT_NAME: str = os.getenv("CBE_ACCOUNT_NAME", os.getenv("CBE_NAME", "")).strip().strip('"')

# Supplier API (AIVerse Hub / Digital Supplier)
AIVERSE_API_KEY: str = os.getenv("AIVERSE_API_KEY", "")
AIVERSE_BASE_URL: str = os.getenv("AIVERSE_BASE_URL", "https://aiversehub.store").rstrip("/")

# Referral & Growth
REFERRAL_PERCENT: float = float(os.getenv("REFERRAL_PERCENT", "5.0"))

def get_channel_list(channel_setting: str) -> List[str]:
    """Helper to parse a single or comma-separated list of channel IDs / usernames."""
    if not channel_setting:
        return []
    result = []
    for c in str(channel_setting).split(","):
        c = c.strip().strip('"').strip("'")
        if not c:
            continue
        # Auto-fix IDs where user forgot leading '-' (e.g. 1002926828033 -> -1002926828033)
        if c.startswith("100") and len(c) >= 12 and not c.startswith("-"):
            c = "-" + c
        result.append(c)
    return result

# 7. Channel Management & Logging
FORCE_JOIN_CHANNEL: str = os.getenv("FORCE_JOIN_CHANNEL", "").strip()
FORCE_JOIN_CHANNELS: List[str] = get_channel_list(os.getenv("FORCE_JOIN_CHANNELS", FORCE_JOIN_CHANNEL))

# Fallback & dedicated logging channels (supports single ID or comma-separated: -100111,-100222)
LOGS_CHANNEL_ID: str = os.getenv("LOGS_CHANNEL_ID", "").strip()
PAYMENTS_CHANNEL_ID: str = os.getenv("PAYMENTS_CHANNEL_ID", LOGS_CHANNEL_ID).strip()
ORDERS_CHANNEL_ID: str = os.getenv("ORDERS_CHANNEL_ID", LOGS_CHANNEL_ID).strip()
REVIEWS_CHANNEL_ID: str = os.getenv("REVIEWS_CHANNEL_ID", LOGS_CHANNEL_ID).strip()

# Web Server
PORT: int = int(os.getenv("PORT", "8080"))
SECRET_KEY: str = os.getenv("SECRET_KEY", "nexus-secret-key-change-me")
