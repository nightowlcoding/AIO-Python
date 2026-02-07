
# Inventory Control System
# Features: Import inventory list from CSV, manual entry, timestamping, product mix, order tracking
import csv
from datetime import datetime

class InventoryManager:
	def __init__(self):
		self.inventory_list = []  # List of dicts: {product, quantity, ...}
		self.product_mix = []     # Placeholder for product mix data
		self.order_history = []   # Placeholder for order tracking

	def import_from_csv(self, file_path):
		"""Import inventory list from a CSV file."""
		try:
			with open(file_path, newline='', encoding='utf-8') as csvfile:
				reader = csv.DictReader(csvfile)
				self.inventory_list = [row for row in reader]
			print(f"Imported {len(self.inventory_list)} items from {file_path}.")
		except Exception as e:
			print(f"Error importing CSV: {e}")

	def manual_entry(self):
		"""Allow user to manually input inventory items."""
		print("Enter inventory items. Type 'done' to finish.")
		while True:
			product = input("Product name: ")
			if product.lower() == 'done':
				break
			quantity = input("Quantity: ")
			self.inventory_list.append({
				'product': product,
				'quantity': quantity
			})
		print(f"Manually entered {len(self.inventory_list)} items.")

	def record_inventory(self):
		"""Record inventory with timestamp."""
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		for item in self.inventory_list:
			item['timestamp'] = timestamp
		print(f"Inventory recorded at {timestamp}.")

	def plan_product_mix(self):
		"""Stub for product mix planning."""
		print("[TODO] Product mix planning feature coming soon.")

	def track_orders(self):
		"""Stub for order tracking."""
		print("[TODO] Order tracking feature coming soon.")

if __name__ == "__main__":
	manager = InventoryManager()
	print("Inventory Control System")
	mode = input("Import from CSV (1) or Manual Entry (2)? ")
	if mode == '1':
		path = input("Enter CSV file path: ")
		manager.import_from_csv(path)
	else:
		manager.manual_entry()
	manager.record_inventory()
	# Stubs for next features
	manager.plan_product_mix()
	manager.track_orders()
