import pandas as pd

# Load the CSV file
df = pd.read_csv('/Users/arnoldoramirezjr/Desktop/Checking1.csv')

# Remove rows where 'Amount' is positive
df = df[df['Amount'] <= 0]

# Sort by the 'Bill' column
df_sorted = df.sort_values(by='Bill')

# Print the sorted DataFrame
print(df_sorted)

# Get the sum total for the 'Amount' column
total_amount = df_sorted['Amount'].sum()
print("Total Amount:", total_amount)

# Save the sorted DataFrame to a new CSV file on the Desktop
df_sorted.to_csv('/Users/arnoldoramirezjr/Desktop/sorted_checking.csv', index=False)