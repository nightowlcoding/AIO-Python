import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
from pathlib import Path
import math


class ProductCategory:
    """Represents a single product category with its items and calculations"""
    def __init__(self, parent_frame, category_name, item_multipliers, case_quantity, is_weight_based=False, oz_per_piece=None):
        self.parent_frame = parent_frame
        self.category_name = category_name
        self.item_multipliers = item_multipliers
        self.case_quantity = case_quantity
        self.is_weight_based = is_weight_based
        self.oz_per_piece = oz_per_piece
        self.item_inventory = 0.0
        self.results = []
        self.df = None
        
        self.setup_ui()
    
    def setup_ui(self):
        # Results frame
        results_frame = tk.Frame(self.parent_frame)
        results_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        results_label = tk.Label(
            results_frame,
            text=f"Results - {self.category_name}:",
            font=("Arial", 12, "bold")
        )
        results_label.pack(anchor="w")
        
        # Treeview for results
        columns = ("Item Name", "Qty Sold", "Multiplier", "Total")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=15)
        
        # Define column headings
        self.tree.heading("Item Name", text="Item Name")
        self.tree.heading("Qty Sold", text="Qty Sold")
        self.tree.heading("Multiplier", text="Multiplier")
        if self.is_weight_based:
            self.tree.heading("Total", text=f"Total Pieces")
        else:
            self.tree.heading("Total", text=f"Total {self.category_name}")
        
        # Define column widths
        self.tree.column("Item Name", width=300)
        self.tree.column("Qty Sold", width=100, anchor="center")
        self.tree.column("Multiplier", width=100, anchor="center")
        self.tree.column("Total", width=150, anchor="center")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind double-click event to edit inventory
        self.tree.bind("<Double-Button-1>", self.on_double_click)
        
        # Summary frame
        summary_frame = tk.Frame(self.parent_frame)
        summary_frame.pack(pady=10, padx=20, fill="x")
        
        self.summary_label = tk.Label(
            summary_frame,
            text=f"Total {self.category_name}: 0 | Cases Required: 0",
            font=("Arial", 12, "bold"),
            fg="#4CAF50"
        )
        self.summary_label.pack()
    
    def process_data(self, df):
        """Process the Excel data for this category"""
        self.df = df
        
        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []
        
        # Column H is index 7 (0-based), Column N is index 13
        item_column = df.iloc[:, 7]  # Column H
        qty_column = df.iloc[:, 13]  # Column N
        
        total_items = 0
        
        # Search for each item in the mapping
        for item_name, multiplier in self.item_multipliers.items():
            # Search for the item in column H
            for idx, cell_value in enumerate(item_column):
                if pd.notna(cell_value) and item_name in str(cell_value):
                    # Get the quantity sold from column N
                    qty_sold = qty_column.iloc[idx]
                    
                    # Handle non-numeric or NaN values
                    if pd.isna(qty_sold):
                        qty_sold = 0
                    else:
                        try:
                            qty_sold = float(qty_sold)
                        except:
                            qty_sold = 0
                    
                    # Calculate total
                    total = qty_sold * multiplier
                    total_items += total
                    
                    # Store result
                    result = {
                        "item_name": item_name,
                        "qty_sold": qty_sold,
                        "multiplier": multiplier,
                        "total": total
                    }
                    self.results.append(result)
                    
                    # Add to treeview
                    self.tree.insert("", "end", values=(
                        item_name,
                        int(qty_sold) if qty_sold == int(qty_sold) else qty_sold,
                        multiplier,
                        int(total) if total == int(total) else total
                    ))
        
        # Add summary rows to the table
        if self.results:
            self.tree.insert("", "end", values=("", "", "", ""))
            
            if self.is_weight_based:
                # Weight-based calculation
                total_oz = total_items * self.oz_per_piece
                total_lbs = total_oz / 16
                cases_required = total_lbs / self.case_quantity
                
                # Add total pieces row
                self.tree.insert("", "end", values=(
                    f"TOTAL PIECES",
                    "",
                    "",
                    int(total_items)
                ), tags=('total',))
                
                # Add total ounces row
                self.tree.insert("", "end", values=(
                    f"TOTAL OUNCES ({self.oz_per_piece} oz per piece)",
                    "",
                    "",
                    f"{total_oz:.2f}"
                ), tags=('weight',))
                
                # Add total pounds row
                self.tree.insert("", "end", values=(
                    f"TOTAL POUNDS",
                    "",
                    "",
                    f"{total_lbs:.2f}"
                ), tags=('weight',))
                
                # Add cases required row
                self.tree.insert("", "end", values=(
                    f"CASES REQUIRED ({self.case_quantity} lbs per case)",
                    "",
                    "",
                    f"{cases_required:.2f}"
                ), tags=('cases',))
            else:
                # Regular calculation
                cases_required = total_items / self.case_quantity
                
                # Add total row
                self.tree.insert("", "end", values=(
                    f"TOTAL {self.category_name.upper()}",
                    "",
                    "",
                    int(total_items)
                ), tags=('total',))
                
                # Add cases required row
                self.tree.insert("", "end", values=(
                    f"CASES REQUIRED ({self.case_quantity} per case)",
                    "",
                    "",
                    f"{cases_required:.2f}"
                ), tags=('cases',))
            
            # Add cases round up row
            cases_rounded = math.ceil(cases_required)
            self.tree.insert("", "end", values=(
                "CASES ROUND UP",
                "",
                "",
                cases_rounded
            ), tags=('rounded',))
            
            # Add item inventory row
            self.tree.insert("", "end", values=(
                "ITEM INVENTORY (double-click to edit)",
                "",
                "",
                f"{self.item_inventory:.2f}"
            ), tags=('inventory',))
            
            # Add total required row
            total_required = math.ceil(cases_rounded - self.item_inventory)
            self.tree.insert("", "end", values=(
                "TOTAL REQUIRED",
                "",
                "",
                total_required
            ), tags=('required',))
            
            # Style the rows
            self.tree.tag_configure('total', background='#FFF9C4', font=('Arial', 10, 'bold'))
            self.tree.tag_configure('weight', background='#E1BEE7', font=('Arial', 10, 'bold'))
            self.tree.tag_configure('cases', background='#E8F5E9', font=('Arial', 10, 'bold'))
            self.tree.tag_configure('rounded', background='#B3E5FC', font=('Arial', 10, 'bold'))
            self.tree.tag_configure('inventory', background='#FFE0B2', font=('Arial', 10, 'bold'))
            self.tree.tag_configure('required', background='#F8BBD0', font=('Arial', 10, 'bold'))
        
        # Update summary
        if self.is_weight_based:
            total_oz = total_items * self.oz_per_piece
            total_lbs = total_oz / 16
            cases_required = total_lbs / self.case_quantity
            self.summary_label.config(
                text=f"Total Pieces: {int(total_items)} | Total Lbs: {total_lbs:.2f} | Cases Required: {cases_required:.2f}"
            )
        else:
            cases_required = total_items / self.case_quantity
            self.summary_label.config(
                text=f"Total {self.category_name}: {int(total_items)} | Cases Required: {cases_required:.2f}"
            )
        
        return len(self.results)
    
    def on_double_click(self, event):
        """Handle double-click to edit inventory value"""
        item = self.tree.selection()
        if not item:
            return
        
        # Get the values of the clicked item
        values = self.tree.item(item[0], 'values')
        
        # Check if it's the inventory row
        if values and "ITEM INVENTORY" in str(values[0]):
            # Get the column that was clicked
            column = self.tree.identify_column(event.x)
            if column == "#4":  # Total column
                # Get current value
                current_value = values[3]
                
                # Create entry widget for editing
                x, y, width, height = self.tree.bbox(item[0], column)
                
                entry = tk.Entry(self.tree)
                entry.place(x=x, y=y, width=width, height=height)
                entry.insert(0, current_value)
                entry.select_range(0, tk.END)
                entry.focus()
                
                def save_edit(event=None):
                    try:
                        new_value = float(entry.get())
                        self.item_inventory = new_value
                        entry.destroy()
                        # Recalculate and update display
                        self.update_calculations()
                    except ValueError:
                        messagebox.showerror("Error", "Please enter a valid number!")
                        entry.destroy()
                
                def cancel_edit(event=None):
                    entry.destroy()
                
                entry.bind("<Return>", save_edit)
                entry.bind("<FocusOut>", save_edit)
                entry.bind("<Escape>", cancel_edit)
    
    def update_calculations(self):
        """Update inventory and total required rows after editing"""
        # Find and update the inventory and total required rows
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            if values and "ITEM INVENTORY" in str(values[0]):
                # Update inventory value
                self.tree.item(item, values=(
                    "ITEM INVENTORY (double-click to edit)",
                    "",
                    "",
                    f"{self.item_inventory:.2f}"
                ))
            elif values and "TOTAL REQUIRED" in str(values[0]):
                # Find cases rounded value
                cases_rounded = 0
                for prev_item in self.tree.get_children():
                    prev_values = self.tree.item(prev_item, 'values')
                    if prev_values and "CASES ROUND UP" in str(prev_values[0]):
                        cases_rounded = int(prev_values[3])
                        break
                
                # Calculate new total required
                total_required = math.ceil(cases_rounded - self.item_inventory)
                self.tree.item(item, values=(
                    "TOTAL REQUIRED",
                    "",
                    "",
                    total_required
                ))
    
    def get_export_data(self):
        """Get data for CSV export"""
        if not self.results:
            return None
        
        df = pd.DataFrame(self.results)
        column_name = "Total Pieces" if self.is_weight_based else f"Total {self.category_name}"
        df.columns = ["Item Name", "Qty Sold", "Multiplier", column_name]
        
        # Add summary rows
        total_items = sum(r["total"] for r in self.results)
        
        if self.is_weight_based:
            total_oz = total_items * self.oz_per_piece
            total_lbs = total_oz / 16
            cases_required = total_lbs / self.case_quantity
            cases_rounded = math.ceil(cases_required)
            total_required = math.ceil(cases_rounded - self.item_inventory)
            
            summary_data = [
                {"Item Name": "", "Qty Sold": "", "Multiplier": "", column_name: ""},
                {"Item Name": "TOTAL PIECES", "Qty Sold": "", "Multiplier": "", column_name: total_items},
                {"Item Name": f"TOTAL OUNCES ({self.oz_per_piece} oz per piece)", "Qty Sold": "", "Multiplier": "", column_name: f"{total_oz:.2f}"},
                {"Item Name": "TOTAL POUNDS", "Qty Sold": "", "Multiplier": "", column_name: f"{total_lbs:.2f}"},
                {"Item Name": f"CASES REQUIRED ({self.case_quantity} lbs per case)", "Qty Sold": "", "Multiplier": "", column_name: f"{cases_required:.2f}"},
                {"Item Name": "CASES ROUND UP", "Qty Sold": "", "Multiplier": "", column_name: cases_rounded},
                {"Item Name": "ITEM INVENTORY", "Qty Sold": "", "Multiplier": "", column_name: f"{self.item_inventory:.2f}"},
                {"Item Name": "TOTAL REQUIRED", "Qty Sold": "", "Multiplier": "", column_name: total_required},
            ]
        else:
            cases_required = total_items / self.case_quantity
            cases_rounded = math.ceil(cases_required)
            total_required = math.ceil(cases_rounded - self.item_inventory)
            
            summary_data = [
                {"Item Name": "", "Qty Sold": "", "Multiplier": "", column_name: ""},
                {"Item Name": f"TOTAL {self.category_name.upper()}", "Qty Sold": "", "Multiplier": "", column_name: total_items},
                {"Item Name": f"CASES REQUIRED ({self.case_quantity} per case)", "Qty Sold": "", "Multiplier": "", column_name: f"{cases_required:.2f}"},
                {"Item Name": "CASES ROUND UP", "Qty Sold": "", "Multiplier": "", column_name: cases_rounded},
                {"Item Name": "ITEM INVENTORY", "Qty Sold": "", "Multiplier": "", column_name: f"{self.item_inventory:.2f}"},
                {"Item Name": "TOTAL REQUIRED", "Qty Sold": "", "Multiplier": "", column_name: total_required},
            ]
        
        summary_df = pd.DataFrame(summary_data)
        return pd.concat([df, summary_df], ignore_index=True)


class ProductMixExtractor:
    def __init__(self, root):
        self.root = root
        self.root.title("Product Mix Extractor")
        self.root.geometry("950x750")
        
        # Define product categories
        self.categories = {
            "Chicken Wings": {
                "items": {
                    "Side Kick Wings 5 Piece": 5,
                    "6pc Wings w Fries": 6,
                    "10pc Wings w Fries": 10,
                    "16pc  Wings": 16,
                    "SideKick of Wings": 5,
                    "8 Wings & 8 O-Rings": 8,
                    "10 Wings": 10,
                    "15 Wings": 15,
                    "20 Wings": 20
                },
                "case_quantity": 250
            },
            "Beef Cutlets": {
                "items": {
                    "Steak Finger Basket": 1,
                    "Chicken Fried Steak": 1,
                },
                "case_quantity": 28
            },
            "Chicken Boneless": {
                "items": {
                    "6pc Boneless": 6,
                    "12pc Boneless": 12,
                    "Chicken Strip Basket (4)": 4,
                    "Grilled Chicken Tater": 4,
                    "Crispy Chicken Tater": 4,
                    "Boneless Wing Tater": 4,
                    "Chicken & Mushroom": 4,
                    "Grilled Chicken Salad": 4,
                    "Crispy Chicken Salad": 4,
                    "Chicken Tacos": 4,
                    "3PC Chicken Strips w Fries": 3,
                    "6 Boneless Wings & Fries": 6,
                    "Crispy Chicken Baked Potato": 4,
                    "Grilled Chicken SALAD": 4,
                    "Kid's Boneless": 4,
                    "Kids Chicken Strip (3)": 3
                },
                "case_quantity": 40,  # 40 lbs per case
                "is_weight_based": True,
                "oz_per_piece": 1.3
            },
            "Chicken Breast 6oz": {
                "items": {
                    "Chicken Fried Chicken" :1,
                    "Grilled Chicken Sandwich": 1,
                    "Crispy Chicken Sandwich": 1,
                    "Spicy Buffalo Chicken Sandwich": 1,
                    "Deluxe Chicken Sandwich": 1,
                    "Add Extra Chicken": 1
                },
                "case_quantity": 53
            },
            "Burger Patties": {
                "items": {
                    "Big House Burger": 1,
                    "Double Burger": 2,
                    "Triple Burger": 3,
                    "Bigun' (4)": 4,
                    "Burger A La Mexicana": 2,
                    "Chili Cheese Burger": 1,
                    "Green Chili Burger": 1,
                    "Fire Burger": 2,
                    "Brunch Burger": 2,
                    "Deluxe Burger": 1,
                    "Single Burger w Fries": 1,
                    "Burger A La Mexicana -- Single": 1,
                    "Chili Cheese Burger -- Single": 1,
                    "Green Chili Burger -- Single": 1,
                    "Fire Burger -- Single": 1,
                    "Brunch Burger -- Single": 1,
                    "Patty Melt": 1,
                    "Hamburger Patty Solo": 1,
                    "Taco Salad": 2,
                    "Beef Tacos": 1,
                    "Cheddar Jala Hamburger Steak": 2,
                    "Mushroom Swiss Hamburger Steak": 2,
                    "Jalapeno Cheddar HBS Lunch": 1.5,
                    "Kid's Burger": .5,
                },
                "case_quantity": 40,  # 70 lbs per case
                "is_weight_based": True,
                "oz_per_piece": 5.28
            },
            "Ribeye Roll": {
                "items": {
                    "Ribeye Tater": 1,
                    "Ribeye Salad": 1,
                    "Ribeye Sandwich": 1,
                    "Side of RIbeye": 1,
                },
                "case_quantity": 70,  # 70 lbs per case
                "is_weight_based": True,
                "oz_per_piece": 8
            },
            # Add more categories here as needed
            # "Category Name": {
            #     "items": {"Item 1": multiplier, "Item 2": multiplier},
            #     "case_quantity": qty
            # }
        }
        
        self.excel_file_path = None
        self.category_objects = {}
        
        self.setup_ui()
    
    def setup_ui(self):
        # Title
        title_label = tk.Label(
            self.root, 
            text="Product Mix Extractor", 
            font=("Arial", 16, "bold")
        )
        title_label.pack(pady=10)
        
        # File selection frame
        file_frame = tk.Frame(self.root)
        file_frame.pack(pady=10, padx=20, fill="x")
        
        self.file_label = tk.Label(
            file_frame, 
            text="No file selected", 
            font=("Arial", 10),
            anchor="w"
        )
        self.file_label.pack(side="left", fill="x", expand=True)
        
        select_btn = tk.Button(
            file_frame,
            text="Select Excel File",
            command=self.select_file,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=5
        )
        select_btn.pack(side="right", padx=5)
        
        # Process button
        process_btn = tk.Button(
            self.root,
            text="Process File",
            command=self.process_file,
            bg="#2196F3",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10
        )
        process_btn.pack(pady=10)
        
        # Create notebook (tabs) for categories
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Create a tab for each category
        for category_name, category_data in self.categories.items():
            # Create frame for this category
            tab_frame = tk.Frame(self.notebook)
            self.notebook.add(tab_frame, text=category_name)
            
            # Create category object
            category_obj = ProductCategory(
                tab_frame,
                category_name,
                category_data["items"],
                category_data["case_quantity"],
                is_weight_based=category_data.get("is_weight_based", False),
                oz_per_piece=category_data.get("oz_per_piece")
            )
            self.category_objects[category_name] = category_obj
        
        # Export button
        export_btn = tk.Button(
            self.root,
            text="Export All Results to CSV",
            command=self.export_results,
            bg="#FF9800",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=5
        )
        export_btn.pack(pady=10)
    
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("All Files", "*.*")]
        )
        
        if file_path:
            self.excel_file_path = file_path
            self.file_label.config(text=f"Selected: {Path(file_path).name}")
    
    def process_file(self):
        if not self.excel_file_path:
            messagebox.showerror("Error", "Please select an Excel file first!")
            return
        
        try:
            # Read the Excel file
            df = pd.read_excel(self.excel_file_path, sheet_name="Selected levels")
            
            # Check if required columns exist
            if df.shape[1] < 14:  # Need at least 14 columns (N is the 14th)
                messagebox.showerror("Error", "Excel file doesn't have enough columns!")
                return
            
            # Process data for each category
            total_found = 0
            for category_name, category_obj in self.category_objects.items():
                found = category_obj.process_data(df)
                total_found += found
            
            if total_found == 0:
                messagebox.showinfo("Info", "No matching items found in the Excel file.")
            else:
                messagebox.showinfo("Success", f"Found {total_found} item(s) across all categories!")
        
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
    
    def export_results(self):
        """Export all category results to a single CSV file"""
        has_results = False
        all_dfs = []
        
        for category_name, category_obj in self.category_objects.items():
            export_data = category_obj.get_export_data()
            if export_data is not None:
                has_results = True
                # Add category separator
                separator_df = pd.DataFrame([{"Item Name": f"\n=== {category_name.upper()} ===", "Qty Sold": "", "Multiplier": "", f"Total {category_name}": ""}])
                all_dfs.append(separator_df)
                all_dfs.append(export_data)
                # Add spacing
                all_dfs.append(pd.DataFrame([{"Item Name": "", "Qty Sold": "", "Multiplier": "", f"Total {category_name}": ""}]))
        
        if not has_results:
            messagebox.showwarning("Warning", "No results to export!")
            return
        
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                title="Save Results As"
            )
            
            if file_path:
                # Combine all dataframes
                final_df = pd.concat(all_dfs, ignore_index=True)
                
                # Save to CSV
                final_df.to_csv(file_path, index=False)
                messagebox.showinfo("Success", f"Results exported to:\n{file_path}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export:\n{str(e)}")


def main():
    root = tk.Tk()
    app = ProductMixExtractor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
