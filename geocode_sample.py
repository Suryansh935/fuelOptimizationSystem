
import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEOAPIFY_API_KEY")

if not API_KEY:
    raise ValueError("API key not found")

df = pd.read_csv("data/sample_stations.csv")

results = []

for _, row in df.iterrows():

    # Strategy A: Include highway/exit address
    query_a = (
        f"{row['Truckstop Name']}, "
        f"{row['Address']}, "
        f"{row['City']}, "
        f"{row['State']}, "
        f"{row['Country']}"
    )

    # Strategy B: Exclude highway/exit address
    query_b = (
        f"{row['Truckstop Name']}, "
        f"{row['City']}, "
        f"{row['State']}, "
        f"{row['Country']}"
    )

    for strategy, query in [("A", query_a), ("B", query_b)]:

        print(f"\nStation: {row['Truckstop Name']}")
        print(f"Strategy {strategy}: {query}")

        url = "https://api.geoapify.com/v1/geocode/search"

        params = {
            "text": query,
            "apiKey": API_KEY,
            "limit": 5
        }

        try:
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()

            features = response.json().get("features", [])

            if not features:
                print("No results found.")

            for candidate_number, feature in enumerate(features, start=1):

                p = feature["properties"]

                print(f"\nCandidate {candidate_number}")
                print("Name:", p.get("name"))
                print("Formatted:", p.get("formatted"))
                print("City:", p.get("city"))
                print("State:", p.get("state"))
                print("Country:", p.get("country"))
                print("Result type:", p.get("result_type"))
                print("Categories:", p.get("categories"))
                print("Coordinates:", p.get("lat"), p.get("lon"))

                results.append({
                    "Station": row["Truckstop Name"],
                    "Strategy": strategy,
                    "Query": query,
                    "Candidate": candidate_number,
                    "Name": p.get("name"),
                    "Formatted": p.get("formatted"),
                    "City": p.get("city"),
                    "State": p.get("state"),
                    "Country": p.get("country"),
                    "Result Type": p.get("result_type"),
                    "Categories": str(p.get("categories")),
                    "Latitude": p.get("lat"),
                    "Longitude": p.get("lon")
                })

        except requests.RequestException as error:
            print("API error:", error)

output = pd.DataFrame(results)
output.to_csv("data/geocoding_comparison.csv", index=False)

print("\nComparison completed!")
print("Results saved to data/geocoding_comparison.csv")
