# Inventory CSV Import Guide

## Overview
The Inventory Control System now supports importing inventory data from CSV files. This feature allows you to quickly upload inventory counts from external sources instead of manually entering each item.

## How It Works

### Step 1: Prepare Your CSV File

**EASY WAY:** Download the sample template directly from the app!
- Go to the "Saved Inventories" tab
- Click the **"⬇️ Download Sample Template"** button
- This gives you a CSV with all your products already listed in the correct order
- Just fill in the quantities and upload!

**MANUAL WAY:** Create your own CSV file with these columns (column names are flexible):

**Product Number Column (REQUIRED - any of these names work):**
- Product Number
- Product #
- ProductNumber
- product_number
- SKU

**Product Name Column (OPTIONAL - any of these names work):**
- Product Name
- Product Description
- Description
- Name
- product_name
- description

**Quantity Column (REQUIRED - any of these names work):**
- Quantity
- Qty
- Count
- quantity
- qty
- count

### Step 2: Upload the CSV

1. Open the Inventory Control System in your browser
2. Navigate to the **"Saved Inventories"** tab
3. In the "Upload Inventory from CSV" section:
   - Select the **Location** (Kingsville or Alice)
   - Choose the **Inventory Date** (the date this inventory count represents)
   - Click **"Select CSV File"** button
   - Choose your CSV file
4. The file will upload automatically once selected

### Step 3: Review Results

After upload, you'll see a status message showing:
- ✅ Success message
- Total items imported
- Number of matched products (products found in your product list)
- Number of unmatched products (product numbers not in your product list)
- Sample list of unmatched products (if any)

## Example CSV Format

**Two-Column Format (Product # and Quantity):**
```csv
Product Number,Quantity
12345,10
67890,25
11111,5
```

**Three-Column Format (Product #, Product Name, and Quantity):**
```csv
Product #,Product Name,Quantity
12345,Coca-Cola 12oz,10
67890,Pepsi 20oz,25
11111,Water Bottle,5
22222,Orange Juice,15
33333,Apple Juice,8
```

Both formats are supported! The Product Name column is optional and helps with readability.

## What Happens During Import

1. **File Validation**: System checks that the file is a CSV with required columns
2. **Product Matching**: Each product number is matched against your master product list
3. **Quantity Import**: Valid quantities are imported for matched products
4. **Data Storage**: Inventory is saved to the database for the specified location and date
5. **Backup Creation**: Original CSV is backed up with timestamp in `backups/inventory_uploads/`
6. **List Refresh**: The saved inventories list is automatically refreshed

## Important Notes

### ✅ Products Are Matched
- Only product numbers that exist in your master product list will be imported
- This prevents accidentally importing invalid product numbers

### 📋 Unmatched Products
- Products not found in your master product list are reported but not imported
- Add these products to your master list first if you want to track them

### 💾 Backup Files
- Every uploaded CSV is backed up with a timestamp
- Backup location: `backups/inventory_uploads/`
- Filename format: `inventory_{location}_{date}_{timestamp}.csv`

### 🔄 Overwriting Data
- Uploading inventory for an existing date/location will **overwrite** the previous data
- Make sure you're uploading to the correct date!

### 📊 After Import
- You can immediately view the imported inventory in the "Enter Inventory" tab
- Edit quantities if needed
- Export to CSV for reporting
- Use in order calculations

## Sample Files

A sample inventory CSV file is included: `sample_inventory.csv`

You can use this as a template for your own imports.

## Troubleshooting

### "No file selected"
- Make sure you clicked the file selection button and chose a file

### "Please provide an inventory date"
- Select a date before uploading the file

### "CSV must contain Product Number and Quantity columns"
- Check your column headers
- Make sure they match one of the accepted formats listed above

### "Products not found in product list"
- The unmatched products need to be added to your master product list first
- Go to "Manage Products" tab to add them

### "File must be a CSV"
- Only .csv files are accepted
- If you have an Excel file, save it as CSV first

## Benefits

✅ **Fast Data Entry**: Upload hundreds of items in seconds  
✅ **Error Reduction**: No manual typing errors  
✅ **Integration**: Import from other systems or handheld scanners  
✅ **Backup**: All uploads are automatically backed up  
✅ **Validation**: Only valid product numbers are imported  
✅ **Flexibility**: Works with various CSV formats and column names

---

**Need Help?** Check that your CSV format matches the examples above, or contact support.
