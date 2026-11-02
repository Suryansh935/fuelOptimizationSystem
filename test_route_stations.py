
from geocoding.route import (
    get_route,
    simplify_route_geometry
)
from geocoding.filter_stations import filter_stations_near_route

from geocoding.geocode import search_fuel_stations_along_route

import json

chicago = (-87.6298, 41.8781)
kansas_city = (-94.5786, 39.0997)

# Step 1: Get route from OSRM
route = get_route(chicago, kansas_city)

# Step 2: Simplify route geometry
simplified_geometry = simplify_route_geometry(
    route["geometry"]
)

# Step 3: Find fuel stations along the route
stations = search_fuel_stations_along_route(
    route_geometry=simplified_geometry,
    buffer=10000,
    limit=500
)

# Step 4: Display results
filtered_stations = filter_stations_near_route(
    stations,
    route["geometry"],
    max_distance_km=2
)
print("Total saved:", len(filtered_stations))
with open(
    "filtered_route_stations.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(filtered_stations, file, indent=4)

print("Filtered stations saved successfully!")
print("\nStations returned by Geoapify:", len(stations))
print("Stations within 2 km of route:", len(filtered_stations))

for index, station in enumerate(filtered_stations[:20], start=1):
    properties = station["properties"]

    print(
        index,
        properties.get("name"),
        properties.get("city"),
        properties.get("state_code"),
        properties.get("distance_from_route_km"),
        "km"
    )