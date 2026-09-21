import re
import ssl
import logging
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx
from bs4 import BeautifulSoup

from bot.config import (
    TELEBIRR_RECEIVER_PHONE, TELEBIRR_RECEIVER_NAME,
    CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME
)
from bot.database.crud import is_payment_link_or_txn_used

logger = logging.getLogger(__name__)

OFFICIAL_CBE_DOMAIN = "mb.cbe.com.et"
OFFICIAL_CBE_RECEIPT_HOST = "mbreciept.cbe.com.et"
TELEBIRR_RECEIPT_BASE_URL = "https://transactioninfo.ethiotelecom.et/receipt/"

# Concurrency limiter to protect bank endpoints and avoid rate bans
bank_request_semaphore = asyncio.Semaphore(3)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,am;q=0.8",
    "Cache-Control": "no-cache"
}


# =====================================================================
# FLOOD PROTECTOR (Anti-Flood / Rate Limiting)
# =====================================================================

class PaymentFloodProtector:
    """
    Protects the payment verification system against flooding, rapid-fire hammering,
    and brute-force transaction guessing.
    """
    def __init__(
        self,
        min_interval_seconds: float = 12.0,
        max_requests_window: int = 3,
        window_seconds: float = 120.0,
        max_failures: int = 4,
        failure_window_seconds: float = 600.0,
        lockout_duration_seconds: float = 900.0
    ):
        self.min_interval = min_interval_seconds
        self.max_requests = max_requests_window
        self.window = window_seconds
        self.max_failures = max_failures
        self.failure_window = failure_window_seconds
        self.lockout_duration = lockout_duration_seconds

        self._last_req: Dict[int, float] = {}
        self._recent_reqs: Dict[int, List[float]] = {}
        self._failures: Dict[int, List[float]] = {}
        self._lockouts: Dict[int, float] = {}

    def check_flood(self, user_id: int, lang: str = "am") -> Tuple[bool, str, int]:
        now = datetime.now(timezone.utc).timestamp()

        # 1. Lockout check
        lock_until = self._lockouts.get(user_id, 0.0)
        if now < lock_until:
            remaining_sec = int(lock_until - now)
            rem_min = max(1, (remaining_sec + 59) // 60)
            msg = (
                f"የክፍያ ማረጋገጫ ገደብ: ተደጋጋሚ ያልተሳኩ ሙከራዎች ተደርገዋል፤ እባክዎ ከ {rem_min} ደቂቃ በኋላ እንደገና ይሞክሩ።"
                if lang == "am" else
                f"Flood Protection: Too many failed verification attempts. Please retry after {rem_min} minutes."
            )
            return True, msg, remaining_sec

        # 2. Minimum interval between consecutive requests
        last = self._last_req.get(user_id, 0.0)
        if now - last < self.min_interval:
            wait_sec = int(self.min_interval - (now - last))
            msg = (
                f"የክፍያ ማረጋገጫ ገደብ: እባክዎ {wait_sec} ሰኮንዶች ቆይተው እንደገና ይሞክሩ።"
                if lang == "am" else
                f"Flood Protection: Please wait {wait_sec} seconds before trying again."
            )
            return True, msg, wait_sec

        # 3. Burst limit in sliding window
        reqs = [t for t in self._recent_reqs.get(user_id, []) if now - t < self.window]
        if len(reqs) >= self.max_requests:
            wait_sec = int(self.window - (now - reqs[0]))
            msg = (
                f"የክፍያ ማረጋገጫ ገደብ: በቅርብ ጊዜ በርካታ ሙከራዎች ተደርገዋል፤ እባክዎ {wait_sec} ሰኮንዶች ይጠብቁ።"
                if lang == "am" else
                f"Flood Protection: Rate limit reached. Please wait {wait_sec} seconds."
            )
            return True, msg, wait_sec

        return False, "", 0

    def record_attempt(self, user_id: int):
        now = datetime.now(timezone.utc).timestamp()
        self._last_req[user_id] = now
        reqs = [t for t in self._recent_reqs.get(user_id, []) if now - t < self.window]
        reqs.append(now)
        self._recent_reqs[user_id] = reqs

    def record_failure(self, user_id: int):
        now = datetime.now(timezone.utc).timestamp()
        fails = [t for t in self._failures.get(user_id, []) if now - t < self.failure_window]
        fails.append(now)
        self._failures[user_id] = fails
        if len(fails) >= self.max_failures:
            self._lockouts[user_id] = now + self.lockout_duration
            logger.warning(f"User {user_id} locked out for {self.lockout_duration}s due to failed payment verifications.")

    def record_success(self, user_id: int):
        self._failures.pop(user_id, None)
        self._lockouts.pop(user_id, None)


payment_flood_protector = PaymentFloodProtector()


# =====================================================================
# EXCEPTIONS & HELPER UTILITIES
# =====================================================================

class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def clean_digits(val: Any) -> str:
    return re.sub(r"[^0-9]", "", str(val or ""))


def match_masked_account(actual_receipt_account: str, expected_account: str) -> bool:
    """
    Validates masked accounts (e.g. 09******78 vs 0912345678 or 1000******789 vs 1000123456789).
    Returns True if actual matches the expected account.
    """
    if not expected_account:
        return True

    clean_act = actual_receipt_account.strip().replace(" ", "").replace("-", "")
    clean_exp = expected_account.strip().replace(" ", "").replace("-", "")

    if not clean_act:
        return True

    # Check if masked with *
    if "*" in clean_act:
        parts = [p for p in clean_act.split("*") if p]
        if not parts:
            return True
        prefix = parts[0]
        suffix = parts[-1]
        if prefix and not clean_exp.startswith(prefix):
            return False
        if suffix and not clean_exp.endswith(suffix):
            return False
        return True

    # Exact or suffix match
    return clean_act == clean_exp or clean_exp.endswith(clean_act) or clean_act.endswith(clean_exp)


def _adjacent(soup: BeautifulSoup, labels: list) -> str:
    norm_labels = [normalize(x) for x in labels]
    for td in soup.find_all(["td", "th", "div", "span", "p"]):
        text = normalize(td.get_text(" ", strip=True))
        if any(label in text for label in norm_labels):
            sibling = td.find_next_sibling(["td", "th", "div", "span", "p"])
            if sibling:
                value = " ".join(sibling.get_text(" ", strip=True).split())
                if value and not any(label in normalize(value) for label in norm_labels):
                    return value
    return ""


def _column(table: Optional[BeautifulSoup], labels: list) -> str:
    if not table:
        return ""
    norm_labels = [normalize(x) for x in labels]
    rows = table.find_all("tr")
    for row_index, row in enumerate(rows):
        cells = row.find_all(["td", "th"])
        for col_index, cell in enumerate(cells):
            if any(label in normalize(cell.get_text(" ", strip=True)) for label in norm_labels):
                if row_index + 1 < len(rows):
                    next_cells = rows[row_index + 1].find_all(["td", "th"])
                    if col_index < len(next_cells):
                        return " ".join(next_cells[col_index].get_text(" ", strip=True).split())
    return ""


# =====================================================================
# URL NORMALIZATION & EXTRACTION
# =====================================================================

def extract_and_normalize_payment_input(raw_input: str) -> Tuple[Optional[str], str, Optional[str], str]:
    """
    Extracts and normalizes receipt link or transaction ID from user message.
    Returns: (normalized_url, provider, transaction_id, original_url_or_input)
    """
    raw_str = (raw_input or "").strip()

    # 1. Search for URL in text
    url_match = re.search(r"https?://[^\s<>'\"\)]+", raw_str)
    if url_match:
        found_url = url_match.group(0).rstrip(".,;")
        parsed = urlparse(found_url)
        host = (parsed.netloc or "").lower()
        path = parsed.path

        # Telebirr receipt
        if "ethiotelecom.et" in host or "telebirr" in host:
            m = re.search(r"/receipt/([A-Za-z0-9]+)", path)
            txn_id = m.group(1) if m else path.rstrip("/").split("/")[-1]
            norm_url = f"https://transactioninfo.ethiotelecom.et/receipt/{txn_id}"
            return norm_url, "telebirr", txn_id, found_url

        # CBE receipt
        elif OFFICIAL_CBE_DOMAIN in host or OFFICIAL_CBE_RECEIPT_HOST in host or "cbe" in host:
            qs = parse_qs(parsed.query)
            txn_id = qs.get("id", [""])[0]
            if not txn_id:
                m = re.search(r"/receipt/([A-Za-z0-9.]+)", path)
                txn_id = m.group(1) if m else path.rstrip("/").split("/")[-1]
            norm_url = f"https://mbreciept.cbe.com.et/receipt/?id={txn_id}"
            return norm_url, "cbe", txn_id, found_url

        else:
            # Generic URL: normalize host, strip tracking query params
            norm_url = f"{parsed.scheme.lower()}://{host}{path}"
            return norm_url, "unknown", None, found_url

    # 2. No URL found: Check if user sent a raw Transaction ID / Reference Number
    clean_code = re.sub(r"[^A-Za-z0-9.]", "", raw_str)

    # Check for CBE Reference (starts with FT...)
    if clean_code.upper().startswith("FT") and len(clean_code) >= 6:
        txn_id = clean_code.upper()
        norm_url = f"https://mbreciept.cbe.com.et/receipt/?id={txn_id}"
        return norm_url, "cbe", txn_id, raw_str

    # Check for Telebirr Transaction ID (digits or alnum 8 to 25 chars)
    if (clean_code.isdigit() and len(clean_code) >= 8) or (clean_code.isalnum() and 8 <= len(clean_code) <= 25):
        txn_id = clean_code
        norm_url = f"https://transactioninfo.ethiotelecom.et/receipt/{txn_id}"
        return norm_url, "telebirr", txn_id, raw_str

    return None, "unknown", None, raw_str


# =====================================================================
# HTML RECEIPT PARSERS
# =====================================================================

def telebirr_verification(raw_html: str) -> Dict[str, Any]:
    """HTML Parser for Telebirr Web Receipts."""
    if not raw_html:
        raise NotFoundError("Empty Telebirr receipt response")

    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    normalized = normalize(text)

    for bad in ("this request is not correct", "receipt not found", "transaction not found", "invalid receipt"):
        if bad in normalized:
            raise NotFoundError("Receipt not found or invalid")

    tables = soup.find_all("table")
    invoice_table = next((t for t in reversed(tables) if "settled amount" in normalize(t.get_text(" ", strip=True))), None)
    status_table = next((t for t in reversed(tables) if "transaction status" in normalize(t.get_text(" ", strip=True))), None)

    name = _adjacent(soup, ["Credited Party name", "Receiver Name", "Recipient Name", "Beneficiary Name"])
    account = _adjacent(soup, ["Credited party account no", "Credited party account", "Receiver Account", "Recipient Account", "Account Number"])

    paid_ref = soup.find(id="paid_reference_number")
    if paid_ref and (not name or not account):
        parts = " ".join(paid_ref.get_text(" ", strip=True).split()).split()
        if not account and parts:
            account = parts[0]
        if not name and len(parts) > 1:
            name = " ".join(parts[1:])

    amount = _column(invoice_table, ["Settled Amount", "Payment Amount", "Transaction Amount", "Amount"])
    amount = re.sub(r"[^0-9.,-]", "", amount).replace(",", "")
    if not amount:
        m = re.search(r"(?:settled\s*amount|payment\s*amount|amount)\s*[:\-]?\s*(?:etb|birr)?\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
        amount = m.group(1).replace(",", "") if m else "0"

    status = _adjacent(status_table or soup, ["Transaction Status", "Payment Status", "Status"])
    if not status:
        m = re.search(r"(?:transaction\s*status|payment\s*status|status)\s*[:\-]?\s*([^\n]+)", text, re.I)
        status = m.group(1).strip() if m else "Completed"

    date = _column(invoice_table, ["Payment date", "Transaction date", "Date"])
    if not date:
        m = re.search(r"(?:payment\s*date|transaction\s*date|date)\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text, re.I)
        date = m.group(1) if m else ""

    return {
        "amount": float(amount) if amount else 0.0,
        "status": status,
        "recipientName": name,
        "accountNumber": account,
        "date": date
    }


def cbe_verification(raw_html: str) -> Dict[str, Any]:
    """HTML Parser for Commercial Bank of Ethiopia (CBE) Receipts."""
    if not raw_html:
        raise NotFoundError("Empty CBE response")

    soup = BeautifulSoup(raw_html, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    normalized = normalize(text)

    for bad in ("receipt not found", "transaction not found", "invalid transaction", "page not found"):
        if bad in normalized:
            raise NotFoundError("CBE receipt not found or invalid")

    amount = ""
    amount_m = re.search(r"(?:transferred\s*amount|amount|debited\s*amount|deposited\s*amount)\s*[:\-]?\s*(?:etb|birr)?\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if amount_m:
        amount = amount_m.group(1).replace(",", "")
    else:
        amount_m2 = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:etb|birr)", text, re.I)
        if amount_m2:
            amount = amount_m2.group(1).replace(",", "")

    receiver_name = _adjacent(soup, ["Credited To", "Receiver Name", "Beneficiary", "To", "Credited Party", "Recipient Name"])
    receiver_acc = _adjacent(soup, ["Account Number", "To Account", "Credited Account", "Account No", "Beneficiary Account"])

    status = _adjacent(soup, ["Transaction Status", "Payment Status", "Status"])
    if not status:
        m = re.search(r"(?:transaction\s*status|status)\s*[:\-]?\s*([^\n]+)", text, re.I)
        status = m.group(1).strip() if m else "Completed"

    # Transaction ID / Reference extraction from page
    page_ref = _adjacent(soup, ["Transaction ID", "Reference No", "Reference Number", "Txn ID", "Journal No", "Receipt Number"])
    if not page_ref:
        m = re.search(r"(?:transaction\s*id|ref(?:erence)?\s*no|txn\s*id)\s*[:\-]?\s*([A-Za-z0-9.]+)", text, re.I)
        page_ref = m.group(1).strip() if m else ""

    date_m = re.search(r"(?:payment\s*date|transaction\s*date|date)\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})", text, re.I)
    date_val = date_m.group(1) if date_m else ""

    return {
        "amount": float(amount) if amount else 0.0,
        "status": status,
        "recipientName": receiver_name,
        "accountNumber": receiver_acc,
        "transactionId": page_ref,
        "date": date_val,
        "raw_text": text[:300]
    }


# =====================================================================
# CORE AUTO-VERIFIER ENGINE
# =====================================================================

async def verify_payment_receipt(
    raw_input: str,
    expected_provider: str = "",
    expected_telebirr: str = "",
    expected_cbe: str = "",
    min_amount: float = 0.0
) -> Dict[str, Any]:
    """
    Extracts, normalizes, duplicate-checks, and auto-verifies Telebirr or CBE receipt.
    Returns:
      dict with valid=True, provider, txn_id, amount, sender_name, recipient_acc, normalized_url, original_url
      or valid=False, error, message.
    """
    # 1. Normalize and extract
    norm_url, provider, candidate_txn_id, original_url = extract_and_normalize_payment_input(raw_input)

    if not norm_url or provider == "unknown":
        return {
            "valid": False,
            "error": "invalid_format",
            "message": "እባክዎ ትክክለኛ የባንክ ደረሰኝ ሊንክ (SMS Link) ወይም የግብይት ቁጥር (Transaction ID) ያስገቡ።"
        }

    # Override provider if explicitly expected and supported
    if expected_provider in ("telebirr", "cbe") and provider in ("unknown", expected_provider):
        provider = expected_provider

    # 2. Pre-check for duplicate in DB
    is_used, duplicate_reason = await is_payment_link_or_txn_used(norm_url, candidate_txn_id)
    if is_used:
        return {
            "valid": False,
            "error": "duplicate_payment",
            "message": duplicate_reason or "ይህ ደረሰኝ ወይም የክፍያ ሊንክ አስቀድሞ ጥቅም ላይ ውሏል።"
        }

    # 3. Fetch receipt from official bank endpoint with concurrency limit & SSL fallback
    async with bank_request_semaphore:
        html = None
        fetch_err = None

        # Try standard HTTPS request first
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=BROWSER_HEADERS) as client:
                resp = await client.get(norm_url)
                if resp.status_code == 200:
                    html = resp.text
                else:
                    fetch_err = f"Bank server returned HTTP {resp.status_code}"
        except (httpx.ConnectError, ssl.SSLError, Exception) as ssl_exc:
            logger.warning(f"Standard HTTPS fetch failed for {norm_url}: {ssl_exc}. Retrying with verify=False...")
            try:
                # Local Ethiopian banking portals sometimes have incomplete intermediate certificate chains
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, verify=False, headers=BROWSER_HEADERS) as unverified_client:
                    resp = await unverified_client.get(norm_url)
                    if resp.status_code == 200:
                        html = resp.text
                    else:
                        fetch_err = f"Bank server returned HTTP {resp.status_code}"
            except Exception as e:
                fetch_err = str(e)

        if not html:
            return {
                "valid": False,
                "error": "fetch_failed",
                "message": f"ከባንክ ኔትወርክ ጋር መገናኘት አልተቻለም ({fetch_err})። እባክዎ ጥቂት ቆይተው እንደገና ይሞክሩ።"
            }

        # 4. Parse receipt HTML
        try:
            if provider == "telebirr":
                data = telebirr_verification(html)
            else:
                data = cbe_verification(html)
        except NotFoundError:
            return {
                "valid": False,
                "error": "receipt_not_found",
                "message": "ደረሰኙ በባንኩ ሲስተም ውስጥ አልተገኘም ወይም ልክ ያልሆነ ነው።"
            }
        except Exception as parse_exc:
            logger.error(f"Receipt parse error: {parse_exc}")
            return {
                "valid": False,
                "error": "parse_error",
                "message": "የደረሰኝ መረጃ ማንበብ አልተቻለም። እባክዎ ትክክለኛውን ሊንክ እንደገና ይሞክሩ።"
            }

        # 5. Validate status (Completed, Success, Successful, Transferred)
        raw_status = normalize(data.get("status", ""))
        if raw_status and not any(ok in raw_status for ok in ["complete", "success", "transferred", "settled", "paid"]):
            return {
                "valid": False,
                "error": "unsuccessful_payment",
                "message": f"ክፍያው አልተጠናቀቀም (ሁኔታ: {data.get('status')})።"
            }

        # 6. Validate parsed amount
        amount = float(data.get("amount", 0.0))
        if amount <= 0:
            return {
                "valid": False,
                "error": "zero_amount",
                "message": "በደረሰኙ ላይ ትክክለኛ የክፍያ መጠን አልተገኘም።"
            }

        if min_amount > 0 and amount < min_amount:
            return {
                "valid": False,
                "error": "below_min_amount",
                "message": f"የተከፈለው መጠን ({amount:.2f} ETB) ከዝቅተኛው የክፍያ ገደብ ({min_amount:.2f} ETB) ያነሰ ነው።"
            }

        # 7. Validate Receiver Account / Phone
        rec_acc = str(data.get("accountNumber", "")).strip()
        if provider == "telebirr" and expected_telebirr:
            if not match_masked_account(rec_acc, expected_telebirr):
                return {
                    "valid": False,
                    "error": "wrong_recipient",
                    "message": "ክፍያው የተላከው ወደ ተሳሳተ የቴሌብር ቁጥር ነው። እባክዎ ለቦቱ የተገለጸውን ትክክለኛ ቁጥር ይጠቀሙ።"
                }
        elif provider == "cbe" and expected_cbe:
            if not match_masked_account(rec_acc, expected_cbe):
                return {
                    "valid": False,
                    "error": "wrong_recipient",
                    "message": "ክፍያው የተላከው ወደ ተሳሳተ የCBE ሒሳብ ቁጥር ነው። እባክዎ ለቦቱ የተገለጸውን ትክክለኛ ሒሳብ ይጠቀሙ።"
                }

        # 8. Resolve final transaction ID
        final_txn_id = candidate_txn_id or data.get("transactionId") or f"{provider}_{int(datetime.now(timezone.utc).timestamp())}"

        # 9. Post-fetch duplicate check with final_txn_id
        is_used_post, dup_post_reason = await is_payment_link_or_txn_used(norm_url, final_txn_id)
        if is_used_post:
            return {
                "valid": False,
                "error": "duplicate_payment",
                "message": dup_post_reason or "ይህ ደረሰኝ ወይም የክፍያ መለያ አስቀድሞ ጥቅም ላይ ውሏል።"
            }

        return {
            "valid": True,
            "provider": provider,
            "txn_id": final_txn_id,
            "amount": Decimal(str(amount)),
            "sender_name": data.get("recipientName", ""),
            "recipient_acc": rec_acc,
            "normalized_url": norm_url,
            "original_url": original_url,
            "date": data.get("date", ""),
            "raw_details": str(data)
        }


# Legacy helper for backward compatibility
async def verify_receipt_url(url: str) -> Dict[str, Any]:
    return await verify_payment_receipt(url)
