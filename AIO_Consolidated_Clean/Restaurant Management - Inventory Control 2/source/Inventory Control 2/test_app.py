#!/usr/bin/env python3
"""
Test script for Inventory Control System
Tests all API endpoints and functionality
"""

import requests
import json
from datetime import date

BASE_URL = "http://localhost:5002"

def test_endpoint(name, method, url, data=None, expected_status=200):
    """Test a single endpoint"""
    try:
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        
        status = "✅ PASS" if response.status_code == expected_status else f"❌ FAIL (Status: {response.status_code})"
        print(f"{status} - {name}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, list):
                    print(f"   └─ Returned {len(result)} items")
                elif isinstance(result, dict):
                    print(f"   └─ Keys: {list(result.keys())}")
            except:
                print(f"   └─ HTML Response (length: {len(response.text)})")
        
        return response.status_code == expected_status
    except Exception as e:
        print(f"❌ ERROR - {name}: {str(e)}")
        return False

def main():
    print("\n" + "="*60)
    print("🧪 INVENTORY CONTROL SYSTEM - COMPREHENSIVE TEST")
    print("="*60 + "\n")
    
    results = []
    
    # Test 1: Main Page
    print("📄 MAIN APPLICATION")
    print("-" * 60)
    results.append(test_endpoint("Main Page Load", "GET", f"{BASE_URL}/"))
    print()
    
    # Test 2: Products API
    print("📦 PRODUCTS ENDPOINTS")
    print("-" * 60)
    results.append(test_endpoint("Get All Products", "GET", f"{BASE_URL}/api/products"))
    results.append(test_endpoint("Get Product History", "GET", f"{BASE_URL}/api/products/history"))
    
    # Test add product
    new_product = {
        "product_number": "TEST001",
        "description": "Test Product",
        "brand": "Test Brand",
        "package_size": "1 EA"
    }
    results.append(test_endpoint("Add Product", "POST", f"{BASE_URL}/api/products/add", new_product))
    
    # Test update product
    update_product = {
        "product_number": "TEST001",
        "description": "Updated Test Product",
        "brand": "Test Brand Updated",
        "package_size": "2 EA"
    }
    results.append(test_endpoint("Update Product", "POST", f"{BASE_URL}/api/products/update", update_product))
    
    # Test delete product
    delete_product = {"product_number": "TEST001"}
    results.append(test_endpoint("Delete Product", "POST", f"{BASE_URL}/api/products/delete", delete_product))
    print()
    
    # Test 3: Inventory API
    print("📋 INVENTORY ENDPOINTS")
    print("-" * 60)
    
    # Save inventory
    today = str(date.today())
    inventory_data = {
        "location": "Kingsville",
        "date": today,
        "inventory": {
            "1": 5,
            "2": 10,
            "3": 3
        }
    }
    results.append(test_endpoint("Save Inventory", "POST", f"{BASE_URL}/api/inventory/save", inventory_data))
    
    # List inventories
    results.append(test_endpoint("List All Inventories", "GET", f"{BASE_URL}/api/inventory/list"))
    
    # Get specific inventory
    results.append(test_endpoint(
        "Get Inventory (Kingsville, Today)", 
        "GET", 
        f"{BASE_URL}/api/inventory/Kingsville/{today}"
    ))
    
    # Export inventory
    results.append(test_endpoint(
        "Export Inventory", 
        "GET", 
        f"{BASE_URL}/api/inventory/export/Kingsville/{today}"
    ))
    
    # Delete inventory
    delete_inventory = {"location": "Kingsville", "date": today}
    results.append(test_endpoint("Delete Inventory", "POST", f"{BASE_URL}/api/inventory/delete", delete_inventory))
    print()
    
    # Test 4: Reports API
    print("📊 REPORTS ENDPOINTS")
    print("-" * 60)
    results.append(test_endpoint("Get Summary Report", "GET", f"{BASE_URL}/api/reports/summary"))
    print()
    
    # Summary
    print("="*60)
    passed = sum(results)
    total = len(results)
    percentage = (passed/total*100) if total > 0 else 0
    
    print(f"\n📈 TEST SUMMARY")
    print(f"   Passed: {passed}/{total} ({percentage:.1f}%)")
    
    if passed == total:
        print("\n   🎉 ALL TESTS PASSED!")
    else:
        print(f"\n   ⚠️  {total - passed} test(s) failed")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
