import pandas as pd
import os

def process_folder(folder_path, output_name, quantity_file):
    # Collect all CSV files in the folder
    csv_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.csv')]
    dfs = []
    for file in csv_files:
        df = pd.read_csv(os.path.join(folder_path, file))
        dfs.append(df)
    combined_df = pd.concat(dfs, ignore_index=True)

    # Group by ProductNumber and ProductDescription, summing QtyShip and ExtendedPrice
    grouped_df = combined_df.groupby(['ProductNumber', 'ProductDescription'], as_index=False).agg({
        'QtyShip': 'sum',
        'ExtendedPrice': 'sum'
    })

    # Load quantity data and merge
    quantity_df = pd.read_csv(quantity_file)
    merged_df = pd.merge(grouped_df, quantity_df[['ProductNumber', 'Quantity']], on='ProductNumber', how='left')

    # Calculate Units
    merged_df['Units'] = merged_df['QtyShip'] * merged_df['Quantity']

    # Save to output file
    output_file = f'/Users/arnoldoramirezjr/Documents/AIO Python/PDFOrderSorter/{output_name}_with_units.csv'
    merged_df.to_csv(output_file, index=False)
    print(f"{output_file} created.")

# Paths
quantity_file = '/Users/arnoldoramirezjr/Documents/AIO Python/PDFOrderSorter/quantity_data.csv'

# Process Kingsville
process_folder(
    '/Users/arnoldoramirezjr/Documents/AIO Python/PDFOrderSorter/KingsvilleCSV',
    'Kingsville',
    quantity_file
)

# Process Alice
process_folder(
    '/Users/arnoldoramirezjr/Documents/AIO Python/PDFOrderSorter/AliceCSV',
    'Alice',
    quantity_file
)