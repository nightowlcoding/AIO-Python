# Inventory Control System

A web-based multi-location inventory management system for tracking products at Kingsville and Alice locations.

## 📁 Folder Structure

```
Inventory Control 2/
├── app.py                          # Main application file
├── README.md                       # This file
├── requirements.txt                # Python dependencies
├── Update - Sept 13th.csv          # Product list (place your CSV here)
├── sample_inventory.csv            # Sample inventory import format
├── data/                           # Inventory database storage
│   └── inventory_database.json     # Automatically created
├── backups/                        # Backup files
│   ├── product_lists/              # Product list version history
│   └── inventory_uploads/          # Uploaded inventory CSV backups
└── exports/                        # Exported CSV files
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install flask pandas
```

Or using the requirements file:
```bash
pip install -r requirements.txt
```

### 2. Add Your Product CSV
Place your product CSV file in this folder and name it: `Update - Sept 13th.csv`

The CSV should have these columns:
- Product Number
- Product Description
- Product Brand
- Product Package Size

### 3. Run the Application
```bash
python app.py
```

### 4. Access the Application
Open your browser and go to:
- Local: http://localhost:5002
- Network: http://YOUR_IP:5002

## 📋 Features

### Inventory Entry
- Select location (Kingsville or Alice)
- Choose date for inventory
- Enter quantities for products
- Save and load inventories by date
- Search and filter products

### Saved Inventories
- **Import inventory from CSV** - Upload CSV files with product numbers and quantities
- View all saved inventories
- Filter by location
- Export to CSV
- Delete old inventories
- Quick load to edit

### Manage Products
- Add new products
- Edit existing products
- Delete products
- Upload new product list CSV
- View backup history
- Search and filter products

### Reports
- Summary by location
- Track inventory dates
- Export capabilities

## 💾 Data Storage

All data is stored within this folder:

- **data/**: Inventory records (JSON format)
- **backups/**: Automatic backups of product lists and CSV files
- **backups/inventory_uploads/**: Uploaded inventory CSV files with timestamps
- **exports/**: Generated CSV export files

## 📤 Importing Inventory from CSV

You can quickly import inventory data from a CSV file instead of manually entering quantities:

### CSV Format Requirements

Your CSV file must contain two columns:
- **Product Number** (or Product #, ProductNumber, SKU)
- **Quantity** (or Qty, Count)

### Example CSV:
```csv
Product Number,Quantity
12345,10
67890,25
11111,5
```

### How to Import:

1. Go to the **"Saved Inventories"** tab
2. Select the **location** (Kingsville or Alice)
3. Choose the **inventory date**
4. Click **"Select CSV File"** and choose your file
5. The system will automatically:
   - Match product numbers with your product list
   - Import all valid quantities
   - Report any unmatched products
   - Save the inventory to the selected date
   - Create a backup of the uploaded file

### Important Notes:
- Only products that exist in your product list will be imported
- Unmatched products will be reported but not imported
- The original CSV is backed up in `backups/inventory_uploads/`
- You can review and edit the imported inventory after upload

A sample file (`sample_inventory.csv`) is included for reference.

## 📦 Portability

This folder is completely self-contained and portable:

1. **To backup**: Copy the entire "Inventory Control 2" folder
2. **To transfer**: Move/copy the folder to any location or computer
3. **To restore**: Place the folder anywhere and run `python app.py`

All paths are relative, so the application will work from any location.

## 🔧 Configuration

The application automatically:
- Creates necessary folders on first run
- Backs up product lists on every change
- Saves inventory data in JSON format
- Creates backups before CSV uploads

## 📝 Notes

- First run will create the folder structure automatically
- Product list changes are backed up with timestamps
- Inventory data is saved immediately
- All exports are saved in the exports/ folder
- Port 5002 is used by default (can be changed in app.py)

## 🆘 Troubleshooting

**Can't access the application:**
- Ensure port 5002 is not in use
- Check firewall settings for network access

**Products not loading:**
- Verify CSV file name: `Update - Sept 13th.csv`
- Check CSV has required columns
- Ensure CSV is in the same folder as app.py

**Data not saving:**
- Check folder permissions
- Ensure data/ folder exists

## 🔄 Integration

This system is designed to integrate with `productmixextraction.py` for automated order generation based on inventory data.

---

**Version:** 2.0  
**Last Updated:** January 2026
