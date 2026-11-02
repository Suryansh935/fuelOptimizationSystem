from geocoding.geocode import find_nearby_fuel_stations
from geocoding.validate import find_best_candidate

candidates = find_nearby_fuel_stations(
    city="Shorter",
    state="AL",
    country="USA"
)

result = find_best_candidate(
    original_name="PETRO STOPPING CENTER #348",
    original_city="Shorter",
    original_state="AL",
    candidates=candidates
)

print("Status:", result["status"])
print("Score:", result["score"])
print("Best candidate:", result["candidate"])