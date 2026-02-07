import os
import pandas as pd

# Define the path to the folder containing the CSV files
folder_path = '/Users/arnoldoramirezjr/Desktop/Kingsville'

# Initialize an empty list to store data from each CSV file
all_data = []

# Iterate over each file in the folder
for filename in os.listdir(folder_path):
    if filename.endswith('.csv'):
        file_path = os.path.join(folder_path, filename)
        # Read the CSV file into a DataFrame
        df = pd.read_csv(file_path)
        # Append the DataFrame to the list
        all_data.append(df)

# Concatenate all DataFrames in the list into a single DataFrame
combined_data = pd.concat(all_data, ignore_index=True)

# Select only the columns 'productnumber', 'productdescription', and 'qtyship'
selected_columns = combined_data[['ProductNumber', 'ProductDescription', 'QtyShip']]

# Group by ProductNumber and ProductDescription, sum the QtyShip
grouped_data = selected_columns.groupby(['ProductNumber', 'ProductDescription'], as_index=False)['QtyShip'].sum()

# Sort the DataFrame by 'productnumber'
sorted_data = grouped_data.sort_values(by='ProductNumber')

# Set display option to show all columns
pd.set_option('display.max_columns', None)

# Display the sorted data
print(sorted_data)

# Optionally, export the sorted data to a new CSV file
output_csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Sorted_InvoiceDetails.csv'
sorted_data.to_csv(output_csv_file_path, index=False)


print(f"Sorted data exported to {output_csv_file_path}")