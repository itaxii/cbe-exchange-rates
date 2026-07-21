from datetime import datetime

import pytest

from update_rates import currency_code_for, extract_rate_date, parse_rates_from_html


def test_parse_rates_detects_exchange_rate_table_and_shapes_rows():
    html = """
    <html>
      <body>
        <p>CBE Official Exchange rates and prices are expressed in pounds.<br /> Rates for Date: 20/07/2026</p>
        <table>
          <tr><th>Name</th><th>Value</th></tr>
          <tr><td>Inflation</td><td>12.3</td></tr>
        </table>
        <table>
          <tr><th>Currency</th><th>Buy</th><th>Sell</th></tr>
          <tr><td>US Dollar</td><td>48.2500</td><td>48.3500</td></tr>
          <tr><td>Euro</td><td>56.1000</td><td>56.2400</td></tr>
        </table>
      </body>
    </html>
    """

    rows = parse_rates_from_html(html, fetched_at=datetime(2026, 7, 20, 0, 30, 15))

    assert rows == [
        {
            "rate_date": "2026-07-20",
            "updated_at": "2026-07-20T00:30:15",
            "currency_code": "USD",
            "currency_name": "US Dollar",
            "buy_rate": 48.25,
            "sell_rate": 48.35,
            "source": "Central Bank of Egypt",
            "source_url": "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates",
        },
        {
            "rate_date": "2026-07-20",
            "updated_at": "2026-07-20T00:30:15",
            "currency_code": "EUR",
            "currency_name": "Euro",
            "buy_rate": 56.1,
            "sell_rate": 56.24,
            "source": "Central Bank of Egypt",
            "source_url": "https://www.cbe.org.eg/en/economic-research/statistics/cbe-exchange-rates",
        },
    ]


def test_parse_rates_uses_rate_date_from_page_not_fetch_date():
    html = """
    <html>
      <body>
        <p>Rates for Date: 20/07/2026</p>
        <table>
          <tr><th>Currency</th><th>Buy</th><th>Sell</th></tr>
          <tr><td>US Dollar</td><td>48.2500</td><td>48.3500</td></tr>
        </table>
      </body>
    </html>
    """

    rows = parse_rates_from_html(html, fetched_at=datetime(2026, 7, 21, 11, 30, 0))

    assert rows[0]["rate_date"] == "2026-07-20"
    assert rows[0]["updated_at"] == "2026-07-21T11:30:00"


def test_extract_rate_date_supports_cbe_date_formats():
    assert extract_rate_date("Rates for Date: 20/07/2026").isoformat() == "2026-07-20"
    assert extract_rate_date("Last Updated: 20 Jul 2026").isoformat() == "2026-07-20"


def test_parse_rates_skips_rows_with_missing_rates(caplog):
    html = """
    <p>Rates for Date: 20/07/2026</p>
    <table>
      <tr><th>Currency Name</th><th>Buy Rate</th><th>Sell Rate</th></tr>
      <tr><td>US Dollar</td><td>48.2500</td><td></td></tr>
      <tr><td>Pound Sterling</td><td>61.0000</td><td>61.2500</td></tr>
    </table>
    """

    rows = parse_rates_from_html(html, fetched_at=datetime(2026, 7, 20, 0, 30, 15))

    assert [row["currency_code"] for row in rows] == ["GBP"]
    assert "Skipping currency row with missing buy or sell rate" in caplog.text


def test_parse_rates_fails_clearly_when_table_is_not_found():
    html = """
    <p>Rates for Date: 20/07/2026</p>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Something else</td><td>1</td></tr>
    </table>
    """

    with pytest.raises(ValueError, match="Could not find an exchange-rates table"):
        parse_rates_from_html(html, fetched_at=datetime(2026, 7, 20, 0, 30, 15))


def test_currency_code_for_known_variants_and_unknown_fallback(caplog):
    assert currency_code_for("U.S. Dollar") == "USD"
    assert currency_code_for("UAE Dirham") == "AED"
    assert currency_code_for("Chinese Yuan Renminbi") == "CNY"
    assert currency_code_for("Japanese Yen 100") == "JPY"
    assert currency_code_for("Swedish Krona") == "SEK"

    assert currency_code_for("Mexican Peso") == "MEX"
    assert "No currency code mapping found for Mexican Peso" in caplog.text
