import streamlit as st
import pandas as pd
from collections import defaultdict
import io

# Category mapping
CATEGORY_MAP = {
    "Food Expense": [
        "Big House Burgers Kingsville", "CC Produce", "Corpus Christi Produce",
        "M&M Ramos Distribution", "MCM Bread and Sweets", "US Foods",
        "Cash & Carry", "Pepsi Cola", "Pepsi-Cola"
    ],
    "Beer Expense": [
        "Andrew's Distributors", "L&F Distributors"
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
        "Toast", "Easy", "City of Kingsville", "City of Alice"
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
    "Entertainment": [
        "Entertainment", "Music", "DJ", "Band"
    ]
}

# Payroll mapping
PAYROLL_MAP = {
    "Hourly Regular": ["Regular Hours"],
    "Hourly OT": ["Overtime Hours", "OT Hours"],
    "Manager Salary": ["Manager"],
    "Assistant Manager": ["Assistant Manager", "Asst Manager"],
    "Admin": ["Administrative", "Admin"],
    "Vacation": ["Vacation", "PTO"],
    "Bonus": ["Bonus"]
}

def get_category(name, payroll_name):
    """Determine category based on name or payroll name"""
    for category, keywords in CATEGORY_MAP.items():
        for keyword in keywords:
            if keyword.lower() in (str(name) or '').lower() or keyword.lower() in (str(payroll_name) or '').lower():
                return category
    return "Other"

def get_payroll_category(payroll_type):
    """Determine payroll category"""
    for category, keywords in PAYROLL_MAP.items():
        for keyword in keywords:
            if keyword.lower() in (str(payroll_type) or '').lower():
                return category
    return "Other Payroll"

def process_excel_file(df):
    """Process the uploaded Excel file and generate all data"""
    # Find header row
    header_row_idx = None
    for i, row in df.iterrows():
        if 'Type' in row.values or 'Name' in row.values:
            header_row_idx = i
            break
    
    if header_row_idx is None:
        return None, None, None, None
    
    # Set header
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    
    # Get column names
    name_col = 'Name' if 'Name' in df.columns else df.columns[-1]
    payroll_col = 'Type' if 'Type' in df.columns else df.columns[0]
    
    # Find amount column
    amount_col = None
    for col in df.columns:
        if 'amount' in str(col).lower() or 'debit' in str(col).lower():
            amount_col = col
            break
    if not amount_col:
        amount_col = df.columns[-2]
    
    # Generate summary
    summary_data = defaultdict(float)
    for _, row in df.iterrows():
        name = row.get(name_col, '')
        payroll_name = row.get(payroll_col, '')
        try:
            amount = float(row.get(amount_col, 0) or 0)
        except:
            amount = 0
        category = get_category(name, payroll_name)
        summary_data[name] += amount
    
    summary_df = pd.DataFrame([
        {'Name': name, 'Amount': f"${amount:,.2f}"}
        for name, amount in summary_data.items()
    ])
    
    # Generate payroll summary
    payroll_data = defaultdict(float)
    for _, row in df.iterrows():
        payroll_type = row.get(payroll_col, '')
        try:
            amount = float(row.get(amount_col, 0) or 0)
        except:
            amount = 0
        payroll_cat = get_payroll_category(payroll_type)
        if payroll_cat != "Other Payroll":
            payroll_data[payroll_cat] += amount
    
    payroll_df = pd.DataFrame([
        {'Payroll Type': cat, 'Amount': f"${amount:,.2f}"}
        for cat, amount in payroll_data.items()
    ])
    
    # Generate sorted by category
    categories = ["Food Expense", "Beer Expense", "Liquor Expenses", "Utility Expense", 
                  "Maintenance", "Entertainment"]
    rows = []
    for cat in categories:
        cat_df = df[df.apply(lambda row: get_category(row.get(name_col, ''), 
                                                       row.get(payroll_col, '')) == cat, axis=1)]
        if not cat_df.empty:
            rows.append({'Category': f"{cat} (Expense)", 'Name': '', 'Amount': ''})
            for _, row in cat_df.iterrows():
                name = row.get(name_col, '')
                try:
                    amount = float(row.get(amount_col, 0) or 0)
                except:
                    amount = 0
                rows.append({'Category': '', 'Name': name, 'Amount': f"${amount:,.2f}"})
            total = sum([float(r['Amount'].replace('$','').replace(',','')) 
                        for r in rows if r['Category'] == '' and r['Amount'] != ''])
            rows.append({'Category': '', 'Name': f"Total {cat} Expense", 'Amount': f"${total:,.2f}"})
    
    sorted_df = pd.DataFrame(rows)
    
    # Generate budget table (group by Name and Category, sum annual expense)
    budget_data = []
    for _, row in df.iterrows():
        name = str(row.get(name_col, '')).strip()
        payroll_name = str(row.get(payroll_col, '')).strip()
        try:
            amount = float(row.get(amount_col, 0) or 0)
        except:
            amount = 0.0
        category = get_category(name, payroll_name)
        if name and amount != 0 and category in categories:
            budget_data.append({'Name': name, 'Category': category, 'Annual Expense': amount})

    # Group by Name and Category, sum annual expense
    if budget_data:
        budget_df_raw = pd.DataFrame(budget_data)
        budget_df_grouped = budget_df_raw.groupby(['Name', 'Category'], as_index=False).agg({'Annual Expense': 'sum'})
        budget_df_grouped['Monthly Budget'] = budget_df_grouped['Annual Expense'] / 12
        budget_df_grouped['Weekly Budget'] = budget_df_grouped['Annual Expense'] / 52
        # Format columns
        budget_df_grouped['Annual Expense'] = budget_df_grouped['Annual Expense'].apply(lambda x: f"${x:,.2f}")
        budget_df_grouped['Monthly Budget'] = budget_df_grouped['Monthly Budget'].apply(lambda x: f"${x:,.2f}")
        budget_df_grouped['Weekly Budget'] = budget_df_grouped['Weekly Budget'].apply(lambda x: f"${x:,.2f}")
        budget_df = budget_df_grouped[['Name', 'Category', 'Annual Expense', 'Monthly Budget', 'Weekly Budget']]
    else:
        budget_df = pd.DataFrame(columns=['Name', 'Category', 'Annual Expense', 'Monthly Budget', 'Weekly Budget'])
    
    return summary_df, payroll_df, sorted_df, budget_df

def compare_budget(budget_csv_df, budget_tab_df):
    """Compare budget CSV with actual budget tab data"""
    if budget_csv_df.empty or budget_tab_df.empty:
        return pd.DataFrame()

    # Try to import fuzzywuzzy for fuzzy matching, fallback if not available
    try:
        from fuzzywuzzy import process as fuzzy_process
    except ImportError:
        fuzzy_process = None

    # Extract actual expenses from budget tab
    actual_expenses = {}
    for _, row in budget_tab_df.iterrows():
        name = str(row.get('Name', '')).strip().lower()
        category = str(row.get('Category', '')).strip().lower()
        if not name or not category:
            continue
        annual_str = str(row.get('Annual Expense', '0')).replace('$', '').replace(',', '')
        try:
            annual_amount = float(annual_str) if annual_str else 0.0
            actual_expenses[name] = {
                'amount': annual_amount,
                'category': category,
                'display_name': row.get('Name', '')
            }
        except:
            pass

    matched_actuals = set()
    comparison_rows = []
    for _, budget_row in budget_csv_df.iterrows():
        budget_name = str(budget_row.get('Name', '')).strip()
        category = str(budget_row.get('Category', '')).strip()
        if not budget_name:
            continue
        # For Utility Expense, use Monthly Budget; for others use Weekly Budget
        if category == 'Utility Expense':
            budget_str = str(budget_row.get('Monthly Budget', '0')).replace('$', '').replace(',', '')
            budget_period = 'Monthly'
        else:
            budget_str = str(budget_row.get('Weekly Budget', '0')).replace('$', '').replace(',', '')
            budget_period = 'Weekly'
        try:
            budget_amount = float(budget_str) if budget_str else 0.0
        except:
            budget_amount = 0.0
        # Find matching actual expense (case-insensitive, trimmed, fuzzy if available)
        budget_name_key = budget_name.strip().lower()
        actual_data = None
        match_name = None
        if budget_name_key in actual_expenses:
            actual_data = actual_expenses[budget_name_key]
            match_name = budget_name_key
        elif fuzzy_process:
            # Use fuzzy matching with a threshold
            choices = list(actual_expenses.keys())
            match, score = fuzzy_process.extractOne(budget_name_key, choices)
            if score >= 90:
                actual_data = actual_expenses[match]
                match_name = match
        else:
            # fallback: substring match
            for actual_name in actual_expenses:
                if budget_name_key in actual_name or actual_name in budget_name_key:
                    actual_data = actual_expenses[actual_name]
                    match_name = actual_name
                    break
        if actual_data:
            actual_amount = actual_data['amount']
            actual_display_name = actual_data['display_name']
            variance = actual_amount - budget_amount
            variance_pct = (variance / budget_amount * 100) if budget_amount != 0 else 0.0
            status = '⚠️ Over' if variance > 0 else '✅ Under' if variance < 0 else '✓ On Track'
            comparison_rows.append({
                'Budget Name': budget_name,
                'Actual Name': actual_display_name,
                'Category': category,
                f'{budget_period} Budget': f"${budget_amount:,.2f}",
                'Actual Expense': f"${actual_amount:,.2f}",
                'Variance ($)': f"${variance:,.2f}",
                'Variance (%)': f"{variance_pct:,.1f}%",
                'Status': status
            })
            matched_actuals.add(match_name)
        else:
            # No match found in actuals
            comparison_rows.append({
                'Budget Name': budget_name,
                'Actual Name': '(No Match)',
                'Category': category,
                f'{budget_period} Budget': f"${budget_amount:,.2f}",
                'Actual Expense': '$0.00',
                'Variance ($)': f"-${budget_amount:,.2f}",
                'Variance (%)': '-100.0%',
                'Status': '❓ No Actual'
            })

    # Add unmatched actuals
    for actual_name, actual_data in actual_expenses.items():
        if actual_name not in matched_actuals:
            actual_amount = actual_data['amount']
            actual_display_name = actual_data['display_name']
            category = actual_data['category']
            comparison_rows.append({
                'Budget Name': '(No Match)',
                'Actual Name': actual_display_name,
                'Category': category,
                'Monthly Budget': '$0.00',
                'Weekly Budget': '$0.00',
                'Actual Expense': f"${actual_amount:,.2f}",
                'Variance ($)': f"${actual_amount:,.2f}",
                'Variance (%)': 'N/A',
                'Status': '❓ No Budget'
            })

    comparison_df = pd.DataFrame(comparison_rows)
    if not comparison_df.empty:
        comparison_df = comparison_df.sort_values(['Category', 'Budget Name']).reset_index(drop=True)
    return comparison_df

# Streamlit App
st.set_page_config(page_title="Expense Budget Analyzer", page_icon="💰", layout="wide")

st.title("💰 Expense Budget Analyzer")
st.markdown("---")

# Initialize session state
if 'summary_df' not in st.session_state:
    st.session_state.summary_df = None
if 'payroll_df' not in st.session_state:
    st.session_state.payroll_df = None
if 'sorted_df' not in st.session_state:
    st.session_state.sorted_df = None
if 'budget_df' not in st.session_state:
    st.session_state.budget_df = None
if 'budget_csv_df' not in st.session_state:
    st.session_state.budget_csv_df = None
if 'comparison_df' not in st.session_state:
    st.session_state.comparison_df = None

# Sidebar for file uploads
with st.sidebar:

    st.header("📂 Upload Files")
    st.subheader("Step 1: Upload Weekly P&L")
    pl_file = st.file_uploader("Upload P&L Excel File", type=['xlsx', 'xlsm', 'xls'], key='pl_upload')
    pl_path = st.text_input("Or enter Excel file path", value="", key="pl_path")
    process_pl = st.button("Process P&L", type="primary")

    if process_pl:
        df = None
        if pl_file is not None:
            with st.spinner("Processing uploaded P&L file..."):
                try:
                    df = pd.read_excel(pl_file, sheet_name="Sheet1", header=None, engine="openpyxl")
                except Exception as e:
                    st.error(f"❌ Error reading uploaded file: {e}")
        elif pl_path:
            with st.spinner(f"Processing file from path: {pl_path}"):
                import os
                if os.path.exists(pl_path):
                    try:
                        df = pd.read_excel(pl_path, sheet_name="Sheet1", header=None, engine="openpyxl")
                    except Exception as e:
                        st.error(f"❌ Error reading file from path: {e}")
                else:
                    st.error("❌ File path does not exist.")
        else:
            st.warning("Please upload a file or enter a valid path.")

        if df is not None:
            summary, payroll, sorted_data, budget = process_excel_file(df)
            if summary is not None:
                st.session_state.summary_df = summary
                st.session_state.payroll_df = payroll
                st.session_state.sorted_df = sorted_data
                st.session_state.budget_df = budget
                st.success("✅ P&L processed successfully!")
            else:
                st.error("❌ Could not process P&L file")

    st.markdown("---")
    
    st.subheader("Step 2: Upload Budget CSV")
    budget_file = st.file_uploader("Upload Budget CSV", type=['csv'], key='budget_upload')
    
    if budget_file:
        if st.button("Load Budget", type="primary"):
            with st.spinner("Loading budget..."):
                st.session_state.budget_csv_df = pd.read_csv(budget_file)
                st.success("✅ Budget loaded successfully!")
    
    st.markdown("---")
    
    st.subheader("Step 3: Compare")
    if st.button("🔍 Compare Budget vs Actual", type="primary", disabled=(st.session_state.budget_csv_df is None or st.session_state.budget_df is None)):
        with st.spinner("Generating comparison..."):
            comparison = compare_budget(st.session_state.budget_csv_df, st.session_state.budget_df)
            st.session_state.comparison_df = comparison
            if not comparison.empty:
                st.success(f"✅ Comparison generated with {len(comparison)} expenses!")
            else:
                st.warning("⚠️ No matching expenses found")

# Main content area with tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Summary", "👥 Payroll", "📑 Sorted by Category", "💼 Budget", "📈 Budget vs Actual"])

with tab1:
    st.header("Summary")
    if st.session_state.summary_df is not None:
        st.dataframe(st.session_state.summary_df, use_container_width=True, hide_index=True, height=600)
        
        # Export button
        csv = st.session_state.summary_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export to CSV", csv, "summary.csv", "text/csv")
    else:
        st.info("👆 Upload and process a P&L file to see summary data")

with tab2:
    st.header("Payroll")
    if st.session_state.payroll_df is not None:
        st.dataframe(st.session_state.payroll_df, use_container_width=True, hide_index=True, height=600)
        
        csv = st.session_state.payroll_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export to CSV", csv, "payroll.csv", "text/csv")
    else:
        st.info("👆 Upload and process a P&L file to see payroll data")

with tab3:
    st.header("Sorted by Category")
    if st.session_state.sorted_df is not None:
        st.dataframe(st.session_state.sorted_df, use_container_width=True, hide_index=True, height=600)
        
        csv = st.session_state.sorted_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export to CSV", csv, "sorted_by_category.csv", "text/csv")
    else:
        st.info("👆 Upload and process a P&L file to see sorted data")

with tab4:
    st.header("Budget")
    if st.session_state.budget_df is not None:
        st.dataframe(st.session_state.budget_df, use_container_width=True, hide_index=True, height=600)
        
        csv = st.session_state.budget_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export to CSV", csv, "budget.csv", "text/csv")
    else:
        st.info("👆 Upload and process a P&L file to see budget data")

with tab5:
    st.header("Budget vs Actual Comparison")
    if st.session_state.comparison_df is not None and not st.session_state.comparison_df.empty:
        # Style the dataframe with better contrast
        def highlight_status(row):
            if '⚠️ Over' in str(row['Status']):
                return ['background-color: #ff6b6b; color: white; font-weight: bold'] * len(row)
            elif '✅ Under' in str(row['Status']):
                return ['background-color: #51cf66; color: white; font-weight: bold'] * len(row)
            else:
                return ['background-color: #228be6; color: white; font-weight: bold'] * len(row)
        
        styled_df = st.session_state.comparison_df.style.apply(highlight_status, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=600)
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        over_budget = len([r for _, r in st.session_state.comparison_df.iterrows() if '⚠️ Over' in str(r['Status'])])
        under_budget = len([r for _, r in st.session_state.comparison_df.iterrows() if '✅ Under' in str(r['Status'])])
        on_track = len([r for _, r in st.session_state.comparison_df.iterrows() if '✓ On Track' in str(r['Status'])])
        
        col1.metric("⚠️ Over Budget", over_budget)
        col2.metric("✅ Under Budget", under_budget)
        col3.metric("✓ On Track", on_track)
        
        csv = st.session_state.comparison_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Comparison to CSV", csv, "budget_vs_actual.csv", "text/csv")
    else:
        st.info("👆 Load both P&L and Budget CSV files, then click 'Compare Budget vs Actual'")

# Footer
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit")
