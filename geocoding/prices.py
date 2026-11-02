import csv
import re
from decimal import Decimal, InvalidOperation


REQUIRED_COLUMNS = (
    "Truckstop Name",
    "City",
    "State",
    "Country",
    "Retail Price",
)

US_STATES = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
}

COUNTRY_ALIASES = {
    "ca": "ca",
    "can": "ca",
    "canada": "ca",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
}


def normalize_text(value):
    if value is None:
        return ""

    text = str(value).strip().casefold().replace("’", "'")
    text = text.replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_station_name(value):
    if value is None:
        return ""

    text = str(value).strip().casefold().replace("’", "'").replace("'", "")
    text = re.sub(r"(?:#\s*|\s+)\d+\s*$", "", text)
    name = normalize_text(text)
    name = re.sub(
        r"\b(gas station|travel center|general store|fuel station)\b$",
        "",
        name,
    )
    return re.sub(r"\s+", " ", name).strip()


def normalize_state(value):
    state = normalize_text(value)
    return US_STATES.get(state, state)


def normalize_country(value):
    country = normalize_text(value)
    return COUNTRY_ALIASES.get(country, country)


def normalize_price(value):
    if value is None:
        return None

    price_text = str(value).strip().replace("$", "").replace(",", "")
    if not price_text:
        return None

    try:
        price = Decimal(price_text)
    except InvalidOperation:
        return None

    if not price.is_finite() or price <= 0:
        return None

    return price


def normalize_price_record(record):
    normalized = {
        key: (value.strip() if isinstance(value, str) else value)
        for key, value in record.items()
    }

    normalized["_normalized_name"] = normalize_station_name(
        normalized.get("Truckstop Name")
    )
    normalized["_normalized_address"] = normalize_text(
        normalized.get("Address")
    )
    normalized["_normalized_city"] = normalize_text(
        normalized.get("City")
    )
    normalized["_normalized_state"] = normalize_state(
        normalized.get("State")
    )
    normalized["_normalized_country"] = normalize_country(
        normalized.get("Country")
    )
    normalized["_price"] = normalize_price(
        normalized.get("Retail Price")
    )

    return normalized


def build_station_index(records):
    """Normalize records and index them by (city, state, country)."""
    index = {}
    seen_records = set()

    for record in records:
        normalized = normalize_price_record(record)
        identity = tuple(
            sorted(
                (key, str(value))
                for key, value in normalized.items()
                if not key.startswith("_")
            )
        )
        if identity in seen_records:
            continue
        seen_records.add(identity)

        key = (
            normalized["_normalized_city"],
            normalized["_normalized_state"],
            normalized["_normalized_country"],
        )
        if all(key):
            index.setdefault(key, []).append(normalized)

    return index


def load_price_data(csv_path):
    """Load and normalize CSV prices into a city/state/country index."""
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        missing_columns = [
            column for column in REQUIRED_COLUMNS if column not in fieldnames
        ]
        if missing_columns:
            raise ValueError(
                "Fuel-price CSV is missing required columns: "
                + ", ".join(missing_columns)
            )

        return build_station_index(reader)
