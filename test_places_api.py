
import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEOAPIFY_API_KEY")

URL = "https://api.geoapify.com/v2/places"

# Approximate coordinates from our earlier geocoding results.
test_locations = [
    {
        "name": "ACI TRUCK STOP",
        "city": "Columbia",
        "state": "NJ",
        "lat": 40.917304,
        "lon": -75.082278
    },
    {
        "name": "SHENANDOAH TRUCK CENTER",
        "city": "Mount Jackson",
        "state": "VA",
        "lat": 38.75,
        "lon": -78.64
    },
    {
        "name": "PETRO STOPPING CENTER #348",
        "city": "Shorter",
        "state": "AL",
        "lat": 32.394861,
        "lon": -85.916902
    }
]

results = []

for station in test_locations:

    params = {
        "categories": "service.vehicle.fuel",
        "filter": (
            f"circle:{station['lon']},"
            f"{station['lat']},10000"
        ),
        "bias": f"proximity:{station['lon']},{station['lat']}",
        "limit": 20,
        "apiKey": API_KEY
    }

    try:
        response = requests.get(URL, params=params, timeout=20)
        response.raise_for_status()

        features = response.json().get("features", [])

        print(f"\nStation: {station['name']}")
        print(f"Fuel POIs found: {len(features)}")

        for feature in features:
            properties = feature.get("properties", {})

            result = {
                "Original Station": station["name"],
                "Candidate Name": properties.get("name"),
                "City": properties.get("city"),
                "State": properties.get("state"),
                "Address": properties.get("formatted"),
                "Latitude": properties.get("lat"),
                "Longitude": properties.get("lon"),
                "Distance (m)": properties.get("distance")
            }

            results.append(result)
            print(result)

    except requests.RequestException as error:
        print(f"API error for {station['name']}: {error}")

if results:
    pd.DataFrame(results).to_csv(
        "data/places_test_results.csv",
        index=False
    )
    print("\nResults saved to data/places_test_results.csv")
else:
    print("\nNo fuel station candidates found.")
