from geocoding.route import get_route

# Coordinates are (longitude, latitude)
chicago = (-87.6298, 41.8781)
kansas_city = (-94.5786, 39.0997)

route = get_route(chicago, kansas_city)

print("Distance:", round(route["distance_miles"], 2), "miles")
print("Duration:", round(route["duration_minutes"], 2), "minutes")
print("Number of route coordinates:", len(route["geometry"]["coordinates"]))