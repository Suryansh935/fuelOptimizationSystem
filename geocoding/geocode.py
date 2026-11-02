
import os
import requests
from dotenv import load_dotenv
from geopy.distance import geodesic
import json
from shapely.geometry import LineString

load_dotenv()

API_KEY = os.getenv("GEOAPIFY_API_KEY")

GEOCODING_URL = "https://api.geoapify.com/v1/geocode/search"
PLACES_URL = "https://api.geoapify.com/v2/places"


def search_geocoding(query, limit=5):
    """
    Search for possible locations using Geoapify Geocoding API.
    """

    if not API_KEY:
        raise ValueError("GEOAPIFY_API_KEY is missing from .env")
 
    params = {
        "text": query,
        "format": "json",
        "limit": limit,
        "apiKey": API_KEY
    }

    response = requests.get(
        GEOCODING_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    return response.json().get("results", [])


def search_fuel_stations(lat, lon, radius=10000, limit=20):
    """
    Search for nearby fuel station POIs using Geoapify Places API.
    """

    if not API_KEY:
        raise ValueError("GEOAPIFY_API_KEY is missing from .env")

    params = {
        "categories": "service.vehicle.fuel",
        "filter": f"circle:{lon},{lat},{radius}",
        "bias": f"proximity:{lon},{lat}",
        "limit": limit,
        "apiKey": API_KEY
    }

    response = requests.get(
        PLACES_URL,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    return response.json().get("features", [])

def get_city_coordinates(city, state, country):
    """
    Get approximate coordinates of a city.
    These coordinates are only used as the centre
    for searching nearby fuel stations.
    """

    query = f"{city}, {state}, {country}"

    results = search_geocoding(query, limit=5)

    for result in results:
        if result.get("result_type") == "city":
            return {
                "latitude": result.get("lat"),
                "longitude": result.get("lon")
            }

    return None

def add_candidate_distances(candidates, reference_lat, reference_lon):
    for candidate in candidates:
        properties = candidate.get("properties", {})

        lat = properties.get("lat")
        lon = properties.get("lon")

        if lat is not None and lon is not None:
            distance = geodesic(
                (reference_lat, reference_lon),
                (lat, lon)
            ).km

            properties["distance_km"] = round(distance, 2)

    return candidates

def find_nearby_fuel_stations(city, state, country, radius=10000):
    """
    Find nearby fuel stations using city coordinates.
    """

    city_coordinates = get_city_coordinates(city, state, country)

    if not city_coordinates:
        return []

    lat = city_coordinates["latitude"]
    lon = city_coordinates["longitude"]

    candidates = search_fuel_stations(
        lat=lat,
        lon=lon,
        radius=radius,
        limit=20
    )

    return candidates


def search_fuel_stations_along_route(
    route_geometry,
    buffer=2000,
    limit=500,
    max_pages=3,
    return_metadata=False,
):
    if not API_KEY:
        raise ValueError("GEOAPIFY_API_KEY is missing from .env")

    payload = {
        "categories": ["service.vehicle.fuel"],
        "filter": {
            "type": "polyline",
            "geometry": route_geometry,
            "buffer": buffer
        },
        "limit": limit
    }

    if limit <= 0 or max_pages <= 0:
        raise ValueError("limit and max_pages must be positive")

    features = []
    requests_made = 0
    truncated = False

    for page in range(max_pages):
        params = {
            "apiKey": API_KEY,
            "offset": page * limit,
        }
        response = requests.post(
            PLACES_URL,
            params=params,
            json=payload,
            timeout=60
        )
        requests_made += 1
        response.raise_for_status()

        data = response.json()
        page_features = data.get("features", [])
        if not isinstance(page_features, list):
            raise ValueError("Geoapify response did not contain a feature list")

        features.extend(page_features)
        if len(page_features) < limit:
            break
        if page + 1 == max_pages:
            truncated = True

    if return_metadata:
        return {
            "features": features,
            "requests_made": requests_made,
            "truncated": truncated,
        }

    return features