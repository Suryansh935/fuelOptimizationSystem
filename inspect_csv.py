
import pandas as pd

# Load the CSV file
file_path = "data/fuelPrices.csv"
df = pd.read_csv(file_path)

# Display basic information
print("First 5 rows:")
print(df.head())

print("\nDataset shape:")
print(df.shape)

print("\nColumn names:")
print(df.columns.tolist())

print("\nData types:")
print(df.dtypes)

print("\nMissing values:")
print(df.isnull().sum())

print("\nExact duplicate rows:")
print(df.duplicated().sum())

print("\nBasic statistics:")
print(df.describe(include="all"))
