import csv
import json
import re

from geocoding.prices import (
    normalize_country,
    normalize_state,
    normalize_station_name,
    normalize_text,
)


VERIFIED = "VERIFIED"
NEEDS_REVIEW = "NEEDS_REVIEW"
AMBIGUOUS = "AMBIGUOUS"
NOT_FOUND = "NOT_FOUND"
NO_PRICE = "NO_PRICE"


def extract_branch_number(name):
    if not isinstance(name, str):
        return None

    match = re.search(r"#\s*(\d+)\b", name)
    if match:
        return match.group(1)

    match = re.search(r"\b(\d+)\s*$", name)
    return match.group(1) if match else None


def _public_record(record, include_price=False):
    public = {
        key: value
        for key, value in record.items()
        if not key.startswith("_") and (include_price or key != "Retail Price")
    }
    return public


def _station_location(properties):
    city = normalize_text(properties.get("city"))
    state = normalize_state(
        properties.get("state_code") or properties.get("state")
    )
    country = normalize_country(
        properties.get("country_code") or properties.get("country")
    )
    return city, state, country


def _station_address(properties):
    address = properties.get("street") or properties.get("address")
    return normalize_text(address)


def _result(status, candidate=None, candidates=None, price=None, **extra):
    return {
        "status": status,
        "candidate": candidate,
        "candidates": candidates or [],
        "price": price,
        **extra,
    }


def match_station(geo_station, station_index):
    """Conservatively match one Geoapify feature to an indexed price record.

    A station is verified only when its normalized name and either its branch
    number or non-empty address identify one CSV station in the same location.
    """
    properties = geo_station.get("properties", {})
    location = _station_location(properties)
    if not all(location):
        return _result(NOT_FOUND, reason="Missing city, state, or country")

    local_records = station_index.get(location, [])
    if not local_records:
        return _result(NOT_FOUND)

    geo_name = properties.get("name")
    geo_name_key = normalize_station_name(geo_name)
    geo_branch = extract_branch_number(geo_name)
    if not geo_name_key:
        return _result(NOT_FOUND, reason="Missing station name")

    name_matches = []
    branch_conflict = False

    for record in local_records:
        csv_name = record.get("Truckstop Name", "")
        csv_name_key = record.get("_normalized_name", "")
        if not csv_name_key or csv_name_key != geo_name_key:
            continue

        csv_branch = extract_branch_number(csv_name)
        if (
            geo_branch is not None
            and csv_branch is not None
            and geo_branch != csv_branch
        ):
            branch_conflict = True
            continue

        name_matches.append(record)

    if not name_matches:
        return _result(
            NOT_FOUND,
            branch_conflict=branch_conflict,
        )

    geo_address = _station_address(properties)
    address_matches = [
        record
        for record in name_matches
        if geo_address
        and record.get("_normalized_address")
        and record["_normalized_address"] == geo_address
    ]

    geo_branch = extract_branch_number(geo_name)
    branch_matches = [
        record
        for record in name_matches
        if geo_branch is not None
        and extract_branch_number(record.get("Truckstop Name", "")) == geo_branch
    ]

    if address_matches:
        matched_records = address_matches
    elif branch_matches:
        matched_records = branch_matches
    else:
        matched_records = name_matches

    station_groups = {}
    for record in matched_records:
        identity = (
            record.get("_normalized_name", ""),
            record.get("_normalized_address", ""),
            record.get("OPIS Truckstop ID", ""),
        )
        station_groups.setdefault(identity, []).append(record)

    if len(station_groups) > 1:
        public_candidates = [
            _public_record(records[0])
            for records in station_groups.values()
        ]
        return _result(
            AMBIGUOUS,
            candidates=public_candidates,
            branch_conflict=branch_conflict,
        )

    records = next(iter(station_groups.values()))
    record = records[0]
    has_address_evidence = bool(address_matches)
    has_branch_evidence = bool(branch_matches)

    if not (has_address_evidence or has_branch_evidence):
        candidate = _public_record(record)
        return _result(
            NEEDS_REVIEW,
            candidate=candidate,
            candidates=[candidate],
            reason="Name and location match, but address or branch evidence is insufficient",
        )

    prices = {item.get("_price") for item in records}
    if None in prices or len(prices) != 1:
        return _result(
            NO_PRICE,
            candidate=_public_record(record),
            reason="Station matched, but its CSV price records are missing or conflicting",
        )

    price = prices.pop()
    return _result(
        VERIFIED,
        candidate=_public_record(record, include_price=True),
        price=price,
    )


def main(
    prices_path="data/cleaned_fuel_prices.csv",
    stations_path="filtered_route_stations.json",
    output_path="matched_route_stations.csv",
):
    from geocoding.prices import load_price_data

    station_index = load_price_data(prices_path)
    with open(stations_path, "r", encoding="utf-8") as stations_file:
        stations = json.load(stations_file)

    results = []
    for station in stations:
        properties = station.get("properties", {})
        match = match_station(station, station_index)
        candidate = match["candidate"]
        results.append(
            {
                "geoapify_name": properties.get("name"),
                "city": properties.get("city"),
                "state": properties.get("state_code"),
                "status": match["status"],
                "matched_csv_name": (
                    candidate.get("Truckstop Name") if candidate else None
                ),
                "retail_price": match["price"],
            }
        )

    fieldnames = [
        "geoapify_name",
        "city",
        "state",
        "status",
        "matched_csv_name",
        "retail_price",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    return results


if __name__ == "__main__":
    main()
