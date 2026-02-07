import pandas as pd

# Define the path to the first CSV file
csv_file_path1 = '/Users/arnoldoramirezjr/Documents/AIO Python/SalesSummary_2025-02-09_2025-02-15/Day of week (totals).csv'

# Read the first CSV file into a DataFrame
df1 = pd.read_csv(csv_file_path1)

# Define the custom sorting order
day_order = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
df1['Day of week'] = pd.Categorical(df1['Day of week'], categories=day_order, ordered=True)

# Sort the DataFrame by 'day of week'
df1 = df1.sort_values('Day of week')

# Calculate the totals for each column (excluding the 'Day of week' column)
totals = df1.iloc[:, 1:].sum()
totals = totals.to_frame().T
totals['Day of week'] = 'Total'

# Append the totals row to the DataFrame
df1 = pd.concat([df1, totals], ignore_index=True)

# Print all columns of the first DataFrame
print("Columns of Day of week (totals):")
print(df1.columns)

# Print all rows of the first DataFrame
print("\nRows of Day of week (totals):")
print(df1)

# Define the path to the second CSV file
csv_file_path2 = '/Users/arnoldoramirezjr/Documents/AIO Python/SalesSummary_2025-02-09_2025-02-15/Sales category summary.csv'

# Read the second CSV file into a DataFrame
df2 = pd.read_csv(csv_file_path2)

# Print all columns of the second DataFrame
print("\nColumns of Sales category summary:")
print(df2.columns)

# Print all rows of the second DataFrame
print("\nRows of Sales category summary:")
print(df2)

# Export the modified first DataFrame to a new CSV file
output_csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/SalesSummary_2025-02-09_2025-02-15/Day of week (totals)_with_totals.csv'
df1.to_csv(output_csv_file_path, index=False)

print(f"\nModified DataFrame has been exported to {output_csv_file_path}")