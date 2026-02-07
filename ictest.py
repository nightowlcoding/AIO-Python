from flask import Flask, render_template_string, request, jsonify, send_file
import pandas as pd
import json
import os
from datetime import datetime, date

app = Flask(__name__)

# Global data storage
inventory_data = {}
products_list = []

# Paths
base_dir = '/Users/arnoldoramirezjr/Documents/AIO Python'
data_dir = os.path.join(base_dir, 'inventory_data')
os.makedirs(data_dir, exist_ok=True)


def load_products():
    """Load product list from reference inventory"""
    global products_list
    try:
        # Primary path in Documents folder
        inventory_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Update - Sept 13th.csv'
        if os.path.exists(inventory_path):
            df = pd.read_csv(inventory_path)
            products_list = df[['Product Number', 'Product Description', 
                               'Product Brand', 'Product Package Size']].to_dict('records')
        else:
            products_list = []
        
        # Save a backup of the product list
        save_product_list_backup()
    except Exception as e:
        print(f"Error loading products: {e}")
        products_list = []


def save_product_list_backup():
    """Save backup of current product list with timestamp"""
    try:
        backup_dir = os.path.join(data_dir, 'product_lists')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file = os.path.join(backup_dir, f'products_{timestamp}.json')
        
        with open(backup_file, 'w') as f:
            json.dump(products_list, f, indent=2)
    except Exception as e:
        print(f"Error saving product list backup: {e}")


def save_products_to_csv():
    """Save current product list back to CSV"""
    try:
        if not products_list:
            return False
            
        df = pd.DataFrame(products_list)
        csv_path = '/Users/arnoldoramirezjr/Documents/AIO Python/Update - Sept 13th.csv'
        df.to_csv(csv_path, index=False)
        
        # Create timestamped backup
        backup_dir = os.path.join(data_dir, 'product_lists')
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = os.path.join(backup_dir, f'Update_Sept_13th_backup_{timestamp}.csv')
        df.to_csv(backup_path, index=False)
        
        return True
    except Exception as e:
        print(f"Error saving products to CSV: {e}")
        return False


def load_inventory_database():
    """Load all saved inventory data"""
    global inventory_data
    db_file = os.path.join(data_dir, 'inventory_database.json')
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                inventory_data = json.load(f)
        except Exception as e:
            print(f"Error loading database: {e}")
            inventory_data = {}
    else:
        inventory_data = {}


def save_inventory_database():
    """Save all inventory data to database"""
    db_file = os.path.join(data_dir, 'inventory_database.json')
    try:
        with open(db_file, 'w') as f:
            json.dump(inventory_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving database: {e}")
        return False


# Initialize data on startup
load_products()
load_inventory_database()


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Inventory Control System - Kingsville & Alice</title>
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
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
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
        
        .control-panel {
            padding: 20px 30px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .control-group {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .control-group label {
            font-weight: 600;
            color: #495057;
        }
        
        .location-buttons {
            display: flex;
            gap: 10px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 14px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .btn-primary { background: #007bff; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn-warning { background: #ffc107; color: #000; }
        .btn-info { background: #17a2b8; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        
        .btn-location {
            background: #e9ecef;
            color: #495057;
        }
        
        .btn-location.active {
            background: #667eea;
            color: white;
        }
        
        input[type="date"] {
            padding: 10px 15px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 14px;
        }
        
        .tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
        }
        
        .tab {
            padding: 15px 30px;
            cursor: pointer;
            border: none;
            background: transparent;
            font-size: 16px;
            font-weight: 600;
            color: #6c757d;
            transition: all 0.3s ease;
        }
        
        .tab:hover {
            background: #e9ecef;
        }
        
        .tab.active {
            background: white;
            color: #667eea;
            border-bottom: 3px solid #667eea;
        }
        
        .tab-content {
            display: none;
            padding: 30px;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .search-box {
            margin-bottom: 20px;
        }
        
        .search-box input {
            width: 100%;
            padding: 15px;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            font-size: 16px;
        }
        
        .search-box input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .inventory-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        .inventory-table th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        
        .inventory-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #dee2e6;
        }
        
        .inventory-table tr:hover {
            background: #f8f9fa;
        }
        
        .quantity-input {
            width: 80px;
            padding: 8px;
            border: 2px solid #dee2e6;
            border-radius: 5px;
            text-align: center;
        }
        
        .quantity-input:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .saved-item {
            padding: 15px;
            margin: 10px 0;
            background: #f8f9fa;
            border-radius: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s ease;
        }
        
        .saved-item:hover {
            background: #e9ecef;
            transform: translateX(5px);
        }
        
        .saved-item-info {
            flex: 1;
        }
        
        .saved-item-actions {
            display: flex;
            gap: 10px;
        }
        
        .status-bar {
            padding: 15px 30px;
            background: #343a40;
            color: white;
            text-align: center;
        }
        
        .report-section {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        
        .location-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 12px;
        }
        
        .badge-kingsville {
            background: #007bff;
            color: white;
        }
        
        .badge-alice {
            background: #28a745;
            color: white;
        }
        
        .table-container {
            max-height: 600px;
            overflow-y: auto;
        }
        
        .action-buttons {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏪 Inventory Control System</h1>
            <p>Multi-Location Inventory Management - Kingsville & Alice</p>
        </div>
        
        <div class="control-panel">
            <div class="control-group">
                <label>Location:</label>
                <div class="location-buttons">
                    <button class="btn btn-location active" onclick="setLocation('Kingsville')">Kingsville</button>
                    <button class="btn btn-location" onclick="setLocation('Alice')">Alice</button>
                </div>
            </div>
            
            <div class="control-group">
                <label>Date:</label>
                <input type="date" id="currentDate" value="">
            </div>
            
            <div class="action-buttons">
                <button class="btn btn-success" onclick="saveInventory()">💾 Save</button>
                <button class="btn btn-primary" onclick="loadInventory()">📂 Load</button>
                <button class="btn btn-warning" onclick="clearAll()">🔄 Clear All</button>
                <button class="btn btn-danger" onclick="deleteInventory()">🗑️ Delete</button>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('entry')">📝 Inventory Entry</button>
            <button class="tab" onclick="showTab('saved')">📋 Saved Inventories</button>
            <button class="tab" onclick="showTab('products')">🛍️ Manage Products</button>
            <button class="tab" onclick="showTab('reports')">📊 Reports</button>
        </div>
        
        <div id="entry-tab" class="tab-content active">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="🔍 Search products by number, description, or brand..." oninput="filterProducts()">
            </div>
            
            <div class="table-container">
                <table class="inventory-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Product #</th>
                            <th>Description</th>
                            <th>Brand</th>
                            <th>Package Size</th>
                            <th>Quantity</th>
                        </tr>
                    </thead>
                    <tbody id="inventoryTableBody">
                        <!-- Products will be loaded here -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div id="saved-tab" class="tab-content">
            <h2>Saved Inventory Records</h2>
            <div class="control-group" style="margin: 20px 0;">
                <label>Filter:</label>
                <div class="location-buttons">
                    <button class="btn btn-location active" onclick="filterSaved('All')">All</button>
                    <button class="btn btn-location" onclick="filterSaved('Kingsville')">Kingsville</button>
                    <button class="btn btn-location" onclick="filterSaved('Alice')">Alice</button>
                </div>
            </div>
            <div id="savedInventoriesList">
                <!-- Saved inventories will be loaded here -->
            </div>
        </div>
        
        <div id="reports-tab" class="tab-content">
            <h2>📊 Inventory Reports & Analysis</h2>
            <div class="action-buttons" style="margin: 20px 0;">
                <button class="btn btn-info" onclick="generateReport('summary')">📈 Summary by Location</button>
                <button class="btn btn-info" onclick="generateReport('trends')">📅 Trends Over Time</button>
                <button class="btn btn-info" onclick="generateReport('compare')">📊 Compare Locations</button>
                <button class="btn btn-warning" onclick="generateOrder()">🛒 Generate Order</button>
            </div>
            <div id="reportContent" class="report-section">
                <p>Select a report type to view analysis...</p>
            </div>
        </div>
        
        <div id="products-tab" class="tab-content">
            <h2>🛍️ Manage Product List</h2>
            
            <div class="action-buttons" style="margin: 20px 0;">
                <button class="btn btn-success" onclick="showAddProductForm()">➕ Add New Product</button>
                <button class="btn btn-warning" onclick="showUploadForm()">📤 Upload CSV</button>
                <button class="btn btn-info" onclick="viewProductHistory()">📜 View History</button>
                <button class="btn btn-secondary" onclick="loadProducts()">🔄 Reload List</button>
            </div>
            
            <!-- Add Product Form -->
            <div id="addProductForm" style="display: none; background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3>Add New Product</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                    <div>
                        <label style="font-weight: 600;">Product Number:</label>
                        <input type="text" id="newProductNumber" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 5px;">
                    </div>
                    <div>
                        <label style="font-weight: 600;">Brand:</label>
                        <input type="text" id="newProductBrand" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 5px;">
                    </div>
                    <div style="grid-column: 1 / -1;">
                        <label style="font-weight: 600;">Description:</label>
                        <input type="text" id="newProductDescription" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 5px;">
                    </div>
                    <div>
                        <label style="font-weight: 600;">Package Size:</label>
                        <input type="text" id="newProductSize" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 5px;">
                    </div>
                </div>
                <div style="margin-top: 15px;">
                    <button class="btn btn-success" onclick="addProduct()">💾 Save Product</button>
                    <button class="btn btn-secondary" onclick="hideAddProductForm()">❌ Cancel</button>
                </div>
            </div>
            
            <!-- Upload CSV Form -->
            <div id="uploadForm" style="display: none; background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h3>Upload Product CSV</h3>
                <p style="color: #6c757d; margin: 10px 0;">Required columns: Product Number, Product Description, Product Brand, Product Package Size</p>
                <input type="file" id="csvFile" accept=".csv" style="margin: 15px 0;">
                <div>
                    <button class="btn btn-success" onclick="uploadCSV()">📤 Upload</button>
                    <button class="btn btn-secondary" onclick="hideUploadForm()">❌ Cancel</button>
                </div>
            </div>
            
            <!-- Product History -->
            <div id="productHistory" style="display: none;">
                <h3>Product List History</h3>
                <div id="historyList"></div>
            </div>
            
            <!-- Products List -->
            <div class="search-box" style="margin-top: 20px;">
                <input type="text" id="productSearchInput" placeholder="🔍 Search products..." oninput="filterProductList()">
            </div>
            
            <div class="table-container">
                <table class="inventory-table">
                    <thead>
                        <tr>
                            <th>Product #</th>
                            <th>Description</th>
                            <th>Brand</th>
                            <th>Package Size</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="productListBody">
                        <!-- Products will be loaded here -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="status-bar">
            <span id="statusMessage">Ready</span>
        </div>
    </div>
    
    <script>
        let currentLocation = 'Kingsville';
        let currentDate = new Date().toISOString().split('T')[0];
        let allProducts = [];
        let currentInventory = {};
        let filterLocation = 'All';
        
        // Initialize
        document.getElementById('currentDate').value = currentDate;
        loadProducts();
        
        function setLocation(location) {
            currentLocation = location;
            document.querySelectorAll('.location-buttons .btn-location').forEach(btn => {
                btn.classList.remove('active');
                if (btn.textContent === location) {
                    btn.classList.add('active');
                }
            });
            loadInventory();
            setStatus(`Location changed to ${location}`);
        }
        
        function showTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
            
            if (tabName === 'saved') {
                loadSavedInventories();
            }
        }
        
        async function loadProducts() {
            try {
                const response = await fetch('/api/products');
                allProducts = await response.json();
                displayProducts();
            } catch (error) {
                console.error('Error loading products:', error);
                setStatus('Error loading products');
            }
        }
        
        function displayProducts(filteredProducts = null) {
            const products = filteredProducts || allProducts;
            const tbody = document.getElementById('inventoryTableBody');
            tbody.innerHTML = '';
            
            products.forEach((product, index) => {
                const productNum = product['Product Number'] || '';
                const qty = currentInventory[productNum] || 0;
                
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td>${productNum}</td>
                    <td>${product['Product Description'] || ''}</td>
                    <td>${product['Product Brand'] || ''}</td>
                    <td>${product['Product Package Size'] || ''}</td>
                    <td>
                        <input type="number" 
                               class="quantity-input" 
                               value="${qty}" 
                               onchange="updateQuantity('${productNum}', this.value)"
                               min="0" 
                               step="0.01">
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
        
        function filterProducts() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            if (!searchTerm) {
                displayProducts();
                return;
            }
            
            const filtered = allProducts.filter(product => {
                return (
                    (product['Product Number'] || '').toString().toLowerCase().includes(searchTerm) ||
                    (product['Product Description'] || '').toLowerCase().includes(searchTerm) ||
                    (product['Product Brand'] || '').toLowerCase().includes(searchTerm)
                );
            });
            
            displayProducts(filtered);
        }
        
        function updateQuantity(productNum, quantity) {
            const qty = parseFloat(quantity) || 0;
            if (qty > 0) {
                currentInventory[productNum] = qty;
            } else {
                delete currentInventory[productNum];
            }
        }
        
        async function saveInventory() {
            const date = document.getElementById('currentDate').value;
            
            try {
                const response = await fetch('/api/inventory/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        location: currentLocation,
                        date: date,
                        inventory: currentInventory
                    })
                });
                
                const result = await response.json();
                if (result.success) {
                    setStatus(`✅ ${result.message} for ${currentLocation} on ${date}`);
                    alert(`Inventory saved successfully!\\n${result.message}`);
                } else {
                    setStatus('❌ Failed to save inventory');
                }
            } catch (error) {
                console.error('Error saving:', error);
                setStatus('❌ Error saving inventory');
            }
        }
        
        async function loadInventory() {
            const date = document.getElementById('currentDate').value;
            
            try {
                const response = await fetch(`/api/inventory/${currentLocation}/${date}`);
                currentInventory = await response.json();
                displayProducts();
                
                const count = Object.keys(currentInventory).length;
                if (count > 0) {
                    setStatus(`📂 Loaded ${count} items for ${currentLocation} on ${date}`);
                } else {
                    setStatus(`No saved inventory for ${currentLocation} on ${date}`);
                }
            } catch (error) {
                console.error('Error loading:', error);
                setStatus('❌ Error loading inventory');
            }
        }
        
        function clearAll() {
            if (confirm('Clear all quantities?')) {
                currentInventory = {};
                displayProducts();
                setStatus('Cleared all quantities');
            }
        }
        
        async function deleteInventory() {
            const date = document.getElementById('currentDate').value;
            
            if (!confirm(`Delete inventory for ${currentLocation} on ${date}?`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/inventory/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        location: currentLocation,
                        date: date
                    })
                });
                
                const result = await response.json();
                if (result.success) {
                    currentInventory = {};
                    displayProducts();
                    setStatus('✅ Inventory deleted');
                    alert('Inventory deleted successfully!');
                }
            } catch (error) {
                console.error('Error deleting:', error);
                setStatus('❌ Error deleting inventory');
            }
        }
        
        async function loadSavedInventories() {
            try {
                const response = await fetch('/api/inventory/list');
                const inventories = await response.json();
                
                const container = document.getElementById('savedInventoriesList');
                container.innerHTML = '';
                
                const filtered = filterLocation === 'All' 
                    ? inventories 
                    : inventories.filter(inv => inv.location === filterLocation);
                
                filtered.forEach(inv => {
                    const badgeClass = inv.location === 'Kingsville' ? 'badge-kingsville' : 'badge-alice';
                    
                    const div = document.createElement('div');
                    div.className = 'saved-item';
                    div.innerHTML = `
                        <div class="saved-item-info">
                            <strong>${inv.date}</strong>
                            <span class="location-badge ${badgeClass}">${inv.location}</span>
                            <span style="color: #6c757d; margin-left: 10px;">${inv.count} items</span>
                        </div>
                        <div class="saved-item-actions">
                            <button class="btn btn-primary btn-sm" onclick="loadSavedInventory('${inv.location}', '${inv.date}')">📂 Load</button>
                            <button class="btn btn-info btn-sm" onclick="exportInventory('${inv.location}', '${inv.date}')">📄 Export</button>
                            <button class="btn btn-danger btn-sm" onclick="deleteSavedInventory('${inv.location}', '${inv.date}')">🗑️</button>
                        </div>
                    `;
                    container.appendChild(div);
                });
                
                if (filtered.length === 0) {
                    container.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 40px;">No saved inventories found</p>';
                }
            } catch (error) {
                console.error('Error loading saved inventories:', error);
            }
        }
        
        function filterSaved(location) {
            filterLocation = location;
            document.querySelectorAll('#saved-tab .location-buttons .btn-location').forEach(btn => {
                btn.classList.remove('active');
                if (btn.textContent === location || (location === 'All' && btn.textContent === 'All')) {
                    btn.classList.add('active');
                }
            });
            loadSavedInventories();
        }
        
        function loadSavedInventory(location, date) {
            currentLocation = location;
            document.getElementById('currentDate').value = date;
            setLocation(location);
            showTab('entry');
            // Trigger the tab switch
            document.querySelector('.tab').click();
        }
        
        async function deleteSavedInventory(location, date) {
            if (!confirm(`Delete inventory for ${location} on ${date}?`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/inventory/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ location, date })
                });
                
                const result = await response.json();
                if (result.success) {
                    loadSavedInventories();
                    setStatus('✅ Inventory deleted');
                }
            } catch (error) {
                console.error('Error:', error);
            }
        }
        
        function exportInventory(location, date) {
            window.location.href = `/api/inventory/export/${location}/${date}`;
            setStatus(`📄 Exporting inventory for ${location} on ${date}`);
        }
        
        async function generateReport(type) {
            const reportContent = document.getElementById('reportContent');
            
            if (type === 'summary') {
                try {
                    const response = await fetch('/api/reports/summary');
                    const data = await response.json();
                    
                    let html = '<h3>Inventory Summary by Location</h3>';
                    for (const [location, info] of Object.entries(data)) {
                        html += `
                            <div style="margin: 20px 0; padding: 15px; background: white; border-radius: 8px;">
                                <h4>${location}</h4>
                                <p>Total Entries: <strong>${info.total_entries}</strong></p>
                                ${info.latest ? `<p>Latest: ${info.latest}</p>` : ''}
                                ${info.oldest ? `<p>Oldest: ${info.oldest}</p>` : ''}
                            </div>
                        `;
                    }
                    reportContent.innerHTML = html;
                } catch (error) {
                    reportContent.innerHTML = '<p>Error loading report</p>';
                }
            } else {
                reportContent.innerHTML = `<p>${type.charAt(0).toUpperCase() + type.slice(1)} report - Feature coming soon!</p>`;
            }
        }
        
        function generateOrder() {
            alert('Generate Order Feature\\n\\nThis will integrate with productmixextraction.py to generate food orders based on inventory data.\\n\\nComing soon!');
        }
        
        function setStatus(message) {
            document.getElementById('statusMessage').textContent = message;
        }
        
        // Update date when changed
        document.getElementById('currentDate').addEventListener('change', function() {
            currentDate = this.value;
            loadInventory();
        });
        
        // Product Management Functions
        function showAddProductForm() {
            document.getElementById('addProductForm').style.display = 'block';
            document.getElementById('uploadForm').style.display = 'none';
            document.getElementById('productHistory').style.display = 'none';
        }
        
        function hideAddProductForm() {
            document.getElementById('addProductForm').style.display = 'none';
            // Clear form
            document.getElementById('newProductNumber').value = '';
            document.getElementById('newProductDescription').value = '';
            document.getElementById('newProductBrand').value = '';
            document.getElementById('newProductSize').value = '';
        }
        
        function showUploadForm() {
            document.getElementById('uploadForm').style.display = 'block';
            document.getElementById('addProductForm').style.display = 'none';
            document.getElementById('productHistory').style.display = 'none';
        }
        
        function hideUploadForm() {
            document.getElementById('uploadForm').style.display = 'none';
            document.getElementById('csvFile').value = '';
        }
        
        async function addProduct() {
            const productNumber = document.getElementById('newProductNumber').value;
            const description = document.getElementById('newProductDescription').value;
            const brand = document.getElementById('newProductBrand').value;
            const packageSize = document.getElementById('newProductSize').value;
            
            if (!productNumber || !description) {
                alert('Product Number and Description are required!');
                return;
            }
            
            try {
                const response = await fetch('/api/products/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        product_number: productNumber,
                        description: description,
                        brand: brand,
                        package_size: packageSize
                    })
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('✅ Product added successfully!');
                    hideAddProductForm();
                    loadProducts();
                    displayProductList();
                } else {
                    alert('❌ ' + result.message);
                }
            } catch (error) {
                alert('❌ Error adding product');
            }
        }
        
        async function updateProduct(productNumber) {
            const description = prompt('New Description:');
            const brand = prompt('New Brand:');
            const packageSize = prompt('New Package Size:');
            
            if (!description && !brand && !packageSize) {
                return;
            }
            
            try {
                const response = await fetch('/api/products/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        product_number: productNumber,
                        description: description,
                        brand: brand,
                        package_size: packageSize
                    })
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('✅ Product updated!');
                    loadProducts();
                    displayProductList();
                }
            } catch (error) {
                alert('❌ Error updating product');
            }
        }
        
        async function deleteProduct(productNumber) {
            if (!confirm('Delete this product?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/products/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ product_number: productNumber })
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('✅ Product deleted!');
                    loadProducts();
                    displayProductList();
                }
            } catch (error) {
                alert('❌ Error deleting product');
            }
        }
        
        function displayProductList() {
            const tbody = document.getElementById('productListBody');
            tbody.innerHTML = '';
            
            allProducts.forEach(product => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${product['Product Number'] || ''}</td>
                    <td>${product['Product Description'] || ''}</td>
                    <td>${product['Product Brand'] || ''}</td>
                    <td>${product['Product Package Size'] || ''}</td>
                    <td>
                        <button class="btn btn-warning btn-sm" onclick="updateProduct('${product['Product Number']}')">✏️ Edit</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteProduct('${product['Product Number']}')">🗑️ Delete</button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
        
        function filterProductList() {
            const searchTerm = document.getElementById('productSearchInput').value.toLowerCase();
            const tbody = document.getElementById('productListBody');
            tbody.innerHTML = '';
            
            const filtered = allProducts.filter(product => {
                return (
                    (product['Product Number'] || '').toString().toLowerCase().includes(searchTerm) ||
                    (product['Product Description'] || '').toLowerCase().includes(searchTerm) ||
                    (product['Product Brand'] || '').toLowerCase().includes(searchTerm)
                );
            });
            
            filtered.forEach(product => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${product['Product Number'] || ''}</td>
                    <td>${product['Product Description'] || ''}</td>
                    <td>${product['Product Brand'] || ''}</td>
                    <td>${product['Product Package Size'] || ''}</td>
                    <td>
                        <button class="btn btn-warning btn-sm" onclick="updateProduct('${product['Product Number']}')">✏️ Edit</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteProduct('${product['Product Number']}')">🗑️ Delete</button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
        
        async function uploadCSV() {
            const fileInput = document.getElementById('csvFile');
            if (!fileInput.files[0]) {
                alert('Please select a CSV file');
                return;
            }
            
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            
            try {
                const response = await fetch('/api/products/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                if (result.success) {
                    alert('✅ ' + result.message);
                    hideUploadForm();
                    loadProducts();
                    displayProductList();
                } else {
                    alert('❌ ' + result.message);
                }
            } catch (error) {
                alert('❌ Error uploading file');
            }
        }
        
        async function viewProductHistory() {
            document.getElementById('productHistory').style.display = 'block';
            document.getElementById('addProductForm').style.display = 'none';
            document.getElementById('uploadForm').style.display = 'none';
            
            try {
                const response = await fetch('/api/products/history');
                const files = await response.json();
                
                const historyList = document.getElementById('historyList');
                historyList.innerHTML = '';
                
                files.forEach(file => {
                    const div = document.createElement('div');
                    div.className = 'saved-item';
                    div.innerHTML = `
                        <div class="saved-item-info">
                            <strong>${file.filename}</strong>
                            <span style="color: #6c757d; margin-left: 10px;">${file.date}</span>
                            <span style="color: #6c757d; margin-left: 10px;">${(file.size / 1024).toFixed(2)} KB</span>
                        </div>
                    `;
                    historyList.appendChild(div);
                });
                
                if (files.length === 0) {
                    historyList.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 20px;">No backup history found</p>';
                }
            } catch (error) {
                alert('❌ Error loading history');
            }
        }
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/products')
def get_products():
    """Get all products"""
    return jsonify(products_list)


@app.route('/api/inventory/<location>/<date_str>')
def get_inventory(location, date_str):
    """Get inventory for specific location and date"""
    if location in inventory_data and date_str in inventory_data[location]:
        return jsonify(inventory_data[location][date_str])
    return jsonify({})


@app.route('/api/inventory/save', methods=['POST'])
def save_inventory():
    """Save inventory data"""
    data = request.json
    location = data.get('location')
    date_str = data.get('date')
    inventory = data.get('inventory', {})
    
    if location not in inventory_data:
        inventory_data[location] = {}
    
    inventory_data[location][date_str] = inventory
    
    if save_inventory_database():
        return jsonify({'success': True, 'message': f'Saved {len(inventory)} items'})
    return jsonify({'success': False, 'message': 'Failed to save'}), 500


@app.route('/api/inventory/list')
def list_inventories():
    """List all saved inventories"""
    items = []
    for location, dates in inventory_data.items():
        for date_str, inventory in dates.items():
            items.append({
                'location': location,
                'date': date_str,
                'count': len(inventory)
            })
    
    items.sort(key=lambda x: x['date'], reverse=True)
    return jsonify(items)


@app.route('/api/inventory/delete', methods=['POST'])
def delete_inventory():
    """Delete inventory"""
    data = request.json
    location = data.get('location')
    date_str = data.get('date')
    
    if location in inventory_data and date_str in inventory_data[location]:
        del inventory_data[location][date_str]
        save_inventory_database()
        return jsonify({'success': True, 'message': 'Deleted successfully'})
    
    return jsonify({'success': False, 'message': 'Not found'}), 404


@app.route('/api/inventory/export/<location>/<date_str>')
def export_inventory(location, date_str):
    """Export inventory to CSV"""
    if location not in inventory_data or date_str not in inventory_data[location]:
        return jsonify({'error': 'Not found'}), 404
    
    inventory = inventory_data[location][date_str]
    
    data = []
    for product in products_list:
        product_num = str(product.get('Product Number', ''))
        if product_num in inventory:
            data.append({
                'Location': location,
                'Date': date_str,
                'Product Number': product_num,
                'Description': product.get('Product Description', ''),
                'Brand': product.get('Product Brand', ''),
                'Package Size': product.get('Product Package Size', ''),
                'Quantity': inventory[product_num]
            })
    
    df = pd.DataFrame(data)
    
    filename = f'inventory_{location}_{date_str}.csv'
    filepath = os.path.join(data_dir, filename)
    df.to_csv(filepath, index=False)
    
    return send_file(filepath, as_attachment=True, download_name=filename)


@app.route('/api/reports/summary')
def report_summary():
    """Generate summary report"""
    summary = {}
    for location in ['Kingsville', 'Alice']:
        if location in inventory_data:
            dates = list(inventory_data[location].keys())
            summary[location] = {
                'total_entries': len(dates),
                'latest': max(dates) if dates else None,
                'oldest': min(dates) if dates else None
            }
        else:
            summary[location] = {'total_entries': 0}
    
    return jsonify(summary)


@app.route('/api/products/add', methods=['POST'])
def add_product():
    """Add new product to list"""
    global products_list
    data = request.json
    
    # Add new product
    new_product = {
        'Product Number': data.get('product_number', ''),
        'Product Description': data.get('description', ''),
        'Product Brand': data.get('brand', ''),
        'Product Package Size': data.get('package_size', '')
    }
    
    products_list.append(new_product)
    
    # Save to CSV
    if save_products_to_csv():
        return jsonify({'success': True, 'message': 'Product added successfully'})
    return jsonify({'success': False, 'message': 'Failed to save'}), 500


@app.route('/api/products/update', methods=['POST'])
def update_product():
    """Update existing product"""
    global products_list
    data = request.json
    product_number = data.get('product_number')
    
    # Find and update product
    for product in products_list:
        if str(product.get('Product Number')) == str(product_number):
            product['Product Description'] = data.get('description', product.get('Product Description'))
            product['Product Brand'] = data.get('brand', product.get('Product Brand'))
            product['Product Package Size'] = data.get('package_size', product.get('Product Package Size'))
            
            # Save to CSV
            if save_products_to_csv():
                return jsonify({'success': True, 'message': 'Product updated successfully'})
            return jsonify({'success': False, 'message': 'Failed to save'}), 500
    
    return jsonify({'success': False, 'message': 'Product not found'}), 404


@app.route('/api/products/delete', methods=['POST'])
def delete_product():
    """Delete product from list"""
    global products_list
    data = request.json
    product_number = data.get('product_number')
    
    # Find and remove product
    products_list = [p for p in products_list if str(p.get('Product Number')) != str(product_number)]
    
    # Save to CSV
    if save_products_to_csv():
        return jsonify({'success': True, 'message': 'Product deleted successfully'})
    return jsonify({'success': False, 'message': 'Failed to save'}), 500


@app.route('/api/products/history')
def product_history():
    """Get list of all product list backups"""
    try:
        backup_dir = os.path.join(data_dir, 'product_lists')
        if not os.path.exists(backup_dir):
            return jsonify([])
        
        files = []
        for filename in os.listdir(backup_dir):
            if filename.endswith('.csv') or filename.endswith('.json'):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                files.append({
                    'filename': filename,
                    'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'size': stat.st_size
                })
        
        files.sort(key=lambda x: x['date'], reverse=True)
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/products/upload', methods=['POST'])
def upload_products():
    """Upload new product CSV file"""
    global products_list
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'message': 'Only CSV files allowed'}), 400
    
    try:
        # Read uploaded CSV
        df = pd.read_csv(file)
        
        # Validate required columns
        required_cols = ['Product Number', 'Product Description', 'Product Brand', 'Product Package Size']
        if not all(col in df.columns for col in required_cols):
            return jsonify({'success': False, 'message': 'CSV missing required columns'}), 400
        
        # Update products list
        products_list = df[required_cols].to_dict('records')
        
        # Save to main CSV file
        if save_products_to_csv():
            return jsonify({'success': True, 'message': f'Loaded {len(products_list)} products'})
        return jsonify({'success': False, 'message': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🏪 Inventory Control System - Web Version")
    print("=" * 60)
    print("\nServer starting...")
    print("Access the application at: http://localhost:5002")
    print("Or from another device: http://YOUR_IP:5002")
    print("\nPress CTRL+C to stop the server")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5002)
