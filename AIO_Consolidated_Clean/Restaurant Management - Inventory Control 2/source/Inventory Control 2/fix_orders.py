import json
import csv

# Load the invoice CSV
invoice_data = []
with open('/Users/arnoldoramirezjr/Downloads/InvoiceDetails (3).csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        invoice_data.append(row)

# Load current orders
with open('data/orders_database.json', 'r') as f:
    orders = json.load(f)

# Reprocess the 2026-01-19 order with case multipliers
fixed_orders = {}
fixed_count = 0

for row in invoice_data:
    product_num = str(row['ProductNumber']).strip()
    try:
        qty = float(row['QtyShip'])
    except (ValueError, TypeError, KeyError):
        continue
    
    if qty > 0:
        pricing_unit = str(row.get('PricingUnit', '')).strip().upper()
        packing_size = str(row.get('PackingSize', '')).strip()
        
        # If sold as case, multiply by case pack
        if pricing_unit == 'CS' and '/' in packing_size:
            try:
                case_pack = int(packing_size.split('/')[0])
                adjusted_qty = qty * case_pack
                fixed_orders[product_num] = adjusted_qty
                if adjusted_qty != qty:
                    fixed_count += 1
                    print(f'Product {product_num}: {qty} CS x {case_pack} = {adjusted_qty} units')
            except (ValueError, IndexError):
                fixed_orders[product_num] = qty
        else:
            fixed_orders[product_num] = qty

# Update the orders database
orders['Kingsville']['2026-01-19'] = fixed_orders

# Save
with open('data/orders_database.json', 'w') as f:
    json.dump(orders, f, indent=2)

print(f'\nFixed {fixed_count} case products')
print(f'Total products in order: {len(fixed_orders)}')
print('\nMargarine (3264931) should now show:', fixed_orders.get('3264931', 'Not found'))
