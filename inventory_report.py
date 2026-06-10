from flask import Blueprint, render_template, request, session, redirect, url_for
import os
import pandas as pd
from datetime import datetime

report_bp = Blueprint('report', __name__)

@report_bp.route('/inventory_report', methods=['GET', 'POST'])
def inventory_report():
    report = None
    begin_date = None
    end_date = None
    error = None
    reference_items = []
    reference_file = 'reference_inventory.csv'
    # 3rd party input handling
    if 'third_party' not in session:
        session['third_party'] = {}
    third_party = session.get('third_party', {})
    if os.path.exists(reference_file):
        df_ref = pd.read_csv(reference_file)
        reference_items = df_ref.to_dict(orient='records')
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
    if request.method == 'POST':
        begin_date = request.form.get('begin_date')
        end_date = request.form.get('end_date')
        # Save 3rd party input
        third_party = {}
        for key in request.form:
            if key.startswith('third_party_'):
                item_num = key.replace('third_party_', '')
                try:
                    third_party[item_num] = float(request.form[key]) if request.form[key] else 0
                except Exception:
                    third_party[item_num] = 0
        session['third_party'] = third_party
        def normalize_date(date_str):
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
            except Exception:
                pass
            try:
                return datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
            except Exception:
                pass
            return date_str
        if begin_date and end_date:
            begin_date_norm = normalize_date(begin_date)
            end_date_norm = normalize_date(end_date)
            try:
                begin_dt = datetime.strptime(begin_date_norm, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date_norm, '%Y-%m-%d')
            except Exception:
                error = 'Invalid date format.'
                return render_template('inventory_report.html', report=None, begin_date=begin_date, end_date=end_date, error=error)

            # Find all inventory files in the range
            inventory_files = []
            for fname in os.listdir('.'):
                if fname.startswith('daily_inventory_') and fname.endswith('.csv'):
                    date_part = fname[len('daily_inventory_'):-len('.csv')]
                    try:
                        file_dt = datetime.strptime(date_part, '%Y-%m-%d')
                        if begin_dt <= file_dt <= end_dt:
                            inventory_files.append((file_dt, fname))
                    except Exception:
                        continue
            inventory_files.sort()
            # Gather order invoice data for the range
            invoice_dir = 'OrderInvoices'
            invoice_files = []
            if os.path.exists(invoice_dir):
                for fname in os.listdir(invoice_dir):
                    if fname.startswith('Order_Invoice_') and fname.endswith('.csv'):
                        date_part = fname[len('Order_Invoice_'):-len('.csv')]
                        try:
                            file_dt = datetime.strptime(date_part, '%Y-%m-%d')
                            if begin_dt <= file_dt <= end_dt:
                                invoice_files.append((file_dt, os.path.join(invoice_dir, fname)))
                        except Exception:
                            continue
            # Build a mapping from item number to total quantity ordered in the range
            item_number_to_qty = {}
            if invoice_files:
                for _, fpath in invoice_files:
                    try:
                        df = pd.read_csv(fpath)
                        for _, row in df.iterrows():
                            item_number = str(row['ProductNumber']) if 'ProductNumber' in row else ''
                            qty = row['QtyShip'] if 'QtyShip' in row else 0
                            if item_number:
                                item_number_to_qty[item_number] = item_number_to_qty.get(item_number, 0) + qty
                    except Exception:
                        continue
            if not inventory_files:
                error = 'No inventory files found in the selected date range.'
            else:
                inventories = []
                for file_dt, fname in inventory_files:
                    df = pd.read_csv(fname)
                    inventories.append({
                        'date': file_dt.strftime('%Y-%m-%d'),
                        'data': df.to_dict(orient='records')
                    })
                # Compute usage for each item number
                usage_dict = {}
                # Find beginning and ending inventory by item number
                begin_inv = {str(row.get('item_number', '')): row for row in inventories[0]['data']} if inventories else {}
                end_inv = {str(row.get('item_number', '')): row for row in inventories[-1]['data']} if inventories else {}
                for ref in reference_items:
                    item_num = str(ref.get('item_number', ''))
                    upp = ref.get('UPP', 1)
                    try:
                        upp = float(upp)
                    except Exception:
                        upp = 1
                    begin_qty = begin_inv.get(item_num, {}).get('quantity_on_hand', 0)
                    end_qty = end_inv.get(item_num, {}).get('quantity_on_hand', 0)
                    try:
                        begin_qty = float(begin_qty)
                    except Exception:
                        begin_qty = 0
                    try:
                        end_qty = float(end_qty)
                    except Exception:
                        end_qty = 0
                    qty_ordered = item_number_to_qty.get(item_num, 0)
                    try:
                        qty_ordered = float(qty_ordered)
                    except Exception:
                        qty_ordered = 0
                    third_party_val = third_party.get(item_num, 0)
                    try:
                        third_party_val = float(third_party_val)
                    except Exception:
                        third_party_val = 0
                    usage = (begin_qty + third_party_val + (qty_ordered * upp)) - end_qty
                    usage_dict[item_num] = usage
                # Build report dict first
                report = {
                    'begin_date': begin_date_norm,
                    'end_date': end_date_norm,
                    'inventories': inventories,
                    'item_number_to_qty': item_number_to_qty,
                    'usage_dict': usage_dict
                }
                # Pass 3rd party values to template
                report['third_party'] = third_party
        else:
            error = 'Please select both a beginning and ending date.'
    return render_template('inventory_report.html', report=report, begin_date=begin_date, end_date=end_date, error=error, reference_items=reference_items)
