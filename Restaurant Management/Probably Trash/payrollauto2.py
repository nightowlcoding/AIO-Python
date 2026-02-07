import pandas as pd

# Define the path to the CSV file
csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/PayrollExport_2025_02_09-2025_02_15.csv'

# Read the CSV file into a DataFrame
payroll_data = pd.read_csv(csv_file_path)

# Extract specific columns
columns_to_extract = [
    'Employee', 'Job Title', 'Regular Hours', 'Overtime Hours', 
    'Declared Tips', 'Non-Cash Tips', 'Total Tips'
]
extracted_data = payroll_data[columns_to_extract]

# Function to reformat employee names
def reformat_employee_name(name):
    parts = [part.strip() for part in name.split(',')]
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    return name

# Apply the reformatting function to the 'Employee' column
extracted_data['Employee'] = extracted_data['Employee'].apply(reformat_employee_name)

# Insert new rows with specified values
new_row = {
    'Employee': 'Arnold Ramirez',
    'Job Title': 'General Manager',
    'Regular Hours': 0,
    'Overtime Hours': 0,
    'Declared Tips': 0,
    'Non-Cash Tips': 0,
    'Total Tips': 0
}
new_row2 = {
    'Employee': 'Anahi Rodriguez',
    'Job Title': 'Manager',
    'Regular Hours': 0,
    'Overtime Hours': 0,
    'Declared Tips': 0,
    'Non-Cash Tips': 0,
    'Total Tips': 0
}
extracted_data = pd.concat([extracted_data, pd.DataFrame([new_row, new_row2])], ignore_index=True)

# Calculate the totals for each column from 'Regular Hours' onwards
totals = extracted_data.iloc[:, 2:].sum()

# Create a new row for the totals
totals_row = pd.DataFrame([{
    'Employee': 'Total',
    'Job Title': '',
    'Regular Hours': totals['Regular Hours'],
    'Overtime Hours': totals['Overtime Hours'],
    'Declared Tips': totals['Declared Tips'],
    'Non-Cash Tips': totals['Non-Cash Tips'],
    'Total Tips': totals['Total Tips']
}])

# Sort the cleaned data alphabetically by the 'Employee' column
sorted_data = extracted_data.sort_values(by='Employee')

# Append the totals row to the DataFrame
sorted_data = pd.concat([sorted_data, totals_row], ignore_index=True)

# Display the cleaned and sorted data
print(sorted_data)

# Export the sorted data to a new CSV file
sorted_csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Sorted_Payroll_Data.csv'
sorted_data.to_csv(sorted_csv_file_path, index=False)

print(f"Data exported to {sorted_csv_file_path}")