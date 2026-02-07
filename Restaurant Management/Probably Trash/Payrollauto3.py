import pandas as pd

# Define the path to the CSV file
csv_file_path = '/Users/arnoldoramirezjr/Downloads/PayrollExport_2025_11_23-2025_11_29 (1).csv'
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
    'Employee': 'Victor Moreno',
    'Job Title': 'Director of Catering',
    'Regular Hours': 0,
    'Overtime Hours': 0,
    'Declared Tips': 0,
    'Non-Cash Tips': 0,
    'Total Tips': 0
}
extracted_data = pd.concat([extracted_data, pd.DataFrame([new_row, new_row2])], ignore_index=True)

# Calculate the totals for each column from 'Regular Hours' onwards
totals = extracted_data.iloc[:, 2:].sum()
# Convert 'Regular Hours' and 'Overtime Hours' to float and combine them
total_combined_hours = float(totals['Regular Hours']) + float(totals['Overtime Hours'])

# Create a new row for the totals
totals_row = pd.DataFrame([{
    'Employee': 'Total',
    'Job Title': total_combined_hours,
    'Regular Hours': totals['Regular Hours'],
    'Overtime Hours': totals['Overtime Hours'],
    'Declared Tips': totals['Declared Tips'],
    'Non-Cash Tips': totals['Non-Cash Tips'],
    'Total Tips': totals['Total Tips']
}])

# Calculate the kitchen totals for each column from 'Regular Hours' onwards
kitchen_totals = extracted_data[extracted_data['Job Title'].isin(['Kitchen', 'Kitchen Manager'])].iloc[:, 2:].sum()

# Calculate the kitchen totals for each column from 'Regular Hours' onwards
kitchen_totals = extracted_data[extracted_data['Job Title'].isin(['Kitchen', 'Kitchen Manager'])].iloc[:, 2:].sum()

# Convert 'Regular Hours' and 'Overtime Hours' to float and combine them
kitchen_combined_hours = float(kitchen_totals['Regular Hours']) + float(kitchen_totals['Overtime Hours'])

# Create a new row for the kitchen totals
kitchen_totals_row = pd.DataFrame([{
    'Employee': 'Kitchen Totals',
    'Job Title': f"{(kitchen_combined_hours/total_combined_hours)*100:.2f}",
    'Regular Hours': kitchen_totals['Regular Hours'],
    'Overtime Hours': kitchen_totals['Overtime Hours'],
    'Declared Tips': kitchen_totals['Declared Tips'],
    'Non-Cash Tips': kitchen_totals['Non-Cash Tips'],
    'Total Tips': kitchen_totals['Total Tips']
}])

# Calculate the server totals for each column from 'Regular Hours' onwards
server_totals = extracted_data[extracted_data['Job Title'].isin(['SERVER', 'Server'])].iloc[:, 2:].sum()

# Convert 'Regular Hours' and 'Overtime Hours' to float and combine them
server_combined_hours = float(server_totals['Regular Hours']) + float(server_totals['Overtime Hours'])

# Create a new row for the server totals
server_totals_row = pd.DataFrame([{
    'Employee': 'Server Totals',
    'Job Title': f"{(server_combined_hours/total_combined_hours)*100:.2f}",
    'Regular Hours': server_totals['Regular Hours'],
    'Overtime Hours': server_totals['Overtime Hours'],
    'Declared Tips': server_totals['Declared Tips'],
    'Non-Cash Tips': server_totals['Non-Cash Tips'],
    'Total Tips': server_totals['Total Tips']
}])

# Calculate the server totals for each column from 'Regular Hours' onwards
host_totals = extracted_data[extracted_data['Job Title'].isin(['HOST', 'Host'])].iloc[:, 2:].sum()

# Convert 'Regular Hours' and 'Overtime Hours' to float and combine them
host_combined_hours = float(host_totals['Regular Hours']) + float(host_totals['Overtime Hours'])

# Create a new row for the server totals
host_totals_row = pd.DataFrame([{
    'Employee': 'Host Totals',
    'Job Title': f"{(host_combined_hours/total_combined_hours)*100: .2f}",
    'Regular Hours': host_totals['Regular Hours'],
    'Overtime Hours': host_totals['Overtime Hours'],
    'Declared Tips': host_totals['Declared Tips'],
    'Non-Cash Tips': host_totals['Non-Cash Tips'],
    'Total Tips': host_totals['Total Tips']
}])

# Calculate the server totals for each column from 'Regular Hours' onwards
bar_totals = extracted_data[extracted_data['Job Title'].isin(['BAR', 'Bartender'])].iloc[:, 2:].sum()

# Convert 'Regular Hours' and 'Overtime Hours' to float and combine them
bar_combined_hours = float(bar_totals['Regular Hours']) + float(bar_totals['Overtime Hours'])

# Create a new row for the server totals
bar_totals_row = pd.DataFrame([{
    'Employee': 'Bar Totals',
    'Job Title': f"{(bar_combined_hours/total_combined_hours)*100:.2f}",
    'Regular Hours': bar_totals['Regular Hours'],
    'Overtime Hours': bar_totals['Overtime Hours'],
    'Declared Tips': bar_totals['Declared Tips'],
    'Non-Cash Tips': bar_totals['Non-Cash Tips'],
    'Total Tips': bar_totals['Total Tips']
}])

# Sort the cleaned data alphabetically by the 'Employee' column
sorted_data = extracted_data.sort_values(by='Employee')

# Append the totals row and kitchen totals row to the DataFrame
sorted_data = pd.concat([sorted_data, totals_row, kitchen_totals_row,server_totals_row,host_totals_row,bar_totals_row], ignore_index=True)

# Display the cleaned and sorted data
print(sorted_data)

# Export the sorted data to a new CSV file
sorted_csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Sorted_Payroll_Data.csv'
sorted_data.to_csv(sorted_csv_file_path, index=False)

print(f"Data exported to {sorted_csv_file_path}")