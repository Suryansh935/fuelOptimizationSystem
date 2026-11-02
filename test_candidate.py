
from geocoding.geocode import search_fuel_stations
from geocoding.validate import validate_candidate

results = search_fuel_stations(
    lat=32.3948615,
    lon=-85.916902
)

for candidate in results:

    validation = validate_candidate(
        original_name="PETRO STOPPING CENTER #348",
        original_city="Shorter",
        original_state="AL",
        candidate=candidate
    )

    print("\nCandidate:", validation["candidate_name"])
    print("Name match:", validation["name_match"])
    print("Location match:", validation["location_match"])
    print("Coordinates:", validation["latitude"], validation["longitude"])
