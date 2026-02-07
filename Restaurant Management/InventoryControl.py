import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
from datetime import datetime
import os

class InventoryControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Daily Inventory Tracker")
        self.root.geometry("1300x600")
        self.root.configure(bg='#E0FFFF')  # Light cyan background
        
        # Initialize inventory counts dictionary
        self.inventory_counts = {}
        # Initialize units ordered dictionary
        self.units_ordered = {}
        # Initialize starting and ending inventory
        self.starting_inventory = {}
        self.ending_inventory = {}
        
        # Load inventory data
        self.load_inventory()
        
        # Create UI
        self.create_ui()
    
    def load_inventory(self):
        """Load inventory from CSV file"""
        try:
            inventory_path = '/Users/arnoldoramirezjr/Downloads/Update - Sept 13th.csv'
            df = pd.read_csv(inventory_path)
            
            # Select required columns from full inventory
            self.inventory_df = df[['Line Number', 'Group Name', 'Product Number', 
                                    'Product Description', 'Product Brand', 'Product Package Size']].copy()
            
            # Reset index
            self.inventory_df.reset_index(drop=True, inplace=True)
            
            messagebox.showinfo("Success", f"Loaded {len(self.inventory_df)} inventory items")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load inventory: {str(e)}")
            self.inventory_df = pd.DataFrame(columns=['Line Number', 'Group Name', 'Product Number', 
                                                      'Product Description', 'Product Brand', 'Product Package Size'])
    
    def create_ui(self):
        """Create the main user interface"""
        # Title
        title_label = tk.Label(self.root, text="Daily Inventory Tracker", 
                              font=("Arial", 14, "bold"), bg='#E0FFFF', fg='black')
        title_label.pack(pady=5)
        
        # ...existing code...
        
        # Button frame
        button_frame = tk.Frame(self.root, bg='#E0FFFF')
        button_frame.pack(pady=5)
        
        tk.Button(button_frame, text="Save Inventory", command=self.save_inventory,
                 font=("Arial", 9, "bold"), bg="#00FF7F", fg="black", 
                 padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Clear All Counts", command=self.clear_counts,
             font=("Arial", 9, "bold"), bg="#FF69B4", fg="black", 
             padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Load Previous Inventory", command=self.load_previous_inventory,
                 font=("Arial", 9, "bold"), bg="#FFD700", fg="black", 
                 padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Load Invoice", command=self.load_invoice,
                 font=("Arial", 9, "bold"), bg="#FFA500", fg="black", 
                 padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Load Starting Inventory", command=self.load_starting_inventory,
             font=("Arial", 9, "bold"), bg="#87CEEB", fg="black", 
             padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Load Ending Inventory", command=self.load_ending_inventory,
                 font=("Arial", 9, "bold"), bg="#DDA0DD", fg="black", 
                 padx=10, pady=5, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        # Search frame
        search_frame = tk.Frame(self.root, bg='#E0FFFF')
        search_frame.pack(pady=5, fill=tk.X, padx=10)
        
        tk.Label(search_frame, text="Search:", font=("Arial", 9), bg='#E0FFFF', fg='black').pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.filter_inventory)
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, width=40, font=("Arial", 9), bg='#FFFACD', fg='black')
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # Treeview frame
        tree_frame = tk.Frame(self.root, bg='#E0FFFF')
        tree_frame.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)
        
        # Scrollbars
        tree_scroll_y = tk.Scrollbar(tree_frame)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree_scroll_x = tk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Create treeview with editable count column
        self.tree = ttk.Treeview(tree_frame, 
                                yscrollcommand=tree_scroll_y.set,
                                xscrollcommand=tree_scroll_x.set,
                                selectmode="browse")
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        # Define columns
        self.tree['columns'] = ('Line Number', 'Group Name', 'Product Number', 
               'Product Description', 'Product Brand', 'Product Package Size', 
               'Units', 'Units Ordered', 'Starting Inv', 'Unit Inventory', 'Ending Inv', 'Count')
        self.tree['show'] = 'headings'
        
        # Format columns
        self.tree.heading('Line Number', text='Line #', anchor=tk.W)
        self.tree.heading('Group Name', text='Group', anchor=tk.W)
        self.tree.heading('Product Number', text='Product #', anchor=tk.W)
        self.tree.heading('Product Description', text='Product Description', anchor=tk.W)
        self.tree.heading('Product Brand', text='Brand', anchor=tk.W)
        self.tree.heading('Product Package Size', text='Package Size', anchor=tk.W)
        self.tree.heading('Units', text='Units', anchor=tk.CENTER)
        self.tree.heading('Starting Inv', text='Starting Inv', anchor=tk.CENTER)
        self.tree.heading('Units Ordered', text='Units Ordered', anchor=tk.CENTER)
        self.tree.heading('Unit Inventory', text='Unit Inventory', anchor=tk.CENTER)
        self.tree.heading('Ending Inv', text='Ending Inv', anchor=tk.CENTER)
        self.tree.heading('Count', text='Count', anchor=tk.CENTER)
        
        self.tree.column('Line Number', width=50, anchor=tk.W)
        self.tree.column('Group Name', width=90, anchor=tk.W)
        self.tree.column('Product Number', width=80, anchor=tk.W)
        self.tree.column('Product Description', width=150, anchor=tk.W)
        self.tree.column('Product Brand', width=80, anchor=tk.W)
        self.tree.column('Product Package Size', width=80, anchor=tk.W)
        self.tree.column('Units', width=70, anchor=tk.CENTER)
        self.tree.column('Starting Inv', width=70, anchor=tk.CENTER)
        self.tree.column('Units Ordered', width=70, anchor=tk.CENTER)
        self.tree.column('Unit Inventory', width=90, anchor=tk.CENTER)
        self.tree.column('Ending Inv', width=70, anchor=tk.CENTER)
        self.tree.column('Count', width=70, anchor=tk.CENTER)
        
        # Bind double-click to edit count
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        
        # Status bar
        self.status_label = tk.Label(self.root, text=f"Total items: {len(self.inventory_df)}", 
                                     bd=1, relief=tk.SUNKEN, anchor=tk.W, bg='#98FB98', fg='black')
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Load all data initially
        self.display_inventory(self.inventory_df)
    
    def display_inventory(self, df):
        """Display inventory data in treeview"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Insert data with counts and units ordered
        for idx, row in df.iterrows():
            product_desc = row['Product Description']
            product_num = str(row['Product Number'])
            display_desc = str(product_desc)[:25] if pd.notna(product_desc) else ""
            count = self.inventory_counts.get(product_desc, 0.0)
            units_ordered = self.units_ordered.get(product_num, 0)
            # Units column: get from starting inventory by Product Number
            units = 0.0
            for desc, val in self.starting_inventory.items():
                match_row = self.inventory_df[(self.inventory_df['Product Description'] == desc)]
                if not match_row.empty and str(match_row.iloc[0]['Product Number']) == product_num:
                    units = val
                    break
            unit_inventory = units * units_ordered
            starting = self.starting_inventory.get(product_desc, 0.0)
            ending = self.ending_inventory.get(product_desc, 0.0)
            self.tree.insert('', tk.END, values=(
                row['Line Number'],
                row['Group Name'],
                product_num,
                display_desc,
                row['Product Brand'],
                row['Product Package Size'],
                units,
                units_ordered,
                starting,
                unit_inventory,
                ending,
                count
            ))
        
        # Update status
        counted_items = sum(1 for v in self.inventory_counts.values() if v > 0)
        ordered_items = sum(1 for v in self.units_ordered.values() if v > 0)
        starting_items = sum(1 for v in self.starting_inventory.values() if v > 0)
        ending_items = sum(1 for v in self.ending_inventory.values() if v > 0)
        self.status_label.config(text=f"Showing {len(df)} items | Start: {starting_items} | Orders: {ordered_items} | End: {ending_items} | Counted: {counted_items}")
    
    def filter_inventory(self, *args):
        """Filter inventory based on search text"""
        search_text = self.search_var.get().lower()
        
        if not search_text:
            self.display_inventory(self.inventory_df)
            return
        
        # Filter dataframe
        filtered_df = self.inventory_df[
            self.inventory_df['Product Description'].astype(str).str.lower().str.contains(search_text, na=False)
        ]
        
        self.display_inventory(filtered_df)
    
    def on_double_click(self, event):
        """Handle double-click to edit count"""
        region = self.tree.identify('region', event.x, event.y)
        if region != 'cell':
            return
        
        column = self.tree.identify_column(event.x)
        if column != '#10':  # Only allow editing the Count column (10th column)
            return
        
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Get item values
        values = self.tree.item(item, 'values')
        product_desc = values[3]  # Product Description is at index 3
        current_count = values[9]  # Count is at index 9
        
        # Create entry popup for editing
        self.edit_count_popup(item, product_desc, current_count)
    
    def edit_count_popup(self, item, product_desc, current_count):
        """Create popup window to edit count"""
        popup = tk.Toplevel(self.root)
        popup.title("Edit Count")
        popup.geometry("350x150")
        popup.configure(bg='#FFE4E1')  # Misty rose background
        popup.transient(self.root)
        popup.grab_set()
        
        # Center the popup
        popup.update_idletasks()
        x = (popup.winfo_screenwidth() // 2) - (popup.winfo_width() // 2)
        y = (popup.winfo_screenheight() // 2) - (popup.winfo_height() // 2)
        popup.geometry(f"+{x}+{y}")
        
        # Product name label (truncated if too long)
        display_name = product_desc[:40] + "..." if len(product_desc) > 40 else product_desc
        tk.Label(popup, text=display_name, font=("Arial", 9, "bold"), 
                wraplength=300, bg='#FFE4E1', fg='black').pack(pady=10)
        
        # Entry frame
        entry_frame = tk.Frame(popup, bg='#FFE4E1')
        entry_frame.pack(pady=5)
        
        tk.Label(entry_frame, text="Count:", font=("Arial", 10), bg='#FFE4E1', fg='black').pack(side=tk.LEFT, padx=5)
        count_var = tk.StringVar(value=str(current_count))
        count_entry = tk.Entry(entry_frame, textvariable=count_var, font=("Arial", 10), width=12, bg='#FFFACD', fg='black')
        count_entry.pack(side=tk.LEFT, padx=5)
        count_entry.select_range(0, tk.END)
        count_entry.focus()
        
        def save_count():
            try:
                new_count = float(count_var.get())
                if new_count < 0:
                    messagebox.showerror("Error", "Count cannot be negative")
                    return
                
                # Update inventory counts
                self.inventory_counts[product_desc] = new_count
                
                # Update tree item
                values = self.tree.item(item, 'values')
                self.tree.item(item, values=(values[0], values[1], values[2], values[3], 
                                             values[4], values[5], values[6], values[7], values[8], new_count))
                
                # Update status
                counted_items = sum(1 for v in self.inventory_counts.values() if v > 0)
                ordered_items = sum(1 for v in self.units_ordered.values() if v > 0)
                starting_items = sum(1 for v in self.starting_inventory.values() if v > 0)
                ending_items = sum(1 for v in self.ending_inventory.values() if v > 0)
                current_display = len(self.tree.get_children())
                self.status_label.config(text=f"Showing {current_display} items | Start: {starting_items} | Orders: {ordered_items} | End: {ending_items} | Counted: {counted_items}")
                
                popup.destroy()
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid number")
        
        # Buttons
        button_frame = tk.Frame(popup, bg='#FFE4E1')
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="Save", command=save_count, 
                 font=("Arial", 9, "bold"), bg="#7FFFD4", fg="black",
                 padx=15, pady=3, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Cancel", command=popup.destroy,
                 font=("Arial", 9), bg="#FFB6C1", fg="black",
                 padx=15, pady=3, relief=tk.RAISED, bd=2).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key to save
        count_entry.bind('<Return>', lambda e: save_count())
        popup.bind('<Escape>', lambda e: popup.destroy())
    
    def load_invoice(self):
        """Load invoice data and match with inventory by Product Number"""
        from tkinter import filedialog
        
        invoice_folder = '/Users/arnoldoramirezjr/Documents/AIO Python/InvoiceDetails'
        initial_dir = invoice_folder if os.path.exists(invoice_folder) else '/Users/arnoldoramirezjr/Documents/AIO Python'
        
        filename = filedialog.askopenfilename(
            title="Select Invoice File",
            initialdir=initial_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            invoice_df = pd.read_csv(filename)
            
            # Clear current units ordered
            self.units_ordered.clear()
            
            # Match by ProductNumber and sum quantities
            for _, row in invoice_df.iterrows():
                product_num = str(row['ProductNumber'])
                qty_ship = int(row['QtyShip'])
                
                # Add or update units ordered (QtyShip)
                if product_num in self.units_ordered:
                    self.units_ordered[product_num] += qty_ship
                else:
                    self.units_ordered[product_num] = qty_ship
            
            # Refresh display
            self.display_inventory(self.inventory_df)
            
            messagebox.showinfo("Success", f"Loaded invoice with {len(invoice_df)} items\n{len(self.units_ordered)} unique products shipped")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load invoice: {str(e)}")
    
    def load_starting_inventory(self):
        """Load starting inventory for the week"""
        from tkinter import filedialog
        
        inventory_folder = '/Users/arnoldoramirezjr/Documents/AIO Python/daily_inventory'
        initial_dir = inventory_folder if os.path.exists(inventory_folder) else '/Users/arnoldoramirezjr/Documents/AIO Python'
        
        filename = filedialog.askopenfilename(
            title="Select Starting Inventory File",
            initialdir=initial_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            df = pd.read_csv(filename)
            
            # Clear current starting inventory
            self.starting_inventory.clear()
            
            # Match by Product Number and load starting inventory
            for _, row in df.iterrows():
                product_num = str(row['Product Number'])
                try:
                    # Try to convert to float, skip if invalid (like '-')
                    count = float(row['Unit Inventory'])
                except (ValueError, TypeError):
                    count = 0.0
                
                # Find matching product description
                matching_products = self.inventory_df[self.inventory_df['Product Number'].astype(str) == product_num]
                if not matching_products.empty:
                    product_desc = matching_products.iloc[0]['Product Description']
                    self.starting_inventory[product_desc] = count
            
            # Refresh display
            self.display_inventory(self.inventory_df)
            
            messagebox.showinfo("Success", f"Loaded starting inventory with {len(self.starting_inventory)} matched products from:\n{os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load starting inventory: {str(e)}")
    
    def load_ending_inventory(self):
        """Load ending inventory for the week"""
        from tkinter import filedialog
        
        inventory_folder = '/Users/arnoldoramirezjr/Documents/AIO Python/daily_inventory'
        initial_dir = inventory_folder if os.path.exists(inventory_folder) else '/Users/arnoldoramirezjr/Documents/AIO Python'
        
        filename = filedialog.askopenfilename(
            title="Select Ending Inventory File",
            initialdir=initial_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            df = pd.read_csv(filename)
            
            # Clear current ending inventory
            self.ending_inventory.clear()
            
            # Match by Product Number and load ending inventory
            for _, row in df.iterrows():
                product_num = str(row['Product Number'])
                try:
                    # Try to convert to float, skip if invalid (like '-')
                    count = float(row['Unit Inventory'])
                except (ValueError, TypeError):
                    count = 0.0
                
                # Find matching product description
                matching_products = self.inventory_df[self.inventory_df['Product Number'].astype(str) == product_num]
                if not matching_products.empty:
                    product_desc = matching_products.iloc[0]['Product Description']
                    self.ending_inventory[product_desc] = count
            
            # Refresh display
            self.display_inventory(self.inventory_df)
            
            messagebox.showinfo("Success", f"Loaded ending inventory with {len(self.ending_inventory)} matched products from:\n{os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load ending inventory: {str(e)}")
    
    def save_inventory(self):
        """Save inventory counts to CSV file"""
        if not self.inventory_counts:
            messagebox.showwarning("Warning", "No inventory counts to save")
            return
        
        try:
            # Create inventory folder if it doesn't exist
            inventory_folder = '/Users/arnoldoramirezjr/Documents/AIO Python/daily_inventory'
            os.makedirs(inventory_folder, exist_ok=True)
            
            # Create dataframe with counted items
            data = []
            for idx, row in self.inventory_df.iterrows():
                product_desc = row['Product Description']
                if product_desc in self.inventory_counts and self.inventory_counts[product_desc] > 0:
                    data.append({
                        'Line Number': row['Line Number'],
                        'Group Name': row['Group Name'],
                        'Product Number': row['Product Number'],
                        'Product Description': product_desc,
                        'Product Brand': row['Product Brand'],
                        'Product Package Size': row['Product Package Size'],
                        'Count': self.inventory_counts[product_desc]
                    })
            
            if not data:
                messagebox.showwarning("Warning", "No items with counts to save")
                return
            
            df_save = pd.DataFrame(data)
            
            # Save with current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            filename = f"{inventory_folder}/Inventory_{current_date}.csv"
            
            df_save.to_csv(filename, index=False)
            
            messagebox.showinfo("Success", f"Inventory saved to:\n{filename}\n\nTotal items: {len(data)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save inventory: {str(e)}")
    
    def clear_counts(self):
        """Clear all inventory counts"""
        if not self.inventory_counts:
            messagebox.showinfo("Info", "No counts to clear")
            return
        
        result = messagebox.askyesno("Confirm", "Are you sure you want to clear all counts?")
        if result:
            self.inventory_counts.clear()
            self.display_inventory(self.inventory_df)
            messagebox.showinfo("Success", "All counts cleared")
    
    def load_previous_inventory(self):
        """Load a previous inventory file"""
        from tkinter import filedialog
        
        inventory_folder = '/Users/arnoldoramirezjr/Documents/AIO Python/daily_inventory'
        initial_dir = inventory_folder if os.path.exists(inventory_folder) else '/Users/arnoldoramirezjr/Documents/AIO Python'
        
        filename = filedialog.askopenfilename(
            title="Select Inventory File",
            initialdir=initial_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            df = pd.read_csv(filename)
            
            # Clear current counts
            self.inventory_counts.clear()
            
            # Load counts from file
            for _, row in df.iterrows():
                product_desc = row['Product Description']
                count = float(row['Count'])
                self.inventory_counts[product_desc] = count
            
            # Refresh display
            self.display_inventory(self.inventory_df)
            
            messagebox.showinfo("Success", f"Loaded {len(df)} items from:\n{os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load inventory: {str(e)}")

def main():
    root = tk.Tk()
    app = InventoryControlApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
