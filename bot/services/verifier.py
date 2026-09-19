import re
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from bot.config import (
    TELEBIRR_RECEIVER_PHONE, TELEBIRR_RECEIVER_NAME,
    CBE_ACCOUNT_NUMBER, CBE_ACCOUNT_NAME
)

logger = logging.getLogger(__name__)

OFFICIAL_CBE_DOMAIN = "mb.cbe.com.et"
OFFICIAL_CBE_RECEIPT_HOST = "mbreciept.cbe.com.et"
TELEBIRR_RECEIPT_BASE_URL = "https://transactioninfo.ethiotelecom.et/receipt/"

VERIFICATION_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
outbound_bank_lock = asyncio.Lock()


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def compare_amount(expected: Any, parsed: Any) -> bool:
    try:
        def num(v):
            return round(float(re.sub(r"[^0-9.-]", "", str(v).replace(",", ""))), 2)
        return num(expected) == num(parsed)
    except (TypeError, ValueError):
        return False


def _adjacent(soup: BeautifulSoup, labels: list) -> str:
    norm_labels = [normalize(x) for x in labels]
    for td in soup.find_all(["td", "th"]):
        text = normalize(td.get_text(" ", strip=True))
        if any(label in text for label in norm_labels):
            sibling = td.find_next_sibling(["td", "th"])
            if sibling:
                value = " ".join(sibling.get_text(" ", strip=True).split())
                if value:
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

    for bad in ("receipt not found", "transaction not found", "invalid transaction"):
        if bad in normalized:
            raise NotFoundError("CBE receipt not found")

    amount = ""
    amount_m = re.search(r"(?:transferred\s*amount|amount|debited\s*amount)\s*[:\-]?\s*(?:etb|birr)?\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if amount_m:
        amount = amount_m.group(1).replace(",", "")
    else:
        amount_m2 = re.search(r"([\d,]+(?:\.\d{1,2})?)\s*(?:etb|birr)", text, re.I)
        if amount_m2:
            amount = amount_m2.group(1).replace(",", "")

    receiver_name = _adjacent(soup, ["Credited To", "Receiver Name", "Beneficiary", "To", "Credited Party"])
    receiver_acc = _adjacent(soup, ["Account Number", "To Account", "Credited Account", "Account No"])

    return {
        "amount": float(amount) if amount else 0.0,
        "status": "Completed",
        "recipientName": receiver_name,
        "accountNumber": receiver_acc,
        "raw_text": text[:300]
    }


async def verify_receipt_url(url: str) -> Dict[str, Any]:
    """
    Downloads and verifies a Telebirr or CBE receipt URL.
    Returns parsed dictionary: {valid: bool, provider: str, txn_id: str, amount: float, ...}
    """
    clean_url = url.strip()
    provider = "unknown"
    txn_id = ""

    # Check provider
    if "ethiotelecom.et" in clean_url or "telebirr" in clean_url:
        provider = "telebirr"
        m = re.search(r"/receipt/([A-Za-z0-9]+)", clean_url)
        if m:
            txn_id = m.group(1)
        else:
            txn_id = clean_url.rstrip("/").split("/")[-1]
    elif OFFICIAL_CBE_DOMAIN in clean_url or OFFICIAL_CBE_RECEIPT_HOST in clean_url or "cbe" in clean_url:
        provider = "cbe"
        m = re.search(r"[?&]id=([A-Za-z0-9]+)", clean_url)
        if m:
            txn_id = m.group(1)
        else:
            txn_id = clean_url.rstrip("/").split("/")[-1]
    else:
        return {"valid": False, "error": "unsupported_provider", "message": "Unknown receipt provider URL"}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            resp = await client.get(clean_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            if resp.status_code != 200:
                return {"valid": False, "error": "fetch_failed", "message": f"Bank returned HTTP {resp.status_code}"}

            html = resp.text
            if provider == "telebirr":
                data = telebirr_verification(html)
            else:
                data = cbe_verification(html)

            data["valid"] = True
            data["provider"] = provider
            data["txn_id"] = txn_id or f"{provider}_{int(datetime.now(timezone.utc).timestamp())}"
            return data

        except NotFoundError:
            return {"valid": False, "error": "receipt_not_found", "message": "Receipt not found or invalid"}
        except Exception as e:
            logger.error(f"Receipt verification failed: {e}")
            return {"valid": False, "error": "verification_error", "message": str(e)}
