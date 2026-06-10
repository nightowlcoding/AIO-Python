"""
Mobile Inventory Sync Bridge - Test Script

This script simulates a mobile device syncing inventory items to the bridge.
It tests all major endpoints and validates the synchronization workflow.

Usage:
    python test_mobile_sync_bridge.py
    
Environment Variables (optional):
    MOBILE_SYNC_API_TOKEN - The API token (if not set, uses bridge-generated token)
    BRIDGE_HOST - Bridge host (default: 127.0.0.1)
    BRIDGE_PORT - Bridge port (default: 5004)
"""

import requests
import json
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any

# Configuration
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 5004
BRIDGE_BASE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"

# Endpoints
ENDPOINTS = {
    'health': '/api/health',
    'token_info': '/api/token-info',
    'mobile_sheet': '/api/inventory/mobile-sheet',
    'mobile_sync': '/api/inventory/mobile-sync',
}

# Test data
TEST_LOCATION = "Test Counter"
TEST_DATE = (datetime.now() - timedelta(days=0)).strftime("%Y-%m-%d")

# Sample inventory counts for testing
TEST_INVENTORY_COUNTS = {
    "PROD001": 10,
    "PROD002": 25,
    "PROD003": 5,
    "PROD004": 30,
    "PROD005": 15,
}

# ANSI color codes for terminal output
class Color:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str) -> None:
    """Print a formatted header"""
    print(f"\n{Color.HEADER}{Color.BOLD}{text}{Color.ENDC}")
    print("=" * 70)


def print_success(text: str) -> None:
    """Print success message"""
    print(f"{Color.OKGREEN}✓ {text}{Color.ENDC}")


def print_error(text: str) -> None:
    """Print error message"""
    print(f"{Color.FAIL}✗ {text}{Color.ENDC}")


def print_warning(text: str) -> None:
    """Print warning message"""
    print(f"{Color.WARNING}⚠ {text}{Color.ENDC}")


def print_info(text: str) -> None:
    """Print info message"""
    print(f"{Color.OKCYAN}ℹ {text}{Color.ENDC}")


def print_json(data: Any, indent: int = 2) -> None:
    """Pretty print JSON data"""
    print(json.dumps(data, indent=indent))


def test_bridge_connectivity() -> Tuple[bool, str]:
    """Test if the bridge is reachable"""
    print_header("Step 1: Testing Bridge Connectivity")
    
    try:
        response = requests.get(
            f"{BRIDGE_BASE_URL}{ENDPOINTS['health']}",
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Bridge is running on {BRIDGE_HOST}:{BRIDGE_PORT}")
            print_info(f"Service: {data.get('service', 'N/A')}")
            print_info(f"Status: {data.get('status', 'N/A')}")
            print_info(f"Authentication Required: {data.get('requires_auth', False)}")
            return True, None
        else:
            error = f"HTTP {response.status_code}: {response.text}"
            print_error(f"Bridge returned error: {error}")
            return False, error
            
    except requests.ConnectionError as e:
        error = f"Connection refused - is the bridge running? {str(e)}"
        print_error(error)
        return False, error
    except Exception as e:
        error = f"Connection error: {str(e)}"
        print_error(error)
        return False, error


def retrieve_api_token() -> Tuple[bool, str]:
    """Retrieve API token information from the bridge"""
    print_header("Step 2: Retrieving API Token Information")
    
    try:
        response = requests.get(
            f"{BRIDGE_BASE_URL}{ENDPOINTS['token_info']}",
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            token_prefix = data.get('token_prefix', 'N/A')
            print_success(f"Token Info: {token_prefix}")
            print_info(f"Message: {data.get('note', 'N/A')}")
            
            # In a real scenario, you'd get the token from secure storage
            # For testing, we'll use a placeholder - in practice this comes from the bridge startup
            print_warning("Note: For testing, the full token should be obtained from bridge startup logs")
            
            return True, token_prefix
        else:
            error = f"HTTP {response.status_code}: {response.text}"
            print_error(f"Failed to get token info: {error}")
            return False, None
            
    except Exception as e:
        error = f"Error retrieving token: {str(e)}"
        print_error(error)
        return False, None


def fetch_mobile_sheet(api_token: str = None) -> Tuple[bool, List[Dict]]:
    """Fetch the mobile inventory sheet (GET endpoint)"""
    print_header("Step 3: Fetching Mobile Inventory Sheet")
    
    try:
        headers = {'Accept': 'application/json'}
        if api_token:
            headers['Authorization'] = f'Bearer {api_token}'
        
        response = requests.get(
            f"{BRIDGE_BASE_URL}{ENDPOINTS['mobile_sheet']}",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('success'):
                products = data.get('products', [])
                print_success(f"Retrieved {len(products)} products from inventory")
                
                if products:
                    print_info("Sample products:")
                    for i, product in enumerate(products[:3], 1):
                        print(f"  {i}. {product.get('name')} (ID: {product.get('item_id')})")
                        print(f"     - Par Level: {product.get('par_level')}")
                        print(f"     - Current: {product.get('current_on_hand')}")
                        print(f"     - Suggested: {product.get('suggested_qty')}")
                
                return True, products
            else:
                error = data.get('message', 'Unknown error')
                print_error(f"API returned error: {error}")
                return False, []
        else:
            error = f"HTTP {response.status_code}: {response.text}"
            print_error(f"Failed to fetch inventory sheet: {error}")
            return False, []
            
    except Exception as e:
        error = f"Error fetching inventory sheet: {str(e)}"
        print_error(error)
        return False, []


def test_mobile_sync_without_token(api_token: str = None) -> Tuple[bool, str]:
    """Test that sync endpoint rejects requests without valid token"""
    print_header("Step 4: Testing Authentication (Should Fail)")
    
    try:
        payload = {
            "location": TEST_LOCATION,
            "date": TEST_DATE,
            "counts": TEST_INVENTORY_COUNTS
        }
        
        # Try without token - should fail
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(
            f"{BRIDGE_BASE_URL}{ENDPOINTS['mobile_sync']}",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 401:
            print_success("Authentication correctly enforced (401 Unauthorized)")
            data = response.json()
            print_info(f"Response: {data.get('message', 'N/A')}")
            return True, "Authentication test passed"
        else:
            print_warning(f"Expected 401, got {response.status_code}")
            return False, f"Expected 401 but got {response.status_code}"
            
    except Exception as e:
        print_error(f"Error in authentication test: {str(e)}")
        return False, str(e)


def synchronize_inventory(api_token: str = None) -> Tuple[bool, Dict]:
    """Synchronize inventory counts with the bridge (POST endpoint)"""
    print_header("Step 5: Synchronizing Inventory Counts")
    
    payload = {
        "location": TEST_LOCATION,
        "date": TEST_DATE,
        "counts": TEST_INVENTORY_COUNTS
    }
    
    print_info(f"Location: {payload['location']}")
    print_info(f"Date: {payload['date']}")
    print_info(f"Items to sync: {len(payload['counts'])}")
    
    print("\nDetailed counts:")
    for item_id, qty in payload['counts'].items():
        print(f"  {item_id}: {qty} units")
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Add API token if provided
        if api_token:
            headers['Authorization'] = f'Bearer {api_token}'
            print_info("Using API token for authentication")
        else:
            print_warning("No API token provided - sync will fail")
        
        response = requests.post(
            f"{BRIDGE_BASE_URL}{ENDPOINTS['mobile_sync']}",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        data = response.json()
        
        if response.status_code == 200 and data.get('success'):
            print_success(f"Sync successful!")
            print_info(f"Message: {data.get('message', 'N/A')}")
            print_info(f"Synced at: {data.get('synced_at', 'N/A')}")
            return True, data
        elif response.status_code == 401:
            print_error("Authentication failed - invalid or missing token")
            print_info(f"Response: {data.get('message', 'N/A')}")
            return False, data
        else:
            error = data.get('message', f'HTTP {response.status_code}')
            print_error(f"Sync failed: {error}")
            return False, data
            
    except Exception as e:
        error = f"Error during sync: {str(e)}"
        print_error(error)
        return False, {}


def validate_sync_results(sync_data: Dict) -> Tuple[bool, List[str]]:
    """Validate the sync response"""
    print_header("Step 6: Validating Sync Results")
    
    errors = []
    
    # Check required fields
    required_fields = ['success', 'message', 'synced_at']
    for field in required_fields:
        if field not in sync_data:
            errors.append(f"Missing required field: {field}")
    
    if not errors:
        print_success("All required fields present in response")
        
        # Verify sync details
        synced_count = len(TEST_INVENTORY_COUNTS)
        if f'{synced_count}' in sync_data.get('message', ''):
            print_success(f"Message indicates {synced_count} items were synced")
        
        # Check timestamp format
        synced_at = sync_data.get('synced_at', '')
        if 'Z' in synced_at and 'T' in synced_at:
            print_success(f"Valid ISO 8601 timestamp: {synced_at}")
        else:
            print_warning(f"Timestamp may be invalid: {synced_at}")
        
        return True, errors
    else:
        for error in errors:
            print_error(error)
        return False, errors


def run_full_test_suite(api_token: str = None) -> bool:
    """Run the complete test suite"""
    print(f"\n{Color.BOLD}{Color.HEADER}")
    print("=" * 70)
    print("MOBILE INVENTORY SYNC BRIDGE - TEST SUITE")
    print("=" * 70)
    print(f"Test Timestamp: {datetime.now().isoformat()}")
    print(f"Bridge URL: {BRIDGE_BASE_URL}")
    print(f"{Color.ENDC}\n")
    
    test_results = []
    
    # Test 1: Connectivity
    success, error = test_bridge_connectivity()
    test_results.append(("Bridge Connectivity", success))
    if not success:
        print_error("Cannot continue - bridge is not reachable")
        return False
    
    # Test 2: Token info
    success, token_prefix = retrieve_api_token()
    test_results.append(("Retrieve Token Info", success))
    
    # Test 3: Fetch mobile sheet (no token required)
    success, products = fetch_mobile_sheet()
    test_results.append(("Fetch Mobile Sheet", success))
    
    # Test 4: Authentication enforcement
    success, msg = test_mobile_sync_without_token()
    test_results.append(("Authentication Enforcement", success))
    
    # Test 5: Synchronize with token
    if api_token:
        success, sync_data = synchronize_inventory(api_token)
        test_results.append(("Inventory Synchronization", success))
        
        if success:
            # Test 6: Validate results
            success, errors = validate_sync_results(sync_data)
            test_results.append(("Sync Validation", success))
    else:
        print_warning("Skipping sync test - no API token provided")
        print_info("To run full tests, set MOBILE_SYNC_API_TOKEN environment variable")
    
    # Print summary
    print_header("Test Summary")
    
    passed = sum(1 for _, success in test_results if success)
    total = len(test_results)
    
    for test_name, success in test_results:
        status = f"{Color.OKGREEN}PASS{Color.ENDC}" if success else f"{Color.FAIL}FAIL{Color.ENDC}"
        print(f"  {status} - {test_name}")
    
    print(f"\n{Color.BOLD}Results: {passed}/{total} tests passed{Color.ENDC}\n")
    
    return passed == total


if __name__ == '__main__':
    # Try to get API token from environment
    import os
    api_token = os.environ.get('MOBILE_SYNC_API_TOKEN')
    
    if not api_token:
        print_warning("MOBILE_SYNC_API_TOKEN environment variable not set")
        print_info("The test will run but skip the full synchronization test")
        print_info("To get the token, check the bridge startup logs")
        print_info("Usage: MOBILE_SYNC_API_TOKEN=<token> python test_mobile_sync_bridge.py")
    
    # Run the test suite
    success = run_full_test_suite(api_token)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
