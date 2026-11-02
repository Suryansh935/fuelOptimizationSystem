
from geocoding.validate import name_matches, location_matches

# Test 1: Name matching
print("Name matching:")

print(name_matches(
    "PETRO STOPPING CENTER #348",
    "Petro"
))

print(name_matches(
    "ACI TRUCK STOP",
    "Shell"
))


# Test 2: Location matching
print("\nLocation matching:")

print(location_matches(
    "Shorter", "AL",
    "Shorter", "Alabama"
))

print(location_matches(
    "Shorter", "AL",
    "Knowlton Township", "New Jersey"
))
