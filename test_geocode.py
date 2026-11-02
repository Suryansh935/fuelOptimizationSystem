from geocoding.geocode import (
    search_fuel_stations,
    add_candidate_distances
)

lat = 40.9173036
lon = -75.0822779

results = search_fuel_stations(
    lat=lat,
    lon=lon,
    radius=5000,
    limit=20
)

results = add_candidate_distances(results, lat, lon)

for feature in results:
    properties = feature.get("properties", {})

    print(
        properties.get("name"),
        properties.get("distance_km"),
        properties.get("formatted")
    )