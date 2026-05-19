import csv

# Path to the CSV file
csv_file_path = '/Users/arnoldoramirezjr/Documents/AIO Python/data.csv'

# Column name to search for
column_name = 'Menu Item'

# Word to search for in the specified column
word_to_search = 'Chicken Wing'

# Words to exclude in the specified column
word_to_exclude = ''
word_to_exclude2 = ''
word_to_exclude3 = ''
word_to_exclude4 = ''

try:
    # Open the CSV file
    with open(csv_file_path, mode='r') as file:
        # Create a CSV DictReader object
        csv_reader = csv.DictReader(file)
        
        # Check if the file is empty
        if csv_reader.fieldnames is None:
            print(f"The file at path {csv_file_path} is empty.")
        # Check if the column exists in the CSV file
        elif column_name not in csv_reader.fieldnames:
            print(f"Column '{column_name}' does not exist in the CSV file.")
        else:
            # Iterate over each row in the CSV file
            items_found = []
            total_qty = 0
            for row in csv_reader:
                if (word_to_search in row[column_name] and 
                    word_to_exclude not in row[column_name] and 
                    word_to_exclude2 not in row[column_name] and
                    word_to_exclude3 not in row[column_name] and
                    word_to_exclude4 not in row[column_name]):
                    items_found.append(row)
                    total_qty += float(row['Item Qty'])
            
            if items_found:
                for item in items_found:
                    print(f"Item Name: {item[column_name]}, Item Qty: {item['Item Qty']}")
                print(f"Total Quantity of items containing '{word_to_search}': {total_qty}")
            else:
                print(f"No item containing '{word_to_search}' found in column '{column_name}', excluding specified words.")
except FileNotFoundError:
    print(f"The file at path {csv_file_path} does not exist.")