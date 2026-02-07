from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DecimalField, FileField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'uploads/'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- Globals ---
inventory_data = []
REFERENCE_INVENTORY_FILE = 'reference_inventory.csv'

# --- Forms ---
class InventoryForm(FlaskForm):
    product = StringField('Product Name', validators=[DataRequired()])
    description = StringField('Description', validators=[DataRequired()])
    package_size = StringField('Package Size', validators=[DataRequired()])
    brand = StringField('Brand', validators=[DataRequired()])
    cost = DecimalField('Cost', validators=[DataRequired()])
    item_number = StringField('Item Number', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired()])
    submit = SubmitField('Add Item')

class UploadCSVForm(FlaskForm):
    file = FileField('CSV File', validators=[DataRequired()])
    submit = SubmitField('Upload CSV')


# --- Import and Register Blueprints ---
from inventory_report import report_bp
app.register_blueprint(report_bp)

# --- US Foods Orders Merge Route ---
@app.route('/merge_usfoodorders', methods=['GET'])
def merge_usfoodorders():
    import os
    import pandas as pd
    folder_path = '/Users/arnoldoramirezjr/Downloads/AliceInvoice'
    all_data = []
    for filename in os.listdir(folder_path):
        if filename.endswith('.csv'):
            file_path = os.path.join(folder_path, filename)
            df = pd.read_csv(file_path)
            all_data.append(df)
    if not all_data:
        flash('No CSV files found in AliceInvoice folder.', 'danger')
        return redirect(url_for('index'))
    combined_data = pd.concat(all_data, ignore_index=True)
    selected_columns = combined_data[['ProductNumber', 'ProductDescription', 'QtyShip']]
    grouped_data = selected_columns.groupby(['ProductNumber', 'ProductDescription'], as_index=False)['QtyShip'].sum()
    sorted_data = grouped_data.sort_values(by='ProductNumber')
    output_csv_file_path = os.path.join(os.getcwd(), 'Sorted_InvoiceDetails.csv')
    sorted_data.to_csv(output_csv_file_path, index=False)
    return send_file(output_csv_file_path, as_attachment=True)

@app.route('/take_inventory', methods=['GET', 'POST'])
def take_inventory():
    inventory_on_hand = []
    reference_items = []
    if os.path.exists(REFERENCE_INVENTORY_FILE):
        df = pd.read_csv(REFERENCE_INVENTORY_FILE)
        reference_items = df.to_dict(orient='records')
        # Ensure UPP is present for all reference_items
        import re
        def calculate_upp(package_size):
            if not isinstance(package_size, str):
                return 1
            package_size = package_size.strip()
            match = re.match(r'^(\d+)\s*/\s*([\d.]+)\s*([a-zA-Z]+)', package_size)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return 1
            return 1
        for item in reference_items:
            if 'UPP' not in item or item['UPP'] in [None, '', '-', 'nan', 'NaN']:
                item['UPP'] = calculate_upp(item.get('package_size', ''))
    default_date = request.form.get('inventory_date') or request.args.get('inventory_date') or datetime.now().strftime('%Y-%m-%d')
    loaded_inventory = None
    loaded_date = default_date
    # Try to load the inventory file for the selected date
    filename = f'daily_inventory_{default_date}.csv'
    if os.path.exists(filename):
        loaded_inventory = pd.read_csv(filename).to_dict(orient='records')
    if request.method == 'POST':
        date_str = request.form.get('inventory_date', default_date)
        def calculate_upp(package_size):
            # If package_size is like '4/5 LB', UPP = 4
            import re
            if not isinstance(package_size, str):
                return 1
            package_size = package_size.strip()
            match = re.match(r'^(\d+)\s*/\s*([\d.]+)\s*([a-zA-Z]+)', package_size)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return 1
            # If package_size is like '60 ea', '10 lb', '3 lb', UPP = 1
            return 1

        for idx, item in enumerate(reference_items):
            qty = request.form.get(f'qty_{idx}', '')
            try:
                qty = float(qty)
            except Exception:
                qty = 0
            package_size = item.get('package_size', '')
            upp = calculate_upp(package_size)
            inventory_on_hand.append({
                'description': item.get('description', ''),
                'package_size': package_size,
                'quantity_on_hand': qty,
                'UPP': upp
            })
        filename = f'daily_inventory_{date_str}.csv'
        pd.DataFrame(inventory_on_hand).to_csv(filename, index=False)
        flash(f'Daily inventory saved for {date_str}!', 'success')
        # Redirect to the same page with the date as a query parameter
        return redirect(url_for('take_inventory', inventory_date=date_str))
    return render_template('take_inventory.html', reference_items=reference_items, default_date=default_date, loaded_inventory=loaded_inventory, loaded_date=loaded_date)

    
# Printable inventory sheet route
@app.route('/print_inventory')
def print_inventory():
    reference_items = []
    if os.path.exists(REFERENCE_INVENTORY_FILE):
        df = pd.read_csv(REFERENCE_INVENTORY_FILE)
        reference_items = df.to_dict(orient='records')
        # Ensure UPP is present for all reference_items
        import re
        def calculate_upp(package_size):
            if not isinstance(package_size, str):
                return 1
            package_size = package_size.strip()
            match = re.match(r'^(\d+)\s*/\s*([\d.]+)\s*([a-zA-Z]+)', package_size)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return 1
            return 1
        for item in reference_items:
            if 'UPP' not in item or item['UPP'] in [None, '', '-', 'nan', 'NaN']:
                item['UPP'] = calculate_upp(item.get('package_size', ''))
        # No sorting, preserve file order
    date_str = datetime.now().strftime('%Y-%m-%d')
    return render_template('print_inventory.html', reference_items=reference_items, date=date_str)

# Route to display order results after invoice upload, with end date filtering and save option
@app.route('/order_results', methods=['GET', 'POST'])
def order_results():
    import os
    import pandas as pd
    from flask import request, flash
    csv_path = os.path.join(os.getcwd(), 'Sorted_InvoiceDetails.csv')
    orders = []
    end_date = None
    order_invoice_dir = os.path.join(os.getcwd(), 'OrderInvoices')
    if not os.path.exists(order_invoice_dir):
        os.makedirs(order_invoice_dir)
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
        # If the file has a 'Date' column, allow filtering
        if not df.empty:
            if request.method == 'POST':
                end_date = request.form.get('end_date')
                filtered_df = df
                if 'Date' in df.columns and end_date:
                    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                    mask = (df['Date'] <= end_date)
                    filtered_df = df[mask]
                else:
                    mask = None
                # Save as order invoice if requested
                if request.form.get('save_invoice') == '1':
                    invoice_path = os.path.join(order_invoice_dir, f'Order_Invoice_{end_date or "all"}.csv')
                    filtered_df.to_csv(invoice_path, index=False)
                    flash(f'Order invoice saved as {os.path.basename(invoice_path)}!', 'success')
                    # Remove the filtered rows from the main CSV
                    if mask is not None:
                        remaining_df = df[~mask]
                        remaining_df.to_csv(csv_path, index=False)
                    else:
                        # If no mask, remove all rows (since all were saved)
                        pd.DataFrame().to_csv(csv_path, index=False)
                    # After deletion, show only the remaining orders
                    orders = []
                    return render_template('order_results.html', orders=orders, end_date=end_date)
                orders = filtered_df.to_dict(orient='records')
            else:
                orders = df.to_dict(orient='records')
        else:
            orders = []
    return render_template('order_results.html', orders=orders, end_date=end_date)

@app.route('/', methods=['GET', 'POST'])
def index():
    form = InventoryForm()
    csv_form = UploadCSVForm()
    global inventory_data
    if form.validate_on_submit() and form.submit.data:
        item = {
            'product': form.product.data,
            'description': form.description.data,
            'package_size': form.package_size.data,
            'brand': form.brand.data,
            'cost': float(form.cost.data),
            'item_number': form.item_number.data,
            'quantity': form.quantity.data,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        inventory_data.append(item)
        flash('Item added!', 'success')
        return redirect(url_for('index'))
    if csv_form.validate_on_submit() and csv_form.submit.data:
        file = csv_form.file.data
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        df = pd.read_csv(filepath)
        # Map alternative headers to expected keys
        header_map = {
            'product': ['product', 'product name', 'item', 'item name'],
            'description': ['description', 'desc', 'item description', 'product description'],
            'package_size': ['package_size', 'package size', 'size', 'pkg size', 'product package size'],
            'brand': ['brand', 'company', 'manufacturer', 'product brand'],
            'cost': ['cost', 'price', 'unit cost', 'unit price'],
            'item_number': ['item_number', 'item number', 'sku', 'code', 'id', 'product number'],
            'quantity': ['quantity', 'qty', 'count', 'amount'],
            'group_name': ['group', 'group name', 'category', 'group_name']
        }
        # Build a mapping from lowercase/stripped column names to original names
        col_map = {str(col).strip().lower(): col for col in df.columns}
        def find_col(possibles):
            for p in possibles:
                p_lc = p.strip().lower()
                if p_lc in col_map:
                    return col_map[p_lc]
            return None
        for _, row in df.iterrows():
            item = {}
            for key, possibles in header_map.items():
                col = find_col(possibles)
                if col:
                    val = row.get(col, '')
                    if key == 'cost':
                        try:
                            val = float(val)
                        except Exception:
                            val = 0.0
                    elif key == 'quantity':
                        try:
                            val = float(val)
                        except Exception:
                            val = 0.0
                    item[key] = val
                else:
                    if key == 'cost' or key == 'quantity':
                        item[key] = 0.0
                    else:
                        item[key] = ''
            item['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            inventory_data.append(item)
        flash('CSV imported!', 'success')
        return redirect(url_for('index'))
    return render_template('index.html', form=form, csv_form=csv_form, inventory=inventory_data, can_save=len(inventory_data) > 0)

# Route to save the imported inventory as the reference inventory
@app.route('/save_reference_inventory', methods=['POST'])
def save_reference_inventory():
    global inventory_data
    if inventory_data:
        df = pd.DataFrame(inventory_data)
        df.to_csv(REFERENCE_INVENTORY_FILE, index=False)
        flash('Reference inventory saved!', 'success')
    else:
        flash('No inventory data to save.', 'danger')
    return redirect(url_for('index'))

# Route to load the reference inventory for daily use
@app.route('/load_reference_inventory', methods=['POST'])
def load_reference_inventory():
    global inventory_data
    if os.path.exists(REFERENCE_INVENTORY_FILE):
        df = pd.read_csv(REFERENCE_INVENTORY_FILE)
        inventory_data = df.to_dict(orient='records')
        flash('Reference inventory loaded for daily use!', 'success')
    else:
        flash('No reference inventory found.', 'danger')
    return redirect(url_for('index'))

# Route to list and download saved order invoices
@app.route('/order_invoices')
def order_invoices():
    order_invoice_dir = os.path.join(os.getcwd(), 'OrderInvoices')
    invoices = []
    if os.path.exists(order_invoice_dir):
        invoices = [f for f in os.listdir(order_invoice_dir) if f.endswith('.csv')]
    return render_template('order_invoices.html', invoices=invoices)

# Route to download a specific order invoice
@app.route('/download_order_invoice/<filename>')
def download_order_invoice(filename):
    order_invoice_dir = os.path.join(os.getcwd(), 'OrderInvoices')
    file_path = os.path.join(order_invoice_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    flash('File not found.', 'danger')
    return redirect(url_for('order_invoices'))

if __name__ == '__main__':
    app.run(debug=True)
