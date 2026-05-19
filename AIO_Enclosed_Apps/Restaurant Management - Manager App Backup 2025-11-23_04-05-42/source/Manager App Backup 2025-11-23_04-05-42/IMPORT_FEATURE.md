# Excel/CSV Import Feature

## Overview
The Daily Log now supports importing data from both CSV and Excel files, matching the functionality of the desktop DLimport.py application.

## Supported File Formats

### 1. CSV Format (Simple)
Basic CSV format with two sections:

```csv
Employee Hours
John Doe,8
Jane Smith,6.5

Sales Summary
Cash Sales,500.00
Visa,300.00
Mastercard,200.00
Amex,150.00
Other Income,50.00
```

### 2. Excel Format (.xlsx)
Excel files with multiple sheets (matching DLimport.py format):

#### Sheet: "All Data"
- Contains: Cash and CC Tips
- Format: Two columns (Description, Amount)

#### Sheet: "Payment Summary"
- Contains: Visa, Mastercard, Amex, Discover totals
- Format: Two columns (Card Type, Amount)

#### Sheet: "Sales Category Summary"
- Contains: Liquor, Beer, Wine, Food sales
- Format: Two columns (Category, Amount)

## How It Works

### Backend (app.py)
1. **API Endpoint**: `/api/import-file` (POST)
   - Accepts CSV or Excel files
   - Routes to appropriate parser
   - Returns JSON with extracted data

2. **Excel Parser**: `parse_excel_file(file)`
   - Uses openpyxl library
   - Searches for sheets by name patterns
   - Extracts data using fuzzy string matching (like DLimport.py)
   - Aggregates amounts for each category
   - Returns structured dict with all fields

3. **CSV Parser**: `parse_csv_file(file)`
   - Simple section-based parsing
   - Handles "Employee Hours" and "Sales Summary" sections
   - Returns structured dict with employee list and sales

### Frontend (daily_log.html)
1. **Import Button**: Triggers file picker for .csv or .xlsx files
2. **File Detection**: Checks extension to determine parsing method
3. **CSV Import**: Client-side parsing with FileReader API
4. **Excel Import**: 
   - Uploads file to backend via fetch API
   - Receives JSON response
   - Fills form fields automatically
5. **Loading State**: Shows spinner during import
6. **Error Handling**: User-friendly error messages

## Data Flow

### Desktop to Web Compatibility
```
DLimport.py (Desktop)                     Web App
     ↓                                        ↓
Read Excel File                        Upload Excel File
     ↓                                        ↓
Parse Multiple Sheets   →  [Same Format] →  Parse Multiple Sheets
     ↓                                        ↓
Extract Data                           Extract Data
     ↓                                        ↓
Save to JSON                           Return JSON to Browser
     ↓                                        ↓
dailylog.py reads JSON                 JavaScript fills form
```

### Data Structure (JSON)
```json
{
  "cash": 1250.50,
  "cc_tips": 185.75,
  "visa": 850.00,
  "mastercard": 620.50,
  "amex": 340.25,
  "discover": 125.00,
  "credit_total": 1935.75,
  "liquor": 450.00,
  "beer": 380.50,
  "wine": 290.00,
  "food": 815.25
}
```

## Features Matching DLimport.py

✅ **Multi-Sheet Parsing**: Searches for sheets by name patterns
✅ **Fuzzy Matching**: Uses lowercase string matching for flexibility
✅ **Data Aggregation**: Sums amounts across multiple rows
✅ **Error Handling**: Try/except blocks prevent crashes
✅ **Validation**: Checks data types and handles None values
✅ **Credit Total**: Auto-calculates total from card types
✅ **Desktop Compatible**: Uses same data extraction logic

## Testing

### Test File Included
- `test_import.xlsx` - Sample Excel file with all three sheets
- Contains realistic test data for all categories

### Test Cases
1. **CSV Import**: Use `sample_daily_log.csv`
2. **Excel Import**: Use `test_import.xlsx`
3. **Error Handling**: Try uploading .txt file (should show error)
4. **Missing Sheets**: Excel with only some sheets (should extract what's available)
5. **Empty Values**: Sheets with no data (should default to 0)

## Usage Instructions

1. **Open Daily Log page**
2. **Click "Import CSV/Excel" button**
3. **Select file** (.csv or .xlsx)
4. **Wait for import** (spinner appears)
5. **Verify data** (form fields auto-filled)
6. **Make adjustments** if needed
7. **Submit form** to save

## Technical Details

### Dependencies
- Flask 3.1.2
- openpyxl 3.1.5 (for Excel parsing)
- JavaScript Fetch API (for file upload)

### File Size Limits
- Default Flask limit: 16MB
- Can be adjusted with `MAX_CONTENT_LENGTH` config

### Performance
- CSV: Instant (client-side)
- Excel: 1-2 seconds (server-side parsing)

### Browser Compatibility
- Chrome/Edge: ✅ Full support
- Firefox: ✅ Full support
- Safari: ✅ Full support
- Mobile: ✅ Responsive design

## Future Enhancements

🔄 **Potential Additions**:
- Drag-and-drop file upload
- Import history tracking
- Bulk import (multiple files)
- Excel template download
- Data validation rules
- Import preview before submission
- Auto-save imported data
- Export to Excel from web

## Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "No file uploaded" | No file selected | Choose a file first |
| "Unsupported file type" | Wrong extension | Use .csv or .xlsx |
| "Import failed: ..." | Parsing error | Check file format |
| "Please log in..." | Session expired | Log in again |

## Comparison: DLimport.py vs Web Import

| Feature | DLimport.py | Web Import | Status |
|---------|-------------|------------|--------|
| Excel Parsing | ✅ openpyxl | ✅ openpyxl | ✅ Same |
| Multi-Sheet | ✅ Yes | ✅ Yes | ✅ Same |
| Fuzzy Matching | ✅ Yes | ✅ Yes | ✅ Same |
| Data Validation | ✅ Yes | ✅ Yes | ✅ Same |
| Error Handling | ✅ Yes | ✅ Yes | ✅ Same |
| CSV Support | ❌ No | ✅ Yes | ✅ Enhanced |
| UI Feedback | ✅ Desktop alerts | ✅ Web alerts | ✅ Same UX |
| File Storage | ✅ JSON file | ✅ In-memory | ⚠️ Different |

## Code Location

- **Backend**: `/app.py` lines 800-1069
  - `/api/import-file` route
  - `parse_excel_file()` function
  - `parse_all_data_sheet()` function
  - `parse_payment_summary_sheet()` function
  - `parse_sales_category_sheet()` function
  - `parse_csv_file()` function

- **Frontend**: `/templates/daily_log.html`
  - Import button (line 12-14)
  - `importCSV()` function (line 215)
  - `importExcelFile()` function (line 252)
  - `fillFormWithExcelData()` function (line 275)
  - `parseAndFillCSV()` function (line 324)

## Maintenance Notes

- **openpyxl version**: Keep updated for Excel compatibility
- **File cleanup**: Uploaded files are processed in memory (no temp files)
- **Session security**: Import requires authentication
- **CORS**: Not configured (same-origin only)

---

**Created**: January 2025  
**Last Updated**: January 2025  
**Status**: ✅ Production Ready
