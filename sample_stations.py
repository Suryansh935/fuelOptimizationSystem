
import pandas as pd

df = pd.read_csv("data/cleaned_fuel_prices.csv")

# Select 10 sample stations
sample = df.head(10).copy()

# Save them separately
sample.to_csv("data/sample_stations.csv", index=False)

print("Sample created successfully!")
print(sample[["Truckstop Name", "Address", "City", "State", "Country"]])
