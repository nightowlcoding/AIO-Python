from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from collections import defaultdict
import io
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Category mapping
CATEGORY_MAP = {
    "Food Expense": [
        "Big House Burgers Kingsville", "CC Produce", "Corpus Christi Produce",
        "M&M Ramos Distribution", "MCM Bread and Sweets", "MCM Bread & Sweets", "US Foods",
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
        "Centerpoint", "Center Point", "CenterPoint Energy", "Constellation", "Directv", "Jim Wells",
        "Jim wells County Appraisal District", "NuCo2", "STGR", "Spectrum",
        "Toast", "Easy", "City of Kingsville", "City of Alice"
    ],
    "Maintenance": [
        "Repair", "Maintenance", "Service Call", "Plumbing", "HVAC", "Electrical",
        "Capital Kleen Air Inc", "Next Level", "Guard Master"
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

# Session storage (in production, use proper session management or database)
session_data = {
    'summary_df': None,
    'payroll_df': None,
    'sorted_df': None,
    'budget_df': None,
    'budget_csv_df': None,
    'comparison_df': None
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
    
    # Generate budget table
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

    if budget_data:
        budget_df_raw = pd.DataFrame(budget_data)
        budget_df_grouped = budget_df_raw.groupby(['Name', 'Category'], as_index=False).agg({'Annual Expense': 'sum'})
        budget_df_grouped['Monthly Budget'] = budget_df_grouped['Annual Expense'] / 12
        budget_df_grouped['Weekly Budget'] = budget_df_grouped['Annual Expense'] / 52
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

    try:
        from fuzzywuzzy import process as fuzzy_process
    except ImportError:
        fuzzy_process = None

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
        
        budget_name_key = budget_name.strip().lower()
        actual_data = None
        match_name = None
        if budget_name_key in actual_expenses:
            actual_data = actual_expenses[budget_name_key]
            match_name = budget_name_key
        elif fuzzy_process:
            choices = list(actual_expenses.keys())
            match, score = fuzzy_process.extractOne(budget_name_key, choices)
            if score >= 90:
                actual_data = actual_expenses[match]
                match_name = match
        else:
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
            status = 'Over' if variance > 0 else 'Under' if variance < 0 else 'On Track'
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
            comparison_rows.append({
                'Budget Name': budget_name,
                'Actual Name': '(No Match)',
                'Category': category,
                f'{budget_period} Budget': f"${budget_amount:,.2f}",
                'Actual Expense': '$0.00',
                'Variance ($)': f"-${budget_amount:,.2f}",
                'Variance (%)': '-100.0%',
                'Status': 'No Actual'
            })

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
                'Status': 'No Budget'
            })

    comparison_df = pd.DataFrame(comparison_rows)
    if not comparison_df.empty:
        comparison_df = comparison_df.sort_values(['Category', 'Budget Name']).reset_index(drop=True)
    return comparison_df

@app.route('/')
def index():
    return render_template('billaverage.html')

@app.route('/upload_pl', methods=['POST'])
def upload_pl():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        print(f"Processing file: {file.filename}")
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        print(f"File saved to: {filepath}")
        
        # Try to read the Excel file
        try:
            df = pd.read_excel(filepath, sheet_name="Sheet1", header=None, engine="openpyxl")
            print(f"Excel loaded from Sheet1, shape: {df.shape}")
        except Exception as read_error:
            print(f"Error reading Sheet1: {read_error}")
            # Try reading first sheet if Sheet1 doesn't exist
            try:
                df = pd.read_excel(filepath, sheet_name=0, header=None, engine="openpyxl")
                print(f"Excel loaded from first sheet, shape: {df.shape}")
            except Exception as e2:
                print(f"Error reading Excel file: {e2}")
                os.remove(filepath)
                return jsonify({'error': f'Could not read Excel file: {str(e2)}'}), 400
        
        summary, payroll, sorted_data, budget = process_excel_file(df)
        
        # Clean up temp file
        try:
            os.remove(filepath)
        except:
            pass
        
        if summary is not None:
            session_data['summary_df'] = summary
            session_data['payroll_df'] = payroll
            session_data['sorted_df'] = sorted_data
            session_data['budget_df'] = budget
            print("Processing successful!")
            return jsonify({'success': True, 'message': 'P&L processed successfully!'})
        else:
            return jsonify({'error': 'Could not process P&L file - no header row found'}), 400
    except Exception as e:
        print(f"Error in upload_pl: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/upload_budget', methods=['POST'])
def upload_budget():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        session_data['budget_csv_df'] = pd.read_csv(file)
        return jsonify({'success': True, 'message': 'Budget loaded successfully!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/compare', methods=['POST'])
def compare():
    try:
        if session_data['budget_csv_df'] is None or session_data['budget_df'] is None:
            return jsonify({'error': 'Please upload both P&L and Budget files first'}), 400
        
        comparison = compare_budget(session_data['budget_csv_df'], session_data['budget_df'])
        session_data['comparison_df'] = comparison
        
        if not comparison.empty:
            return jsonify({
                'success': True,
                'message': f'Comparison generated with {len(comparison)} expenses!',
                'count': len(comparison)
            })
        else:
            return jsonify({'error': 'No matching expenses found'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_data/<data_type>')
def get_data(data_type):
    try:
        df_map = {
            'summary': session_data['summary_df'],
            'payroll': session_data['payroll_df'],
            'sorted': session_data['sorted_df'],
            'budget': session_data['budget_df'],
            'comparison': session_data['comparison_df']
        }
        
        df = df_map.get(data_type)
        if df is None or df.empty:
            return jsonify({'data': []})
        
        return jsonify({'data': df.to_dict(orient='records')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<data_type>')
def download(data_type):
    try:
        df_map = {
            'summary': session_data['summary_df'],
            'payroll': session_data['payroll_df'],
            'sorted': session_data['sorted_df'],
            'budget': session_data['budget_df'],
            'comparison': session_data['comparison_df']
        }
        
        df = df_map.get(data_type)
        if df is None or df.empty:
            return "No data available", 404
        
        output = io.BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{data_type}.csv'
        )
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
