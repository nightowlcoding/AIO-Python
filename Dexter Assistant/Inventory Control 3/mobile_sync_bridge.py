"""
Mobile Inventory Synchronization Bridge

A lightweight Flask app that runs on a separate port (5004) to provide mobile-friendly
inventory synchronization APIs. This bridge imports the parent app's globals
(products_list, inventory_data) without modifying the core app.py.

The bridge runs in a separate daemon thread, so it doesn't block the main application startup.
"""

from flask import Flask, jsonify, request
from pathlib import Path
import threading
import logging
import sys
import json
from datetime import datetime
import os
import secrets
from functools import wraps

# Setup logging
logger = logging.getLogger("mobile_sync_bridge")
logger.setLevel(logging.DEBUG)

# Create a simple console handler for debugging
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Port for the mobile bridge
MOBILE_BRIDGE_PORT = 5004
MOBILE_BRIDGE_HOST = '127.0.0.1'

# API Token for authentication (can be set via environment variable or auto-generated)
MOBILE_SYNC_API_TOKEN = os.environ.get('MOBILE_SYNC_API_TOKEN') or secrets.token_urlsafe(32)


def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Token'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response


def _calculate_suggested_qty(par_level, current_on_hand):
    """Calculate suggested quantity as Par Level - Current On Hand"""
    try:
        par = float(par_level or 0)
        current = float(current_on_hand or 0)
        return max(0, par - current)
    except (TypeError, ValueError):
        return 0


def _get_parent_app_module():
    """
    Import and return the parent app module (__main__).
    This allows access to products_list and inventory_data globals.
    """
    try:
        import __main__
        return __main__
    except Exception as e:
        logger.warning(f"Could not import __main__: {e}")
        return None


def _validate_api_token(f):
    """
    Decorator to validate API token in request headers.
    Checks for 'Authorization: Bearer <token>' or 'X-API-Token: <token>'
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Check Authorization header (Bearer token)
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        
        # Check X-API-Token header
        if not token:
            token = request.headers.get('X-API-Token', '')
        
        # Check query parameter (fallback)
        if not token:
            token = request.args.get('token', '')
        
        if not token or token != MOBILE_SYNC_API_TOKEN:
            logger.warning(f"Unauthorized sync attempt with invalid or missing token")
            return jsonify({
                'success': False,
                'message': 'Unauthorized: Invalid or missing API token'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


def create_mobile_bridge_app():
    """Create and configure the mobile sync bridge Flask app"""
    
    # Setup static and template folders for mobile UI
    root_dir = Path(__file__).resolve().parent
    mobile_dir = root_dir / "mobile"
    
    app = Flask(__name__, static_folder=str(mobile_dir), static_url_path="")
    
    # Add CORS headers to all responses
    @app.after_request
    def apply_cors(response):
        return add_cors_headers(response)
    
    @app.route('/', methods=['GET'])
    def root_redirect():
        """Redirect root to mobile UI"""
        from flask import send_file
        mobile_index = mobile_dir / "index.html"
        if mobile_index.exists():
            return send_file(str(mobile_index))
        return jsonify({'error': 'Mobile UI not found'}), 404
    
    @app.route('/mobile/', methods=['GET'])
    def mobile_ui():
        """Serve the mobile UI index page"""
        from flask import send_file
        mobile_index = mobile_dir / "index.html"
        if mobile_index.exists():
            return send_file(str(mobile_index))
        return jsonify({'error': 'Mobile UI not found'}), 404
    
    @app.route('/mobile/script.js', methods=['GET'])
    def mobile_script():
        """Serve the mobile UI JavaScript"""
        from flask import send_file
        mobile_script = mobile_dir / "script.js"
        if mobile_script.exists():
            return send_file(str(mobile_script), mimetype='application/javascript')
        return jsonify({'error': 'Script not found'}), 404
    
    # Handle OPTIONS requests for CORS preflight
    @app.route('/api/inventory/mobile-sheet', methods=['OPTIONS'])
    @app.route('/api/inventory/mobile-sync', methods=['OPTIONS'])
    @app.route('/api/health', methods=['OPTIONS'])
    @app.route('/api/token-info', methods=['OPTIONS'])
    def handle_preflight():
        return '', 200
    
    @app.route('/api/inventory/mobile-sheet', methods=['GET'])
    def get_mobile_sheet():
        """
        GET /api/inventory/mobile-sheet
        
        Returns a JSON list of products with:
        - item_id: Product identifier
        - name: Product name
        - suggested_qty: Par Level - Current On Hand
        - current_on_hand: Current quantity on hand
        """
        try:
            parent_module = _get_parent_app_module()
            products_list = []
            
            if parent_module:
                products_list = getattr(parent_module, 'products_list', None) or []
            else:
                # Fallback: try to get from globals
                import app as parent_app
                products_list = getattr(parent_app, 'products_list', None) or []
            
            if not isinstance(products_list, list):
                products_list = []
            
            # Transform products to mobile-friendly format
            mobile_products = []
            for product in products_list:
                if not isinstance(product, dict):
                    continue
                
                # Extract relevant fields (using correct IC3 field names)
                item_id = product.get('Product Number') or product.get('item_id') or product.get('id')
                # Try different name field variations
                name = (product.get('Product Description') or 
                       product.get('Description') or 
                       product.get('Product Name') or 
                       product.get('name') or '')
                par_level = product.get('Par Level', 0)
                current_on_hand = product.get('Current On Hand', 0)
                
                suggested_qty = _calculate_suggested_qty(par_level, current_on_hand)
                
                mobile_products.append({
                    'item_id': str(item_id),
                    'name': str(name).strip(),
                    'par_level': float(par_level or 0),
                    'suggested_qty': suggested_qty,
                    'current_on_hand': float(current_on_hand or 0),
                })
            
            logger.info(f"Returning {len(mobile_products)} products to mobile client")
            return jsonify({
                'success': True,
                'count': len(mobile_products),
                'products': mobile_products,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }), 200
        
        except Exception as e:
            logger.error(f"Error in get_mobile_sheet: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f"Error retrieving inventory sheet: {str(e)}"
            }), 500
    
    @app.route('/api/inventory/mobile-sync', methods=['POST'])
    @_validate_api_token
    def mobile_sync():
        """
        POST /api/inventory/mobile-sync
        
        Receives a JSON payload with:
        - location: Location identifier
        - date: Date of the sync (YYYY-MM-DD)
        - counts: Dictionary of {item_id: quantity, ...}
        
        Updates the inventory_data global dictionary and calls save_inventory_database() if available.
        """
        try:
            payload = request.get_json(silent=True) or {}
            
            location = str(payload.get('location', '')).strip()
            date_str = str(payload.get('date', '')).strip()
            counts = payload.get('counts', {})
            
            # Validation
            if not location:
                return jsonify({
                    'success': False,
                    'message': 'location is required'
                }), 400
            
            if not date_str:
                return jsonify({
                    'success': False,
                    'message': 'date is required (format: YYYY-MM-DD)'
                }), 400
            
            if not isinstance(counts, dict):
                return jsonify({
                    'success': False,
                    'message': 'counts must be a dictionary'
                }), 400
            
            logger.info(f"Mobile sync request: location={location}, date={date_str}, item_count={len(counts)}")
            
            parent_module = _get_parent_app_module()
            
            if not parent_module:
                logger.error("Could not access parent app module")
                return jsonify({
                    'success': False,
                    'message': 'Could not access inventory data store'
                }), 500
            
            # Get or initialize inventory_data
            inventory_data = getattr(parent_module, 'inventory_data', None)
            if inventory_data is None:
                inventory_data = {}
                setattr(parent_module, 'inventory_data', inventory_data)
                logger.info("Initialized empty inventory_data in parent module")
            
            if not isinstance(inventory_data, dict):
                logger.error("inventory_data is not a dict")
                return jsonify({
                    'success': False,
                    'message': 'Inventory data store is corrupted'
                }), 500
            
            # Update the inventory data structure
            # Structure: inventory_data[location][date_str] = {item_id: quantity, ...}
            if location not in inventory_data:
                inventory_data[location] = {}
            
            if not isinstance(inventory_data[location], dict):
                inventory_data[location] = {}
            
            # Update the counts for this location and date
            inventory_data[location][date_str] = counts.copy()
            
            logger.info(f"Updated inventory_data['{location}']['{date_str}'] with {len(counts)} items")
            
            # Call save_inventory_database if it exists
            save_func = getattr(parent_module, 'save_inventory_database', None)
            if callable(save_func):
                try:
                    save_func()
                    logger.info("Called save_inventory_database()")
                except Exception as e:
                    logger.error(f"Error calling save_inventory_database: {e}")
                    # Don't fail the sync if save fails - data is still in memory
            
            return jsonify({
                'success': True,
                'message': f'Synced {len(counts)} items for {location} on {date_str}',
                'synced_at': datetime.utcnow().isoformat() + 'Z'
            }), 200
        
        except Exception as e:
            logger.error(f"Error in mobile_sync: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f"Sync error: {str(e)}"
            }), 500
    
    @app.route('/api/locations', methods=['OPTIONS'])
    @app.route('/api/locations', methods=['GET'])
    def get_locations():
        """
        GET /api/locations
        
        Returns a list of available storage locations (categories) from products.
        """
        try:
            parent_module = _get_parent_app_module()
            products_list = []
            
            if parent_module:
                products_list = getattr(parent_module, 'products_list', None) or []
            else:
                # Fallback: try to get from globals
                import app as parent_app
                products_list = getattr(parent_app, 'products_list', None) or []
            
            if not isinstance(products_list, list):
                products_list = []
            
            # Extract unique categories (storage locations) from products
            categories = set()
            for product in products_list:
                if isinstance(product, dict):
                    category = product.get('category') or product.get('Category')
                    if category:
                        categories.add(str(category).strip())
            
            # Sort and return as list
            locations = sorted(list(categories))
            
            logger.info(f"Returning {len(locations)} storage locations")
            return jsonify({
                'success': True,
                'locations': locations,
                'count': len(locations),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }), 200
        
        except Exception as e:
            logger.error(f"Error in get_locations: {e}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f"Error retrieving locations: {str(e)}"
            }), 500
    
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        return jsonify({
            'status': 'ok',
            'service': 'mobile_sync_bridge',
            'port': MOBILE_BRIDGE_PORT,
            'requires_auth': True,
        }), 200
    
    @app.route('/api/token-info', methods=['GET'])
    def token_info():
        """
        Get information about the API token (admin endpoint).
        Returns the first 8 characters of the token for verification.
        """
        token_prefix = MOBILE_SYNC_API_TOKEN[:8]
        return jsonify({
            'status': 'ok',
            'token_prefix': token_prefix + '...',
            'note': 'Use this token in requests with Authorization: Bearer <token> or X-API-Token: <token>',
        }), 200
    
    return app


def run_mobile_sync_bridge():
    """
    Create and run the mobile sync bridge Flask app on port 5004.
    This is designed to run in a separate daemon thread.
    """
    try:
        app = create_mobile_bridge_app()
        logger.info(f"Starting Mobile Sync Bridge on {MOBILE_BRIDGE_HOST}:{MOBILE_BRIDGE_PORT}")
        logger.info(f"API Token (first 8 chars): {MOBILE_SYNC_API_TOKEN[:8]}...")
        logger.info(f"Full token: {MOBILE_SYNC_API_TOKEN}")
        logger.info(f"Health check: http://{MOBILE_BRIDGE_HOST}:{MOBILE_BRIDGE_PORT}/api/health")
        logger.info(f"Mobile UI: http://{MOBILE_BRIDGE_HOST}:{MOBILE_BRIDGE_PORT}/mobile/")
        app.run(host=MOBILE_BRIDGE_HOST, port=MOBILE_BRIDGE_PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start mobile sync bridge: {e}", exc_info=True)


def start_mobile_sync_bridge_thread():
    """
    Start the mobile sync bridge in a separate daemon thread.
    Call this from the main app to launch the bridge without blocking.
    
    Usage in main app:
        from mobile_sync_bridge import start_mobile_sync_bridge_thread
        start_mobile_sync_bridge_thread()
    """
    bridge_thread = threading.Thread(
        target=run_mobile_sync_bridge,
        name="MobileSyncBridge",
        daemon=True
    )
    bridge_thread.start()
    logger.info("Mobile Sync Bridge thread started (daemon)")
    return bridge_thread


if __name__ == '__main__':
    # Direct execution for testing
    logger.info("Running Mobile Sync Bridge in standalone mode")
    run_mobile_sync_bridge()
