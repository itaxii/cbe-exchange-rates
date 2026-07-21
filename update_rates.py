from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import date
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests


CBE_URL = "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates"
SOURCE_NAME = "Central Bank of Egypt"
OUTPUT_PATH = Path("rates/latest.json")
REQUEST_TIMEOUT_SECONDS = 30
ALLOW_INSECURE_SSL_ENV = "CBE_ALLOW_INSECURE_SSL"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

LOGGER = logging.getLogger("update_rates")
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

CURRENCY_CODE_MAP = {
    "us dollar": "USD",
    "u s dollar": "USD",
    "u.s. dollar": "USD",
    "united states dollar": "USD",
    "usd": "USD",
    "euro": "EUR",
    "eur": "EUR",
    "pound sterling": "GBP",
    "sterling pound": "GBP",
    "british pound": "GBP",
    "gbp": "GBP",
    "saudi riyal": "SAR",
    "saudi rial": "SAR",
    "sar": "SAR",
    "kuwaiti dinar": "KWD",
    "kwd": "KWD",
    "uae dirham": "AED",
    "u.a.e dirham": "AED",
    "emirati dirham": "AED",
    "united arab emirates dirham": "AED",
    "aed": "AED",
    "swiss franc": "CHF",
    "chf": "CHF",
    "japanese yen": "JPY",
    "japanese yen 100": "JPY",
    "yen": "JPY",
    "jpy": "JPY",
    "canadian dollar": "CAD",
    "cad": "CAD",
    "australian dollar": "AUD",
    "aud": "AUD",
    "bahraini dinar": "BHD",
    "bhd": "BHD",
    "omani rial": "OMR",
    "omani riyal": "OMR",
    "omr": "OMR",
    "qatari riyal": "QAR",
    "qatari rial": "QAR",
    "qar": "QAR",
    "jordanian dinar": "JOD",
    "jod": "JOD",
    "chinese yuan": "CNY",
    "chinese yuan renminbi": "CNY",
    "yuan renminbi": "CNY",
    "renminbi": "CNY",
    "cny": "CNY",
    "danish krone": "DKK",
    "norwegian krone": "NOK",
    "swedish krona": "SEK",
}


class FetchError(RuntimeError):
    """Raised when the CBE source page cannot be downloaded."""


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(value: Any) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def currency_code_for(currency_name: str) -> str:
    normalized = normalize_key(currency_name)
    code = CURRENCY_CODE_MAP.get(normalized)
    if code:
        return code

    compact_name = re.sub(r"[^A-Za-z]", "", currency_name).upper()
    fallback = (compact_name[:3] or "UNK").ljust(3, "X")
    LOGGER.warning(
        "No currency code mapping found for %s; using fallback code %s",
        currency_name,
        fallback,
    )
    return fallback


def parse_decimal(value: Any) -> float | None:
    if pd.isna(value):
        return None

    text = normalize_text(value)
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None

    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", "."}:
        return None

    try:
        return round(float(cleaned), 4)
    except ValueError:
        return None


def extract_rate_date(html: str) -> date:
    compact_html = normalize_text(re.sub(r"<[^>]+>", " ", html))

    numeric_match = re.search(
        r"rates?\s+for\s+date\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        compact_html,
        re.IGNORECASE,
    )
    if numeric_match:
        day, month, year = (int(part) for part in numeric_match.groups())
        return date(year, month, day)

    text_match = re.search(
        r"(?:last\s+updated|this\s+page\s+was\s+last\s+updated)\s*:?\s*"
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        compact_html,
        re.IGNORECASE,
    )
    if text_match:
        day_text, month_text, year_text = text_match.groups()
        month = MONTHS.get(month_text.lower())
        if month:
            return date(int(year_text), month, int(day_text))

    raise ValueError(f"Could not find the exchange-rate date on {CBE_URL}.")


def flatten_columns(columns: Any) -> list[str]:
    flattened: list[str] = []
    for column in columns:
        if isinstance(column, tuple):
            parts = [normalize_text(part) for part in column if "Unnamed:" not in str(part)]
            flattened.append(" ".join(part for part in parts if part))
        else:
            flattened.append(normalize_text(column))
    return flattened


def find_column(columns: list[str], patterns: tuple[str, ...]) -> str | None:
    for column in columns:
        normalized = normalize_key(column)
        if any(pattern in normalized for pattern in patterns):
            return column
    return None


def find_exchange_rate_table(tables: list[pd.DataFrame]) -> tuple[pd.DataFrame, str, str, str]:
    candidates: list[tuple[int, pd.DataFrame, str, str, str]] = []

    for table in tables:
        table = table.copy()
        table.columns = flatten_columns(table.columns)
        columns = [str(column) for column in table.columns]

        currency_col = find_column(columns, ("currency",))
        buy_col = find_column(columns, ("buy", "buying"))
        sell_col = find_column(columns, ("sell", "selling"))

        score = sum(column is not None for column in (currency_col, buy_col, sell_col))
        if score == 3 and currency_col and buy_col and sell_col:
            candidates.append((len(table), table, currency_col, buy_col, sell_col))

    if not candidates:
        raise ValueError(
            "Could not find an exchange-rates table with currency, buy, and sell columns "
            f"at {CBE_URL}."
        )

    # Prefer the matching table with the most rows; short matching tables are often legends.
    _, table, currency_col, buy_col, sell_col = max(candidates, key=lambda candidate: candidate[0])
    return table, currency_col, buy_col, sell_col


def parse_rates_from_html(html: str, fetched_at: datetime | None = None) -> list[dict[str, object]]:
    fetched_at = fetched_at or datetime.now(ZoneInfo("Africa/Cairo")).replace(microsecond=0)
    if fetched_at.tzinfo is not None:
        fetched_at = fetched_at.astimezone(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
    rate_date = extract_rate_date(html)

    try:
        tables = pd.read_html(StringIO(html))
    except ValueError as exc:
        raise ValueError(f"No HTML tables were found at {CBE_URL}.") from exc

    table, currency_col, buy_col, sell_col = find_exchange_rate_table(tables)
    rows: list[dict[str, object]] = []

    for _, row in table.iterrows():
        currency_name = normalize_text(row.get(currency_col))
        buy_rate = parse_decimal(row.get(buy_col))
        sell_rate = parse_decimal(row.get(sell_col))

        if not currency_name or currency_name.lower().startswith("currency"):
            continue

        if buy_rate is None or sell_rate is None:
            LOGGER.warning(
                "Skipping currency row with missing buy or sell rate: %s",
                currency_name,
            )
            continue

        rows.append(
            {
                "rate_date": rate_date.isoformat(),
                "updated_at": fetched_at.isoformat(timespec="seconds"),
                "currency_code": currency_code_for(currency_name),
                "currency_name": currency_name,
                "buy_rate": buy_rate,
                "sell_rate": sell_rate,
                "source": SOURCE_NAME,
                "source_url": CBE_URL,
            }
        )

    if not rows:
        raise ValueError(f"No valid exchange-rate rows were parsed from {CBE_URL}.")

    return rows


def fetch_html() -> str:
    allow_insecure_ssl = os.getenv(ALLOW_INSECURE_SSL_ENV, "").lower() in {"1", "true", "yes"}
    if allow_insecure_ssl:
        LOGGER.warning(
            "SSL certificate verification is disabled because %s is set. "
            "Use this only for controlled environments with certificate-chain issues.",
            ALLOW_INSECURE_SSL_ENV,
        )

    try:
        response = requests.get(
            CBE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            verify=not allow_insecure_ssl,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"Could not reach CBE exchange-rates page: {exc}") from exc

    return response.text


def write_latest_json(rows: list[dict[str, object]], output_path: Path = OUTPUT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        html = fetch_html()
        rows = parse_rates_from_html(html)
        write_latest_json(rows)
    except (FetchError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(rows)} exchange-rate rows to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
