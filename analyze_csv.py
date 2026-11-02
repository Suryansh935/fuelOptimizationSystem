
import pandas as pd

df = pd.read_csv("data/fuelPrices.csv")

# Remove only exact duplicate rows
df = df.drop_duplicates()

# Map US state codes to country
us_states = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE",
    "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY"
}

df["Country"] = df["State"].apply(
    lambda state: "USA" if state in us_states else "Canada"
)

# Save the cleaned dataset
df.to_csv("data/cleaned_fuel_prices.csv", index=False)

print("Cleaned CSV created successfully!")
print("\nCountry distribution:")
print(df["Country"].value_counts())

print("\nFinal shape:", df.shape)
