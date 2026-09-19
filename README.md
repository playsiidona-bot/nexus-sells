# 🚀 Nexus Hub Bot (aiogram 3.22+ & SQLAlchemy 2.0)

**Nexus Hub Bot** is a modern, production-ready Telegram Digital Commerce & Reseller Platform fusing the best features of **EthioCart** (automated Telebirr & CBE receipt verification, AIVerse Hub Supplier API) and **Telegram-shop** (shopping cart, digital key/account inventory management, promo codes, multi-payment, and dual-language Amharic/English interface).

---

## 🌟 Key Features

1. **Local Ethiopian Automated Payments**:
   - **Telebirr** instant receipt URL verification (`transactioninfo.ethiotelecom.et`).
   - **Commercial Bank of Ethiopia (CBE)** mobile banking receipt validation (`mbreciept.cbe.com.et`).
   - Automatic amount and transaction ID parsing, duplicate protection, and referral bonus crediting.
2. **Shopping Cart & Checkout**:
   - Add multiple items with quantities.
   - Adjust quantities or clear cart.
   - Promo codes (percentage and fixed discounts).
   - Atomic checkout with row locking (`with_for_update`) to prevent double-spending.
3. **Dual Fulfillment Modes**:
   - **Local Stock**: Instantly delvers digital keys, credentials, or accounts stored in the database.
   - **Supplier API**: Direct integration with AIVerse Hub REST API for automated service delivery.
4. **Bilingual Support (አማርኛ / English)**:
   - Full toggle between Amharic (አማርኛ) and English for all buttons, alerts, and notifications.
5. **In-Chat Admin Suite**:
   - Real-time business analytics (total revenue, orders, active users, stock count).
   - Add new categories and products.
   - Batch upload license keys/accounts (`Batch paste`).
   - Broadcast engine to all registered bot users.
6. **Community & Security**:
   - Mandatory Channel Membership (Force Join).
   - Anti-flood & rate-limiting middleware.
   - Channel event notifier (`LOGS_CHANNEL_ID`).
   - Cloud keep-alive HTTP server for Render/Railway hosting.

---

## 📦 Project Structure

```
nexus-hub-bot/
├── bot/
│   ├── config.py             # Environment configuration & secrets
│   ├── main.py               # Application orchestration & polling
│   ├── database/             # SQLAlchemy 2.0 async models, engine & CRUD
│   ├── handlers/             # Modular aiogram 3 routers (user & admin)
│   ├── keyboards/            # Inline & Reply navigation keyboards
│   ├── locales/              # JSON translation catalogs (am.json & en.json)
│   ├── middleware/           # Rate limiter & channel force join
│   ├── services/             # Telebirr/CBE receipt verifier & AIVerse client
│   └── web/                  # Keep-alive web server
├── .env.example              # Pre-configured configuration template
├── requirements.txt          # Python dependencies
└── run.py                    # Application launcher
```

---

## ⚡ Quick Start

### 1. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
- `BOT_TOKEN`: Your bot token from `@BotFather`.
- `OWNER_ID`: Your Telegram user ID.
- `TELEBIRR_RECEIVER_PHONE` & `CBE_ACCOUNT_NUMBER`: Your payment receiving accounts.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Launch Bot
```bash
python run.py
```

The database (`nexus_hub.db`) and all tables will be initialized automatically on first startup!
