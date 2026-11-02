import requests
from shapely.geometry import LineString
import json

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

def get_route(start, end):
    coordinates = f"{start[0]},{start[1]};{end[0]},{end[1]}"

    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false"
    }

    response = requests.get(
        f"{OSRM_URL}/{coordinates}",
        params=params,
        timeout=30
    )

    response.raise_for_status()
    data = response.json()

    if data["code"] != "Ok" or not data["routes"]:
        raise ValueError("Could not find a route")

    route = data["routes"][0]

    return {
        "distance_miles": route["distance"] / 1609.344,
        "duration_minutes": route["duration"] / 60,
        "geometry": route["geometry"]
    }

def simplify_route_geometry(geometry, max_bytes=90000):
    coordinates = geometry["coordinates"]

    route_line = LineString(coordinates)

    tolerance = 0.001

    while True:
        simplified_line = route_line.simplify(
            tolerance,
            preserve_topology=True
        )

        simplified_geometry = {
            "type": "LineString",
            "coordinates": list(simplified_line.coords)
        }

        geometry_size = len(
            json.dumps(simplified_geometry).encode("utf-8")
        )

        if geometry_size <= max_bytes:
            return simplified_geometry

        tolerance *= 1.5