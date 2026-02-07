import pandas as pd

def create_inventory_database():
    """
    Extracts inventory data from the provided image and creates a Pandas DataFrame.
    The DataFrame is then saved to an Excel file named 'inventory_database.xlsx'.
    """

    # Data extracted from the image, categorized by type
    inventory_data = []

    # Tequila
    tequila_data = [
        {"Brand Name": "El Torro (Well)", "Bottle Size": "Liter", "Inventory": "6", "Order": "1/2"},
        {"Brand Name": "Patron Silver", "Bottle Size": "1/2 G", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Cazadores", "Bottle Size": "1/2 G", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "Jose Cuervo Gold", "Bottle Size": "1/2 G", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "Jose Tradicional Silver", "Bottle Size": "1/2 G", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "Don Julio", "Bottle Size": "1/2 G", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "El Torro (Margarita Mix)", "Bottle Size": "1/2 G", "Inventory": "2", "Order": "1/2"},
    ]
    for item in tequila_data:
        inventory_data.append({"Category": "Tequila", **item})

    # Whiskey
    whiskey_data = [
        {"Brand Name": "Disarino", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Grand Marnier", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Malibu", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Hpnotiq", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "X-Rated", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Blue Curacao", "Bottle Size": "Liter", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Water Melon", "Bottle Size": "Liter", "Inventory": "5", "Order": "1/2"},
        {"Brand Name": "Creme de Banana", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
    ]
    for item in whiskey_data:
        inventory_data.append({"Category": "Whiskey", **item})

    # Vodka
    vodka_data = [
        {"Brand Name": "Taaka (WELL)", "Bottle Size": "Liter", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Tito's Vodka", "Bottle Size": "1/2 G", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Grey Goose", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Cucumber Vodka", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Ciroc Apple", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Ciroc Red Berry", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
    ]
    for item in vodka_data:
        inventory_data.append({"Category": "Vodka", **item})

    # Rum
    rum_data = [
        {"Brand Name": "Malibu", "Bottle Size": "1/2 G", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Capt Morgan", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Ron Rio Silver", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Bacardi Dragon Berry", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
    ]
    for item in rum_data:
        inventory_data.append({"Category": "Rum", **item})

    # Gin
    gin_data = [
        {"Brand Name": "Crystal Palace (well)", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Bombay Sapphire", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
    ]
    for item in gin_data:
        inventory_data.append({"Category": "Gin", **item})

    # Bourbon/Whiskey/Scotch
    bourbon_data = [
        {"Brand Name": "Kentucky Deluxe", "Bottle Size": "Liter", "Inventory": "5", "Order": "1/2"},
        {"Brand Name": "Crown", "Bottle Size": "1/2 G", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Crown Apple", "Bottle Size": "1/2 G", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Jack Daniels", "Bottle Size": "1/2 G", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Jameson", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Jameson Orange", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Jim Beam", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Buchanans", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Jim Beam", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
    ]
    for item in bourbon_data:
        inventory_data.append({"Category": "Bourbon/Whiskey/Scotch", **item})

    # Bottled Beer
    beer_data = [
        {"Brand Name": "Bud Light", "Bottle Size": "8 pack", "Inventory": "6", "Order": "2"},
        {"Brand Name": "Budweiser", "Bottle Size": "8 pack", "Inventory": "2", "Order": "2"},
        {"Brand Name": "Coors Light", "Bottle Size": "8 pack", "Inventory": "2", "Order": "2"},
        {"Brand Name": "DosXX", "Bottle Size": "24 pack", "Inventory": "2", "Order": "3"},
        {"Brand Name": "Miller Lite", "Bottle Size": "12 pack", "Inventory": "2", "Order": "0"},
        {"Brand Name": "Ranch Water", "Bottle Size": "12 pack", "Inventory": "2", "Order": "0"},
        {"Brand Name": "Ultra Lite", "Bottle Size": "8 pack", "Inventory": "6", "Order": "0"},
    ]
    for item in beer_data:
        inventory_data.append({"Category": "Bottled Beer", **item})

    # Cointreau
    cointreau_data = [
        {"Brand Name": "Amaretto Mr. B", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Blue Curacao", "Bottle Size": "Liter", "Inventory": "5", "Order": "1/2"},
        {"Brand Name": "Triple Sec", "Bottle Size": "Liter", "Inventory": "5", "Order": "1/2"},
        {"Brand Name": "Peach Tree", "Bottle Size": "Liter", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Midori", "Bottle Size": "Liter", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Bailey's", "Bottle Size": "Liter", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Fireball", "Bottle Size": "Liter", "Inventory": "4", "Order": "1/2"},
        {"Brand Name": "Razzmatazz", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Strawberry Puckers", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
    ]
    for item in cointreau_data:
        inventory_data.append({"Category": "Cointreau", **item})

    # Rumple mints
    rumple_mints_data = [
        {"Brand Name": "Rumple mints", "Bottle Size": "Liter", "Inventory": "2", "Order": "1/2"},
    ]
    for item in rumple_mints_data:
        inventory_data.append({"Category": "Rumple mints", **item})

    # Beverages in Bag (BIB)
    bib_data = [
        {"Brand Name": "Pepsi", "Bottle Size": "BIB", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Diet Pepsi", "Bottle Size": "BIB", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "Dr Pepper", "Bottle Size": "BIB", "Inventory": "2", "Order": "1/2"},
        {"Brand Name": "Diet Dr Pepper", "Bottle Size": "BIB", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Big Red", "Bottle Size": "BIB", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Starry", "Bottle Size": "BIB", "Inventory": "3", "Order": "1/2"},
        {"Brand Name": "Pink Lemonade", "Bottle Size": "BIB", "Inventory": "1", "Order": "1/2"},
        {"Brand Name": "Root Beer Mug", "Bottle Size": "BIB", "Inventory": "1", "Order": "1/2"},
    ]
    for item in bib_data:
        inventory_data.append({"Category": "Beverages in Bag (BIB)", **item})

    # Additional Items
    additional_items_data = [
        {"Brand Name": "Tamarind Calypso", "Bottle Size": "N/A", "Inventory": "2", "Order": "1/2"}, # Size not specified in image
    ]
    for item in additional_items_data:
        inventory_data.append({"Category": "Additional Items", **item})


    # Create a Pandas DataFrame
    df = pd.DataFrame(inventory_data)

    # Define the output Excel file name
    excel_file_name = 'inventory_database.xlsx'

    # Save the DataFrame to an Excel file
    try:
        df.to_excel(excel_file_name, index=False)
        print(f"Database successfully created and saved to '{excel_file_name}'")
    except Exception as e:
        print(f"Error saving Excel file: {e}")

# Call the function to create the database
create_inventory_database()
