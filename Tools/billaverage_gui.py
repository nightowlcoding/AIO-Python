print('DEBUG: billaverage_gui.py started')
import sys
import pandas as pd
import csv
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QTableView, QVBoxLayout, QWidget, QPushButton, QLabel, QHBoxLayout, QTabWidget, QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

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
    ],
    "Maintenance": [
        "Repair", "Maintenance", "Service Call", "Plumbing", "HVAC", "Electrical"
    ],
    "Tax & Licenses": [
        "Tax", "License", "Permit", "Registration", "State Comptroller", "IRS"
    ],
    "Insurance": [
        "Insurance", "Policy", "Premium"
    ],
    "Advertising": [
        "Ad", "Advertising", "Marketing", "Promotion"
    ],
    "Office Supplies": [
        "Office", "Supplies", "Stationery", "Printer", "Ink"
    ],
    "Bank Fees": [
        "Bank Fee", "Service Charge", "Overdraft", "Wire Fee"
    ],
    "Miscellaneous": [
        "Misc", "Other", "Uncategorized"
    ],
    "Reimbursement": [
        "Reimburse", "Reimbursement", "Refund", "Repayment"
    ],
    "Employee Check Tip": [
        "Tip", "Employee Tip", "Check Tip"
    ]
}

ASSIGNMENTS_CSV = "assigned_expense_names.csv"
CATEGORY_MAP_CSV = "category_map.csv"

ASSIGNED_NAMES = {}

def save_category_map():
    """Save CATEGORY_MAP to CSV file"""
    with open(CATEGORY_MAP_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Keywords"])
        for cat, keywords in CATEGORY_MAP.items():
            # Join keywords with semicolon to allow commas in keywords
            writer.writerow([cat, ";".join(keywords)])

def load_category_map():
    """Load CATEGORY_MAP from CSV file if it exists"""
    global CATEGORY_MAP, ASSIGNED_NAMES
    if not os.path.exists(CATEGORY_MAP_CSV):
        # Initialize ASSIGNED_NAMES with default categories
        ASSIGNED_NAMES = {cat: set() for cat in CATEGORY_MAP}
        return
    temp_map = {}
    with open(CATEGORY_MAP_CSV, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row["Category"]
            keywords_str = row["Keywords"]
            # Split by semicolon and filter empty strings
            keywords = [k.strip() for k in keywords_str.split(";") if k.strip()]
            temp_map[cat] = keywords
    if temp_map:
        CATEGORY_MAP = temp_map
    # Reinitialize ASSIGNED_NAMES with loaded categories
    ASSIGNED_NAMES = {cat: set() for cat in CATEGORY_MAP}

def save_assignments_to_csv():
    with open(ASSIGNMENTS_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Name"])
        for cat, names in ASSIGNED_NAMES.items():
            for name in names:
                writer.writerow([cat, name])

def load_assignments_from_csv():
    if not os.path.exists(ASSIGNMENTS_CSV):
        return
    with open(ASSIGNMENTS_CSV, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row["Category"]
            name = row["Name"]
            if cat in ASSIGNED_NAMES:
                ASSIGNED_NAMES[cat].add(name)

def get_expense_category(name, type_):
    for category, keywords in CATEGORY_MAP.items():
        for keyword in keywords:
            if (isinstance(name, str) and keyword.lower() in name.lower()) or \
               (isinstance(type_, str) and keyword.lower() in type_.lower()):
                return category
    return None

class DataFrameModel(QStandardItemModel):
    def __init__(self, df=pd.DataFrame()):
        super().__init__()
        self._df = pd.DataFrame()  # Store reference to dataframe
        self.set_dataframe(df)

    def set_dataframe(self, df):
        self.clear()
        self._df = df if df is not None else pd.DataFrame()  # Store the dataframe
        if df is None or df.empty:
            return
        self.setHorizontalHeaderLabels([str(col) for col in df.columns])
        for row in df.itertuples(index=False):
            items = [QStandardItem(str(field)) for field in row]
            self.appendRow(items)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modern Expense Categorizer (Remake)")
        self.resize(1200, 700)
        # Load saved category map and assignments
        load_category_map()
        load_assignments_from_csv()
        self.df = pd.DataFrame()
        self.summary_df = pd.DataFrame()
        self.payroll_df = pd.DataFrame()
        self.sorted_df = pd.DataFrame()
        self.budget_csv_df = pd.DataFrame()  # Store loaded budget CSV
        self.model = DataFrameModel(self.summary_df)
        self.payroll_model = DataFrameModel(self.payroll_df)
        self.sorted_model = DataFrameModel(self.sorted_df)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        btn_layout = QHBoxLayout()
        self.label = QLabel("No file loaded.")
        self.label.setStyleSheet("font-size: 16px; color: #333;")
        btn_load = QPushButton("Load Excel File")
        btn_load.clicked.connect(self.load_file)
        btn_export = QPushButton("Export Summary to CSV")
        btn_export.clicked.connect(self.export_summary)
        btn_export_excel = QPushButton("Export Summary to Excel")
        btn_export_excel.clicked.connect(self.export_summary_excel)
        # Add assign to category button
        btn_assign_category = QPushButton("Assign to Category")
        btn_assign_category.clicked.connect(self.assign_to_category)
        # Add manage categories button
        btn_manage_categories = QPushButton("Manage Categories")
        btn_manage_categories.clicked.connect(self.manage_categories)
        # Add update category map button
        btn_update_catmap = QPushButton("Update Category Map from Assignments")
        btn_update_catmap.clicked.connect(self.update_category_map_from_assignments)
        # Add input revenue button
        btn_input_revenue = QPushButton("Input Category Revenue")
        btn_input_revenue.clicked.connect(self.input_category_revenue)

        # Add export buttons for Sorted by Category and Budget tabs
        btn_export_sorted = QPushButton("Export 'Sorted by Category' to CSV")
        btn_export_sorted.clicked.connect(self.export_sorted_by_category)
        btn_export_budget = QPushButton("Export 'Budget' to CSV")
        btn_export_budget.clicked.connect(self.export_budget)
        
        # Add budget comparison buttons
        btn_load_budget = QPushButton("Load Budget CSV")
        btn_load_budget.clicked.connect(self.load_budget_csv)
        btn_compare = QPushButton("Compare with Budget")
        btn_compare.clicked.connect(self.compare_with_budget)

        btn_layout.addWidget(btn_load)
        btn_layout.addWidget(btn_export)
        btn_layout.addWidget(btn_export_excel)
        btn_layout.addWidget(btn_export_sorted)
        btn_layout.addWidget(btn_export_budget)
        btn_layout.addWidget(btn_load_budget)
        btn_layout.addWidget(btn_compare)
        btn_layout.addWidget(btn_assign_category)
        btn_layout.addWidget(btn_manage_categories)
        btn_layout.addWidget(btn_update_catmap)
        btn_layout.addWidget(btn_input_revenue)
        btn_layout.addWidget(self.label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.tabs = QTabWidget()
        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.setModel(self.model)
        # Set font and color for summary table (improved visibility)
        font = self.table.font()
        font.setPointSize(15)
        font.setFamily('Arial')
        self.table.setFont(font)
        self.table.setStyleSheet("QTableView { color: #000; background: #fff; selection-background-color: #0055ff; selection-color: #fff; font-size: 15pt; } QHeaderView::section { background: #333; color: #fff; font-weight: bold; }")
        # Set row height for better readability
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.tabs.addTab(self.table, "Summary (Non-Payroll)")
        self.payroll_table = QTableView()
        self.payroll_table.setSortingEnabled(True)
        self.payroll_table.setModel(self.payroll_model)
        self.tabs.addTab(self.payroll_table, "Payroll Names")
        self.tabs.addTab(QTableView(), "Sorted by Category")
        self.sorted_table = self.tabs.widget(2)
        self.sorted_table.setSortingEnabled(True)
        self.sorted_table.setModel(self.sorted_model)
        # Add Budget tab
        self.budget_table = QTableView()
        self.budget_model = DataFrameModel(pd.DataFrame())
        self.budget_table.setModel(self.budget_model)
        self.tabs.addTab(self.budget_table, "Budget")
        # Add Budget Comparison tab
        self.comparison_table = QTableView()
        self.comparison_model = DataFrameModel(pd.DataFrame())
        self.comparison_table.setModel(self.comparison_model)
        self.tabs.addTab(self.comparison_table, "Budget vs Actual")
        layout.addWidget(self.tabs)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def load_file(self):
        load_assignments_from_csv()  # Load assignments before processing
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Excel File", "", "Excel Files (*.xls *.xlsx *.xlsm)")
        if not file_path:
            return
        try:
            try:
                df = pd.read_excel(file_path, sheet_name="Sheet1", engine="openpyxl")
            except Exception:
                df = pd.read_excel(file_path, engine="openpyxl")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")
            return
        self.df = df
        self.process_data()

    def process_data(self):
        df = self.df.copy()
        # Payroll detection logic (columns E and I, 0-indexed 4 and 8)
        if df.shape[1] >= 9:
            payroll_mask_e = df.iloc[:,4].astype(str).str.lower().str.contains('payroll', na=False)
            payroll_mask_i = df.iloc[:,8].astype(str).str.lower().str.contains('paycheck|direct deposit', na=False)
            payroll_mask = payroll_mask_e | payroll_mask_i
            payroll_rows = df[payroll_mask]
            non_payroll_rows = df[~payroll_mask]
            # Payroll table: just show Name column if present
            if 'Name' in payroll_rows.columns:
                payroll_export = payroll_rows[['Name']].copy()
            elif len(payroll_rows.columns) > 16:
                col_q = payroll_rows.columns[16]
                payroll_export = payroll_rows[[col_q]].copy()
                payroll_export = payroll_export.rename(columns={col_q: 'Name'})
            else:
                payroll_export = payroll_rows.copy()
            self.payroll_df = payroll_export
        else:
            self.payroll_df = pd.DataFrame()
            non_payroll_rows = df

        # Ensure column Q is named 'Name' (adjust if needed)
        if 'Name' not in non_payroll_rows.columns:
            if len(non_payroll_rows.columns) > 16:
                col_q = non_payroll_rows.columns[16]
                non_payroll_rows = non_payroll_rows.rename(columns={col_q: 'Name'})

        # Clean up and ensure 'Date' and 'Debit' columns are usable
        for col in ['Name', 'Date', 'Debit']:
            if col not in non_payroll_rows.columns:
                self.label.setText(f"Missing required column: {col}")
                self.summary_df = pd.DataFrame()
                self.model.set_dataframe(self.summary_df)
                self.payroll_model.set_dataframe(self.payroll_df)
                return
        df2 = non_payroll_rows.dropna(subset=['Name', 'Date', 'Debit'])
        df2.loc[:, 'Date'] = pd.to_datetime(df2['Date'], errors='coerce')
        df2 = df2.dropna(subset=['Date'])
        df2.loc[:, 'Debit'] = pd.to_numeric(df2['Debit'], errors='coerce').fillna(0)

        def is_likely_name(val):
            if pd.isnull(val):
                return False
            return isinstance(val, str) and not val.strip().isdigit() and len(val.strip()) > 0

        name_mask = df2['Name'].apply(is_likely_name)
        names_df = df2[name_mask]

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
        self.summary_df = pd.DataFrame(results)

        # Format currency columns
        currency_cols = ['Total Paid', 'Average Paid', 'Average Per Check', 'Highest Bill', 'Lowest Bill']
        for col in currency_cols:
            if col in self.summary_df.columns:
                self.summary_df[col] = self.summary_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "")
        self.model.set_dataframe(self.summary_df)
        self.payroll_model.set_dataframe(self.payroll_df)
        self.label.setText(f"Loaded. Summary rows: {len(self.summary_df)}, Payroll rows: {len(self.payroll_df)}")
        # Update sorted table
        self.update_sorted_table()
        # Update budget table
        self.update_budget_table()
        # Highlight summary rows
        self.highlight_summary_rows()

    def update_sorted_table(self):
        if self.df is None or self.df.empty:
            self.sorted_df = pd.DataFrame()
            self.sorted_model.set_dataframe(self.sorted_df)
            self.update_budget_table()
            return
        # Auto-apply saved assignments to matching names
        if 'ManualCategory' not in self.df.columns:
            self.df['ManualCategory'] = None
        for cat, names in ASSIGNED_NAMES.items():
            for name in names:
                mask = self.df['Name'] == name
                self.df.loc[mask, 'ManualCategory'] = cat
        # Categorize all expenses, using manual override if present
        df_categorized = self.df.copy()
        if 'ManualCategory' in df_categorized.columns:
            df_categorized['Category'] = df_categorized['ManualCategory'].combine_first(
                df_categorized.apply(lambda row: get_expense_category(row['Name'], row['Type']), axis=1)
            )
        elif 'Name' in df_categorized.columns and 'Type' in df_categorized.columns:
            df_categorized['Category'] = df_categorized.apply(lambda row: get_expense_category(row['Name'], row['Type']), axis=1)
        else:
            df_categorized['Category'] = None
        df_categorized = df_categorized[df_categorized['Category'].notnull()].copy()
        # For each category, show each expense (Name) and its total, then a total row for the category
        rows = []
        cat_order = list(CATEGORY_MAP.keys())
        for cat in cat_order:
            cat_df = df_categorized[df_categorized['Category'] == cat]
            if cat_df.empty:
                continue
            # Group by Name within category
            name_grouped = cat_df.groupby('Name', as_index=False)['Debit'].sum()
            # Add a header row for the category
            rows.append({
                'Category': f"{cat} (Expense)",
                'Name': '',
                'Amount': ''
            })
            for _, row in name_grouped.iterrows():
                rows.append({
                    'Category': '',
                    'Name': row['Name'],
                    'Amount': f"${row['Debit']:,.2f}" if pd.notnull(row['Debit']) else ""
                })
            # Add total row for the category
            total = cat_df['Debit'].sum()
            rows.append({
                'Category': '',
                'Name': f"Total {cat} Expense",
                'Amount': f"${total:,.2f}"
            })
        sorted_expenses = pd.DataFrame(rows)
        self.sorted_df = sorted_expenses
        self.sorted_model.set_dataframe(self.sorted_df)
        self.update_budget_table()

    def update_budget_table(self):
        # Budget tab matches the rows and logic of the Sorted by Category tab for Food, Beer, Liquor, Utility, Maintenance, and Entertainment
        categories = ["Food Expense", "Beer Expense", "Liquor Expenses", "Utility Expense", "Maintenance", "Entertainment"]
        budget_rows = []
        if self.sorted_df is not None and not self.sorted_df.empty:
            for cat in categories:
                # Find all rows for this category in sorted_df (excluding header and total rows)
                in_cat = False
                for idx, row in self.sorted_df.iterrows():
                    # Detect start of category section
                    if row['Category'] == f"{cat} (Expense)":
                        in_cat = True
                        continue
                    # End of category section (next header or end of table)
                    if in_cat and row['Category'] != '' and row['Category'] != f"{cat} (Expense)":
                        in_cat = False
                    # Only process rows within the category section, skip header/total/empty
                    if in_cat and row['Category'] == '' and row['Name'] and not row['Name'].startswith('Total'):
                        name = row['Name']
                        try:
                            annual = float(str(row['Amount']).replace('$','').replace(',',''))
                        except Exception:
                            annual = 0.0
                        monthly = annual / 12 if annual else 0.0
                        weekly = annual / 52 if annual else 0.0
                        budget_rows.append({
                            'Name': name,
                            'Category': cat,
                            'Annual Expense': f"${annual:,.2f}",
                            'Monthly Budget': f"${monthly:,.2f}",
                            'Weekly Budget': f"${weekly:,.2f}"
                        })
        budget_df = pd.DataFrame(budget_rows)
        self.budget_model.set_dataframe(budget_df)
        # Add profit and percentage of sales columns for Food, Beer, Liquor
        if hasattr(self, 'category_revenue'):
            df = self.sorted_df.copy()
            df['Profit'] = ''
            df['% of Sales'] = ''
            for cat, revenue in self.category_revenue.items():
                # Find total row for this category
                mask = (df['Name'] == f"Total {cat} Expense")
                if mask.any():
                    total_expense = df.loc[mask, 'Amount'].str.replace('$','').str.replace(',','').astype(float).values[0]
                    profit = revenue - total_expense
                    percent = (total_expense / revenue * 100) if revenue else 0
                    df.loc[mask, 'Profit'] = f"${profit:,.2f}"
                    df.loc[mask, '% of Sales'] = f"{percent:.2f}%"
            self.sorted_df = df
            self.sorted_model.set_dataframe(self.sorted_df)

    def export_summary(self):
        if self.summary_df is None or self.summary_df.empty:
            QMessageBox.warning(self, "Export", "No summary data to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Summary CSV", "", "CSV Files (*.csv)")
        if file_path:
            self.summary_df.to_csv(file_path, index=False)
            QMessageBox.information(self, "Export", f"Summary exported to {file_path}")

    def export_summary_excel(self):
        if self.summary_df is None or self.summary_df.empty:
            QMessageBox.warning(self, "Export", "No summary data to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Summary Excel", "", "Excel Files (*.xlsx)")
        if file_path:
            self.summary_df.to_excel(file_path, index=False)
            QMessageBox.information(self, "Export", f"Summary exported to {file_path}")

    def export_sorted_by_category(self):
        if self.sorted_df is None or self.sorted_df.empty:
            QMessageBox.warning(self, "Export", "No 'Sorted by Category' data to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save 'Sorted by Category' CSV", "", "CSV Files (*.csv)")
        if file_path:
            self.sorted_df.to_csv(file_path, index=False)
            QMessageBox.information(self, "Export", f"'Sorted by Category' exported to {file_path}")

    def export_budget(self):
        budget_df = self.budget_model._df if hasattr(self, 'budget_model') and hasattr(self.budget_model, '_df') else None
        if budget_df is None or budget_df.empty:
            QMessageBox.warning(self, "Export", "No 'Budget' data to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save 'Budget' CSV", "", "CSV Files (*.csv)")
        if file_path:
            budget_df.to_csv(file_path, index=False)
            QMessageBox.information(self, "Export", f"'Budget' exported to {file_path}")

    def load_budget_csv(self):
        """Load the budget CSV file for comparison"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Open Budget CSV", 
            "/Users/arnoldoramirezjr/Desktop/", 
            "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            self.budget_csv_df = pd.read_csv(file_path)
            QMessageBox.information(self, "Success", f"Budget loaded from {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load budget: {str(e)}")

    def compare_with_budget(self):
        """Compare current week's expenses with the budget by expense name (from Budget tab)"""
        if self.budget_csv_df.empty:
            QMessageBox.warning(self, "No Budget", "Please load a budget CSV first using 'Load Budget CSV' button.")
            return
        
        # Get data from the Budget tab (generated from P&L without division)
        budget_tab_df = self.budget_model._df if hasattr(self, 'budget_model') and hasattr(self.budget_model, '_df') else pd.DataFrame()
        
        if budget_tab_df.empty:
            QMessageBox.warning(self, "No Data", "Please load a weekly P&L Excel file first. Make sure data is processed and the Budget tab is populated.")
            return
        
        # Extract actual expenses by name from Budget tab
        actual_expenses = {}
        for _, row in budget_tab_df.iterrows():
            name = str(row.get('Name', '')).strip()
            category = str(row.get('Category', '')).strip()
            
            if not name or not category:
                continue
            
            # Get the actual weekly expense amount from the Budget tab (Annual Expense column)
            annual_str = str(row.get('Annual Expense', '0')).replace('$', '').replace(',', '')
            try:
                annual_amount = float(annual_str) if annual_str else 0.0
                # This "Annual Expense" is actually the weekly amount from the weekly P&L
                actual_expenses[name.lower()] = {
                    'amount': annual_amount,
                    'category': category,
                    'display_name': name
                }
            except Exception:
                pass
        
        # Build comparison dataframe - compare loaded budget CSV with actual weekly expenses
        comparison_rows = []
        unmatched_budget_items = []
        
        for _, budget_row in self.budget_csv_df.iterrows():
            budget_name = str(budget_row.get('Name', '')).strip()
            category = str(budget_row.get('Category', '')).strip()
            
            if not budget_name:
                continue
            
            # For Utility Expense, use Monthly Budget column; for others use Weekly Budget
            if category == 'Utility Expense':
                budget_str = str(budget_row.get('Monthly Budget', '0')).replace('$', '').replace(',', '')
                budget_period = 'Monthly'
            else:
                budget_str = str(budget_row.get('Weekly Budget', '0')).replace('$', '').replace(',', '')
                budget_period = 'Weekly'
            
            try:
                budget_amount = float(budget_str) if budget_str else 0.0
            except Exception:
                budget_amount = 0.0
            
            # Try to find matching actual expense (case-insensitive exact match first)
            actual_data = None
            budget_name_lower = budget_name.lower()
            
            if budget_name_lower in actual_expenses:
                actual_data = actual_expenses[budget_name_lower]
            else:
                # Try partial matching - check if budget name is in actual or actual is in budget
                for actual_name_lower, data in actual_expenses.items():
                    if budget_name_lower in actual_name_lower or actual_name_lower in budget_name_lower:
                        actual_data = data
                        break
            
            if actual_data:
                actual_amount = actual_data['amount']
                actual_display_name = actual_data['display_name']
                
                # Calculate variance
                variance = actual_amount - budget_amount
                variance_pct = (variance / budget_amount * 100) if budget_amount != 0 else 0.0
                
                comparison_rows.append({
                    'Budget Name': budget_name,
                    'Actual Name': actual_display_name,
                    'Category': category,
                    f'{budget_period} Budget': f"${budget_amount:,.2f}",
                    'Actual Expense': f"${actual_amount:,.2f}",
                    'Variance ($)': f"${variance:,.2f}",
                    'Variance (%)': f"{variance_pct:,.1f}%",
                    'Status': '⚠️ Over' if variance > 0 else '✅ Under' if variance < 0 else '✓ On Track'
                })
            else:
                unmatched_budget_items.append(budget_name)
        
        if not comparison_rows:
            QMessageBox.warning(
                self, 
                "No Matches", 
                f"No matching expenses found between budget CSV and weekly P&L.\n\nBudget CSV items: {len(self.budget_csv_df)}\nWeekly P&L expenses: {len([k for k in actual_expenses.keys()])}\n\nMake sure expense names match."
            )
            return
        
        comparison_df = pd.DataFrame(comparison_rows)
        # Sort by category and then by budget name
        comparison_df = comparison_df.sort_values(['Category', 'Budget Name']).reset_index(drop=True)
        
        self.comparison_model.set_dataframe(comparison_df)
        
        # Switch to the Budget vs Actual tab
        self.tabs.setCurrentIndex(4)  # Budget vs Actual tab
        
        message = f"Budget vs Actual comparison generated with {len(comparison_rows)} expense(s)!"
        if unmatched_budget_items:
            message += f"\n\n{len(unmatched_budget_items)} budget item(s) not found in actual expenses."
        
        QMessageBox.information(self, "Comparison Complete", message)

    def assign_to_category(self):
        # Get selected rows in summary table
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Assign to Category", "Please select one or more rows in the summary table.")
            return
        names = []
        for idx in selected:
            name = self.model.item(idx.row(), 0).text() if self.model.item(idx.row(), 0) else None
            if name:
                names.append(name)
        if not names:
            QMessageBox.warning(self, "Assign to Category", "Could not determine the names for the selected rows.")
            return
        # Let user pick a category
        categories = list(CATEGORY_MAP.keys())
        cat, ok = QInputDialog.getItem(self, "Assign to Category", f"Assign selected names to which category?", categories, 0, False)
        if ok and cat:
            # Update the original DataFrame (self.df)
            mask = self.df['Name'].isin(names)
            self.df.loc[mask, 'ManualCategory'] = cat
            # Remove names from all other categories before adding to new category
            for name in names:
                for other_cat in ASSIGNED_NAMES:
                    if other_cat != cat and name in ASSIGNED_NAMES[other_cat]:
                        ASSIGNED_NAMES[other_cat].discard(name)
                # Add to the selected category
                ASSIGNED_NAMES[cat].add(name)
            save_assignments_to_csv()  # Save after each assignment
            # Immediately update CATEGORY_MAP from assignments and refresh sorted table
            self.update_category_map_from_assignments()
            self.update_sorted_table()
            self.highlight_summary_rows()
            QMessageBox.information(self, "Assign to Category", f"Assigned {len(names)} names to '{cat}'.")

    def highlight_summary_rows(self):
        # Highlight rows in the summary (non-payroll) table that are present in the sorted category table
        if self.summary_df is None or self.summary_df.empty or self.sorted_df is None or self.sorted_df.empty:
            return
        # Get all names that appear in the sorted_df (excluding TOTAL rows)
        sorted_names = set(self.sorted_df[self.sorted_df['Name'] != 'TOTAL']['Name'])
        for row in range(self.model.rowCount()):
            name = self.model.item(row, 0).text() if self.model.item(row, 0) else None
            if name in sorted_names:
                for col in range(self.model.columnCount()):
                    self.model.item(row, col).setBackground(Qt.yellow)
            else:
                for col in range(self.model.columnCount()):
                    self.model.item(row, col).setBackground(Qt.white)

    def manage_categories(self):
        # Simple dialog to display, add, and remove categories and keywords
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QListWidget, QLabel, QInputDialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Categories")
        layout = QVBoxLayout(dialog)
        label = QLabel("Categories:")
        layout.addWidget(label)
        list_widget = QListWidget()
        for cat in CATEGORY_MAP:
            list_widget.addItem(cat)
        layout.addWidget(list_widget)
        btn_add_cat = QPushButton("Add Category")
        btn_add_cat.clicked.connect(lambda: self.add_category(list_widget))
        layout.addWidget(btn_add_cat)
        btn_remove_cat = QPushButton("Remove Selected Category")
        btn_remove_cat.clicked.connect(lambda: self.remove_category(list_widget))
        layout.addWidget(btn_remove_cat)
        btn_manage_keywords = QPushButton("Manage Keywords for Selected Category")
        btn_manage_keywords.clicked.connect(lambda: self.manage_keywords(list_widget))
        layout.addWidget(btn_manage_keywords)
        btn_export = QPushButton("Export Category Map to CSV")
        btn_export.clicked.connect(self.export_category_map)
        layout.addWidget(btn_export)
        dialog.setLayout(layout)
        dialog.exec()

    def add_category(self, list_widget):
        cat, ok = QInputDialog.getText(self, "Add Category", "Category name:")
        if ok and cat and cat not in CATEGORY_MAP:
            CATEGORY_MAP[cat] = []
            ASSIGNED_NAMES[cat] = set()
            list_widget.addItem(cat)
            save_category_map()
            QMessageBox.information(self, "Success", f"Category '{cat}' added and saved.")

    def remove_category(self, list_widget):
        selected = list_widget.currentItem()
        if selected:
            cat = selected.text()
            if cat in CATEGORY_MAP:
                del CATEGORY_MAP[cat]
                if cat in ASSIGNED_NAMES:
                    del ASSIGNED_NAMES[cat]
                save_category_map()
                QMessageBox.information(self, "Success", f"Category '{cat}' removed and saved.")
            list_widget.takeItem(list_widget.row(selected))

    def manage_keywords(self, list_widget):
        selected = list_widget.currentItem()
        if not selected:
            return
        cat = selected.text()
        keywords = CATEGORY_MAP.get(cat, [])
        kw, ok = QInputDialog.getText(self, "Manage Keywords", f"Current keywords: {keywords}\nAdd keyword:")
        if ok and kw:
            CATEGORY_MAP[cat].append(kw)
            save_category_map()
            QMessageBox.information(self, "Success", f"Keyword '{kw}' added to '{cat}' and saved.")

    def export_category_map(self):
        with open("category_map_export.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Category", "Keywords"])
            for cat, keywords in CATEGORY_MAP.items():
                writer.writerow([cat, ", ".join(keywords)])
        QMessageBox.information(self, "Export", "Category map exported to category_map_export.csv")

    def update_category_map_from_assignments(self):
        # Load assignments from CSV and update CATEGORY_MAP keywords
        load_assignments_from_csv()
        for cat, names in ASSIGNED_NAMES.items():
            for name in names:
                if name not in CATEGORY_MAP[cat]:
                    CATEGORY_MAP[cat].append(name)
        QMessageBox.information(self, "Update Category Map", "CATEGORY_MAP updated with assigned names from CSV.")

    def input_category_revenue(self):
        # Let user input revenue for Food, Beer, Liquor categories
        from PySide6.QtWidgets import QInputDialog
        revenue_inputs = {}
        for cat in ["Food Expense", "Beer Expense", "Liquor Expenses"]:
            val, ok = QInputDialog.getDouble(self, f"Input Revenue for {cat}", f"Enter total revenue for {cat}:", 0, 0, 1e9, 2)
            if ok:
                revenue_inputs[cat] = val
        self.category_revenue = revenue_inputs
        self.update_sorted_table()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()