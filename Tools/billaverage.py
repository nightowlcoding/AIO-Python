# --- Custom Expense Category Breakdown ---
# Define category mapping
CATEGORY_MAP = {
    "Food Expense": [
        "Big House Burgers Kingsville", "CC Produce", "Corpus Christi Produce",
        "M&M Ramos Distribution", "MCM Bread and Sweets", "US Foods",
        "Cash & Carry", "Pepsi Cola", "Pepsi-Cola"
    ],
    "Beer Expense": [
        "Andrew’s Distributors", "L&F Distributors"
    ],
    "Liquor Expenses": [
        "The Jigger", "Jigger", "Discount Liquor"
    ],
    "Payroll Expense": [
        "Hourly Regular", "Hourly OT", "Manager Salary", "Assistant Manager",
        "Admin", "Vacation", "Bonus"
    ],
    "Utility Expense": [
        "Centerpoint", "Center Point", "Constellation", "Directv", "Jim Wells",
        "Jim wells County Appraisal District", "NuCo2", "STGR", "Spectrum",
        "Toast", "Easy", "City of Kingsville"
    ]
}

def get_expense_category(name, type_):
    for category, keywords in CATEGORY_MAP.items():
        for keyword in keywords:
            if (isinstance(name, str) and keyword.lower() in name.lower()) or \
               (isinstance(type_, str) and keyword.lower() in type_.lower()):
                return category
    return None

# Filter and categorize
if 'Name' in df.columns and 'Type' in df.columns:
    df['Expense Category'] = df.apply(lambda row: get_expense_category(row['Name'], row['Type']), axis=1)
    categorized = df[df['Expense Category'].notnull()].copy()
    categorized = categorized.sort_values(['Expense Category', 'Name'])
    # Save to a new sheet in the Excel file
    with pd.ExcelWriter('/Users/arnoldoramirezjr/Desktop/Budget_Breakdowns.xlsx', mode='a', if_sheet_exists='replace') as writer:
        categorized.to_excel(writer, sheet_name='Categorized Expenses', index=False)
    print("Categorized expenses saved to 'Categorized Expenses' sheet in Budget_Breakdowns.xlsx")
import pandas as pd

file_path = '/Users/arnoldoramirezjr/Desktop/Profit and Loss Detail 2025.xlsm'
try:
    df = pd.read_excel(file_path, sheet_name="Sheet1", engine="openpyxl")
except Exception:
    df = pd.read_excel(file_path, engine="openpyxl")

if df.shape[1] >= 9:
    payroll_mask_e = df.iloc[:,4].astype(str).str.lower().str.contains('payroll', na=False)
    payroll_mask_i = df.iloc[:,8].astype(str).str.lower().str.contains('paycheck|direct deposit', na=False)
    payroll_mask = payroll_mask_e | payroll_mask_i
    payroll_rows = df[payroll_mask]
    non_payroll_rows = df[~payroll_mask]
    # Export only the Name column (Q) for payroll rows
    if 'Name' in payroll_rows.columns:
        payroll_export = payroll_rows[['Name']].copy()
    elif len(payroll_rows.columns) > 16:
        col_q = payroll_rows.columns[16]
        payroll_export = payroll_rows[[col_q]].copy()
        payroll_export = payroll_export.rename(columns={col_q: 'Name'})
    else:
        payroll_export = payroll_rows.copy()
    payroll_export.to_excel('/Users/arnoldoramirezjr/Desktop/Payroll_Non_Managerial.xlsx', index=False)
    print(f"Payroll employee names saved to /Users/arnoldoramirezjr/Desktop/Payroll_Non_Managerial.xlsx. Rows: {len(payroll_export)}")
    df = non_payroll_rows
else:
    print('File does not have at least 9 columns.')

# Ensure column Q is named 'Name' (adjust if needed)
if 'Name' not in df.columns:
    if len(df.columns) > 16:
        col_q = df.columns[16]  # Q is the 17th column (0-indexed)
        df = df.rename(columns={col_q: 'Name'})

# Clean up and ensure 'Date' and 'Debit' columns are usable
df = df.dropna(subset=['Name', 'Date', 'Debit'])
df.loc[:, 'Date'] = pd.to_datetime(df['Date'], errors='coerce')
df = df.dropna(subset=['Date'])
df.loc[:, 'Debit'] = pd.to_numeric(df['Debit'], errors='coerce').fillna(0)

# Assume names are those with non-empty and non-numeric values in 'Name'
def is_likely_name(val):
    if pd.isnull(val):
        return False
    return isinstance(val, str) and not val.strip().isdigit() and len(val.strip()) > 0

name_mask = df['Name'].apply(is_likely_name)

# Exclude any row where column E contains 'payroll' or column I contains 'paycheck' from all summary calculations
if df.shape[1] >= 9:
    payroll_mask_e = df.iloc[:,4].astype(str).str.lower().str.contains('payroll', na=False)
    payroll_mask_i = df.iloc[:,8].astype(str).str.lower().str.contains('paycheck|direct deposit', na=False)
    payroll_mask = payroll_mask_e | payroll_mask_i
    non_payroll_mask = ~payroll_mask
    # Only use non-payroll rows for summary
    names_df = df[name_mask & non_payroll_mask]
else:
    names_df = df[name_mask]

checks_written = df['Num'].dropna().nunique() if 'Num' in df.columns else 0

# Group by Name (excluding payroll rows)
results = []
for name, group in names_df.groupby('Name'):
    group = group.sort_values(by='Date')
    start_date = group['Date'].min()
    end_date = group['Date'].max()
    num_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    total_paid = group['Debit'].sum()
    num_checks = group['Num'].dropna().nunique() if 'Num' in group.columns else 0
    avg_paid = total_paid / num_months if num_months > 0 else 0
    avg_per_check = total_paid / num_checks if num_checks > 0 else 0
    high_bill = group['Debit'].max()
    low_bill = group['Debit'].min()
    recurring = len(group) > 1
    results.append({
        'Name': name,
        'Start Date': start_date,
        'End Date': end_date,
        'Months Paid': num_months,
        'Total Paid': total_paid,
        'Average Paid': avg_paid,
        'Average Per Check': avg_per_check,
        'Highest Bill': high_bill,
        'Lowest Bill': low_bill,
        'Checks Written': num_checks,
        'Recurring': recurring
    })

# Convert results to DataFrame and save (excluding payroll rows)
results_df = pd.DataFrame(results)
results_df.to_csv("/Users/arnoldoramirezjr/Desktop/Profit_and_Loss_bill_summary.csv", index=False)
print(f"Summary saved to /Users/arnoldoramirezjr/Desktop/Profit_and_Loss_bill_summary.csv\nTotal unique checks written: {checks_written}")

# --- Budget Breakdowns ---
budget_breakdowns = {}

# Monthly totals
if 'Date' in df.columns and 'Debit' in df.columns:
    df['Month'] = df['Date'].dt.to_period('M')
    monthly_totals = df.groupby('Month')['Debit'].sum().reset_index()
    budget_breakdowns['Monthly Totals'] = monthly_totals

# Category totals by Type
if 'Type' in df.columns and 'Debit' in df.columns:
    type_totals = df.groupby('Type')['Debit'].sum().reset_index()
    budget_breakdowns['Type Totals'] = type_totals

# Category totals by Memo
if 'Memo' in df.columns and 'Debit' in df.columns:
    memo_totals = df.groupby('Memo')['Debit'].sum().reset_index()
    budget_breakdowns['Memo Totals'] = memo_totals

# Top spenders by Name
if 'Name' in df.columns and 'Debit' in df.columns:
    name_totals = df.groupby('Name')['Debit'].sum().reset_index().sort_values(by='Debit', ascending=False)
    budget_breakdowns['Top Spenders'] = name_totals

# Average monthly spend (overall)
if 'Month' in df.columns and 'Debit' in df.columns:
    avg_monthly_spend = monthly_totals['Debit'].mean()
    budget_breakdowns['Average Monthly Spend'] = avg_monthly_spend

# Save all budget breakdowns to a new Excel file
with pd.ExcelWriter('/Users/arnoldoramirezjr/Desktop/Budget_Breakdowns.xlsx') as writer:
    for sheet, breakdown in budget_breakdowns.items():
        if isinstance(breakdown, pd.DataFrame):
            breakdown.to_excel(writer, sheet_name=sheet, index=False)
        else:
            # For single values, save as a one-row DataFrame
            pd.DataFrame({sheet: [breakdown]}).to_excel(writer, sheet_name=sheet, index=False)
print("Budget breakdowns saved to /Users/arnoldoramirezjr/Desktop/Budget_Breakdowns.xlsx")
