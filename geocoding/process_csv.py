import pandas as pd

from geocoding.geocode import find_nearby_fuel_stations
from geocoding.validate import find_best_candidate


def process_station(row):

    original_name = row["Truckstop Name"]
    city = row["City"]
    state = row["State"]
    country = row["Country"]

    candidates = find_nearby_fuel_stations(
        city=city,
        state=state,
        country=country
    )

    result = find_best_candidate(
        original_name=original_name,
        original_city=city,
        original_state=state,
        candidates=candidates
    )

    candidate = result["candidate"]

    return {
        "latitude": candidate["latitude"] if candidate else None,
        "longitude": candidate["longitude"] if candidate else None,
        "matched_name": candidate["candidate_name"] if candidate else None,
        "matched_address": candidate["candidate_address"] if candidate else None,
        "match_score": result["score"],
        "status": result["status"]
    }


def process_csv(input_file, output_file, limit=10):

    df = pd.read_csv(input_file)

    # Initially process only a small sample
    df = df.head(limit).copy()

    results = []

    for index, row in df.iterrows():

        print(f"Processing {index + 1}: {row['Truckstop Name']}")

        try:
            result = process_station(row)
        except Exception as error:
            print("Error:", error)

            result = {
                "latitude": None,
                "longitude": None,
                "matched_name": None,
                "matched_address": None,
                "match_score": 0,
                "status": "ERROR"
            }

        results.append(result)

        # Save after every record to avoid losing progress
        result_df = pd.DataFrame(results, index=df.index[:len(results)])
        output_df = pd.concat(
            [df.iloc[:len(results)], result_df],
            axis=1
        )
        output_df.to_csv(output_file, index=False)

    print(f"\nCompleted! Results saved to {output_file}")