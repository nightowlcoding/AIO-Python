from flask import Flask, render_template_string, request, jsonify, send_file
import pandas as pd
import json
import os
from datetime import datetime, date

app = Flask(__name__)

# Global data storage
inventory_data = {}
products_list = []
order_data = {}  # Store order estimates by location and date
invoice_import_log = []  # Log of all invoice imports

# Products that should show case count instead of unit count in orders
# For these products, do not multiply by package size when importing invoices
CASE_COUNT_PRODUCTS = [
    '2725042',
    '2720977',
    '2725661',
    '5314208',
    '3408822',
    '4558003',
    '2571705',
    '6911663',
    '1552124',
    '6083968',
    '7979586'
]

# Paths - Using relative paths for portability
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, 'data')
backup_dir = os.path.join(base_dir, 'backups')
export_dir = os.path.join(base_dir, 'exports')

# Create directories if they don't exist
os.makedirs(data_dir, exist_ok=True)
os.makedirs(backup_dir, exist_ok=True)
os.makedirs(export_dir, exist_ok=True)


def load_products():
    """Load product list from reference inventory"""
    global products_list
    try:
        # Look for CSV in the application directory
        inventory_path = os.path.join(base_dir, 'Update - Sept 13th.csv')
        if os.path.exists(inventory_path):
            df = pd.read_csv(inventory_path)
            
            # Check what columns are available
            print(f"Loading products from: {inventory_path}")
            print(f"Available columns: {list(df.columns)}")
            
            # Ensure required columns exist
            required_columns = ['Product Number', 'Product Description', 
                              'Product Brand', 'Product Package Size', 'Group Name', 'Case Count Type']
            
            # Add missing columns if they don't exist
            for col in required_columns:
                if col not in df.columns:
                    print(f"  Warning: Missing column '{col}', adding with default values")
                    if col == 'Case Count Type':
                        df[col] = 'No'  # Default to regular products
                    else:
                        df[col] = ''
            
            # Include Group Name for categorization and fill NaN values
            df = df[required_columns]
            # Replace NaN with empty strings or default values
            df = df.fillna({
                'Product Number': '',
                'Product Description': '',
                'Product Brand': '',
                'Product Package Size': '',
                'Group Name': 'OTHER',
                'Case Count Type': 'No'
            })
            
            # Migrate old CASE_COUNT_PRODUCTS to new system
            for i, row in df.iterrows():
                if str(row['Product Number']) in CASE_COUNT_PRODUCTS:
                    df.at[i, 'Case Count Type'] = 'Yes'
            products_list = df.to_dict('records')
            print(f"✓ Loaded {len(products_list)} products from CSV")
        else:
            print(f"Warning: Product file not found at {inventory_path}")
            products_list = []
        
        # Save a backup of the product list
        save_product_list_backup()
    except Exception as e:
        print(f"Error loading products: {e}")
        import traceback
        traceback.print_exc()
        products_list = []


def save_product_list_backup():
    """Save backup of current product list with timestamp"""
    try:
        product_backup_dir = os.path.join(backup_dir, 'product_lists')
        os.makedirs(product_backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(product_backup_dir, f'products_{timestamp}.json')
        
        with open(backup_file, 'w') as f:
            json.dump(products_list, f, indent=2)
    except Exception as e:
        print(f"Error saving backup: {e}")


def save_products_to_csv():
    """Save current product list back to CSV file with backup"""
    try:
        # Create backup of original file
        inventory_path = os.path.join(base_dir, 'Update - Sept 13th.csv')
        if os.path.exists(inventory_path):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = os.path.join(backup_dir, f'Update_Sept_13th_backup_{timestamp}.csv')
            pd.read_csv(inventory_path).to_csv(backup_path, index=False)
        
        # Ensure all products have required columns with proper defaults
        required_columns = ['Product Number', 'Product Description', 
                          'Product Brand', 'Product Package Size', 'Group Name', 'Case Count Type']
        
        cleaned_products = []
        for product in products_list:
            cleaned_product = {
                'Product Number': str(product.get('Product Number', '')),
                'Product Description': str(product.get('Product Description', '')),
                'Product Brand': str(product.get('Product Brand', '')),
                'Product Package Size': str(product.get('Product Package Size', '')),
                'Group Name': str(product.get('Group Name', 'OTHER')),
                'Case Count Type': str(product.get('Case Count Type', 'No'))
            }
            cleaned_products.append(cleaned_product)
        
        # Save updated product list with explicit column order
        df = pd.DataFrame(cleaned_products, columns=required_columns)
        df.to_csv(inventory_path, index=False)
        print(f"✓ Saved {len(cleaned_products)} products to CSV")
        
        # Save JSON backup as well
        save_product_list_backup()
        
        # Don't reload - keep current in-memory state
        # This prevents losing newly added products or reordered items
        return True
    except Exception as e:
        print(f"Error saving products to CSV: {e}")
        import traceback
        traceback.print_exc()
        return False


def reload_products_from_csv():
    """Reload products from CSV file into memory"""
    global products_list
    try:
        inventory_path = os.path.join(base_dir, 'Update - Sept 13th.csv')
        if os.path.exists(inventory_path):
            df = pd.read_csv(inventory_path)
            # Ensure required columns exist
            required_columns = ['Product Number', 'Product Description', 
                              'Product Brand', 'Product Package Size', 'Group Name', 'Case Count Type']
            
            # Add missing columns if they don't exist
            for col in required_columns:
                if col not in df.columns:
                    if col == 'Case Count Type':
                        df[col] = 'No'
                    else:
                        df[col] = ''
            
            # Select only required columns
            df = df[required_columns]
            df = df.fillna({
                'Product Number': '',
                'Product Description': '',
                'Product Brand': '',
                'Product Package Size': '',
                'Group Name': 'OTHER',
                'Case Count Type': 'No'
            })
            products_list = df.to_dict('records')
            print(f"✓ Reloaded {len(products_list)} products from CSV")
    except Exception as e:
        print(f"Error reloading products: {e}")


def load_inventory_database():
    """Load inventory database from disk"""
    global inventory_data
    try:
        db_path = os.path.join(data_dir, 'inventory_database.json')
        if os.path.exists(db_path):
            with open(db_path, 'r') as f:
                inventory_data = json.load(f)
        else:
            inventory_data = {}
    except Exception as e:
        print(f"Error loading database: {e}")
        inventory_data = {}


def save_inventory_database():
    """Save inventory database to disk"""
    try:
        db_path = os.path.join(data_dir, 'inventory_database.json')
        with open(db_path, 'w') as f:
            json.dump(inventory_data, f, indent=2)
    except Exception as e:
        print(f"Error saving database: {e}")


def load_orders_database():
    """Load order database from disk"""
    global order_data
    try:
        db_path = os.path.join(data_dir, 'orders_database.json')
        if os.path.exists(db_path):
            with open(db_path, 'r') as f:
                order_data = json.load(f)
        else:
            order_data = {}
    except Exception as e:
        print(f"Error loading order database: {e}")
        order_data = {}


def save_orders_database():
    """Save order database to disk"""
    try:
        db_path = os.path.join(data_dir, 'orders_database.json')
        with open(db_path, 'w') as f:
            json.dump(order_data, f, indent=2)
    except Exception as e:
        print(f"Error saving order database: {e}")


def load_invoice_import_log():
    """Load invoice import log from disk"""
    global invoice_import_log
    try:
        log_path = os.path.join(data_dir, 'invoice_import_log.json')
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                invoice_import_log = json.load(f)
        else:
            invoice_import_log = []
    except Exception as e:
        print(f"Error loading invoice import log: {e}")
        invoice_import_log = []


def save_invoice_import_log():
    """Save invoice import log to disk"""
    try:
        log_path = os.path.join(data_dir, 'invoice_import_log.json')
        with open(log_path, 'w') as f:
            json.dump(invoice_import_log, f, indent=2)
    except Exception as e:
        print(f"Error saving invoice import log: {e}")


def add_invoice_import_entry(location, delivery_date, filename, products_imported, new_products, matched_count):
    """Add an entry to the invoice import log"""
    global invoice_import_log
    
    import_id = f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    entry = {
        'import_id': import_id,
        'timestamp': datetime.now().isoformat(),
        'filename': filename,
        'location': location,
        'delivery_date': delivery_date,
        'matched_count': matched_count,
        'new_products_created': len(new_products),
        'new_product_numbers': new_products,
        'total_products': len(products_imported),
        'products': products_imported  # Store the actual product numbers and quantities
    }
    
    invoice_import_log.append(entry)
    save_invoice_import_log()
    
    return import_id


# API Endpoints
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/products', methods=['GET'])
def get_products():
    """Get all products"""
    print(f"API /api/products called - returning {len(products_list)} products")
    return jsonify(products_list)


@app.route('/api/inventory/<location>/<date>', methods=['GET'])
def get_inventory(location, date):
    """Get inventory for a specific location and date"""
    print(f"GET inventory request - Location: {location}, Date: {date}")
    print(f"Available locations: {list(inventory_data.keys())}")
    if location in inventory_data:
        print(f"Dates for {location}: {list(inventory_data[location].keys())}")
    
    if location in inventory_data and date in inventory_data[location]:
        item_count = len(inventory_data[location][date])
        print(f"Found inventory: {item_count} items")
        return jsonify(inventory_data[location][date])
    
    print(f"No inventory found for {location} on {date}")
    return jsonify({})


@app.route('/api/inventory/save', methods=['POST'])
def save_inventory():
    """Save inventory data"""
    data = request.json
    location = data.get('location')
    date = data.get('date')
    inventory = data.get('inventory')
    
    if location not in inventory_data:
        inventory_data[location] = {}
    
    inventory_data[location][date] = inventory
    save_inventory_database()
    
    return jsonify({'success': True, 'message': 'Inventory saved successfully'})


@app.route('/api/inventory/list', methods=['GET'])
def list_inventories():
    """List all saved inventories"""
    result = []
    for location in inventory_data:
        for date in inventory_data[location]:
            result.append({
                'location': location,
                'date': date,
                'item_count': len(inventory_data[location][date])
            })
    return jsonify(result)


@app.route('/api/inventory/delete', methods=['POST'])
def delete_inventory():
    """Delete an inventory"""
    data = request.json
    location = data.get('location')
    date = data.get('date')
    
    if location in inventory_data and date in inventory_data[location]:
        del inventory_data[location][date]
        save_inventory_database()
        return jsonify({'success': True, 'message': 'Inventory deleted successfully'})
    
    return jsonify({'success': False, 'message': 'Inventory not found'})


@app.route('/api/inventory/export/<location>/<date>', methods=['GET'])
def export_inventory(location, date):
    """Export inventory to CSV"""
    if location in inventory_data and date in inventory_data[location]:
        data = inventory_data[location][date]
        
        # Create DataFrame
        rows = []
        for product_num, quantity in data.items():
            product = next((p for p in products_list if str(p['Product Number']) == product_num), None)
            if product:
                rows.append({
                    'Product Number': product_num,
                    'Product Description': product['Product Description'],
                    'Product Brand': product['Product Brand'],
                    'Product Package Size': product['Product Package Size'],
                    'Quantity': quantity
                })
        
        df = pd.DataFrame(rows)
        
        # Save to exports folder
        filename = f'inventory_{location}_{date}.csv'
        filepath = os.path.join(export_dir, filename)
        df.to_csv(filepath, index=False)
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    return jsonify({'success': False, 'message': 'Inventory not found'})


@app.route('/api/reports/summary', methods=['GET'])
def get_summary():
    """Get summary report"""
    summary = {}
    for location in inventory_data:
        summary[location] = {
            'total_inventories': len(inventory_data[location]),
            'dates': list(inventory_data[location].keys())
        }
    return jsonify(summary)


@app.route('/api/reports/product-activity', methods=['GET'])
def get_product_activity():
    """Get product activity report showing inventory and order frequency by product"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        location = request.args.get('location', 'all')
        
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': 'Start date and end date are required'})
        
        # Track activity per product
        product_activity = {}
        
        # Process inventory data
        locations_to_check = [location] if location != 'all' else inventory_data.keys()
        
        for loc in locations_to_check:
            if loc not in inventory_data:
                continue
                
            for inv_date, inventory in inventory_data[loc].items():
                # Check if date is in range
                if start_date <= inv_date <= end_date:
                    for product_num, quantity in inventory.items():
                        if product_num not in product_activity:
                            product_activity[product_num] = {
                                'inventory_count': 0,
                                'order_count': 0,
                                'inventory_dates': [],
                                'order_dates': []
                            }
                        product_activity[product_num]['inventory_count'] += 1
                        product_activity[product_num]['inventory_dates'].append({'date': inv_date, 'location': loc, 'quantity': quantity})
        
        # Process order data
        for loc in locations_to_check:
            if loc not in order_data:
                continue
                
            for order_date, orders in order_data[loc].items():
                # Check if date is in range
                if start_date <= order_date <= end_date:
                    for product_num, quantity in orders.items():
                        if product_num not in product_activity:
                            product_activity[product_num] = {
                                'inventory_count': 0,
                                'order_count': 0,
                                'inventory_dates': [],
                                'order_dates': []
                            }
                        product_activity[product_num]['order_count'] += 1
                        product_activity[product_num]['order_dates'].append({'date': order_date, 'location': loc, 'quantity': quantity})
        
        # Enrich with product details - maintain CSV order by iterating through products_list
        result = []
        for product in products_list:
            product_num = str(product['Product Number'])
            if product_num in product_activity:
                activity = product_activity[product_num]
                
                # Calculate usage: Beginning Inventory + Total Orders - Ending Inventory
                beginning_inventory = 0
                ending_inventory = 0
                total_orders = 0
                
                # Find beginning inventory (earliest date)
                if activity['inventory_dates']:
                    sorted_inv = sorted(activity['inventory_dates'], key=lambda x: x['date'])
                    beginning_inventory = sorted_inv[0]['quantity'] or 0
                    ending_inventory = sorted_inv[-1]['quantity'] or 0
                
                # Sum all orders
                if activity['order_dates']:
                    total_orders = sum((o['quantity'] or 0) for o in activity['order_dates'])
                
                # Calculate usage
                usage = beginning_inventory + total_orders - ending_inventory
                
                # Calculate cases required (convert usage units back to cases)
                cases_required = 0
                package_size_str = product.get('Product Package Size', '')
                if package_size_str:
                    try:
                        # Extract the number before the slash (e.g., "6/4LB" -> 6)
                        case_pack = int(str(package_size_str).split('/')[0])
                        if case_pack > 0:
                            cases_required = round(usage / case_pack, 2)
                    except (ValueError, IndexError, ZeroDivisionError):
                        cases_required = 0
                
                result.append({
                    'product_number': product_num,
                    'description': product.get('Product Description', ''),
                    'brand': product.get('Product Brand', ''),
                    'package_size': product.get('Product Package Size', ''),
                    'group': product.get('Group Name', ''),
                    'case_count_type': product.get('Case Count Type', 'No'),
                    'inventory_count': activity['inventory_count'],
                    'order_count': activity['order_count'],
                    'total_activity': activity['inventory_count'] + activity['order_count'],
                    'inventory_dates': activity['inventory_dates'],
                    'order_dates': activity['order_dates'],
                    'beginning_inventory': beginning_inventory,
                    'ending_inventory': ending_inventory,
                    'total_orders': total_orders,
                    'usage': usage,
                    'cases_required': cases_required
                })
        
        return jsonify({
            'success': True,
            'products': result,
            'total_products': len(result),
            'date_range': {'start': start_date, 'end': end_date},
            'location': location
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/add', methods=['POST'])
def add_product():
    """Add a new product to the list"""
    try:
        data = request.json
        new_product = {
            'Product Number': data.get('product_number'),
            'Product Description': data.get('description'),
            'Product Brand': data.get('brand'),
            'Product Package Size': data.get('package_size'),
            'Group Name': data.get('group_name', 'OTHER')
        }
        
        # Handle insert position
        insert_position = data.get('insert_position')
        if insert_position is not None and insert_position > 0:
            # Insert at specific position (convert to 0-based index)
            insert_index = insert_position - 1
            if insert_index > len(products_list):
                insert_index = len(products_list)
            products_list.insert(insert_index, new_product)
        else:
            # Add at end
            products_list.append(new_product)
        
        # Save to CSV
        if save_products_to_csv():
            print(f"Product added successfully. Total products now: {len(products_list)}")
            return jsonify({'success': True, 'message': 'Product added successfully'})
        else:
            return jsonify({'success': False, 'message': 'Error saving product'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/update', methods=['POST'])
def update_product():
    """Update an existing product"""
    try:
        data = request.json
        product_num = str(data.get('product_number'))
        
        # Find and update product
        for i, product in enumerate(products_list):
            if str(product['Product Number']) == product_num:
                products_list[i] = {
                    'Product Number': product_num,
                    'Product Description': data.get('description'),
                    'Product Brand': data.get('brand'),
                    'Product Package Size': data.get('package_size')
                }
                
                # Update Group Name if provided
                if 'group_name' in data and data.get('group_name'):
                    product['Group Name'] = data.get('group_name')
                
                # Save to CSV
                if save_products_to_csv():
                    return jsonify({'success': True, 'message': 'Product updated successfully'})
                else:
                    return jsonify({'success': False, 'message': 'Error saving product'})
        
        return jsonify({'success': False, 'message': 'Product not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/update-case-count', methods=['POST'])
def update_case_count_type():
    """Update Case Count Type for a product"""
    try:
        data = request.json
        product_num = str(data.get('product_number'))
        case_count_type = data.get('case_count_type', 'No')
        
        # Find and update product
        for product in products_list:
            if str(product['Product Number']) == product_num:
                product['Case Count Type'] = case_count_type
                
                # Save to CSV
                if save_products_to_csv():
                    return jsonify({'success': True, 'message': f'Case Count Type updated to {case_count_type}'})
                else:
                    return jsonify({'success': False, 'message': 'Error saving product'})
        
        return jsonify({'success': False, 'message': 'Product not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/delete', methods=['POST'])
def delete_product():
    """Delete a product"""
    try:
        data = request.json
        product_num = str(data.get('product_number'))
        
        # Find and remove product
        global products_list
        products_list = [p for p in products_list if str(p['Product Number']) != product_num]
        
        # Save to CSV
        if save_products_to_csv():
            return jsonify({'success': True, 'message': 'Product deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Error saving product'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/history', methods=['GET'])
def get_product_history():
    """Get product list backup history"""
    try:
        product_backup_dir = os.path.join(backup_dir, 'product_lists')
        if os.path.exists(product_backup_dir):
            files = [f for f in os.listdir(product_backup_dir) if f.endswith('.json')]
            files.sort(reverse=True)
            return jsonify({'success': True, 'files': files})
        return jsonify({'success': True, 'files': []})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/reorder', methods=['POST'])
def reorder_products():
    """Reorder products based on drag-and-drop"""
    try:
        global products_list
        data = request.json
        product_order = data.get('product_order', [])
        
        if not product_order:
            return jsonify({'success': False, 'message': 'No product order provided'})
        
        # Create new ordered list
        new_products_list = []
        for product_num in product_order:
            product = next((p for p in products_list if str(p['Product Number']) == str(product_num)), None)
            if product:
                new_products_list.append(product)
        
        # Update global list - this maintains the new order
        products_list = new_products_list
        print(f"✓ Reordered products list: {len(products_list)} products")
        
        # Save to CSV (will persist the new order)
        if save_products_to_csv():
            return jsonify({'success': True, 'message': 'Product order saved successfully'})
        else:
            return jsonify({'success': False, 'message': 'Error saving product order'})
    except Exception as e:
        print(f"Error reordering products: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/products/upload', methods=['POST'])
def upload_products():
    """Upload a CSV file to replace product list"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'Only CSV files are allowed'})
        
        # Read and validate CSV before saving
        df = pd.read_csv(file)
        
        # Check for required columns
        required_columns = ['Product Number', 'Product Description', 'Product Brand', 'Product Package Size', 'Group Name']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return jsonify({
                'success': False, 
                'message': f'CSV is missing required columns: {", ".join(missing_columns)}. Found columns: {", ".join(df.columns)}. This appears to be an inventory CSV, not a product list CSV.'
            })
        
        # Save uploaded file
        upload_path = os.path.join(base_dir, 'Update - Sept 13th.csv')
        
        # Backup existing file first
        if os.path.exists(upload_path):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = os.path.join(backup_dir, f'Update_Sept_13th_backup_{timestamp}.csv')
            os.rename(upload_path, backup_path)
        
        # Save new file
        file.save(upload_path)
        
        # Reload products
        load_products()
        
        return jsonify({'success': True, 'message': 'Product list uploaded successfully', 
                       'product_count': len(products_list)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# Order Management Endpoints
@app.route('/api/orders/upload', methods=['POST'])
def upload_orders():
    """Upload order CSV for a location"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['file']
        location = request.form.get('location', 'Kingsville')
        order_date = request.form.get('order_date')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'File must be a CSV'})
        
        if not order_date:
            return jsonify({'success': False, 'message': 'Please provide an order date'})
        
        # Read and parse CSV
        df = pd.read_csv(file)
        
        # Check for required columns (flexible column name matching)
        possible_product_cols = ['Product Number', 'Product #', 'ProductNumber', 'product_number', 'SKU', 'Item Number', 'Item #']
        possible_quantity_cols = ['Quantity', 'Qty', 'Count', 'quantity', 'qty', 'count', 'Amount', 'Order Quantity', 'Order Qty']
        
        product_col = None
        quantity_col = None
        
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if not product_col:
                for possible in possible_product_cols:
                    if col.strip() == possible or col_lower == possible.lower():
                        product_col = col
                        break
            if not quantity_col:
                for possible in possible_quantity_cols:
                    if col.strip() == possible or col_lower == possible.lower():
                        quantity_col = col
                        break
        
        if not product_col or not quantity_col:
            return jsonify({
                'success': False, 
                'message': f'CSV must contain Product Number and Quantity columns. Found columns: {", ".join(df.columns)}'
            })
        
        # Parse order data
        orders = {}
        for _, row in df.iterrows():
            product_num = str(row.get(product_col, '')).strip()
            try:
                qty_value = row.get(quantity_col, 0)
                # Treat empty/blank/dash as 0
                if qty_value == '' or pd.isna(qty_value) or str(qty_value).strip() in ['-', '_', 'N/A', 'n/a', 'NA']:
                    quantity = 0
                else:
                    quantity = float(str(qty_value).strip())
            except (ValueError, TypeError):
                quantity = 0
            if product_num and quantity >= 0:
                orders[product_num] = quantity
        
        # Store order data
        if location not in order_data:
            order_data[location] = {}
        order_data[location][order_date] = orders
        
        # Save to database
        save_orders_database()
        
        return jsonify({'success': True, 'message': 'Orders uploaded successfully', 
                       'order_count': len(orders)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/orders/upload-invoice', methods=['POST'])
def upload_invoice():
    """Upload invoice CSV from food provider"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['file']
        location = request.form.get('location', 'Kingsville')
        delivery_date = request.form.get('delivery_date')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'File must be a CSV'})
        
        if not delivery_date:
            return jsonify({'success': False, 'message': 'Please provide a delivery date'})
        
        # Read and parse CSV
        df = pd.read_csv(file)
        
        # Look for required columns from food provider invoice
        required_mapping = {
            'ProductNumber': ['ProductNumber', 'Product Number', 'Product#', 'SKU'],
            'QtyShip': ['QtyShip', 'Qty Ship', 'Quantity Shipped', 'Shipped', 'Qty'],
            'PricingUnit': ['PricingUnit', 'Pricing Unit', 'Unit', 'UOM'],
            'PackingSize': ['PackingSize', 'Packing Size', 'Pack Size', 'Package Size'],
            'ProductDescription': ['ProductDescription', 'Product Description', 'Description', 'Item Description'],
            'ProductLabel': ['Product Label', 'ProductLabel', 'Brand', 'Label', 'Manufacturer']
        }
        
        column_map = {}
        for field, possible_names in required_mapping.items():
            found = False
            for col in df.columns:
                if col.strip() in possible_names:
                    column_map[field] = col.strip()
                    found = True
                    break
            if not found and field not in ['PricingUnit', 'PackingSize', 'ProductDescription', 'ProductLabel']:  # Optional columns
                return jsonify({
                    'success': False,
                    'message': f'Could not find {field} column. Available columns: {", ".join(df.columns.tolist())}'
                })
        
        # Parse order data from invoice
        orders = {}
        matched_count = 0
        unmatched_products = []
        new_products_created = []
        
        for _, row in df.iterrows():
            product_num = str(row[column_map['ProductNumber']]).strip()
            try:
                qty = float(row[column_map['QtyShip']])
            except (ValueError, TypeError):
                qty = 0
            
            # Check PricingUnit and adjust quantity for cases
            if 'PricingUnit' in column_map and 'PackingSize' in column_map:
                pricing_unit = str(row[column_map['PricingUnit']]).strip().upper()
                packing_size = str(row[column_map['PackingSize']]).strip()
                
                # If sold as case (CS), multiply by case pack size
                # EXCEPT for products marked as Case Count Type - keep those as case count
                if pricing_unit == 'CS' and '/' in packing_size:
                    # Find the product and check if it's marked as Case Count Type
                    product_info = next((p for p in products_list if str(p['Product Number']) == product_num), None)
                    is_case_count = product_info and str(product_info.get('Case Count Type', 'No')).upper() == 'YES'
                    
                    # Debug logging
                    if product_info:
                        case_count_value = product_info.get('Case Count Type', 'Not Set')
                        print(f"Product {product_num}: Case Count Type = '{case_count_value}', is_case_count = {is_case_count}")
                    else:
                        print(f"Product {product_num}: Product not found in products_list!")
                    
                    # Also check legacy hardcoded list for backwards compatibility
                    if product_num in CASE_COUNT_PRODUCTS:
                        is_case_count = True
                        print(f"Product {product_num}: Found in legacy CASE_COUNT_PRODUCTS list")
                    
                    if not is_case_count:
                        # Extract the number before the slash (e.g., "6/4LB" -> 6)
                        try:
                            case_pack = int(packing_size.split('/')[0])
                            original_qty = qty
                            qty = qty * case_pack
                            print(f"✓ Product {product_num}: MULTIPLIED - {original_qty} cases × {case_pack} = {qty} units")
                        except (ValueError, IndexError):
                            pass  # If parsing fails, use original quantity
                    else:
                        # Keep as case count for special products
                        print(f"✓ Product {product_num}: CASE COUNT - keeping qty as {qty} cases (NOT multiplied)")
            
            if product_num and qty >= 0:
                # Check if product exists in our product list
                product_exists = any(str(p['Product Number']) == product_num for p in products_list)
                
                if product_exists:
                    orders[product_num] = qty
                    matched_count += 1
                else:
                    # Create new product from invoice data
                    new_product = {
                        'Product Number': product_num,
                        'Product Description': str(row.get(column_map.get('ProductDescription', 'ProductDescription'), 'Unknown Product')).strip() if 'ProductDescription' in column_map else 'Unknown Product',
                        'Product Brand': str(row.get(column_map.get('ProductLabel', 'ProductLabel'), 'Unknown Brand')).strip() if 'ProductLabel' in column_map else 'Unknown Brand',
                        'Product Package Size': str(row.get(column_map.get('PackingSize', 'PackingSize'), '')).strip() if 'PackingSize' in column_map else '',
                        'Group Name': 'Unassigned',  # Default group for new products
                        'Case Count Type': 'No'  # Default to regular product
                    }
                    
                    # Add to products list
                    products_list.append(new_product)
                    new_products_created.append(product_num)
                    
                    # Still record the order
                    orders[product_num] = qty
                    matched_count += 1
        
        # Save new products to CSV if any were created
        if new_products_created:
            print(f"✓ Creating {len(new_products_created)} new products from invoice")
            print(f"  Product numbers: {', '.join(new_products_created)}")
            if save_products_to_csv():
                print(f"✓ Successfully saved {len(new_products_created)} new products to CSV")
            else:
                print("✗ ERROR: Failed to save new products to CSV!")
        
        # Merge order data (add to existing orders for the same date instead of replacing)
        if location not in order_data:
            order_data[location] = {}
        if delivery_date not in order_data[location]:
            order_data[location][delivery_date] = {}
        
        # Merge quantities - if product already exists for this date, add the quantities
        for product_num, qty in orders.items():
            if product_num in order_data[location][delivery_date]:
                order_data[location][delivery_date][product_num] += qty
            else:
                order_data[location][delivery_date][product_num] = qty
        
        # Save to database
        save_orders_database()
        
        # Add to import log
        import_id = add_invoice_import_entry(
            location=location,
            delivery_date=delivery_date,
            filename=file.filename,
            products_imported=orders,
            new_products=new_products_created,
            matched_count=matched_count
        )
        
        message = f'Invoice imported successfully! Import ID: {import_id}<br>Matched {matched_count} products.'
        if new_products_created:
            message += f' Created {len(new_products_created)} new products.'
        
        return jsonify({
            'success': True,
            'message': message,
            'import_id': import_id,
            'matched_count': matched_count,
            'unmatched_count': len(unmatched_products),
            'unmatched_products': unmatched_products[:10] if unmatched_products else [],
            'new_products_created': len(new_products_created),
            'new_product_numbers': new_products_created[:10] if new_products_created else [],
            'total_items': len(orders)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/invoices/import-log', methods=['GET'])
def get_invoice_import_log():
    """Get the invoice import log"""
    try:
        # Return log in reverse chronological order (newest first)
        return jsonify({
            'success': True,
            'imports': sorted(invoice_import_log, key=lambda x: x['timestamp'], reverse=True)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/invoices/import/<import_id>', methods=['GET'])
def get_invoice_import_details(import_id):
    """Get details of a specific invoice import"""
    try:
        import_entry = next((entry for entry in invoice_import_log if entry['import_id'] == import_id), None)
        
        if not import_entry:
            return jsonify({'success': False, 'message': 'Import not found'})
        
        return jsonify({
            'success': True,
            'import': import_entry
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/invoices/import/<import_id>', methods=['DELETE'])
def delete_invoice_import(import_id):
    """Delete/reverse a specific invoice import"""
    try:
        import_entry = next((entry for entry in invoice_import_log if entry['import_id'] == import_id), None)
        
        if not import_entry:
            return jsonify({'success': False, 'message': 'Import not found'})
        
        # Remove the quantities from order_data
        location = import_entry['location']
        delivery_date = import_entry['delivery_date']
        products = import_entry['products']
        
        if location in order_data and delivery_date in order_data[location]:
            for product_num, qty in products.items():
                if product_num in order_data[location][delivery_date]:
                    order_data[location][delivery_date][product_num] -= qty
                    # Remove if quantity becomes 0 or negative
                    if order_data[location][delivery_date][product_num] <= 0:
                        del order_data[location][delivery_date][product_num]
            
            # Clean up empty dates
            if not order_data[location][delivery_date]:
                del order_data[location][delivery_date]
        
        # Remove from log
        invoice_import_log.remove(import_entry)
        
        # Save changes
        save_orders_database()
        save_invoice_import_log()
        
        return jsonify({
            'success': True,
            'message': f'Import {import_id} has been reversed and removed'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/orders/calculate', methods=['POST'])
def calculate_official_order():
    """Calculate official order: Order - Inventory"""
    try:
        data = request.json
        location = data.get('location')
        order_date = data.get('order_date')
        inventory_date = data.get('inventory_date')
        
        # Get order data
        if location not in order_data or order_date not in order_data[location]:
            return jsonify({'success': False, 'message': 'No order found for this date'})
        
        orders = order_data[location][order_date]
        
        # Get inventory data
        inventory = {}
        if location in inventory_data and inventory_date in inventory_data[location]:
            inventory = inventory_data[location][inventory_date]
        
        # Calculate: Official Order = Order - Inventory
        official_order = {}
        for product_num, order_qty in orders.items():
            inventory_qty = inventory.get(product_num, 0)
            official_qty = max(0, order_qty - inventory_qty)  # Can't be negative
            if official_qty > 0:
                official_order[product_num] = official_qty
        
        return jsonify({
            'success': True,
            'official_order': official_order,
            'order_total': sum(orders.values()),
            'inventory_total': sum(inventory.values()),
            'official_total': sum(official_order.values())
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/orders/list', methods=['GET'])
def list_orders():
    """List all orders"""
    result = []
    for location in order_data:
        for order_date in order_data[location]:
            result.append({
                'location': location,
                'date': order_date,
                'item_count': len(order_data[location][order_date])
            })
    return jsonify(result)


@app.route('/api/inventory/upload', methods=['POST'])
def upload_inventory():
    """Upload inventory CSV for a specific location and date"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['file']
        location = request.form.get('location', 'Kingsville')
        inventory_date = request.form.get('inventory_date')
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'message': 'File must be a CSV'})
        
        if not inventory_date:
            return jsonify({'success': False, 'message': 'Please provide an inventory date'})
        
        # Read and parse CSV
        df = pd.read_csv(file)
        
        # Check for required columns (flexible column name matching)
        possible_product_cols = ['Product Number', 'Product #', 'ProductNumber', 'product_number', 'SKU']
        possible_product_name_cols = ['Product Name', 'Product Description', 'Description', 'Name', 'product_name', 'description']
        possible_quantity_cols = ['Quantity', 'Qty', 'Count', 'quantity', 'qty', 'count']
        
        product_col = None
        product_name_col = None
        quantity_col = None
        
        for col in df.columns:
            if col in possible_product_cols:
                product_col = col
            if col in possible_product_name_cols:
                product_name_col = col
            if col in possible_quantity_cols:
                quantity_col = col
        
        if not product_col or not quantity_col:
            return jsonify({
                'success': False, 
                'message': f'CSV must contain Product Number and Quantity columns. Found columns: {", ".join(df.columns)}'
            })
        
        # Parse inventory data
        inventory = {}
        matched_products = 0
        unmatched_products = []
        
        for _, row in df.iterrows():
            product_num = str(row.get(product_col, '')).strip()
            try:
                qty_value = row.get(quantity_col, '')
                # Treat empty/blank/dash as 0
                if qty_value == '' or pd.isna(qty_value) or str(qty_value).strip() in ['-', '_', 'N/A', 'n/a', 'NA']:
                    quantity = 0
                else:
                    # Remove any whitespace and try to convert
                    quantity = float(str(qty_value).strip())
            except (ValueError, TypeError):
                quantity = 0
            
            if product_num and quantity >= 0:
                # Check if product exists in product list
                product_exists = any(str(p['Product Number']) == product_num for p in products_list)
                
                if product_exists:
                    inventory[product_num] = quantity
                    matched_products += 1
                else:
                    unmatched_products.append(product_num)
        
        # Store inventory data
        if location not in inventory_data:
            inventory_data[location] = {}
        inventory_data[location][inventory_date] = inventory
        
        print(f"Inventory saved - Location: {location}, Date: {inventory_date}, Items: {len(inventory)}")
        print(f"First 3 items: {list(inventory.items())[:3]}")
        
        # Save to database
        save_inventory_database()
        
        # Save uploaded file as backup
        upload_backup_dir = os.path.join(backup_dir, 'inventory_uploads')
        os.makedirs(upload_backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f'inventory_{location}_{inventory_date}_{timestamp}.csv'
        backup_path = os.path.join(upload_backup_dir, backup_filename)
        df.to_csv(backup_path, index=False)
        
        message = f'Inventory uploaded successfully! {matched_products} products matched.'
        if unmatched_products:
            message += f' {len(unmatched_products)} products not found in product list.'
        
        return jsonify({
            'success': True,
            'message': message,
            'matched_count': matched_products,
            'unmatched_count': len(unmatched_products),
            'unmatched_products': unmatched_products[:10],  # Return first 10 unmatched
            'total_items': len(inventory)
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error uploading inventory: {str(e)}'})


@app.route('/api/inventory/sample-csv', methods=['GET'])
def download_sample_inventory_csv():
    """Generate and download a sample inventory CSV with actual products in display order"""
    try:
        # Create sample data in the same order as displayed in Enter Inventory
        rows = []
        
        for product in products_list:
            rows.append({
                'Product #': product.get('Product Number', ''),
                'Product Name': product.get('Product Description', ''),
                'Quantity': ''  # Empty quantity for user to fill in
            })
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # Save to exports folder
        filename = 'sample_inventory_template.csv'
        filepath = os.path.join(export_dir, filename)
        df.to_csv(filepath, index=False)
        
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error generating sample CSV: {str(e)}'})


@app.route('/favicon.ico')
def favicon():
    """Return empty response for favicon to prevent 404 errors"""
    return '', 204


# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Inventory Control System</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
        }
        
        .tab {
            flex: 1;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 1.1em;
            font-weight: 600;
            color: #6c757d;
            transition: all 0.3s;
        }
        
        .tab:hover {
            background: #e9ecef;
            color: #495057;
        }
        
        .tab.active {
            color: #667eea;
            border-bottom: 3px solid #667eea;
            background: white;
        }
        
        .tab-content {
            display: none;
            padding: 30px;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .location-selector {
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            justify-content: center;
        }
        
        .location-option {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 15px 30px;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .location-option:hover {
            border-color: #667eea;
            background: #f8f9fa;
        }
        
        .location-option input[type="radio"]:checked + label {
            color: #667eea;
            font-weight: bold;
        }
        
        .date-selector {
            display: flex;
            gap: 15px;
            align-items: center;
            margin-bottom: 30px;
            justify-content: center;
        }
        
        .date-selector input {
            padding: 12px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 1em;
        }
        
        .btn {
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn-secondary {
            background: #6c757d;
            color: white;
        }
        
        .btn-secondary:hover {
            background: #5a6268;
        }
        
        .btn-danger {
            background: #dc3545;
            color: white;
        }
        
        .btn-danger:hover {
            background: #c82333;
        }
        
        .btn-success {
            background: #28a745;
            color: white;
        }
        
        .btn-success:hover {
            background: #218838;
        }
        
        .search-box {
            width: 100%;
            padding: 15px;
            margin-bottom: 20px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 1em;
        }
        
        .search-box:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .product-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .product-table th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            font-size: 0.9em;
        }
        
        .product-table td {
            padding: 8px 10px;
            border-bottom: 1px solid #dee2e6;
            font-size: 0.9em;
        }
        
        .product-table tr:hover {
            background: #f8f9fa;
        }
        
        .category-section {
            margin-bottom: 30px;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            overflow: hidden;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .category-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 20px;
            font-size: 1.1em;
            font-weight: bold;
            text-align: center;
        }
        
        .category-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .category-table thead th {
            background: #f1f3f5;
            color: #495057;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #dee2e6;
            font-size: 0.85em;
        }
        
        .category-table tbody td {
            padding: 6px 8px;
            border-bottom: 1px solid #e9ecef;
            font-size: 0.85em;
        }
        
        .category-table tbody tr:hover {
            background: #f8f9fa;
        }
        
        .categories-container {
            max-height: 65vh;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
        }
        
        .quantity-input {
            width: 70px;
            padding: 6px;
            border: 2px solid #dee2e6;
            border-radius: 5px;
            text-align: center;
            font-size: 0.9em;
        }
        
        .inventory-controls-panel {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        
        .control-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .control-group label {
            font-weight: 600;
            color: #495057;
            font-size: 0.9em;
        }
        
        .control-group select {
            padding: 8px 12px;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            font-size: 0.95em;
            background: white;
            cursor: pointer;
        }
        
        .control-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .edit-btn {
            background: #17a2b8;
            color: white;
            border: none;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.8em;
            margin-left: 5px;
        }
        
        .edit-btn:hover {
            background: #138496;
        }
        
        .row-controls {
            display: flex;
            gap: 5px;
            align-items: center;
        }
        
        /* Print Styles */
        @media print {
            .tabs, .btn, .location-selector, .date-selector, 
            .inventory-controls-panel, #statusMessage, .edit-btn, 
            .row-controls, .search-box {
                display: none !important;
            }
            
            body {
                font-size: 5pt;
                margin: 0;
                padding: 0;
            }
            
            .tab-content {
                display: block !important;
            }
            
            #inventory {
                display: block !important;
            }
            
            .categories-container {
                max-height: none !important;
                overflow: visible !important;
                padding: 0 !important;
                background: white !important;
                columns: 5;
                column-gap: 4px;
                column-fill: auto;
            }
            
            .category-section {
                page-break-inside: avoid;
                break-inside: avoid;
                margin-bottom: 2px;
                display: inline-block;
                width: 100%;
            }
            
            .category-header {
                font-size: 6pt;
                padding: 0.5px 2px;
                background: #e9ecef !important;
                color: black !important;
                font-weight: bold;
                margin-bottom: 0.5px;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
            
            .category-table {
                font-size: 4.5pt;
                width: 100%;
                border-collapse: collapse;
            }
            
            .category-table thead {
                display: none;
            }
            
            .category-table tbody td {
                padding: 0px 1px;
                font-size: 4pt;
                border: 0.5pt solid #ddd;
                line-height: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 50px;
            }
            
            /* Limit item description to ~20 characters */
            .category-table tbody td:first-child {
                max-width: 40px;
            }
            
            .category-table tbody tr {
                height: 8pt;
            }
            
            .quantity-input {
                width: 20px;
                padding: 0;
                font-size: 5pt;
                border: 0.5pt solid #000;
                height: 7pt;
            }
            
            .print-header {
                display: block !important;
                text-align: center;
                margin-bottom: 3px;
                border-bottom: 0.5pt solid #000;
                padding-bottom: 1px;
            }
            
            .print-header h2 {
                margin: 0 0 1px 0;
                font-size: 8pt;
            }
            
            .print-info {
                display: flex !important;
                justify-content: space-between;
                font-size: 5pt;
                margin: 0;
                font-weight: bold;
            }
            
            @page {
                size: letter;
                margin: 0.2in 0.15in;
            }
            
            /* Force specific column widths */
            .category-table tbody td:nth-child(1) {
                width: 50%;
            }
            
            .category-table tbody td:nth-child(2) {
                width: 30%;
            }
            
            .category-table tbody td:nth-child(3) {
                width: 20%;
                text-align: center;
            }
        }
        
        .print-header, .print-info {
            display: none;
        }
        
        /* Mobile Responsive Styles */
        @media (max-width: 768px) {
            body {
                padding: 0;
            }
            
            .container {
                border-radius: 0;
                min-height: 100vh;
            }
            
            .header {
                padding: 20px 10px;
            }
            
            .header h1 {
                font-size: 1.5em;
            }
            
            .header p {
                font-size: 0.9em;
            }
            
            .tabs {
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            
            .tab {
                padding: 15px 10px;
                font-size: 0.9em;
                min-width: 100px;
            }
            
            .tab-content {
                padding: 15px;
            }
            
            .location-selector {
                flex-direction: column;
                gap: 10px;
            }
            
            .location-option {
                width: 100%;
                justify-content: center;
            }
            
            .date-selector {
                flex-direction: column;
                gap: 10px;
            }
            
            .date-selector input,
            .date-selector button {
                width: 100%;
            }
            
            .inventory-controls-panel {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            
            .btn {
                width: 100%;
                margin-bottom: 10px;
            }
            
            .categories-container {
                max-height: none;
                padding: 10px;
            }
            
            .category-section {
                margin-bottom: 20px;
            }
            
            .category-header {
                font-size: 1em;
                padding: 10px;
            }
            
            .category-table {
                font-size: 0.75em;
            }
            
            .category-table thead th {
                padding: 8px 4px;
                font-size: 0.7em;
            }
            
            .category-table tbody td {
                padding: 8px 4px;
                font-size: 0.75em;
            }
            
            .quantity-input {
                width: 60px;
                padding: 8px;
                font-size: 1em;
                touch-action: manipulation;
            }
            
            .search-box {
                padding: 12px;
                font-size: 1em;
            }
            
            .product-table {
                display: block;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            
            .product-table thead th {
                padding: 10px 6px;
                font-size: 0.75em;
            }
            
            .product-table tbody td {
                padding: 8px 6px;
                font-size: 0.75em;
            }
            
            .inventory-list {
                grid-template-columns: 1fr;
            }
            
            .inventory-card {
                padding: 15px;
            }
            
            .card-actions {
                flex-direction: column;
            }
            
            .card-actions .btn {
                width: 100%;
            }
            
            .form-group input {
                padding: 12px;
                font-size: 1em;
            }
            
            .filter-controls {
                flex-direction: column;
            }
            
            .filter-controls select,
            .filter-controls button {
                width: 100%;
            }
            
            .edit-btn {
                padding: 6px 10px;
                font-size: 0.75em;
            }
            
            .row-controls {
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }
            
            .control-group select {
                padding: 10px;
                font-size: 1em;
            }
            
            /* Hide edit buttons on mobile by default */
            #showEditButtons {
                display: none;
            }
            
            .control-group label {
                font-size: 1em;
            }
        }
        
        .status-message {
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
            display: none;
        }
        
        .status-message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status-message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .inventory-list-container {
            margin-top: 20px;
        }
        
        .location-section {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            margin-bottom: 15px;
            overflow: hidden;
        }
        
        .location-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
        }
        
        .location-header:hover {
            background: linear-gradient(135deg, #5568d3 0%, #653a8b 100%);
        }
        
        .location-header h3 {
            margin: 0;
            font-size: 1.3em;
        }
        
        .location-badge {
            background: rgba(255, 255, 255, 0.2);
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.9em;
        }
        
        .inventory-items-list {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }
        
        .inventory-items-list.expanded {
            max-height: 2000px;
            transition: max-height 0.5s ease-in;
        }
        
        .inventory-item {
            border-bottom: 1px solid #e9ecef;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        
        .inventory-item:hover {
            background: #f8f9fa;
        }
        
        .inventory-item:last-child {
            border-bottom: none;
        }
        
        .inventory-info {
            flex: 1;
            display: grid;
            grid-template-columns: 150px 1fr;
            gap: 15px;
            align-items: center;
        }
        
        .inventory-date {
            font-weight: 600;
            color: #495057;
        }
        
        .inventory-meta {
            color: #6c757d;
            font-size: 0.95em;
        }
        
        .inventory-actions {
            display: flex;
            gap: 8px;
        }
        
        .inventory-actions button {
            padding: 6px 12px;
            font-size: 0.9em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #495057;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 1em;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
        }
        
        .modal-content {
            background: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 15px;
            max-width: 600px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        
        .upload-area {
            border: 2px dashed #667eea;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .upload-area:hover {
            background: #f8f9fa;
            border-color: #764ba2;
        }
        
        .filter-controls {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .filter-controls select {
            padding: 10px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 1em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>&#127978; Inventory Control System</h1>
            <p>Multi-Location Inventory Management</p>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('inventory')">Enter Inventory</button>
            <button class="tab" onclick="showTab('saved')">Saved Inventories</button>
            <button class="tab" onclick="showTab('orders')">Orders</button>
            <button class="tab" onclick="showTab('products')">Manage Products</button>
            <button class="tab" onclick="showTab('reports')">Reports</button>
        </div>
        
        <!-- Enter Inventory Tab -->
        <div id="inventory" class="tab-content active">
            <div class="location-selector">
                <div class="location-option">
                    <input type="radio" name="location" id="kingsville" value="Kingsville" checked>
                    <label for="kingsville">&#128205; Kingsville</label>
                </div>
                <div class="location-option">
                    <input type="radio" name="location" id="alice" value="Alice">
                    <label for="alice">&#128205; Alice</label>
                </div>
            </div>
            
            <div class="date-selector">
                <label for="inventoryDate">Select Date:</label>
                <input type="date" id="inventoryDate" />
                <button class="btn btn-secondary" onclick="setToday()">Today</button>
            </div>
            
            <!-- Inventory Controls Panel -->
            <div class="inventory-controls-panel">
                <div class="control-group">
                    <label for="searchBox">&#128269; Search:</label>
                    <input type="text" class="search-box" id="searchBox" placeholder="Search products..." onkeyup="filterProducts()">
                </div>
                
                <div class="control-group">
                    <label for="sortBy">&#128202; Sort By:</label>
                    <select id="sortBy" onchange="applySortAndDisplay()">
                        <option value="csv-order">CSV Order (Row Numbers)</option>
                        <option value="category">By Category</option>
                        <option value="product-name">By Product Name</option>
                        <option value="product-number">By Product Number</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label for="viewMode">&#128065; View:</label>
                    <select id="viewMode" onchange="applySortAndDisplay()">
                        <option value="list">Single List View (Shows Row Order)</option>
                        <option value="categorized">Categorized View (Groups by Category)</option>
                    </select>
                </div>
                
                <div class="control-group">
                    <label>
                        <input type="checkbox" id="showEditButtons" onchange="toggleEditButtons()" checked>
                        Show Edit Buttons
                    </label>
                </div>
            </div>
            
            <div style="text-align: center; margin: 20px 0;">
                <button class="btn btn-primary" onclick="saveInventory()">&#128190; Save Inventory</button>
                <button class="btn btn-secondary" onclick="loadInventory()">&#128194; Load Inventory</button>
                <button class="btn btn-success" onclick="printInventory()">&#128424; Print</button>
            </div>
            
            <div id="statusMessage" class="status-message"></div>
            
            <!-- Print Header (hidden on screen, visible in print) -->
            <div class="print-header">
                <h2>INVENTORY COUNT SHEET</h2>
                <div class="print-info">
                    <span>Location: <span id="printLocation"></span></span>
                    <span>Date: <span id="printDate"></span></span>
                </div>
            </div>
            
            <div class="categories-container" id="categoriesContainer">
                <!-- Categories will be dynamically generated here -->
            </div>
        </div>
        
        <!-- Saved Inventories Tab -->
        <div id="saved" class="tab-content">
            <h2>Saved Inventories</h2>
            
            <!-- Upload Inventory Section -->
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 30px; border-left: 5px solid #667eea;">
                <h3 style="margin-top: 0;">&#128228; Upload Inventory from CSV</h3>
                <p style="margin-bottom: 15px; color: #6c757d;">Upload a CSV file with Product Number and Quantity columns to import inventory for a specific date.</p>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="uploadLocation" style="display: block; margin-bottom: 5px; font-weight: 600;">Location:</label>
                        <select id="uploadLocation" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; font-size: 1em;">
                            <option value="Kingsville">Kingsville</option>
                            <option value="Alice">Alice</option>
                        </select>
                    </div>
                    
                    <div>
                        <label for="uploadInventoryDate" style="display: block; margin-bottom: 5px; font-weight: 600;">Inventory Date:</label>
                        <input type="date" id="uploadInventoryDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; font-size: 1em;" />
                    </div>
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label for="uploadInventoryCSV" class="btn btn-primary" style="cursor: pointer; display: inline-block;">&#128193; Select CSV File</label>
                    <input type="file" id="uploadInventoryCSV" accept=".csv" style="display: none;" onchange="uploadInventoryCSV()">
                    <a href="/api/inventory/sample-csv" class="btn btn-success" style="display: inline-block; text-decoration: none; margin-left: 10px;">&#11015; Download Sample Template</a>
                    <span id="selectedFileName" style="margin-left: 15px; color: #6c757d; font-style: italic;"></span>
                </div>
                
                <div id="uploadStatus" style="padding: 10px; border-radius: 5px; margin-top: 10px; display: none;"></div>
                
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; font-weight: 600; color: #667eea;">&#8505; CSV Format Requirements</summary>
                    <div style="margin-top: 10px; padding: 15px; background: white; border-radius: 5px;">
                        <p style="margin: 5px 0;"><strong>Required columns:</strong></p>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li><strong>Product Number</strong> (or Product #, ProductNumber, SKU) - Required</li>
                            <li><strong>Quantity</strong> (or Qty, Count) - Required</li>
                            <li><strong>Product Name</strong> (or Description, Name) - Optional</li>
                        </ul>
                        <p style="margin: 10px 0;"><strong>Example CSV (3 columns):</strong></p>
                        <pre style="background: #f8f9fa; padding: 10px; border-radius: 5px; overflow-x: auto;">Product #,Product Name,Quantity
12345,Coca-Cola 12oz,10
67890,Pepsi 20oz,25
11111,Water Bottle,5</pre>
                        <p style="margin: 5px 0; font-size: 0.9em;"><em>Note: 2-column format (Product #, Quantity) also works!</em></p>
                        <p style="margin: 10px 0; color: #0c5460; background: #d1ecf1; padding: 10px; border-radius: 5px;">
                            <strong>&#128161; Tip:</strong> Click the "Download Sample Template" button above to get a CSV file pre-filled with all your products in the correct order. Just add quantities and upload!
                        </p>
                        <p style="margin: 10px 0; color: #856404; background: #fff3cd; padding: 10px; border-radius: 5px;">
                            <strong>Note:</strong> Only products that exist in your product list will be imported. Products not found will be reported.
                        </p>
                    </div>
                </details>
            </div>
            
            <h3 style="margin-top: 30px;">&#128203; Saved Inventories List</h3>
            <div class="filter-controls">
                <button class="btn btn-secondary" onclick="loadInventoriesList()">&#128260; Refresh</button>
                <button class="btn btn-secondary" onclick="toggleAllLocations()">&#128194; Expand/Collapse All</button>
            </div>
            
            <div id="inventoriesList" class="inventory-list-container"></div>
        </div>
        
        <!-- Manage Products Tab -->
        <div id="products" class="tab-content">
            <h2>Product List Management</h2>
            
            <div style="margin-bottom: 30px;">
                <button class="btn btn-primary" onclick="showAddProductForm()">&#10133; Add Product</button>
                <button class="btn btn-secondary" onclick="viewProductHistory()">&#128220; View History</button>
                <label for="uploadCSV" class="btn btn-success" style="cursor: pointer;">&#128228; Upload CSV</label>
                <input type="file" id="uploadCSV" accept=".csv" style="display: none;" onchange="uploadCSV()">
            </div>
            
            <div style="background: #e8f4fd; padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #2196f3;">
                <h4 style="margin-top: 0; color: #1976d2;">&#128161; Case Count Feature</h4>
                <p style="margin: 5px 0; color: #424242;">
                    <strong>Case Count checkbox:</strong> Use this to mark products that should NOT be multiplied by package size when importing invoices.
                </p>
                <p style="margin: 5px 0; color: #424242;">
                    &#10004; <strong>Checked (Case Count):</strong> Invoice quantity stays as-is (e.g., 5 cases = 5)<br>
                    &#10006; <strong>Unchecked (Regular):</strong> Invoice quantity multiplied by package size (e.g., 5 cases &#215; 6 units = 30)
                </p>
            </div>
            
            <div id="addProductForm" style="display: none; background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>Add New Product</h3>
                <div class="form-group">
                    <label for="newProductNum">Product Number:</label>
                    <input type="text" id="newProductNum" />
                </div>
                <div class="form-group">
                    <label for="newDescription">Description:</label>
                    <input type="text" id="newDescription" />
                </div>
                <div class="form-group">
                    <label for="newBrand">Brand:</label>
                    <input type="text" id="newBrand" />
                </div>
                <div class="form-group">
                    <label for="newPackageSize">Package Size:</label>
                    <input type="text" id="newPackageSize" />
                </div>
                <div class="form-group">
                    <label for="newGroupName">Category/Group Name:</label>
                    <input type="text" id="newGroupName" placeholder="e.g., BEVERAGES, SNACKS" />
                </div>
                <div class="form-group">
                    <label for="insertPosition">Insert at Position #:</label>
                    <input type="number" id="insertPosition" min="1" placeholder="Leave blank to add at end" />
                    <small style="display: block; color: #6c757d; margin-top: 5px;">Enter row number where you want to insert this product (1 = first position)</small>
                </div>
                <button class="btn btn-primary" onclick="addProduct()">Save Product</button>
                <button class="btn btn-secondary" onclick="hideAddProductForm()">Cancel</button>
            </div>
            
            <label for="productSearchBox" style="display: none;">Search Products</label>
            <input type="text" class="search-box" id="productSearchBox" placeholder="&#128269; Search products..." onkeyup="filterProductList()">
            
            <table class="product-table" id="productManagementTable">
                <thead>
                    <tr>
                        <th style="width: 50px;">#</th>
                        <th>Category</th>
                        <th>Product #</th>
                        <th>Description</th>
                        <th>Brand</th>
                        <th>Package Size</th>
                        <th style="width: 110px;" title="Mark as Case Count (won't multiply by package size on invoice import)">Case Count</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="productManagementTableBody">
                </tbody>
            </table>
        </div>
        
        <!-- Orders Tab -->
        <div id="orders" class="tab-content">
            <h2>Order Management</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                <h3>Order Schedule:</h3>
                <p><strong>Kingsville:</strong> Sunday, Tuesday, Thursday</p>
                <p><strong>Alice:</strong> Sunday, Wednesday</p>
            </div>
            
            <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #ffc107;">
                <h3 style="margin-top: 0;">&#128230; Understanding Package Sizes & Inventory Units</h3>
                <p style="margin: 0 0 10px 0;"><strong>Important:</strong> All inventory quantities represent full units based on the Package Size:</p>
                <ul style="margin: 5px 0; padding-left: 20px;">
                    <li><strong>60 EA</strong> → Inventory of 1 = 1 unit of 60 items</li>
                    <li><strong>4/5 LB</strong> → Inventory of 1 = 1 unit (4 pieces at 5 lbs each)</li>
                    <li><strong>12/6/3.5 OZ</strong> → Inventory of 1 = 1 unit (12 cases with 6 items per case at 3.5 oz each)</li>
                </ul>
                <p style="margin: 10px 0 0 0; font-style: italic;">When entering inventory, always count complete units as shown in the Package Size column.</p>
            </div>
            
            <div style="margin-bottom: 30px;">
                <h3>Upload Order Estimate</h3>
                <div class="form-group">
                    <label for="orderLocation">Location:</label>
                    <select id="orderLocation" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;">
                        <option value="Kingsville">Kingsville</option>
                        <option value="Alice">Alice</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="orderDate">Order Date:</label>
                    <input type="date" id="orderDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />
                </div>
                <label for="uploadOrderCSV" class="btn btn-success" style="cursor: pointer; display: inline-block;">&#128228; Upload Order CSV</label>
                <input type="file" id="uploadOrderCSV" accept=".csv" style="display: none;" onchange="uploadOrderCSV()">
            </div>
            
            <!-- Upload Invoice from Food Provider -->
            <div style="background: #e8f5e9; padding: 20px; border-radius: 10px; margin-bottom: 30px; border-left: 5px solid #4caf50;">
                <h3 style="margin-top: 0;">&#128179; Import Invoice from Food Provider</h3>
                <p style="margin-bottom: 15px; color: #2e7d32;">Upload your delivery invoice CSV to automatically record what was received.</p>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label for="invoiceLocation" style="display: block; margin-bottom: 5px; font-weight: 600;">Location:</label>
                        <select id="invoiceLocation" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; font-size: 1em;">
                            <option value="Kingsville">Kingsville</option>
                            <option value="Alice">Alice</option>
                        </select>
                    </div>
                    
                    <div>
                        <label for="deliveryDate" style="display: block; margin-bottom: 5px; font-weight: 600;">Delivery Date:</label>
                        <input type="date" id="deliveryDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; font-size: 1em;" />
                    </div>
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label for="uploadInvoiceCSV" class="btn btn-success" style="cursor: pointer; display: inline-block;">&#128206; Select Invoice CSV</label>
                    <input type="file" id="uploadInvoiceCSV" accept=".csv" style="display: none;" onchange="uploadInvoiceCSV()">
                    <span id="invoiceFileName" style="margin-left: 15px; color: #2e7d32; font-style: italic;"></span>
                </div>
                
                <div id="invoiceUploadStatus" style="padding: 10px; border-radius: 5px; margin-top: 10px; display: none;"></div>
                
                <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; font-weight: 600; color: #2e7d32;">&#8505; Invoice Format Requirements</summary>
                    <div style="margin-top: 10px; padding: 15px; background: white; border-radius: 5px;">
                        <p style="margin: 5px 0;"><strong>Required columns:</strong></p>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li><strong>ProductNumber</strong> - Must match products in your inventory</li>
                            <li><strong>QtyShip</strong> - Quantity shipped/delivered</li>
                        </ul>
                        <p style="margin: 10px 0;"><strong>Optional columns (for reference):</strong></p>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li>ProductDescription</li>
                            <li>Product Label</li>
                            <li>PackingSize</li>
                            <li>UnitPrice</li>
                        </ul>
                        <p style="margin: 10px 0; color: #2e7d32; background: #e8f5e9; padding: 10px; border-radius: 5px;">
                            <strong>&#128161; Tip:</strong> This imports your actual delivery invoice from US Foods or your food provider. The system will match ProductNumber with your inventory and record the quantities shipped.
                        </p>
                    </div>
                </details>
            </div>
            
            <!-- Invoice Import History Section -->
            <div style="margin-bottom: 30px; background: #e7f3ff; padding: 20px; border-radius: 10px; border: 2px solid #2196f3;">
                <h3 style="margin-top: 0;">&#128221; Invoice Import History</h3>
                <p style="color: #1565c0;">View and manage all imported invoices. You can review details or reverse imports if needed.</p>
                
                <button class="btn" style="background: #2196f3; color: white; margin-bottom: 15px;" onclick="loadInvoiceHistory()">
                    &#128260; Refresh Import Log
                </button>
                
                <div id="invoiceHistoryContent" style="background: white; padding: 15px; border-radius: 8px; margin-top: 15px;">
                    <p style="color: #999;">Click "Refresh Import Log" to view invoice history</p>
                </div>
            </div>
            
            <div style="margin-bottom: 30px;">
                <h3>Calculate Official Order</h3>
                <p style="color: #6c757d; margin-bottom: 15px;">Formula: Official Order = Order Estimate - Current Inventory</p>
                <div class="form-group">
                    <label for="calcLocation">Location:</label>
                    <select id="calcLocation" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;">
                        <option value="Kingsville">Kingsville</option>
                        <option value="Alice">Alice</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="calcOrderDate">Order Date:</label>
                    <input type="date" id="calcOrderDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />
                </div>
                <div class="form-group">
                    <label for="calcInventoryDate">Inventory Date:</label>
                    <input type="date" id="calcInventoryDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />
                </div>
                <button class="btn btn-primary" onclick="calculateOrder()">&#129526; Calculate Official Order</button>
                <button class="btn btn-success" onclick="exportOfficialOrder()">&#128229; Export to CSV</button>
            </div>
            
            <div id="orderResults" style="display: none; background: #f8f9fa; padding: 20px; border-radius: 10px;">
                <h3>Order Calculation Results</h3>
                <div id="orderSummary"></div>
                <div id="orderDetails" style="max-height: 400px; overflow-y: auto; margin-top: 20px;"></div>
            </div>
        </div>
        
        <!-- Reports Tab -->
        <div id="reports" class="tab-content">
            <h2>Reports & Analytics</h2>
            
            <div style="margin-bottom: 30px;">
                <h3>Product Activity Report</h3>
                <p style="color: #6c757d;">View how many times each product was inventoried and ordered within a date range.</p>
                
                <div class="form-group">
                    <label for="reportLocation">Location:</label>
                    <select id="reportLocation" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;">
                        <option value="all">All Locations</option>
                        <option value="Kingsville">Kingsville</option>
                        <option value="Alice">Alice</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="reportStartDate">Start Date:</label>
                    <input type="date" id="reportStartDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />
                </div>
                
                <div class="form-group">
                    <label for="reportEndDate">End Date:</label>
                    <input type="date" id="reportEndDate" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />
                </div>
                
                <button class="btn btn-primary" onclick="generateProductActivityReport()">&#128202; Generate Product Activity Report</button>
                <button class="btn btn-secondary" onclick="exportReportToCSV()" id="exportReportBtn" style="display: none;">&#128229; Export to CSV</button>
            </div>
            
            <div id="reportContent"></div>
        </div>
    </div>
    
    <script>
        let currentProducts = [];
        let allInventories = [];
        let lastCalculatedOrder = null;
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            setToday();
            loadProducts();
            loadInventoriesList();
        });
        
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
            
            // Load data if needed
            if (tabName === 'saved') {
                loadInventoriesList();
            } else if (tabName === 'products') {
                displayProductList();
            }
        }
        
        function setToday() {
            const today = new Date().toISOString().split('T')[0];
            document.getElementById('inventoryDate').value = today;
        }
        
        function getSelectedLocation() {
            return document.querySelector('input[name="location"]:checked').value;
        }
        
        function loadProducts() {
            console.log('Loading products...');
            // Add timestamp to prevent caching
            fetch('/api/products?t=' + new Date().getTime())
                .then(response => response.json())
                .then(data => {
                    console.log('Products loaded:', data.length, 'items');
                    console.log('First 3 products:', data.slice(0, 3));
                    currentProducts = data;
                    displayProducts();
                })
                .catch(error => {
                    console.error('Error loading products:', error);
                    const container = document.getElementById('categoriesContainer');
                    if (container) {
                        container.innerHTML = '<div style="text-align: center; padding: 40px; color: #dc3545;"><h3>Error Loading Products</h3><p>' + error + '</p></div>';
                    }
                });
        }
        
        function displayProducts() {
            const container = document.getElementById('categoriesContainer');
            if (!container) {
                console.error('Categories container not found!');
                return;
            }
            
            container.innerHTML = '';
            
            if (!currentProducts || currentProducts.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #6c757d;"><h3>No products loaded</h3><p>Please add products or upload a CSV file in the Manage Products tab.</p></div>';
                return;
            }
            
            console.log('Displaying products, total:', currentProducts.length);
            console.log('Last product:', currentProducts[currentProducts.length - 1]);
            
            const viewMode = document.getElementById('viewMode').value;
            const sortBy = document.getElementById('sortBy').value;
            const showEdit = document.getElementById('showEditButtons').checked;
            
            console.log('View Mode:', viewMode, 'Sort By:', sortBy);
            
            if (viewMode === 'list') {
                displayAsList(sortBy, showEdit);
            } else {
                displayAsCategorized(sortBy, showEdit);
            }
        }
        
        function displayAsCategorized(sortBy, showEdit) {
            const container = document.getElementById('categoriesContainer');
            
            // Preserve CSV order - track order of first appearance for each category
            const categoryOrder = [];
            const categories = {};
            
            currentProducts.forEach(product => {
                const groupName = product['Group Name'] || 'OTHER';
                if (!categories[groupName]) {
                    categories[groupName] = [];
                    categoryOrder.push(groupName); // Track order as we encounter categories
                }
                categories[groupName].push(product);
            });
            
            console.log('Categories found:', Object.keys(categories));
            
            // Only sort products within each category if user chose a sort option
            if (sortBy === 'product-name') {
                Object.keys(categories).forEach(categoryName => {
                    categories[categoryName].sort((a, b) => 
                        (a['Product Description'] || '').localeCompare(b['Product Description'] || '')
                    );
                });
            } else if (sortBy === 'product-number') {
                Object.keys(categories).forEach(categoryName => {
                    categories[categoryName].sort((a, b) => 
                        (a['Product Number'] || '').localeCompare(b['Product Number'] || '')
                    );
                });
            }
            // If sortBy is 'category' (default), maintain CSV order - no sorting needed
            
            // Display each category in the order they appear in CSV
            categoryOrder.forEach(categoryName => {
                const categoryProducts = categories[categoryName];
                
                const categoryDiv = document.createElement('div');
                categoryDiv.className = 'category-section';
                
                let tableHTML = '<div class="category-header">' + categoryName.toUpperCase() + '</div>';
                tableHTML += '<table class="category-table">';
                tableHTML += '<thead><tr>';
                tableHTML += '<th style="width: 35%">Item</th>';
                tableHTML += '<th style="width: 25%">Product Size</th>';
                tableHTML += '<th style="width: 15%">Inventory</th>';
                if (showEdit) {
                    tableHTML += '<th style="width: 25%">Actions</th>';
                }
                tableHTML += '</tr></thead><tbody>';
                
                categoryProducts.forEach(product => {
                    tableHTML += '<tr>';
                    tableHTML += '<td>' + product['Product Description'] + '</td>';
                    tableHTML += '<td>' + product['Product Package Size'] + '</td>';
                    tableHTML += '<td><input type="number" class="quantity-input" ';
                    tableHTML += 'id="qty_' + product['Product Number'] + '" ';
                    tableHTML += 'value="0" min="0" step="0.25" /></td>';
                    
                    if (showEdit) {
                        tableHTML += '<td class="row-controls">';
                        tableHTML += '<button class="edit-btn quick-edit-btn" data-product-id="' + product['Product Number'] + '">&#9999; Edit</button>';
                        tableHTML += '<span style="font-size: 0.75em; color: #6c757d;">ID: ' + product['Product Number'] + '</span>';;
                        tableHTML += '</td>';
                    }
                    
                    tableHTML += '</tr>';
                });
                
                tableHTML += '</tbody></table>';
                categoryDiv.innerHTML = tableHTML;
                container.appendChild(categoryDiv);
            });
            
            // Add event delegation for edit buttons
            container.addEventListener('click', function(e) {
                if (e.target.classList.contains('quick-edit-btn')) {
                    const productId = e.target.getAttribute('data-product-id');
                    quickEditProduct(productId);
                }
            });
        }
        
        function displayAsList(sortBy, showEdit) {
            const container = document.getElementById('categoriesContainer');
            
            // Create a copy and sort (or keep original order)
            let sortedProducts = [...currentProducts];
            
            console.log('displayAsList - sortBy:', sortBy, 'Original count:', currentProducts.length);
            
            if (sortBy === 'product-name') {
                sortedProducts.sort((a, b) => 
                    (a['Product Description'] || '').localeCompare(b['Product Description'] || '')
                );
            } else if (sortBy === 'product-number') {
                sortedProducts.sort((a, b) => 
                    (a['Product Number'] || '').localeCompare(b['Product Number'] || '')
                );
            } else if (sortBy === 'category') {
                sortedProducts.sort((a, b) => {
                    const catCompare = (a['Group Name'] || 'OTHER').localeCompare(b['Group Name'] || 'OTHER');
                    if (catCompare !== 0) return catCompare;
                    return (a['Product Description'] || '').localeCompare(b['Product Description'] || '');
                });
            }
            // else if sortBy === 'csv-order', keep original order (no sorting)
            
            console.log('After sorting, count:', sortedProducts.length, 'Last item:', sortedProducts[sortedProducts.length - 1]);
            
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'category-section';
            
            let tableHTML = '<div class="category-header">ALL PRODUCTS</div>';
            tableHTML += '<table class="category-table">';
            tableHTML += '<thead><tr>';
            tableHTML += '<th style="width: 20%">Category</th>';
            tableHTML += '<th style="width: 30%">Item</th>';
            tableHTML += '<th style="width: 20%">Product Size</th>';
            tableHTML += '<th style="width: 10%">Inventory</th>';
            if (showEdit) {
                tableHTML += '<th style="width: 20%">Actions</th>';
            }
            tableHTML += '</tr></thead><tbody>';
            
            sortedProducts.forEach(product => {
                tableHTML += '<tr>';
                tableHTML += '<td><span style="background: #e9ecef; padding: 2px 6px; border-radius: 3px; font-size: 0.75em;">' + (product['Group Name'] || 'OTHER') + '</span></td>';
                tableHTML += '<td>' + product['Product Description'] + '</td>';
                tableHTML += '<td>' + product['Product Package Size'] + '</td>';
                tableHTML += '<td><input type="number" class="quantity-input" ';
                tableHTML += 'id="qty_' + product['Product Number'] + '" ';
                tableHTML += 'value="0" min="0" step="0.25" /></td>';
                
                if (showEdit) {
                    tableHTML += '<td class="row-controls">';
                    tableHTML += '<button class="edit-btn quick-edit-btn" data-product-id="' + product['Product Number'] + '">&#9999; Edit</button>';
                    tableHTML += '<span style="font-size: 0.75em; color: #6c757d;">ID: ' + product['Product Number'] + '</span>';
                    tableHTML += '</td>';
                }
                
                tableHTML += '</tr>';
            });
            
            tableHTML += '</tbody></table>';
            categoryDiv.innerHTML = tableHTML;
            container.appendChild(categoryDiv);
            
            // Add event delegation for edit buttons
            container.addEventListener('click', function(e) {
                if (e.target.classList.contains('quick-edit-btn')) {
                    const productId = e.target.getAttribute('data-product-id');
                    quickEditProduct(productId);
                }
            });
        }
        
        function applySortAndDisplay() {
            displayProducts();
        }
        
        function toggleEditButtons() {
            displayProducts();
        }
        
        function quickEditProduct(productNum) {
            const product = currentProducts.find(p => p['Product Number'] === productNum);
            if (!product) {
                alert('Product not found');
                return;
            }
            
            const newDesc = prompt('Edit Description:', product['Product Description']);
            if (newDesc === null) return;
            
            const newBrand = prompt('Edit Brand:', product['Product Brand']);
            if (newBrand === null) return;
            
            const newSize = prompt('Edit Package Size:', product['Product Package Size']);
            if (newSize === null) return;
            
            const newGroup = prompt('Edit Category/Group:', product['Group Name']);
            if (newGroup === null) return;
            
            fetch('/api/products/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    product_number: productNum,
                    description: newDesc,
                    brand: newBrand,
                    package_size: newSize,
                    group_name: newGroup
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    loadProducts();
                    showMessage('Product updated successfully', 'success');
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => console.error('Error updating product:', error));
        }
        
        function filterProducts() {
            const searchTerm = document.getElementById('searchBox').value.toLowerCase();
            const sections = document.querySelectorAll('.category-section');
            
            sections.forEach(section => {
                const rows = section.querySelectorAll('tbody tr');
                let hasVisibleRows = false;
                
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    const isVisible = text.includes(searchTerm);
                    row.style.display = isVisible ? '' : 'none';
                    if (isVisible) hasVisibleRows = true;
                });
                
                // Hide entire category if no rows match
                section.style.display = hasVisibleRows ? '' : 'none';
            });
        }
        
        function printInventory() {
            const location = getSelectedLocation();
            const date = document.getElementById('inventoryDate').value || 'Not Set';
            
            // Update print header
            document.getElementById('printLocation').textContent = location;
            document.getElementById('printDate').textContent = date;
            
            // Trigger print dialog
            window.print();
        }
        
        function saveInventory() {
            const location = getSelectedLocation();
            const date = document.getElementById('inventoryDate').value;
            
            if (!date) {
                showMessage('Please select a date', 'error');
                return;
            }
            
            const inventory = {};
            currentProducts.forEach(product => {
                const qty = document.getElementById('qty_' + product['Product Number']).value;
                if (qty > 0) {
                    inventory[product['Product Number']] = parseInt(qty);
                }
            });
            
            fetch('/api/inventory/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({location, date, inventory})
            })
            .then(response => response.json())
            .then(data => {
                showMessage(data.message, 'success');
            })
            .catch(error => {
                showMessage('Error saving inventory', 'error');
            });
        }
        
        function loadInventory() {
            const location = getSelectedLocation();
            const date = document.getElementById('inventoryDate').value;
            
            if (!date) {
                showMessage('Please select a date', 'error');
                return;
            }
            
            fetch('/api/inventory/' + location + '/' + date)
                .then(response => response.json())
                .then(data => {
                    // Reset all quantities
                    currentProducts.forEach(product => {
                        document.getElementById('qty_' + product['Product Number']).value = 0;
                    });
                    
                    // Set loaded quantities
                    for (let productNum in data) {
                        const input = document.getElementById('qty_' + productNum);
                        if (input) {
                            input.value = data[productNum];
                        }
                    }
                    
                    showMessage('Inventory loaded successfully', 'success');
                })
                .catch(error => {
                    showMessage('Error loading inventory', 'error');
                });
        }
        
        function loadInventoriesList() {
            fetch('/api/inventory/list')
                .then(response => response.json())
                .then(data => {
                    allInventories = data;
                    displayInventories(data);
                })
                .catch(error => console.error('Error loading inventories:', error));
        }
        
        function displayInventories(inventories) {
            const container = document.getElementById('inventoriesList');
            container.innerHTML = '';
            
            if (inventories.length === 0) {
                container.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 40px;">No saved inventories found</p>';
                return;
            }
            
            // Group inventories by location
            const byLocation = {};
            inventories.forEach(inv => {
                if (!byLocation[inv.location]) {
                    byLocation[inv.location] = [];
                }
                byLocation[inv.location].push(inv);
            });
            
            // Sort dates within each location (newest first)
            Object.keys(byLocation).forEach(location => {
                byLocation[location].sort((a, b) => new Date(b.date) - new Date(a.date));
            });
            
            // Create sections for each location
            Object.keys(byLocation).sort().forEach(location => {
                const section = document.createElement('div');
                section.className = 'location-section';
                
                // Location header
                const header = document.createElement('div');
                header.className = 'location-header';
                header.innerHTML = '<h3>&#128205; ' + location + '</h3>' +
                    '<span class="location-badge">' + byLocation[location].length + ' inventories</span>';
                header.onclick = () => toggleLocationSection(location);
                
                // Items list
                const itemsList = document.createElement('div');
                itemsList.className = 'inventory-items-list';
                itemsList.id = 'location-' + location.replace(/\\s+/g, '-');
                
                byLocation[location].forEach(inv => {
                    const item = document.createElement('div');
                    item.className = 'inventory-item';
                    item.innerHTML = '<div class="inventory-info">' +
                        '<div class="inventory-date">&#128197; ' + inv.date + '</div>' +
                        '<div class="inventory-meta">' + inv.item_count + ' items</div>' +
                        '</div>' +
                        '<div class="inventory-actions">' +
                        '<button class="btn btn-primary view-inv-btn" onclick="viewInventory(&quot;' + inv.location + '&quot;, &quot;' + inv.date + '&quot;)">&#128065; View</button>' +
                        '<button class="btn btn-success export-inv-btn" onclick="exportInventory(&quot;' + inv.location + '&quot;, &quot;' + inv.date + '&quot;)">&#128229; Export</button>' +
                        '<button class="btn btn-danger delete-inv-btn" onclick="deleteInventoryConfirm(&quot;' + inv.location + '&quot;, &quot;' + inv.date + '&quot;)">&#128465;</button>' +
                        '</div>';
                    itemsList.appendChild(item);
                });
                
                section.appendChild(header);
                section.appendChild(itemsList);
                container.appendChild(section);
            });
        }
        
        function toggleLocationSection(location) {
            const itemsList = document.getElementById('location-' + location.replace(/\\s+/g, '-'));
            itemsList.classList.toggle('expanded');
        }
        
        function toggleAllLocations() {
            const allLists = document.querySelectorAll('.inventory-items-list');
            const anyExpanded = Array.from(allLists).some(list => list.classList.contains('expanded'));
            
            allLists.forEach(list => {
                if (anyExpanded) {
                    list.classList.remove('expanded');
                } else {
                    list.classList.add('expanded');
                }
            });
        }
        
        function deleteInventoryConfirm(location, date) {
            if (!confirm('Delete inventory for ' + location + ' on ' + date + '?')) return;
            deleteInventory(location, date);
        }
        
        function viewInventory(location, date) {
            // Switch to inventory tab and load
            document.querySelector('input[value="' + location + '"]').checked = true;
            document.getElementById('inventoryDate').value = date;
            showTab('inventory');
            loadInventory();
        }
        
        function exportInventory(location, date) {
            window.location.href = '/api/inventory/export/' + location + '/' + date;
        }
        
        function deleteInventory(location, date) {
            if (!confirm('Delete inventory for ' + location + ' on ' + date + '?')) return;
            
            fetch('/api/inventory/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({location, date})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadInventoriesList();
                    showMessage(data.message, 'success');
                }
            })
            .catch(error => console.error('Error deleting inventory:', error));
        }
        
        function generateSummaryReport() {
            fetch('/api/reports/summary')
                .then(response => response.json())
                .then(data => {
                    let html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">';
                    html += '<h3>Inventory Summary by Location</h3>';
                    
                    for (let location in data) {
                        html += '<div style="margin: 20px 0; padding: 15px; background: white; border-radius: 8px;">';
                        html += '<h4>' + location + '</h4>';
                        html += '<p><strong>Total Inventories:</strong> ' + data[location].total_inventories + '</p>';
                        html += '<p><strong>Dates:</strong> ' + data[location].dates.join(', ') + '</p>';
                        html += '</div>';
                    }
                    
                    html += '</div>';
                    document.getElementById('reportContent').innerHTML = html;
                })
                .catch(error => console.error('Error generating report:', error));
        }
        
        let currentReportData = null;
        
        function generateProductActivityReport() {
            const location = document.getElementById('reportLocation').value;
            const startDate = document.getElementById('reportStartDate').value;
            const endDate = document.getElementById('reportEndDate').value;
            
            if (!startDate || !endDate) {
                alert('Please select start and end dates');
                return;
            }
            
            if (startDate > endDate) {
                alert('Start date must be before end date');
                return;
            }
            
            fetch(`/api/reports/product-activity?location=${location}&start_date=${startDate}&end_date=${endDate}`)
                .then(response => response.json())
                .then(data => {
                    if (!data.success) {
                        alert('Error: ' + data.message);
                        return;
                    }
                    
                    currentReportData = data;
                    displayProductActivityReport(data);
                    document.getElementById('exportReportBtn').style.display = 'inline-block';
                })
                .catch(error => {
                    console.error('Error generating report:', error);
                    alert('Error generating report');
                });
        }
        
        function displayProductActivityReport(data) {
            let html = '<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">';
            html += '<h3>Product Activity Report</h3>';
            html += '<p><strong>Date Range:</strong> ' + data.date_range.start + ' to ' + data.date_range.end + '</p>';
            html += '<p><strong>Location:</strong> ' + (data.location === 'all' ? 'All Locations' : data.location) + '</p>';
            html += '<p><strong>Total Products:</strong> ' + data.total_products + '</p>';
            
            // Legend for colors
            html += '<div style="display: flex; gap: 20px; margin-top: 15px; padding: 10px; background: white; border-radius: 5px;">';
            html += '<div><span style="display: inline-block; width: 20px; height: 20px; background: #e3f2fd; border: 1px solid #90caf9; vertical-align: middle;"></span> <strong>Inventory Count</strong></div>';
            html += '<div><span style="display: inline-block; width: 20px; height: 20px; background: #fff3e0; border: 1px solid #ffb74d; vertical-align: middle;"></span> <strong>Order/Delivery</strong></div>';
            html += '</div>';
            
            if (data.products.length === 0) {
                html += '<p style="color: #6c757d; margin-top: 20px;">No activity found for the selected date range.</p>';
            } else {
                // Keep products in CSV order (no sorting)
                
                // Collect all unique dates and locations from both inventory and orders
                let allDates = new Map(); // Map of date -> {location -> type (inventory/order)}
                
                data.products.forEach(product => {
                    if (product.inventory_dates) {
                        product.inventory_dates.forEach(inv => {
                            if (!allDates.has(inv.date)) {
                                allDates.set(inv.date, new Map());
                            }
                            if (!allDates.get(inv.date).has(inv.location)) {
                                allDates.get(inv.date).set(inv.location, new Set());
                            }
                            allDates.get(inv.date).get(inv.location).add('inventory');
                        });
                    }
                    if (product.order_dates) {
                        product.order_dates.forEach(ord => {
                            if (!allDates.has(ord.date)) {
                                allDates.set(ord.date, new Map());
                            }
                            if (!allDates.get(ord.date).has(ord.location)) {
                                allDates.get(ord.date).set(ord.location, new Set());
                            }
                            allDates.get(ord.date).get(ord.location).add('order');
                        });
                    }
                });
                
                // Sort dates
                let sortedDates = Array.from(allDates.keys()).sort();
                
                html += '<div style="overflow-x: auto; margin-top: 20px;">';
                html += '<table style="width: 100%; border-collapse: collapse; background: white;">';
                html += '<thead><tr style="background: #6f42c1; color: white;">';
                html += '<th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Product #</th>';
                html += '<th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Description</th>';
                html += '<th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Brand</th>';
                html += '<th style="padding: 12px; text-align: left; border: 1px solid #dee2e6;">Package Size</th>';
                html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #28a745;" title="Beginning Inventory">Begin Inv</th>';
                html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #ffc107;" title="Total Orders">Total Orders</th>';
                html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #dc3545;" title="Ending Inventory">End Inv</th>';
                html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #007bff; font-weight: bold;" title="Usage = Begin + Orders - End">USAGE</th>';
                html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #6f42c1; color: white; font-weight: bold;" title="Cases Required (Usage ÷ Package Size)">Cases Required</th>';
                
                // Add column for each date/location combo
                sortedDates.forEach(date => {
                    let locationTypes = allDates.get(date);
                    let locations = Array.from(locationTypes.keys()).sort();
                    locations.forEach(loc => {
                        let types = locationTypes.get(loc);
                        let isOrder = types.has('order');
                        let isInventory = types.has('inventory');
                        let label = isInventory && isOrder ? 'INV+ORD' : isOrder ? 'ORDER' : 'INV';
                        html += '<th style="padding: 12px; text-align: center; border: 1px solid #dee2e6; background: #8e70c7;">' + date + '<br>(' + loc + ')<br><small>' + label + '</small></th>';
                    });
                });
                
                html += '</tr></thead><tbody>';
                
                data.products.forEach(product => {
                    html += '<tr style="border-bottom: 1px solid #dee2e6;">';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6;">' + product.product_number;
                    // Add Case Count badge if applicable
                    if (product.case_count_type && product.case_count_type.toUpperCase() === 'YES') {
                        html += '<br><span style="background: #ffc107; color: #000; padding: 2px 6px; border-radius: 3px; font-size: 0.75em; font-weight: bold;">CASE COUNT</span>';
                    }
                    html += '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6;">' + product.description + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6;">' + product.brand + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6;">' + product.package_size + '</td>';
                    
                    // Add usage calculation columns
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #d4edda; font-weight: bold;">' + 
                        (product.beginning_inventory || 0) + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #fff3cd; font-weight: bold;">' + 
                        (product.total_orders || 0) + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #f8d7da; font-weight: bold;">' + 
                        (product.ending_inventory || 0) + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #cce5ff; font-weight: bold; font-size: 1.1em;">' + 
                        (product.usage || 0) + '</td>';
                    html += '<td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: #e9d5ff; font-weight: bold; font-size: 1.1em;">' + 
                        (product.cases_required || 0) + '</td>';
                    
                    // Create maps for inventory and orders
                    let productInventory = new Map();
                    let productOrders = new Map();
                    
                    if (product.inventory_dates) {
                        product.inventory_dates.forEach(inv => {
                            let key = inv.date + '|' + inv.location;
                            productInventory.set(key, inv.quantity);
                        });
                    }
                    
                    if (product.order_dates) {
                        product.order_dates.forEach(ord => {
                            let key = ord.date + '|' + ord.location;
                            productOrders.set(key, ord.quantity);
                        });
                    }
                    
                    // Fill in quantities for each date/location
                    sortedDates.forEach(date => {
                        let locationTypes = allDates.get(date);
                        let locations = Array.from(locationTypes.keys()).sort();
                        locations.forEach(loc => {
                            let key = date + '|' + loc;
                            let types = locationTypes.get(loc);
                            
                            let invQty = productInventory.get(key);
                            let ordQty = productOrders.get(key);
                            
                            // Determine background color based on what data we have
                            let bgColor = '#fff';
                            let displayValue = '0';
                            
                            if (types.has('inventory') && types.has('order')) {
                                // Both inventory and order on same date
                                bgColor = '#f0e5ff'; // Light purple blend
                                displayValue = '<strong>' + (invQty || 0) + '</strong> / <strong style="color: #ff6f00;">' + (ordQty || 0) + '</strong>';
                            } else if (types.has('order')) {
                                // Order only
                                bgColor = '#fff3e0'; // Light orange
                                displayValue = '<strong style="color: #ff6f00;">' + (ordQty || 0) + '</strong>';
                            } else {
                                // Inventory only
                                bgColor = '#e3f2fd'; // Light blue
                                displayValue = '<strong>' + (invQty || 0) + '</strong>';
                            }
                            
                            html += '<td style="padding: 10px; text-align: center; border: 1px solid #dee2e6; background: ' + bgColor + ';">';
                            html += displayValue;
                            html += '</td>';
                        });
                    });
                    
                    html += '</tr>';
                });
                
                html += '</tbody></table></div>';
            }
            
            html += '</div>';
            document.getElementById('reportContent').innerHTML = html;
        }
        
        function exportReportToCSV() {
            if (!currentReportData || !currentReportData.products) {
                alert('No report data to export');
                return;
            }
            
            // Keep products in CSV order (no sorting)
            const products = currentReportData.products;
            
            // Collect all unique dates and locations from both inventory and orders
            let allDates = new Map();
            products.forEach(product => {
                if (product.inventory_dates) {
                    product.inventory_dates.forEach(inv => {
                        if (!allDates.has(inv.date)) {
                            allDates.set(inv.date, new Map());
                        }
                        if (!allDates.get(inv.date).has(inv.location)) {
                            allDates.get(inv.date).set(inv.location, new Set());
                        }
                        allDates.get(inv.date).get(inv.location).add('inventory');
                    });
                }
                if (product.order_dates) {
                    product.order_dates.forEach(ord => {
                        if (!allDates.has(ord.date)) {
                            allDates.set(ord.date, new Map());
                        }
                        if (!allDates.get(ord.date).has(ord.location)) {
                            allDates.get(ord.date).set(ord.location, new Set());
                        }
                        allDates.get(ord.date).get(ord.location).add('order');
                    });
                }
            });
            
            // Sort dates
            let sortedDates = Array.from(allDates.keys()).sort();
            
            // Build CSV header
            let csv = 'Product Number,Description,Brand,Package Size,Group,Beginning Inventory,Total Orders,Ending Inventory,USAGE,Cases Required';
            sortedDates.forEach(date => {
                let locationTypes = allDates.get(date);
                let locations = Array.from(locationTypes.keys()).sort();
                locations.forEach(loc => {
                    let types = locationTypes.get(loc);
                    let label = types.has('inventory') && types.has('order') ? 'INV+ORD' : types.has('order') ? 'ORDER' : 'INV';
                    csv += `,"${date} (${loc}) ${label}"`;
                });
            });
            csv += '\\n';
            
            // Package size exceptions list
            const packageSizeExceptions = ['2725042', '2720977', '2725661', '5314208', '3408822', 
                                          '4558003', '2571705', '6911663', '1552124', '6083968', '7979586'];
            
            // Build CSV rows
            products.forEach(product => {
                // Check if product is in exception list
                const packageSize = packageSizeExceptions.includes(String(product.product_number)) 
                                  ? '1 unit' 
                                  : product.package_size;
                
                csv += `"${product.product_number}",`;
                csv += `"${product.description}",`;
                csv += `"${product.brand}",`;
                csv += `"${packageSize}",`;
                csv += `"${product.group}",`;
                csv += `"${product.beginning_inventory || 0}",`;
                csv += `"${product.total_orders || 0}",`;
                csv += `"${product.ending_inventory || 0}",`;
                csv += `"${product.usage || 0}",`;
                csv += `"${product.cases_required || 0}"`;
                
                // Create maps for inventory and orders
                let productInventory = new Map();
                let productOrders = new Map();
                
                if (product.inventory_dates) {
                    product.inventory_dates.forEach(inv => {
                        let key = inv.date + '|' + inv.location;
                        productInventory.set(key, inv.quantity);
                    });
                }
                
                if (product.order_dates) {
                    product.order_dates.forEach(ord => {
                        let key = ord.date + '|' + ord.location;
                        productOrders.set(key, ord.quantity);
                    });
                }
                
                // Fill in quantities for each date/location
                sortedDates.forEach(date => {
                    let locationTypes = allDates.get(date);
                    let locations = Array.from(locationTypes.keys()).sort();
                    locations.forEach(loc => {
                        let key = date + '|' + loc;
                        let types = locationTypes.get(loc);
                        
                        let invQty = productInventory.get(key);
                        let ordQty = productOrders.get(key);
                        
                        if (types.has('inventory') && types.has('order')) {
                            let invValue = invQty != null ? (invQty || 0) : '';
                            let ordValue = ordQty != null ? (ordQty || 0) : '';
                            csv += `,"${invValue} / ${ordValue}"`;
                        } else if (types.has('order')) {
                            csv += `,"${ordQty != null ? (ordQty || 0) : ''}"`;
                        } else {
                            csv += `,"${invQty != null ? (invQty || 0) : ''}"`;
                        }
                    });
                });
                
                csv += '\\n';
            });
            
            // Download CSV
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `product_activity_${currentReportData.date_range.start}_to_${currentReportData.date_range.end}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }
        
        function showMessage(message, type) {
            const msgDiv = document.getElementById('statusMessage');
            msgDiv.textContent = message;
            msgDiv.className = 'status-message ' + type;
            msgDiv.style.display = 'block';
            
            setTimeout(() => {
                msgDiv.style.display = 'none';
            }, 3000);
        }
        
        // Product Management Functions
        function displayProductList() {
            // Add timestamp to prevent caching
            fetch('/api/products?t=' + new Date().getTime())
                .then(response => response.json())
                .then(data => {
                    currentProducts = data;
                    const tbody = document.getElementById('productManagementTableBody');
                    tbody.innerHTML = '';
                    
                    // Display products in the same order as they appear in Enter Inventory (CSV order)
                    currentProducts.forEach((product, index) => {
                        const row = tbody.insertRow();
                        row.draggable = true;
                        row.dataset.productNumber = product['Product Number'];
                        row.style.cursor = 'move';
                        
                        // Safely escape HTML entities
                        function escapeHtml(str) {
                            const div = document.createElement('div');
                            div.textContent = str;
                            return div.innerHTML;
                        }
                        
                        const productNum = escapeHtml(product['Product Number']);
                        const productDesc = escapeHtml(product['Product Description'] || '');
                        const productBrand = escapeHtml(product['Product Brand'] || '');
                        const productPackage = escapeHtml(product['Product Package Size'] || '');
                        const caseCountType = product['Case Count Type'] || 'No';
                        const caseCountChecked = caseCountType.toUpperCase() === 'YES' ? 'checked' : '';
                        
                        row.innerHTML = '<td style="font-weight: bold; color: #667eea; text-align: center;">&#128070; ' + (index + 1) + '</td>' +
                            '<td><span style="background: #e9ecef; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600;">' + 
                            (product['Group Name'] || 'OTHER') + '</span></td>' +
                            '<td>' + productNum + '</td>' +
                            '<td>' + productDesc + '</td>' +
                            '<td>' + productBrand + '</td>' +
                            '<td>' + productPackage + '</td>' +
                            '<td style="text-align: center;">' +
                            '<input type="checkbox" class="case-count-checkbox" data-product-num="' + productNum + '" ' + caseCountChecked + ' ' +
                            'onchange="toggleCaseCount(&quot;' + productNum + '&quot;, this.checked)" ' +
                            'title="When checked, invoice quantities stay as case count (not multiplied)" ' +
                            'style="width: 20px; height: 20px; cursor: pointer;" ondragstart="event.stopPropagation()">' +
                            '</td>' +
                            '<td class="action-buttons">' +
                            '<button class="btn btn-primary edit-product-btn" style="padding: 8px 15px;" ondragstart="event.stopPropagation()">&#9999; Edit</button>' +
                            '<button class="btn btn-danger delete-product-btn" style="padding: 8px 15px;" ondragstart="event.stopPropagation()">&#128465; Delete</button>' +
                            '</td>';
                        
                        // Add drag event listeners
                        row.addEventListener('dragstart', handleDragStart);
                        row.addEventListener('dragover', handleDragOver);
                        row.addEventListener('drop', handleDrop);
                        row.addEventListener('dragend', handleDragEnd);
                        
                        // Add click listeners to buttons (no inline onclick!)
                        const editBtn = row.querySelector('.edit-product-btn');
                        const deleteBtn = row.querySelector('.delete-product-btn');
                        
                        editBtn.addEventListener('click', function(e) {
                            e.stopPropagation();
                            editProductByNumber(product['Product Number']);
                        });
                        
                        deleteBtn.addEventListener('click', function(e) {
                            e.stopPropagation();
                            deleteProduct(product['Product Number']);
                        });
                    });
                })
                .catch(error => console.error('Error loading products:', error));
        }
        
        function filterProductList() {
            const searchTerm = document.getElementById('productSearchBox').value.toLowerCase();
            const rows = document.getElementById('productManagementTableBody').rows;
            
            for (let row of rows) {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchTerm) ? '' : 'none';
            }
        }
        
        function showAddProductForm() {
            document.getElementById('addProductForm').style.display = 'block';
            document.getElementById('newProductNum').value = '';
            document.getElementById('newDescription').value = '';
            document.getElementById('newBrand').value = '';
            document.getElementById('newPackageSize').value = '';
            document.getElementById('newGroupName').value = '';
            document.getElementById('insertPosition').value = '';
        }
        
        function hideAddProductForm() {
            document.getElementById('addProductForm').style.display = 'none';
        }
        
        function addProduct() {
            const insertPosition = document.getElementById('insertPosition').value;
            const data = {
                product_number: document.getElementById('newProductNum').value,
                description: document.getElementById('newDescription').value,
                brand: document.getElementById('newBrand').value,
                package_size: document.getElementById('newPackageSize').value,
                group_name: document.getElementById('newGroupName').value || 'OTHER',
                insert_position: insertPosition ? parseInt(insertPosition) : null
            };
            
            if (!data.product_number || !data.description) {
                alert('Product Number and Description are required');
                return;
            }
            
            fetch('/api/products/add', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    hideAddProductForm();
                    displayProductList();
                    loadProducts(); // Refresh main inventory table
                    alert(result.message);
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => console.error('Error adding product:', error));
        }
        
        function toggleCaseCount(productNumber, isChecked) {
            const product = currentProducts.find(p => String(p['Product Number']) === String(productNumber));
            if (!product) return;
            
            fetch('/api/products/update-case-count', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    product_number: productNumber,
                    case_count_type: isChecked ? 'Yes' : 'No'
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    console.log('Case Count Type updated for product ' + productNumber);
                    // Update local data
                    product['Case Count Type'] = isChecked ? 'Yes' : 'No';
                } else {
                    alert('Error updating Case Count Type: ' + result.message);
                    // Revert checkbox
                    const checkbox = document.querySelector('.case-count-checkbox[data-product-num="' + productNumber + '"]');
                    if (checkbox) checkbox.checked = !isChecked;
                }
            })
            .catch(error => {
                console.error('Error updating Case Count Type:', error);
                alert('Error updating Case Count Type');
                // Revert checkbox
                const checkbox = document.querySelector('.case-count-checkbox[data-product-num="' + productNumber + '"]');
                if (checkbox) checkbox.checked = !isChecked;
            });
        }
        
        function editProduct(product) {
            const newDesc = prompt('Edit Description:', product['Product Description']);
            const newBrand = prompt('Edit Brand:', product['Product Brand']);
            const newSize = prompt('Edit Package Size:', product['Product Package Size']);
            
            if (newDesc === null) return;
            
            fetch('/api/products/update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    product_number: product['Product Number'],
                    description: newDesc || product['Product Description'],
                    brand: newBrand || product['Product Brand'],
                    package_size: newSize || product['Product Package Size']
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    displayProductList();
                    loadProducts();
                    alert(result.message);
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => console.error('Error updating product:', error));
        }
        
        function editProductByNumber(productNumber) {
            // Find the product from currentProducts array
            const product = currentProducts.find(p => String(p['Product Number']) === String(productNumber));
            if (product) {
                editProduct(product);
            } else {
                alert('Product not found');
            }
        }
        
        function deleteProduct(productNum) {
            if (!confirm('Delete product ' + productNum + '?')) return;
            
            fetch('/api/products/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({product_number: productNum})
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    displayProductList();
                    loadProducts();
                    alert(result.message);
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => console.error('Error deleting product:', error));
        }
        
        function uploadCSV() {
            const fileInput = document.getElementById('uploadCSV');
            const file = fileInput.files[0];
            
            if (!file) return;
            
            const formData = new FormData();
            formData.append('file', file);
            
            fetch('/api/products/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    displayProductList();
                    loadProducts();
                    alert(result.message + '\\nProducts loaded: ' + result.product_count);
                } else {
                    alert('Error: ' + result.message);
                }
                fileInput.value = '';
            })
            .catch(error => {
                console.error('Error uploading CSV:', error);
                fileInput.value = '';
            });
        }
        
        function viewProductHistory() {
            fetch('/api/products/history')
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        if (result.files.length === 0) {
                            alert('No backup history found');
                        } else {
                            alert('Product List Backups:\\n\\n' + result.files.join('\\n'));
                        }
                    } else {
                        alert('Error: ' + result.message);
                    }
                })
                .catch(error => console.error('Error loading history:', error));
        }
        
        // Inventory Upload Functions
        function uploadInventoryCSV() {
            const fileInput = document.getElementById('uploadInventoryCSV');
            const file = fileInput.files[0];
            const location = document.getElementById('uploadLocation').value;
            const inventoryDate = document.getElementById('uploadInventoryDate').value;
            const statusDiv = document.getElementById('uploadStatus');
            const fileNameSpan = document.getElementById('selectedFileName');
            
            if (!file) return;
            
            // Show selected file name
            fileNameSpan.textContent = file.name;
            
            if (!inventoryDate) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.innerHTML = '&#9888; Please select an inventory date before uploading.';
                return;
            }
            
            // Show loading status
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#d1ecf1';
            statusDiv.style.color = '#0c5460';
            statusDiv.innerHTML = '⏳ Uploading inventory CSV...';
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('location', location);
            formData.append('inventory_date', inventoryDate);
            
            fetch('/api/inventory/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    statusDiv.style.background = '#d4edda';
                    statusDiv.style.color = '#155724';
                    
                    let message = '&#9989; ' + result.message;
                    message += '<br><strong>Total Items:</strong> ' + result.total_items;
                    message += '<br><strong>Matched Products:</strong> ' + result.matched_count;
                    
                    if (result.unmatched_count > 0) {
                        message += '<br><strong>Unmatched Products:</strong> ' + result.unmatched_count;
                        if (result.unmatched_products && result.unmatched_products.length > 0) {
                            message += '<br><em>Sample unmatched: ' + result.unmatched_products.join(', ') + '</em>';
                        }
                    }
                    
                    statusDiv.innerHTML = message;
                    
                    // Refresh the inventories list
                    loadInventoriesList();
                    
                    // Reset file input after a delay
                    setTimeout(() => {
                        fileInput.value = '';
                        fileNameSpan.textContent = '';
                    }, 500);
                } else {
                    statusDiv.style.background = '#f8d7da';
                    statusDiv.style.color = '#721c24';
                    statusDiv.innerHTML = '&#10060; Error: ' + result.message;
                }
            })
            .catch(error => {
                console.error('Error uploading inventory CSV:', error);
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.innerHTML = '&#10060; Error uploading file: ' + error.message;
            });
        }
        
        // Order Management Functions
        function uploadOrderCSV() {
            const fileInput = document.getElementById('uploadOrderCSV');
            const file = fileInput.files[0];
            const location = document.getElementById('orderLocation').value;
            const orderDate = document.getElementById('orderDate').value;
            
            if (!file) return;
            
            if (!orderDate) {
                alert('Please select an order date');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('location', location);
            formData.append('order_date', orderDate);
            
            fetch('/api/orders/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    alert(result.message + '\\nOrders loaded: ' + result.order_count);
                } else {
                    alert('Error: ' + result.message);
                }
                fileInput.value = '';
            })
            .catch(error => {
                console.error('Error uploading orders:', error);
                alert('Error uploading orders');
                fileInput.value = '';
            });
        }
        
        function uploadInvoiceCSV() {
            const fileInput = document.getElementById('uploadInvoiceCSV');
            const file = fileInput.files[0];
            const location = document.getElementById('invoiceLocation').value;
            const deliveryDate = document.getElementById('deliveryDate').value;
            const statusDiv = document.getElementById('invoiceUploadStatus');
            const fileNameSpan = document.getElementById('invoiceFileName');
            
            if (!file) return;
            
            // Show selected file name
            fileNameSpan.textContent = 'Selected: ' + file.name;
            
            if (!deliveryDate) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.innerHTML = '&#9888; Please select a delivery date before uploading.';
                return;
            }
            
            // Show loading status
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#d1ecf1';
            statusDiv.style.color = '#0c5460';
            statusDiv.innerHTML = '&#8987; Uploading invoice...';
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('location', location);
            formData.append('delivery_date', deliveryDate);
            
            fetch('/api/orders/upload-invoice', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    statusDiv.style.background = '#d4edda';
                    statusDiv.style.color = '#155724';
                    
                    let message = '&#9989; ' + result.message;
                    message += '<br><strong>Total Items:</strong> ' + result.total_items;
                    message += '<br><strong>Matched Products:</strong> ' + result.matched_count;
                    
                    if (result.new_products_created > 0) {
                        message += '<br><strong style="color: #0056b3;">&#127381; New Products Created:</strong> ' + result.new_products_created;
                        if (result.new_product_numbers && result.new_product_numbers.length > 0) {
                            message += '<br><small>Product Numbers: ' + result.new_product_numbers.join(', ') + '</small>';
                        }
                        message += '<br><small>New products added to the bottom of your product list with Group = &quot;Unassigned&quot;</small>';
                    }
                    
                    if (result.unmatched_count > 0) {
                        message += '<br><strong>Unmatched Products:</strong> ' + result.unmatched_count;
                        if (result.unmatched_products && result.unmatched_products.length > 0) {
                            message += '<br><small>First few unmatched: ' + result.unmatched_products.join(', ') + '</small>';
                        }
                    }
                    
                    statusDiv.innerHTML = message;
                    
                    // Reload products list to show new products
                    if (result.new_products_created > 0) {
                        setTimeout(() => {
                            loadProducts();
                        }, 1000);
                    }
                    
                    // Refresh invoice history if visible
                    setTimeout(() => {
                        loadInvoiceHistory();
                    }, 1000);
                } else {
                    statusDiv.style.background = '#f8d7da';
                    statusDiv.style.color = '#721c24';
                    statusDiv.innerHTML = '&#10060; Error: ' + result.message;
                }
                fileInput.value = '';
                fileNameSpan.textContent = '';
            })
            .catch(error => {
                console.error('Error uploading invoice:', error);
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.innerHTML = '&#10060; Error uploading file: ' + error.message;
                fileInput.value = '';
                fileNameSpan.textContent = '';
            });
        }
        
        function calculateOrder() {
            const location = document.getElementById('calcLocation').value;
            const orderDate = document.getElementById('calcOrderDate').value;
            const inventoryDate = document.getElementById('calcInventoryDate').value;
            
            if (!orderDate || !inventoryDate) {
                alert('Please select both order date and inventory date');
                return;
            }
            
            fetch('/api/orders/calculate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    location: location,
                    order_date: orderDate,
                    inventory_date: inventoryDate
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    lastCalculatedOrder = result;
                    displayOrderResults(result);
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => {
                console.error('Error calculating order:', error);
                alert('Error calculating order');
            });
        }
        
        function displayOrderResults(result) {
            const resultsDiv = document.getElementById('orderResults');
            const summaryDiv = document.getElementById('orderSummary');
            const detailsDiv = document.getElementById('orderDetails');
            
            // Show summary
            summaryDiv.innerHTML = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">' +
                '<div style="background: white; padding: 15px; border-radius: 8px; border: 2px solid #667eea;">' +
                '<h4 style="margin: 0 0 10px 0; color: #667eea;">Order Total</h4>' +
                '<p style="font-size: 2em; margin: 0; font-weight: bold;">' + Math.round(result.order_total) + '</p>' +
                '</div>' +
                '<div style="background: white; padding: 15px; border-radius: 8px; border: 2px solid #ffc107;">' +
                '<h4 style="margin: 0 0 10px 0; color: #ffc107;">Inventory Total</h4>' +
                '<p style="font-size: 2em; margin: 0; font-weight: bold;">' + Math.round(result.inventory_total) + '</p>' +
                '</div>' +
                '<div style="background: white; padding: 15px; border-radius: 8px; border: 2px solid #28a745;">' +
                '<h4 style="margin: 0 0 10px 0; color: #28a745;">Official Order</h4>' +
                '<p style="font-size: 2em; margin: 0; font-weight: bold;">' + Math.round(result.official_total) + '</p>' +
                '</div>' +
                '</div>';
            
            // Show detailed order
            let detailsHTML = '<table class="product-table"><thead><tr>' +
                '<th>Product #</th><th>Description</th><th>Order Est.</th>' +
                '<th>Inventory</th><th>Official Order</th></tr></thead><tbody>';
            
            for (let productNum in result.official_order) {
                const product = currentProducts.find(p => String(p['Product Number']) === String(productNum));
                const officialQty = result.official_order[productNum];
                
                if (product && officialQty > 0) {
                    detailsHTML += '<tr>' +
                        '<td>' + productNum + '</td>' +
                        '<td>' + (product['Product Description'] || '') + '</td>' +
                        '<td>-</td>' +
                        '<td>-</td>' +
                        '<td><strong>' + officialQty + '</strong></td>' +
                        '</tr>';
                }
            }
            
            detailsHTML += '</tbody></table>';
            detailsDiv.innerHTML = detailsHTML;
            
            resultsDiv.style.display = 'block';
        }
        
        function exportOfficialOrder() {
            if (!lastCalculatedOrder) {
                alert('Please calculate an order first');
                return;
            }
            
            // Create CSV content
            let csv = 'Product Number,Product Description,Official Order Quantity\\n';
            
            for (let productNum in lastCalculatedOrder.official_order) {
                const product = currentProducts.find(p => String(p['Product Number']) === String(productNum));
                const qty = lastCalculatedOrder.official_order[productNum];
                
                if (product && qty > 0) {
                    const desc = (product['Product Description'] || '').replace(/,/g, ' ');
                    csv += productNum + ',' + desc + ',' + qty + '\\n';
                }
            }
            
            // Download CSV
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'official_order_' + document.getElementById('calcLocation').value + '_' + 
                         document.getElementById('calcOrderDate').value + '.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        }
        
        // Invoice Import History Functions
        function loadInvoiceHistory() {
            fetch('/api/invoices/import-log')
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        displayInvoiceHistory(result.imports);
                    } else {
                        document.getElementById('invoiceHistoryContent').innerHTML = 
                            '<p style="color: #d32f2f;">Error loading import history: ' + result.message + '</p>';
                    }
                })
                .catch(error => {
                    console.error('Error loading invoice history:', error);
                    document.getElementById('invoiceHistoryContent').innerHTML = 
                        '<p style="color: #d32f2f;">Error loading import history</p>';
                });
        }
        
        function displayInvoiceHistory(imports) {
            const container = document.getElementById('invoiceHistoryContent');
            
            if (imports.length === 0) {
                container.innerHTML = '<p style="color: #999;">No invoices have been imported yet.</p>';
                return;
            }
            
            let html = '<div style="max-height: 500px; overflow-y: auto;">';
            html += '<table style="width: 100%; border-collapse: collapse;">';
            html += '<thead><tr style="background: #2196f3; color: white; position: sticky; top: 0;">';
            html += '<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Import ID</th>';
            html += '<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Date/Time</th>';
            html += '<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Filename</th>';
            html += '<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Location</th>';
            html += '<th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Delivery Date</th>';
            html += '<th style="padding: 10px; text-align: center; border: 1px solid #ddd;">Products</th>';
            html += '<th style="padding: 10px; text-align: center; border: 1px solid #ddd;">New Items</th>';
            html += '<th style="padding: 10px; text-align: center; border: 1px solid #ddd;">Actions</th>';
            html += '</tr></thead><tbody>';
            
            imports.forEach(imp => {
                const timestamp = new Date(imp.timestamp).toLocaleString();
                html += '<tr style="border-bottom: 1px solid #ddd;">';
                html += '<td style="padding: 10px; border: 1px solid #ddd;"><code>' + imp.import_id + '</code></td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd;">' + timestamp + '</td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd;">' + imp.filename + '</td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd;">' + imp.location + '</td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd;"><strong>' + imp.delivery_date + '</strong></td>';
                html += '<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">' + imp.total_products + '</td>';
                html += '<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">';
                if (imp.new_products_created > 0) {
                    html += '<span style="color: #0056b3; font-weight: bold;">+' + imp.new_products_created + '</span>';
                } else {
                    html += '-';
                }
                html += '</td>';
                html += '<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">';
                html += '<button onclick="viewInvoiceDetails(&quot;' + imp.import_id + '&quot;)" style="padding: 5px 10px; background: #4caf50; color: white; border: none; border-radius: 4px; cursor: pointer; margin-right: 5px;">View</button>';
                html += '<button onclick="deleteInvoiceImport(&quot;' + imp.import_id + '&quot;)" style="padding: 5px 10px; background: #f44336; color: white; border: none; border-radius: 4px; cursor: pointer;">Delete</button>';
                html += '</td>';
                html += '</tr>';
            });
            
            html += '</tbody></table></div>';
            container.innerHTML = html;
        }
        
        function viewInvoiceDetails(importId) {
            fetch('/api/invoices/import/' + importId)
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        const imp = result.import;
                        let details = 'Import ID: ' + imp.import_id + '\\n';
                        details += 'Timestamp: ' + new Date(imp.timestamp).toLocaleString() + '\\n';
                        details += 'Filename: ' + imp.filename + '\\n';
                        details += 'Location: ' + imp.location + '\\n';
                        details += 'Delivery Date: ' + imp.delivery_date + '\\n';
                        details += 'Total Products: ' + imp.total_products + '\\n';
                        details += 'Matched: ' + imp.matched_count + '\\n';
                        details += 'New Products Created: ' + imp.new_products_created + '\\n\\n';
                        
                        if (imp.new_product_numbers && imp.new_product_numbers.length > 0) {
                            details += 'New Product Numbers:\\n' + imp.new_product_numbers.join(', ') + '\\n\\n';
                        }
                        
                        details += 'Products in this import:\\n';
                        for (let prodNum in imp.products) {
                            details += prodNum + ': ' + imp.products[prodNum] + ' units\\n';
                        }
                        
                        alert(details);
                    } else {
                        alert('Error: ' + result.message);
                    }
                })
                .catch(error => {
                    console.error('Error fetching details:', error);
                    alert('Error loading import details');
                });
        }
        
        function deleteInvoiceImport(importId) {
            if (!confirm('Are you sure you want to delete this import?\\n\\nThis will remove the quantities from your orders but will NOT delete any new products that were created.\\n\\nImport ID: ' + importId)) {
                return;
            }
            
            fetch('/api/invoices/import/' + importId, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    alert(result.message);
                    loadInvoiceHistory();
                } else {
                    alert('Error: ' + result.message);
                }
            })
            .catch(error => {
                console.error('Error deleting import:', error);
                alert('Error deleting import');
            });
        }
        
        // Drag and Drop Functions for Product Reordering
        let draggedRow = null;
        
        function handleDragStart(e) {
            draggedRow = this;
            this.style.opacity = '0.4';
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/html', this.innerHTML);
        }
        
        function handleDragOver(e) {
            if (e.preventDefault) {
                e.preventDefault();
            }
            e.dataTransfer.dropEffect = 'move';
            return false;
        }
        
        function handleDrop(e) {
            if (e.stopPropagation) {
                e.stopPropagation();
            }
            
            if (draggedRow !== this) {
                // Get current order
                const tbody = document.getElementById('productManagementTableBody');
                const rows = Array.from(tbody.rows);
                const fromIndex = rows.indexOf(draggedRow);
                const toIndex = rows.indexOf(this);
                
                // Insert dragged row before or after target
                if (fromIndex < toIndex) {
                    this.parentNode.insertBefore(draggedRow, this.nextSibling);
                } else {
                    this.parentNode.insertBefore(draggedRow, this);
                }
                
                // Update row numbers
                updateRowNumbers();
                
                // Save new order to backend
                saveProductOrder();
            }
            
            return false;
        }
        
        function handleDragEnd(e) {
            this.style.opacity = '1';
            
            // Remove drag over styling from all rows
            const rows = document.querySelectorAll('#productManagementTableBody tr');
            rows.forEach(row => {
                row.style.background = '';
            });
        }
        
        function updateRowNumbers() {
            const rows = document.querySelectorAll('#productManagementTableBody tr');
            rows.forEach((row, index) => {
                row.cells[0].innerHTML = '&#128070; ' + (index + 1);
            });
        }
        
        function saveProductOrder() {
            const tbody = document.getElementById('productManagementTableBody');
            const rows = Array.from(tbody.rows);
            const productNumbers = rows.map(row => row.dataset.productNumber);
            
            fetch('/api/products/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_order: productNumbers })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    console.log('Product order saved successfully');
                    // Reload products to update all views
                    loadProducts();
                } else {
                    alert('Error saving order: ' + result.message);
                }
            })
            .catch(error => {
                console.error('Error saving product order:', error);
                alert('Error saving order');
            });
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    # Load data on startup
    print("\n" + "="*60)
    print("🏪 Inventory Control System - Loading Data...")
    print("="*60)
    
    load_products()
    load_inventory_database()
    load_orders_database()
    load_invoice_import_log()
    
    # Display what was loaded
    print(f"\n📊 Data Summary:")
    print(f"  • Products: {len(products_list)}")
    print(f"  • Locations with orders: {len(order_data)}")
    total_orders = sum(len(dates) for dates in order_data.values())
    print(f"  • Total order dates: {total_orders}")
    print(f"  • Invoice imports: {len(invoice_import_log)}")
    
    print("\n" + "="*60)
    print("🏪 Inventory Control System - Web Version")
    print("="*60)
    print("\nServer starting...")
    print("Access the application at: http://localhost:5002")
    print("Or from another device: http://YOUR_IP:5002")
    print("\nPress CTRL+C to stop the server")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5002)
