
import pandas as pd
from collections import defaultdict
import sys
import os

# Category mapping based on vendor/payroll names
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

def get_category(name, payroll_name):
	for category, keywords in CATEGORY_MAP.items():
		for keyword in keywords:
			if keyword.lower() in (str(name) or '').lower() or keyword.lower() in (str(payroll_name) or '').lower():
				return category
	return "Other"


def breakdown_budget_excel(excel_file, output_file):
	# Read the specified sheet
	sheet_name = 'Sheet1'

	# Read all rows as raw data
	raw_df = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, engine='openpyxl')

	# Use header row 19 (Excel row 20)
	header_row_idx = 19
	df = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row_idx, engine='openpyxl')
	columns = list(df.columns)

	# Use header names if available, else fallback to index
	name_col = 'Name' if 'Name' in columns else (columns[16] if len(columns) > 16 else columns[-1])
	payroll_col = 'Type' if 'Type' in columns else (columns[8] if len(columns) > 8 else columns[0])
	# Try to find the amount column by common names
	amount_col = None
	for col in columns:
		if 'amount' in str(col).lower() or 'total' in str(col).lower() or 'debit' in str(col).lower():
			amount_col = col
			break
	if not amount_col:
		amount_col = columns[-2]  # fallback

	budget = defaultdict(float)
	for _, row in df.iterrows():
		name = row.get(name_col, '')
		payroll_name = row.get(payroll_col, '')
		try:
			amount = float(row.get(amount_col, 0) or 0)
		except Exception:
			amount = 0
		category = get_category(name, payroll_name)
		budget[category] += amount

	# Create a summary DataFrame sorted by Total (descending)
	summary = pd.DataFrame({
		'Category': list(budget.keys()),
		'Total': [round(budget[k], 2) for k in budget.keys()]
	})
	summary = summary.sort_values('Total', ascending=False).reset_index(drop=True)
	
	# Print the sorted budget to console
	print("\n" + "="*50)
	print("BUDGET SUMMARY (Sorted by Total)")
	print("="*50)
	total_sum = 0
	for _, row in summary.iterrows():
		print(f"{row['Category']:<30} ${row['Total']:>15,.2f}")
		total_sum += row['Total']
	print("-"*50)
	print(f"{'GRAND TOTAL':<30} ${total_sum:>15,.2f}")
	print("="*50 + "\n")

	# Write to Excel with some formatting
	with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
		summary.to_excel(writer, index=False, sheet_name='Budget Summary')
		ws = writer.sheets['Budget Summary']
		# Set column widths and header style
		for col in ws.columns:
			max_length = 0
			column = col[0].column_letter
			for cell in col:
				try:
					if len(str(cell.value)) > max_length:
						max_length = len(str(cell.value))
				except:
					pass
			ws.column_dimensions[column].width = max_length + 2
		# Bold headers
		for cell in ws[1]:
			cell.font = cell.font.copy(bold=True)

	print(f"Budget summary written to {output_file}")

if __name__ == "__main__":
	# Accept command-line arguments
	if len(sys.argv) > 1:
		excel_file = sys.argv[1]
		output_file = sys.argv[2] if len(sys.argv) > 2 else "Budget_Summary.xlsx"
	else:
		excel_file = "/Users/arnoldoramirezjr/Desktop/Profit and Loss Detail 2025.xlsm"
		output_file = "Budget_Summary.xlsx"
	
	# Check if input file exists
	if not os.path.exists(excel_file):
		print(f"Error: File not found: {excel_file}")
		print(f"\nUsage: python {sys.argv[0]} <input_excel_file> [output_file]")
		print(f"Example: python {sys.argv[0]} 'Profit and Loss Detail 2025.xlsm' Budget_Summary.xlsx")
		sys.exit(1)
	
	breakdown_budget_excel(excel_file, output_file)
