import math
import json
from datetime import date, datetime, timezone


def json_request_text(value):
    if not isinstance(value, dict):
        raise ValueError("Task JSON must be an object")
    lines = []

    def add(key, raw):
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)) or "\n" in str(raw) or "\r" in str(raw):
            raise ValueError(f"{key} must be a single-line string or number")
        lines.append(f"{key}: {raw}")

    def money(key, alias):
        if key in value:
            add(key, value[key])
        elif alias in value:
            amount = value[alias]
            if not isinstance(amount, dict) or amount.get("currency") != "EUR":
                raise ValueError(f"{alias} must have amount and currency EUR")
            add(key, amount.get("amount"))

    if "item" in value or "product" in value:
        add("item", value.get("item", value.get("product")))
    for key in ("quantity", "delivery_days"):
        if key in value:
            add(key, value[key])
    money("max_unit_price_eur", "maximum_unit_price")
    money("max_total_eur", "maximum_total_price")
    if "delivery_days" not in value and "delivery_deadline" in value:
        try:
            reference = date.fromisoformat(value["request_date"]) if "request_date" in value else datetime.now(timezone.utc).date()
            days = (date.fromisoformat(value["delivery_deadline"]) - reference).days
        except (TypeError, ValueError):
            raise ValueError("delivery_deadline and request_date must be ISO dates (YYYY-MM-DD)")
        if days <= 0:
            raise ValueError("delivery_deadline must be after request_date (defaults to today's UTC date)")
        add("delivery_days", days)
    must_haves = value.get("must_haves", value.get("mandatory_commercial_terms", []))
    if not isinstance(must_haves, list) or any(not isinstance(term, str) for term in must_haves):
        raise ValueError("must_haves / mandatory_commercial_terms must be an array of strings")
    for term in must_haves:
        add("must_have", term)
    quotes = value.get("supplier_quotes", [])
    if not isinstance(quotes, list):
        raise ValueError("supplier_quotes must be an array")
    for quote in quotes:
        if not isinstance(quote, dict) or not isinstance(quote.get("name"), str):
            raise ValueError("supplier_quotes entries need name and unit_price_eur")
        price = quote.get("unit_price_eur")
        if isinstance(price, bool) or not isinstance(price, (str, int, float)):
            raise ValueError("supplier_quote unit_price_eur must be a number")
        add("supplier_quote", f"{quote['name']} = {price}")
    return "\n".join(lines)


REQUIRED = ("item", "quantity", "max_unit_price_eur", "delivery_days")
OPTIONAL = ("max_total_eur",)


def parse_request(text):
    """Return (request, errors). The request always has every key; missing values are None."""
    request = {"item": None, "quantity": None, "max_unit_price_eur": None, "delivery_days": None, "must_haves": []}
    if text.lstrip().startswith(("{", "[")):
        try:
            text = json_request_text(json.loads(text))
        except (ValueError, TypeError) as error:
            return request, [f"invalid JSON request: {error}"]
    raw = {}
    quotes = []
    quote_errors = []
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower().replace(" ", "_").replace("-", "_")
        value = value.strip()
        if key == "supplier_quote":
            name, eq, price_text = value.rpartition("=")
            name = name.strip()
            try:
                price = float(price_text)
            except ValueError:
                price = math.nan
            if eq and name and math.isfinite(price) and price > 0:
                quotes.append({"name": name, "unit_price_eur": price})
            else:
                quote_errors.append(f"supplier_quote must be '<name> = <positive EUR unit price>', got {value!r}")
        elif key == "must_have":
            if value:
                request["must_haves"].append(value)
        elif key in REQUIRED or key in OPTIONAL:
            raw[key] = value

    errors = list(quote_errors)
    if quotes or quote_errors:
        if not quote_errors and len(quotes) != 3:
            errors.append(f"supplier_quote must be given exactly 3 times or not at all, got {len(quotes)}")
        elif not quote_errors:
            request["supplier_quotes"] = quotes
    for key in REQUIRED:
        if not raw.get(key):
            errors.append(f"missing {key}")
    if raw.get("item"):
        request["item"] = raw["item"]
    for key in ("quantity", "delivery_days"):
        if raw.get(key):
            try:
                number = int(raw[key])
            except ValueError:
                number = 0
            if number > 0:
                request[key] = number
            else:
                errors.append(f"{key} must be a positive whole number, got {raw[key]!r}")
    for key in ("max_unit_price_eur", "max_total_eur"):
        if raw.get(key):
            try:
                price = float(raw[key])
            except ValueError:
                price = math.nan
            if math.isfinite(price) and price > 0:
                request[key] = price
            else:
                errors.append(f"{key} must be a positive number, got {raw[key]!r}")
    return request, errors


CHANNELS = ("protocol", "free_text", "mixed")


def parse_channel(text):
    """(channel, error) from an optional `supplier_channel:` line: `protocol` (the default), `free_text` (every
    supplier answers in prose) or `mixed` (the first supplier does). Read only with the LLM flag on, and kept out of
    the request dict, so a run with the flag off is the same as without the line."""
    values = []
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower().replace(" ", "_").replace("-", "_") == "supplier_channel":
            values.append(value.strip().lower().replace("-", "_"))
    if not values:
        return "protocol", None
    if len(values) > 1 or values[0] not in CHANNELS:
        return "protocol", f"supplier_channel must be given once, as one of {', '.join(CHANNELS)}"
    return values[0], None
