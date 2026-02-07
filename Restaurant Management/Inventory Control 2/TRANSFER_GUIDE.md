# Transfer & Backup Guide

## 📦 Complete Folder Contents

This folder contains everything needed to run the Inventory Control System:

```
Inventory Control 2/
├── app.py                      # Main application
├── README.md                   # Documentation
├── TRANSFER_GUIDE.md          # This file
├── requirements.txt           # Dependencies
├── start.sh                   # Mac/Linux startup script
├── start.bat                  # Windows startup script
├── Update - Sept 13th.csv     # Product list
├── data/                      # Created automatically
├── backups/                   # Created automatically
└── exports/                   # Created automatically
```

## ✅ How to Transfer

### Method 1: Copy the Entire Folder
Simply copy the entire "Inventory Control 2" folder to:
- Another location on your computer
- External drive (USB, external HDD)
- Cloud storage (Dropbox, Google Drive, iCloud)
- Another computer
- Network drive

The application will work from any location!

### Method 2: Compress for Transfer
**On Mac/Linux:**
```bash
# Navigate to parent folder
cd "/Users/arnoldoramirezjr/Documents/AIO Python"

# Create compressed archive
tar -czf "Inventory_Control_2_Backup.tar.gz" "Inventory Control 2"

# Or create a zip file
zip -r "Inventory_Control_2_Backup.zip" "Inventory Control 2"
```

**On Windows:**
Right-click the folder → "Compress to ZIP file"

### Method 3: Git Repository (Recommended for version control)
```bash
cd "Inventory Control 2"
git init
git add .
git commit -m "Initial commit of Inventory Control System"
```

## 🚀 How to Run After Transfer

### On Mac/Linux:
1. Open Terminal
2. Navigate to the folder:
   ```bash
   cd "/path/to/Inventory Control 2"
   ```
3. Run the startup script:
   ```bash
   ./start.sh
   ```
   
   Or run directly:
   ```bash
   python3 app.py
   ```

### On Windows:
1. Double-click `start.bat`
   
   Or open Command Prompt:
   ```cmd
   cd "C:\path\to\Inventory Control 2"
   python app.py
   ```

### First Time Setup on New Computer:
1. Install Python 3 (if not installed)
2. Navigate to the folder
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application

## 💾 What Gets Saved

### Automatically Created:
- `data/inventory_database.json` - All inventory records
- `backups/product_lists/` - Product list version history
- `backups/*.csv` - CSV file backups
- `exports/*.csv` - Exported inventory files

### Important Files:
- `Update - Sept 13th.csv` - Master product list
- All content in `data/`, `backups/`, `exports/` folders

## 🔄 Backup Schedule Recommendations

### Daily Backup (Automatic):
The system automatically creates backups when:
- Product list is modified
- CSV files are uploaded
- Changes are saved

### Manual Backup (Weekly Recommended):
Copy the entire "Inventory Control 2" folder to:
1. External drive
2. Cloud storage
3. Network location

### Example Backup Script (Mac/Linux):
```bash
#!/bin/bash
# Save as backup.sh in parent folder

DATE=$(date +%Y-%m-%d)
SOURCE="Inventory Control 2"
BACKUP_DIR="Backups"
BACKUP_NAME="Inventory_Control_2_Backup_$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/$BACKUP_NAME" "$SOURCE"
echo "✅ Backup created: $BACKUP_DIR/$BACKUP_NAME"
```

## 📤 Sharing with Team Members

### Option 1: Direct Copy
1. Copy entire folder to shared drive
2. Team members can run from shared location
3. Everyone accesses same data

### Option 2: Individual Copies
1. Each user gets their own copy
2. Use CSV export/import to share inventory data
3. Merge data manually as needed

### Option 3: Centralized Server (Advanced)
1. Run on one computer as server
2. Other team members access via IP address
3. Example: http://192.168.1.100:5002

## 🔧 Troubleshooting After Transfer

### "Module not found" error:
```bash
pip install flask pandas
```

### "Permission denied" on Mac/Linux:
```bash
chmod +x start.sh
```

### Port 5002 already in use:
Edit app.py, line at bottom:
```python
app.run(debug=True, host='0.0.0.0', port=5003)  # Change port
```

### Can't find CSV file:
Ensure "Update - Sept 13th.csv" is in the same folder as app.py

## 📊 Data Migration

### Export All Data:
1. Go to "Saved Inventories" tab
2. Export each inventory to CSV
3. Save all CSV files
4. Copy to new location with folder

### Import Data:
1. Place CSV files in new folder
2. Use "Manage Products" → "Upload CSV" for product list
3. Inventory data is in data/inventory_database.json

## ✨ Best Practices

1. **Before Transfer:**
   - Export all recent inventories
   - Note current product count
   - Close the application

2. **During Transfer:**
   - Copy entire folder, not individual files
   - Maintain folder structure
   - Use compression for email/upload

3. **After Transfer:**
   - Test by running application
   - Verify product list loads
   - Check inventory data is present

## 📝 Checklist for Complete Transfer

- [ ] Copy entire "Inventory Control 2" folder
- [ ] Verify all subfolders (data, backups, exports)
- [ ] Check CSV file is present
- [ ] Install Python on new system (if needed)
- [ ] Install dependencies (requirements.txt)
- [ ] Test run application
- [ ] Verify products load correctly
- [ ] Check saved inventories are accessible
- [ ] Test save/load functionality

## 🆘 Support

If you encounter issues after transfer:
1. Check Python is installed: `python3 --version`
2. Verify dependencies: `pip list | grep -E "flask|pandas"`
3. Check folder permissions
4. Review error messages in terminal
5. Ensure CSV file has correct name and format

---

**Remember:** This folder is completely self-contained and portable. Everything needed to run the system is included!
