from functools import lru_cache
import math
from pathlib import Path

from geocoding.geocode import search_geocoding
from geocoding.prices import load_price_data, normalize_country, normalize_price
from geocoding.route_stations import (
    DEFAULT_PRICE_CSV,
    get_route_stations_with_prices,
)
from optimizer.fuel_optimizer import optimize_fuel_stops


class LocationNotFoundError(ValueError):
    pass


class FuelPriceDataError(Exception):
    pass


@lru_cache(maxsize=128)
def geocode_us_location(location):
    """Resolve a place description to a US coordinate pair."""
    results = search_geocoding(f"{location}, USA", limit=5)

    for result in results:
        country_code = normalize_country(result.get("country_code"))
        latitude = result.get("lat")
        longitude = result.get("lon")
        if country_code != "us":
            continue
        if not isinstance(latitude, (int, float)) or not isinstance(
            longitude, (int, float)
        ):
            continue
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            continue
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue

        return {
            "latitude": latitude,
            "longitude": longitude,
            "formatted": result.get("formatted") or result.get("address_line1"),
        }

    raise LocationNotFoundError(
        f"Could not resolve '{location}' to a location in the United States"
    )


@lru_cache(maxsize=2)
def _cached_us_average_price(csv_path, modified_time_ns):
    station_index = load_price_data(csv_path)
    prices = [
        record["_price"]
        for (_, _, country), records in station_index.items()
        if country == "us"
        for record in records
        if record.get("_price") is not None
    ]
    if not prices:
        raise FuelPriceDataError(
            "Fuel-price CSV contains no valid US prices for optimization"
        )
    return sum(prices, start=prices[0] * 0) / len(prices)


def get_average_dataset_fuel_price():
    csv_path = Path(DEFAULT_PRICE_CSV).resolve()
    modified_time_ns = csv_path.stat().st_mtime_ns
    return _cached_us_average_price(str(csv_path), modified_time_ns)


def _prepare_optimizer_stations(stations, average_price):
    prepared = []
    estimated_count = 0
    for station in stations:
        if not isinstance(station, dict):
            prepared.append(station)
            continue
        properties = station.get("properties")
        if not isinstance(properties, dict):
            prepared.append(station)
            continue

        match = dict(properties)
        station_copy = dict(station)
        station_copy["properties"] = match
        verified_price = (
            normalize_price(match.get("csv_price_per_gallon"))
            if match.get("match_status") == "VERIFIED"
            else None
        )
        if verified_price is None:
            match["optimizer_price_per_gallon"] = str(average_price)
            match["optimizer_price_source"] = "dataset_average"
            estimated_count += 1
        prepared.append(station_copy)
    return prepared, estimated_count


def build_route_station_response(start_location, destination_location):
    start = geocode_us_location(" ".join(start_location.split()))
    destination = geocode_us_location(" ".join(destination_location.split()))
    response = get_route_stations_with_prices(
        start=(start["longitude"], start["latitude"]),
        end=(destination["longitude"], destination["latitude"]),
    )
    average_price = get_average_dataset_fuel_price()
    optimizer_stations, estimated_count = _prepare_optimizer_stations(
        response["stations"]["features"],
        average_price,
    )
    optimization = optimize_fuel_stops(
        optimizer_stations,
        response["route"]["properties"]["distance_miles"],
        fuel_economy=10,
    )
    selected_stops = sorted(
        optimization.get("selected_stations", []),
        key=lambda stop: stop["distance_along_route_miles"],
    )
    selected_station_summaries = [
        {
            "id": stop["id"] or f"selected-station-{index}",
            "name": stop["name"],
        }
        for index, stop in enumerate(selected_stops, start=1)
    ]
    response["fuel_optimization"] = {
        "status": optimization["status"],
        "message": optimization.get("message"),
        "total_route_distance_miles": optimization[
            "total_route_distance_miles"
        ],
        "fuel_economy_mpg": 10,
        "total_fuel_cost": optimization["total_fuel_cost"],
        "selected_station_names": [
            stop["name"] for stop in selected_stops
        ],
        "selected_stations": selected_station_summaries,
        "price_assumptions": {
            "dataset_average_price_per_gallon": float(average_price),
            "estimated_station_count": estimated_count,
            "description": (
                "Stations without a verified CSV price use the overall US dataset "
                "average for optimization only; this is an estimate, not a station quote."
            ),
        },
    }
    response["locations"] = {
        "start": {
            "input": start_location,
            "formatted": start["formatted"],
            "coordinates": [start["longitude"], start["latitude"]],
        },
        "destination": {
            "input": destination_location,
            "formatted": destination["formatted"],
            "coordinates": [
                destination["longitude"],
                destination["latitude"],
            ],
        },
    }
    response["stations"] = [
        properties["name"]
        for station in sorted(
            response["stations"]["features"],
            key=lambda feature: feature.get("properties", {}).get(
                "distance_along_route_miles",
                float("inf"),
            ),
        )
        if isinstance((properties := station.get("properties")), dict)
        and properties.get("name")
    ]
    response["geocoding_lookups"] = 2
    return response
