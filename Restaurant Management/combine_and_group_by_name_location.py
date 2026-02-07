import pandas as pd
import os

# File paths
files = [
    "/Users/arnoldoramirezjr/Desktop/Kingsville.csv",
    "/Users/arnoldoramirezjr/Desktop/Alice.csv"
]

# List to hold DataFrames
dfs = []

for file in files:
    # Extract location from file name
    location = os.path.splitext(os.path.basename(file))[0].capitalize()
    df = pd.read_csv(file)
    df['Location'] = location
    dfs.append(df)

# Combine all data
combined_df = pd.concat(dfs, ignore_index=True)

# Assume 'Name' column exists and is the grouping key
# Clean up names (strip whitespace)
combined_df['Name'] = combined_df['Name'].astype(str).str.strip()

# Group by Name and Location, sum numeric columns
grouped = combined_df.groupby(['Name', 'Location'], as_index=False).sum(numeric_only=True)

# Save the grouped data
output_path = "/Users/arnoldoramirezjr/Desktop/combined_grouped_by_name_location.csv"
grouped.to_csv(output_path, index=False)
print(f"Grouped data saved to {output_path}")
