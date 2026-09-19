import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

LOCALES: Dict[str, Dict[str, str]] = {}


def load_locales():
    """Load JSON translation dictionaries."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    locales_dir = os.path.join(base_dir, "locales")
    for lang in ("am", "en"):
        file_path = os.path.join(locales_dir, f"{lang}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    LOCALES[lang] = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load locale {lang}: {e}")
                LOCALES[lang] = {}
        else:
            LOCALES[lang] = {}


load_locales()


def t(key: str, lang: str = "am", **kwargs) -> str:
    """Get localized text string with optional formatting."""
    lang_dict = LOCALES.get(lang) or LOCALES.get("am", {})
    text = lang_dict.get(key) or LOCALES.get("en", {}).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
