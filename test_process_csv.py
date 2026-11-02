from geocoding.process_csv import process_csv

process_csv(
    input_file="data/cleaned_fuel_prices.csv",
    output_file="data/geocoded_test.csv",
    limit=10
)