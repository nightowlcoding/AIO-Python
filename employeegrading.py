import pandas as pd
import pdfplumber
import os
import sys
from datetime import datetime
from tkinter import Tk, filedialog

# Hide the main tkinter window
root = Tk()
root.withdraw()
root.attributes('-topmost', True)

# Get PDF file path from command line argument or file dialog
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]
    pdf_path = os.path.expanduser(pdf_path)
else:
    # Open file dialog to select PDF
    print("Please select a PDF file to grade...")
    pdf_path = filedialog.askopenfilename(
        title="Select Employee Productivity PDF",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        initialdir=os.path.expanduser("~/Downloads")
    )
    
    # Check if user cancelled
    if not pdf_path:
        print("No file selected. Exiting.")
        sys.exit(0)

# Check if file exists
if not os.path.exists(pdf_path):
    print(f"Error: File not found: {pdf_path}")
    print("\nUsage: python employeegrading.py [path_to_pdf_file]")
    print("Example: python employeegrading.py '/Users/username/Downloads/Alice November.pdf'")
    sys.exit(1)

print(f"Reading PDF: {pdf_path}")

# Extract tables from PDF
all_tables = []
with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, 1):
        print(f"Processing page {page_num}...")
        tables = page.extract_tables()
        for table in tables:
            if table:
                all_tables.append(table)

# Convert extracted tables to DataFrame
# Assuming the first table contains the main data
if not all_tables:
    raise ValueError("No tables found in PDF")

# Find the table with employee data (look for headers)
df = None
for table in all_tables:
    if len(table) > 1:
        # Check if this looks like the employee productivity table
        headers = table[0]
        if any('Employee' in str(cell) or 'Sales' in str(cell) for cell in headers if cell):
            # Create DataFrame from this table
            df = pd.DataFrame(table[1:], columns=headers)
            break

if df is None:
    # If no clear headers found, use the first substantial table
    df = pd.DataFrame(all_tables[0][1:], columns=all_tables[0][0])

print(f"\nFound {len(df)} employees")
print(f"Columns: {df.columns.tolist()}")

# Clean column names (remove extra spaces, newlines, standardize)
df.columns = df.columns.str.replace('\n', ' ').str.strip()

# Function to find column by partial name match
def find_column(df, keywords):
    """Find column that contains any of the keywords"""
    for col in df.columns:
        col_lower = str(col).lower()
        for keyword in keywords:
            if keyword.lower() in col_lower:
                return col
    return None

# Map columns to expected names
employee_col = find_column(df, ['employee', 'name', 'server'])
sales_col = find_column(df, ['sales'])
void_col = find_column(df, ['void total', 'void count'])
hours_col = find_column(df, ['hours worked', 'hours', 'hrs'])
turn_time_col = find_column(df, ['average turn time', 'turn time', 'avg turn'])
tips_col = find_column(df, ['non-cash tips', 'tips %', 'non cash tips'])

# Find void total specifically (not void count)
for col in df.columns:
    if 'void' in col.lower() and 'total' in col.lower():
        void_col = col
        break

print(f"\nMapped columns:")
print(f"  Employee: {employee_col}")
print(f"  Sales: {sales_col}")
print(f"  Void: {void_col}")
print(f"  Hours: {hours_col}")
print(f"  Turn Time: {turn_time_col}")
print(f"  Non-Cash Tips: {tips_col}")

# Rename columns for easier processing
column_mapping = {}
if employee_col:
    column_mapping[employee_col] = 'Employee'
if sales_col:
    column_mapping[sales_col] = 'Sales $'
if void_col:
    column_mapping[void_col] = 'Void total'
if hours_col:
    column_mapping[hours_col] = 'Hours worked'
if turn_time_col:
    column_mapping[turn_time_col] = 'Average turn time'
if tips_col:
    column_mapping[tips_col] = 'Non-cash tips %'

df = df.rename(columns=column_mapping)

# Remove any completely empty rows
df = df.dropna(how='all')

# Remove rows where employee name is empty or looks like a header/footer
df = df[df['Employee'].notna()]
df = df[~df['Employee'].astype(str).str.lower().str.contains('employee|total|average|summary', na=False)]

# Clean all cell values (remove newlines and extra spaces)
for col in df.columns:
    if df[col].dtype == 'object':
        df[col] = df[col].astype(str).str.replace('\n', ' ').str.strip()

print(f"\nAfter cleaning: {len(df)} employees")

# Function to clean currency columns and handle missing data
def clean_currency(col):
    return df[col].astype(str).str.replace(r'[$,]', '', regex=True).replace('--', '0').replace('None', '0').replace('nan', '0').astype(float)

# Check if required columns exist
required_cols = ['Sales $', 'Void total', 'Hours worked']
missing_cols = [col for col in required_cols if col not in df.columns]
if missing_cols:
    print(f"\nWarning: Missing columns: {missing_cols}")
    print("Available columns:", df.columns.tolist())
    # Add missing columns with default values
    for col in missing_cols:
        df[col] = '0'

df['Sales'] = clean_currency('Sales $')
df['Void total'] = clean_currency('Void total')
df['Hours worked'] = df['Hours worked'].astype(str).replace('--', '0').replace('None', '0').replace('nan', '0').astype(float)

# Handle non-cash tips percentage
if 'Non-cash tips %' in df.columns:
    df['Tips %'] = df['Non-cash tips %'].astype(str).str.replace('%', '').str.replace('--', '0').replace('None', '0').replace('nan', '0').astype(float)
else:
    print("\nWarning: Non-cash tips % column not found, using default value of 0")
    df['Tips %'] = 0.0

# Function to convert 'MM:SS:SS' turn time to total seconds (assuming M:S format)
def time_to_seconds(time_str):
    if pd.isna(time_str) or time_str == '--' or str(time_str).lower() in ['none', 'nan', '']:
        return 0
    try:
        time_str = str(time_str).strip()
        parts = time_str.split(':')
        if len(parts) >= 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
    except:
        pass
    return 0

# Handle turn time - if column doesn't exist, use 0
if 'Average turn time' in df.columns:
    df['Turn Time (sec)'] = df['Average turn time'].apply(time_to_seconds)
else:
    print("\nWarning: Average turn time column not found, using default value of 0")
    df['Turn Time (sec)'] = 0

# 2. Feature Engineering (Calculating KPIs)
df['Sales/Hour'] = df['Sales'] / df['Hours worked'].replace(0, 1)
df['Void %'] = (df['Void total'] / df['Sales']).replace([float('inf'), -float('inf')], 0).fillna(0)

# 3. Normalization and Weighted Scoring
weights = {
    'Sales/Hour': 0.35,
    'Turn Time (sec)': 0.05,
    'Void %': 0.20,
    'Hours worked': 0.20,
    'Tips %': 0.20
}

min_max = {col: {'min': df[col].min(), 'max': df[col].max()} for col in weights.keys()}

def normalize_score(value, col_name, direction):
    min_val = min_max[col_name]['min']
    max_val = min_max[col_name]['max']

    if max_val == min_val:
        return 1.0

    normalized = (value - min_val) / (max_val - min_val)

    if direction == 'higher_is_better':
        return normalized
    elif direction == 'lower_is_better':
        return 1.0 - normalized
    return 0.0

# Apply Normalization
df['Normalized Sales/Hour'] = df.apply(lambda row: normalize_score(row['Sales/Hour'], 'Sales/Hour', 'higher_is_better'), axis=1)
df['Normalized Turn Time'] = df.apply(lambda row: normalize_score(row['Turn Time (sec)'], 'Turn Time (sec)', 'lower_is_better'), axis=1)
df['Normalized Void %'] = df.apply(lambda row: normalize_score(row['Void %'], 'Void %', 'lower_is_better'), axis=1)
df['Normalized Hours worked'] = df.apply(lambda row: normalize_score(row['Hours worked'], 'Hours worked', 'higher_is_better'), axis=1)
df['Normalized Tips %'] = df.apply(lambda row: normalize_score(row['Tips %'], 'Tips %', 'higher_is_better'), axis=1)

# Calculate Weighted Score
df['Weighted Score'] = (
    df['Normalized Sales/Hour'] * weights['Sales/Hour'] +
    df['Normalized Turn Time'] * weights['Turn Time (sec)'] +
    df['Normalized Void %'] * weights['Void %'] +
    df['Normalized Hours worked'] * weights['Hours worked'] +
    df['Normalized Tips %'] * weights['Tips %']
)

# 4. Grade Assignment based on weighted score, tips percentage, and void percentage
def assign_grade(row):
    score = row['Weighted Score']
    tips_pct = row['Tips %']
    void_pct = row['Void %']
    
    # Determine base grade from weighted score
    if score >= 0.90:
        base_grade = 'A'
    elif score >= 0.80:
        base_grade = 'B'
    elif score >= 0.70:
        base_grade = 'C'
    elif score >= 0.60:
        base_grade = 'D'
    else:
        base_grade = 'F'
    
    # Adjust grade based on tips percentage
    if tips_pct >= 15:
        # A+ boost - move up one grade
        if base_grade == 'B':
            base_grade = 'A'
        elif base_grade == 'C':
            base_grade = 'B'
        elif base_grade == 'D':
            base_grade = 'C'
        elif base_grade == 'F':
            base_grade = 'D'
    elif tips_pct < 6:
        # F penalty - move down one grade
        if base_grade == 'A':
            base_grade = 'B'
        elif base_grade == 'B':
            base_grade = 'C'
        elif base_grade == 'C':
            base_grade = 'D'
        elif base_grade == 'D':
            base_grade = 'F'
    
    # Adjust grade based on void percentage
    # 0% voids = A (boost), Max voids = F (penalty)
    # Break down between min and max
    if void_pct == 0:
        # Perfect - boost up one grade
        if base_grade == 'B':
            base_grade = 'A'
        elif base_grade == 'C':
            base_grade = 'B'
        elif base_grade == 'D':
            base_grade = 'C'
        elif base_grade == 'F':
            base_grade = 'D'
    elif void_pct >= 0.08:  # 8% or higher voids = F penalty
        # Very high voids - move down one grade
        if base_grade == 'A':
            base_grade = 'B'
        elif base_grade == 'B':
            base_grade = 'C'
        elif base_grade == 'C':
            base_grade = 'D'
        elif base_grade == 'D':
            base_grade = 'F'
    elif void_pct >= 0.06:  # 6-8% voids = D penalty
        # High voids - slight penalty
        if base_grade == 'A':
            base_grade = 'B'
        elif base_grade == 'B':
            base_grade = 'C'
        elif base_grade == 'C':
            base_grade = 'D'
    elif void_pct >= 0.04:  # 4-6% voids = C (neutral/slight penalty)
        # Moderate voids - minor penalty
        if base_grade == 'A':
            base_grade = 'B'
        elif base_grade == 'B':
            base_grade = 'C'
    elif void_pct >= 0.02:  # 2-4% voids = B (acceptable)
        # Low voids - slight penalty only for A
        if base_grade == 'A':
            base_grade = 'B'
    # else 0-2% voids = A range (minimal or no penalty)
    
    return base_grade

df['Grade'] = df.apply(assign_grade, axis=1)

# Output the final table
grading_results = df[['Employee', 'Sales/Hour', 'Turn Time (sec)', 'Void %', 'Tips %', 'Hours worked', 'Weighted Score', 'Grade']].sort_values(by='Weighted Score', ascending=False)

# Generate output filename with timestamp
output_filename = f"employee_grades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
output_path = os.path.expanduser(f"~/Documents/AIO Python/{output_filename}")

# Save to CSV with grading summary at the bottom
with open(output_path, 'w', newline='') as f:
    # Write the main data
    grading_results.to_csv(f, index=False)
    
    # Add blank rows for separation
    f.write('\n\n')
    
    # Write grading formula summary
    f.write('GRADING FORMULA SUMMARY\n')
    f.write('======================\n\n')
    
    f.write('BASE WEIGHTED SCORE CALCULATION:\n')
    f.write('- Sales per Hour: 35% weight (higher is better)\n')
    f.write('- Void %: 20% weight (lower is better)\n')
    f.write('- Non-Cash Tips %: 20% weight (higher is better)\n')
    f.write('- Hours Worked: 20% weight (higher is better)\n')
    f.write('- Turn Time: 5% weight (lower is better)\n\n')
    
    f.write('BASE GRADE THRESHOLDS (from weighted score):\n')
    f.write('- A: 0.90 and above\n')
    f.write('- B: 0.80 to 0.89\n')
    f.write('- C: 0.70 to 0.79\n')
    f.write('- D: 0.60 to 0.69\n')
    f.write('- F: Below 0.60\n\n')
    
    f.write('GRADE ADJUSTMENTS:\n\n')
    
    f.write('Non-Cash Tips % Adjustments:\n')
    f.write('- 15% or higher tips: Grade BOOSTED up one level (B→A, C→B, D→C, F→D)\n')
    f.write('- Below 6% tips: Grade REDUCED down one level (A→B, B→C, C→D, D→F)\n\n')
    
    f.write('Void % Adjustments:\n')
    f.write('- 0% voids: Grade BOOSTED up one level (perfect performance)\n')
    f.write('- 0-2% voids: Minimal or no penalty (A range)\n')
    f.write('- 2-4% voids: Slight penalty (A→B only)\n')
    f.write('- 4-6% voids: Moderate penalty (A→B, B→C)\n')
    f.write('- 6-8% voids: High penalty (A→B, B→C, C→D)\n')
    f.write('- 8%+ voids: Maximum penalty - Grade REDUCED down one level\n\n')
    
    f.write('HOW TO IMPROVE YOUR GRADE:\n')
    f.write('1. Increase sales per hour (35% weight - HIGHEST PRIORITY!)\n')
    f.write('2. Work more consistent hours (20% weight - commitment!)\n')
    f.write('3. Minimize voids - aim for 0% (20% weight + grade boost)\n')
    f.write('4. Keep tips above 15% (20% weight + grade boost)\n')
    f.write('5. Reduce turn time - serve guests faster (5% weight)\n')

print(f"\n{'='*70}")
print("EMPLOYEE GRADING RESULTS")
print(f"{'='*70}")
print(grading_results.to_string(index=False))
print(f"\n{'='*70}")
print(f"Results saved to: {output_path}")
print(f"{'='*70}")

# Also print summary statistics
print("\nGrade Distribution:")
grade_counts = grading_results['Grade'].value_counts().sort_index()
for grade, count in grade_counts.items():
    print(f"  Grade {grade}: {count} employee(s)")

print(f"\nAverage Weighted Score: {grading_results['Weighted Score'].mean():.3f}")
print(f"Highest Score: {grading_results['Weighted Score'].max():.3f} ({grading_results.iloc[0]['Employee']})")
print(f"Lowest Score: {grading_results['Weighted Score'].min():.3f} ({grading_results.iloc[-1]['Employee']})")