from pathlib import Path
from functools import lru_cache

from geocoding.filter_stations import filter_stations_near_route
from geocoding.geocode import search_fuel_stations_along_route
from geocoding.match_stations import match_station
from geocoding.prices import load_price_data, normalize_station_name, normalize_text
from geocoding.route import get_route, simplify_route_geometry


DEFAULT_PRICE_CSV = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "cleaned_fuel_prices.csv"
)


@lru_cache(maxsize=2)
def _load_cached_price_data(csv_path, modified_time_ns):
    return load_price_data(csv_path)


def _get_price_index(csv_path):
    resolved_path = Path(csv_path).resolve()
    modified_time_ns = resolved_path.stat().st_mtime_ns
    return _load_cached_price_data(str(resolved_path), modified_time_ns)


def _deduplicate_stations(stations):
    unique_stations = []
    seen = set()
    address_groups = {}

    for index, station in enumerate(stations):
        properties = station.get("properties", {})
        place_id = properties.get("place_id")
        latitude = properties.get("lat")
        longitude = properties.get("lon")
        if place_id and ("place_id", place_id) in seen:
            continue

        identity = ("place_id", place_id) if place_id else None
        if identity is None and isinstance(latitude, (int, float)) and isinstance(
            longitude, (int, float)
        ):
            identity = (
                "fallback",
                normalize_station_name(properties.get("name")),
                normalize_text(properties.get("city")),
                str(properties.get("state_code") or "").casefold(),
                round(latitude, 5),
                round(longitude, 5),
            )
        if identity is None:
            identity = ("unlocated", index)

        if identity in seen:
            continue

        address = normalize_text(
            properties.get("formatted") or properties.get("address")
        )
        location = (
            normalize_station_name(properties.get("name")),
            address,
            normalize_text(properties.get("city")),
            str(properties.get("state_code") or "").casefold(),
        )
        if (
            address
            and isinstance(latitude, (int, float))
            and isinstance(longitude, (int, float))
        ):
            nearby_points = address_groups.setdefault(location, [])
            is_duplicate = any(
                (latitude - old_lat) ** 2 + (longitude - old_lon) ** 2
                <= 0.000001
                for old_lat, old_lon in nearby_points
            )
            if is_duplicate:
                continue
            nearby_points.append((latitude, longitude))

        seen.add(identity)
        unique_stations.append(station)

    return unique_stations


def build_route_station_result(
    route,
    discovered_stations,
    station_index,
    max_distance_km=2,
    response_geometry=None,
):
    """Filter, match, and order already discovered route stations."""
    filtered = filter_stations_near_route(
        discovered_stations,
        route["geometry"],
        max_distance_km=max_distance_km,
    )
    route_distance_miles = route["distance_miles"]

    unique_stations = _deduplicate_stations(filtered)
    enriched_stations = []
    for station in unique_stations:
        properties = station.get("properties", {})
        match = match_station(station, station_index)
        position = properties.get("route_position_fraction")
        if position is not None:
            properties["distance_along_route_miles"] = round(
                position * route_distance_miles,
                2,
            )

        properties["match_status"] = match["status"]
        properties["csv_price_per_gallon"] = (
            format(match["price"], "f") if match["price"] is not None else None
        )
        properties["price_source"] = (
            "data/cleaned_fuel_prices.csv"
            if match["price"] is not None
            else None
        )
        properties["csv_match"] = match["candidate"]
        properties["csv_candidates"] = match["candidates"]
        properties["match_reason"] = match.get("reason")
        enriched_stations.append(station)

    enriched_stations.sort(
        key=lambda station: station.get("properties", {}).get(
            "distance_along_route_miles",
            float("inf"),
        )
    )

    return {
        "route": {
            "type": "Feature",
            "geometry": (
                response_geometry
                if response_geometry is not None
                else route["geometry"]
            ),
            "properties": {
                "distance_miles": route_distance_miles,
                "duration_minutes": route["duration_minutes"],
            },
        },
        "stations": {
            "type": "FeatureCollection",
            "features": enriched_stations,
        },
        "duplicates_removed": len(filtered) - len(unique_stations),
    }


def get_route_stations_with_prices(
    start,
    end,
    price_csv_path=DEFAULT_PRICE_CSV,
    buffer_m=2000,
    max_distance_km=2,
    result_limit=500,
    max_pages=3,
):
    """Fetch a route and route stations, then attach only verified CSV prices.

    ``start`` and ``end`` are ``(longitude, latitude)`` tuples. This function
    does not geocode text locations.
    """
    route = get_route(start, end)
    simplified_geometry = simplify_route_geometry(route["geometry"])
    search_result = search_fuel_stations_along_route(
        route_geometry=simplified_geometry,
        buffer=buffer_m,
        limit=result_limit,
        max_pages=max_pages,
        return_metadata=True,
    )
    if isinstance(search_result, dict):
        discovered_stations = search_result["features"]
        geoapify_requests = search_result["requests_made"]
        truncated = search_result["truncated"]
    else:
        discovered_stations = search_result
        geoapify_requests = 1
        truncated = len(discovered_stations) >= result_limit

    station_index = _get_price_index(price_csv_path)
    result = build_route_station_result(
        route,
        discovered_stations,
        station_index,
        max_distance_km=max_distance_km,
        response_geometry=simplified_geometry,
    )

    if truncated:
        result.setdefault("warnings", []).append(
            "Station search reached its pagination limit; results may be incomplete."
        )

    statuses = {}
    for station in result["stations"]["features"]:
        status = station["properties"]["match_status"]
        statuses[status] = statuses.get(status, 0) + 1
    result["price_match_summary"] = statuses
    station_count = len(result["stations"]["features"])
    verified_count = statuses.get("VERIFIED", 0)
    if verified_count < station_count:
        result.setdefault("warnings", []).append(
            f"Only {verified_count} of {station_count} route stations have a verified CSV price; "
            "all other stations are returned without prices."
        )
    if not station_count:
        result.setdefault("warnings", []).append(
            "No fuel stations were found within 2 km of the route."
        )

    result["external_request_count"] = {
        "osrm": 1,
        "geoapify": geoapify_requests,
    }
    return result
