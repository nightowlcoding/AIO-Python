# Quarterly Report Automation

This project provides tools to automatically generate quarterly reports from weekly Excel data.

## Files

### 1. `automate_quarterly_report.py` (Command-line version)
- **Purpose**: Standalone script with hardcoded values
- **Usage**: Quick runs with predefined settings
- **Configuration**: Edit the script to change SOURCE_FILE, OUTPUT_FILE, locations, and week sheets

### 2. `automate_quarterly_report_gui.py` (GUI version) ⭐ **RECOMMENDED**
- **Purpose**: User-friendly interface with dynamic configuration
- **Usage**: Run the GUI and fill in the form
- **Features**:
  - Browse for source and output files
  - Configure quarter name (e.g., "Q1 2026", "Q2 2026")
  - Set locations (comma-separated)
  - Set week sheet names (comma-separated, supports 52 weeks)
  - Real-time feedback and error handling

## Installation

```bash
# Activate your virtual environment
venv\Scripts\activate

# Install required packages (if not already installed)
pip install openpyxl
```

## Usage

### GUI Version (Recommended)
```bash
python automate_quarterly_report_gui.py
```

Then fill in the form:
- **Source Excel File**: Browse to your quarterly report Excel file
- **Output Excel File**: Choose where to save the updated report
- **Quarter Name**: e.g., "Q1 2026", "Q2 2026", "2026 Annual Report"
- **Locations**: e.g., "Kingsville, Alice" or "Location1, Location2, Location3"
- **Week Sheet Names**: e.g., "Q1W1, Q1W2, Q1W3, Q1W4, Q1W5" or for annual "W1, W2, W3, ..., W52"

### Command-line Version
```bash
python automate_quarterly_report.py
```

Edit the script first to set:
- `SOURCE_FILE`: Path to your source Excel file
- `OUTPUT_FILE`: Path for the output file
- `LOCATIONS`: List of location names
- `WEEK_SHEETS`: List of week sheet names

## Features

✅ **Dynamic week configuration** - Supports any number of weeks (5, 13, 26, 52, etc.)
✅ **Multiple locations** - Compare data across different locations
✅ **Auto-calculation** - Calculates percentages, variances, totals, and averages
✅ **Center-aligned cells** - Professional formatting throughout
✅ **Shift analysis** - Morning vs Night comparisons
✅ **Category breakdown** - Beer, Liquor, Wine, Food/NA tracking
✅ **Day-by-day analysis** - Performance by day of the week

## Report Sections Generated

1. **Summary** - Forecast vs Actual, Variance %, Morning %, Night %
2. **Shift by Day - Morning** - Sales by day for morning shift + totals & averages
3. **Shift by Day - Night** - Sales by day for night shift + totals & averages
4. **Shift by Day - Combined** - Combined morning + night sales + totals & averages
5. **Category by Shift - Morning** - Morning sales by category (Beer, Liquor, Wine, Food/NA)
6. **Category by Shift - Night** - Night sales by category
7. **Category by Shift - Combined** - Combined category sales
8. **Best/Worst Day by Shift** - Performance analysis by day of week

## Future-Proofing for 52 Weeks

The system is ready for annual (52-week) reports:

```
Week Sheet Names: W1, W2, W3, W4, W5, ..., W52
```

Or quarterly:
```
Q1: Q1W1, Q1W2, Q1W3, Q1W4, Q1W5
Q2: Q2W1, Q2W2, Q2W3, Q2W4, Q2W5
Q3: Q3W1, Q3W2, Q3W3, Q3W4, Q3W5
Q4: Q4W1, Q4W2, Q4W3, Q4W4, Q4W5
```

## Troubleshooting

**Sheet not found error**: Make sure the week sheet names in your configuration match exactly with the sheet names in your Excel file.

**No data error**: Verify that your Excel sheets contain the expected data structure with "Total Week Forecast", "Total Week Actual", and location names.

**File permissions error**: Make sure the source file is not open in Excel when running the script.

## Notes

- The original weekly sheets are preserved and not modified
- An "Overview" sheet is created/updated with all analysis
- All cells are center-aligned for professional appearance
- Number formatting is applied automatically ($#,##0.00 for currency, 0.00% for percentages)
