import pandas as pd

# Load the CSV file
df = pd.read_csv('/Users/arnoldoramirezjr/Downloads/pmix_2025_03_02-2025_03_08.csv')

# Filter rows where 'Menu Item' contains zero characters (empty or only whitespace)
filtered = df[df['Menu Item'].str.strip() == '']

# Get unique items in 'Menu Group' for these rows
menu_groups = filtered['Menu Group'].unique().tolist()

# Prepare summary data
summary = []
for group in menu_groups:
    group_data = filtered[filtered['Menu Group'] == group]
    qty = group_data['Item Qty'].sum()
    gross = group_data['Gross Amount'].sum()
    discount = group_data['Discount Amount'].sum()
    net = group_data['Net Amount'].sum()
    summary.append({
        'Menu Group': group,
        'Item Qty': qty,
        'Gross Amount': gross,
        'Discount Amount': discount,
        'Net Amount': net
    })

# Create a DataFrame and save to CSV
summary_df = pd.DataFrame(summary)
summary_df.to_csv('/Users/arnoldoramirezjr/Desktop/menu_group_summary.csv', index=False)