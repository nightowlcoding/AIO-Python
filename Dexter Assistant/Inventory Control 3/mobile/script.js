/**
 * Mobile Inventory Sync - Client Script
 * 
 * Handles:
 * - Fetching inventory data from /api/inventory/mobile-sheet
 * - Rendering a form with quantity inputs for each product
 * - Submitting counts to /api/inventory/mobile-sync
 * - Status management and error handling
 */

const CONFIG = {
    BRIDGE_BASE_URL: 'http://127.0.0.1:5004',
    ENDPOINTS: {
        HEALTH: '/api/health',
        TOKEN_INFO: '/api/token-info',
        MOBILE_SHEET: '/api/inventory/mobile-sheet',
        MOBILE_SYNC: '/api/inventory/mobile-sync',
    },
    HEALTH_CHECK_INTERVAL: 5000, // Check bridge health every 5 seconds
    // API Token - Get from environment or local storage
    // In production, this should come from a secure backend
    API_TOKEN: localStorage.getItem('mobile_sync_token') || '',
};

class MobileInventoryApp {
    constructor() {
        this.products = [];
        this.locations = [];
        this.isLoading = false;
        this.isBridgeReady = false;
        this.healthCheckInterval = null;
        this.initializeElements();
        this.setupEventListeners();
        this.initializeDateInput();
        this.checkBridgeHealth();
        this.loadLocations();
        this.loadInventoryData();
    }

    initializeElements() {
        this.elements = {
            token: document.getElementById('token'),
            location: document.getElementById('location'),
            date: document.getElementById('date'),
            productsContainer: document.getElementById('productsContainer'),
            messageContainer: document.getElementById('messageContainer'),
            submitBtn: document.getElementById('submitBtn'),
            resetBtn: document.getElementById('resetBtn'),
            stats: document.getElementById('stats'),
            totalItems: document.getElementById('totalItems'),
            filledItems: document.getElementById('filledItems'),
            bridgeStatus: document.getElementById('bridgeStatus'),
            bridgeStatusText: document.getElementById('bridgeStatusText'),
        };
    }

    setupEventListeners() {
        this.elements.submitBtn.addEventListener('click', () => this.submitCounts());
        this.elements.resetBtn.addEventListener('click', () => this.resetForm());
        document.addEventListener('input', () => this.updateStats());
        
        // Save token to localStorage when changed
        this.elements.token.addEventListener('change', (e) => {
            const token = e.target.value.trim();
            if (token) {
                localStorage.setItem('mobile_sync_token', token);
                CONFIG.API_TOKEN = token;
                console.log('✓ API token saved to browser storage');
            } else {
                localStorage.removeItem('mobile_sync_token');
                CONFIG.API_TOKEN = '';
                console.log('API token cleared');
            }
        });
        
        // Restore token from localStorage on page load
        if (CONFIG.API_TOKEN) {
            this.elements.token.value = CONFIG.API_TOKEN;
        }
    }

    initializeDateInput() {
        // Set date input to today's date
        const today = new Date();
        const year = today.getFullYear();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        this.elements.date.value = `${year}-${month}-${day}`;
    }

    /**
     * Check if the mobile sync bridge is reachable
     */
    async checkBridgeHealth() {
        try {
            const response = await fetch(
                `${CONFIG.BRIDGE_BASE_URL}${CONFIG.ENDPOINTS.HEALTH}`,
                { method: 'GET', timeout: 2000 }
            );
            
            if (response.ok) {
                this.isBridgeReady = true;
                this.updateBridgeStatus(true);
                console.log('✓ Mobile sync bridge is ready');
                
                // Try to fetch and cache the API token if not already set
                if (!CONFIG.API_TOKEN) {
                    await this.fetchAndCacheToken();
                }
                
                // Start periodic health checks
                if (!this.healthCheckInterval) {
                    this.healthCheckInterval = setInterval(
                        () => this.checkBridgeHealth(),
                        CONFIG.HEALTH_CHECK_INTERVAL
                    );
                }
                return true;
            }
        } catch (error) {
            this.isBridgeReady = false;
            this.updateBridgeStatus(false);
            console.warn('⚠ Mobile sync bridge is not responding', error.message);
        }
        return false;
    }

    /**
     * Fetch and cache the API token from the bridge
     */
    async fetchAndCacheToken() {
        try {
            const response = await fetch(
                `${CONFIG.BRIDGE_BASE_URL}${CONFIG.ENDPOINTS.TOKEN_INFO}`,
                { method: 'GET', timeout: 2000 }
            );
            
            if (response.ok) {
                const data = await response.json();
                console.log('✓ Token info retrieved:', data.token_prefix);
                // Note: In a real implementation, the token should be fetched from a secure endpoint
                // For now, we're just acknowledging that authentication is required
            }
        } catch (error) {
            console.warn('Could not fetch token info:', error.message);
        }
    }

    updateBridgeStatus(isReady) {
        const statusEl = this.elements.bridgeStatus;
        const textEl = this.elements.bridgeStatusText;
        
        if (isReady) {
            statusEl.className = 'status-indicator ready';
            textEl.textContent = 'Bridge Connected';
        } else {
            statusEl.className = 'status-indicator error';
            textEl.textContent = 'Bridge Offline';
        }
    }

    /**
     * Load available locations from the locations endpoint
     */
    async loadLocations() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

            const response = await fetch(
                `${CONFIG.BRIDGE_BASE_URL}/api/locations`,
                {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                    signal: controller.signal,
                }
            );

            clearTimeout(timeoutId);

            if (!response.ok) {
                console.warn(`Could not load locations: HTTP ${response.status}`);
                return;
            }

            const data = await response.json();

            if (data.success && Array.isArray(data.locations)) {
                this.locations = data.locations;
                console.log(`✓ Loaded ${this.locations.length} locations`);
                this.populateLocationDropdown();
            }
        } catch (error) {
            console.warn('Error loading locations:', error.message);
        }
    }

    /**
     * Populate the location dropdown with available locations
     */
    populateLocationDropdown() {
        const locationSelect = this.elements.location;
        
        // Keep the default option
        const defaultOption = locationSelect.querySelector('option[value=""]');
        
        // Clear all options except the default
        while (locationSelect.options.length > 1) {
            locationSelect.remove(1);
        }
        
        // Add location options
        this.locations.forEach(location => {
            const option = document.createElement('option');
            option.value = location;
            option.textContent = location;
            locationSelect.appendChild(option);
        });
        
        console.log(`✓ Populated location dropdown with ${this.locations.length} locations`);
    }

    /**
     * Load inventory data from the mobile sheet endpoint
     */
    async loadInventoryData() {
        if (!this.isBridgeReady) {
            this.showMessage('Waiting for bridge to connect...', 'loading');
            // Retry after 2 seconds
            setTimeout(() => this.loadInventoryData(), 2000);
            return;
        }

        this.isLoading = true;
        this.showMessage('Loading inventory data...', 'loading');

        try {
            // Create an AbortController for timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

            const response = await fetch(
                `${CONFIG.BRIDGE_BASE_URL}${CONFIG.ENDPOINTS.MOBILE_SHEET}`,
                {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                    signal: controller.signal,
                }
            );

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.success && Array.isArray(data.products)) {
                this.products = data.products;
                console.log(`✓ Loaded ${this.products.length} products`);
                this.renderProducts();
                this.hideMessage();
                this.elements.stats.style.display = 'grid';
                this.updateStats();
            } else {
                throw new Error(data.message || 'Invalid response format');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                error.message = 'Request timeout - bridge is not responding quickly';
            }
            console.error('Error loading inventory data:', error);
            this.showMessage(
                `Failed to load inventory: ${error.message}. Retrying...`,
                'error'
            );
            
            // Retry after 3 seconds
            setTimeout(() => this.loadInventoryData(), 3000);
        } finally {
            this.isLoading = false;
        }
    }

    /**
     * Render the products list with quantity inputs
     */
    renderProducts() {
        if (this.products.length === 0) {
            this.elements.productsContainer.innerHTML = `
                <div class="empty-state">
                    <div style="font-size: 48px;">📭</div>
                    <p>No inventory items found</p>
                </div>
            `;
            return;
        }

        const html = `
            <div class="products-list">
                ${this.products.map((product) => `
                    <div class="product-item">
                        <div class="product-info">
                            <div class="product-name">${this.escapeHtml(product.name || 'Unknown')}</div>
                            <div class="product-id">ID: ${this.escapeHtml(product.item_id)}</div>
                            <div class="product-par">
                                <span class="par-badge">Par: ${product.par_level || 0}</span>
                                <span class="par-badge">Current: ${product.current_on_hand || 0}</span>
                                <span class="par-badge suggested-qty">Suggest: ${product.suggested_qty}</span>
                            </div>
                        </div>
                        <div class="product-input">
                            <input 
                                type="number" 
                                class="product-qty" 
                                data-item-id="${this.escapeHtml(product.item_id)}"
                                placeholder="0"
                                min="0"
                                step="0.1"
                            >
                            <div class="unit">units</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        this.elements.productsContainer.innerHTML = html;
    }

    /**
     * Update statistics (items loaded, filled in)
     */
    updateStats() {
        const inputs = document.querySelectorAll('.product-qty');
        const filledCount = Array.from(inputs).filter(
            (input) => input.value && input.value.trim() !== ''
        ).length;

        this.elements.totalItems.textContent = this.products.length;
        this.elements.filledItems.textContent = filledCount;
    }

    /**
     * Collect all quantity inputs into a counts dictionary
     */
    collectCounts() {
        const counts = {};
        const inputs = document.querySelectorAll('.product-qty');

        inputs.forEach((input) => {
            const itemId = input.dataset.itemId;
            const value = input.value.trim();

            if (value) {
                try {
                    counts[itemId] = parseFloat(value);
                } catch (e) {
                    console.warn(`Invalid quantity for ${itemId}: ${value}`);
                }
            }
        });

        return counts;
    }

    /**
     * Validate form inputs
     */
    validateForm() {
        const location = this.elements.location.value.trim();
        const date = this.elements.date.value.trim();
        const counts = this.collectCounts();

        const errors = [];

        if (!location) {
            errors.push('Location is required');
        }

        if (!date) {
            errors.push('Date is required');
        }

        if (Object.keys(counts).length === 0) {
            errors.push('Enter at least one quantity');
        }

        return { isValid: errors.length === 0, errors, location, date, counts };
    }

    /**
     * Submit the inventory counts to the bridge
     */
    async submitCounts() {
        if (this.isLoading || !this.isBridgeReady) {
            this.showMessage('Bridge is not ready. Please wait...', 'error');
            return;
        }

        const validation = this.validateForm();

        if (!validation.isValid) {
            this.showMessage(
                `Validation errors: ${validation.errors.join(', ')}`,
                'error'
            );
            return;
        }

        this.isLoading = true;
        this.elements.submitBtn.disabled = true;
        this.showMessage('Syncing inventory...', 'loading');

        try {
            const payload = {
                location: validation.location,
                date: validation.date,
                counts: validation.counts,
            };

            console.log('Submitting payload:', payload);

            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            };

            // Add API token to headers if available
            if (CONFIG.API_TOKEN) {
                headers['Authorization'] = `Bearer ${CONFIG.API_TOKEN}`;
            }

            const response = await fetch(
                `${CONFIG.BRIDGE_BASE_URL}${CONFIG.ENDPOINTS.MOBILE_SYNC}`,
                {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload),
                }
            );

            const data = await response.json();

            if (response.ok && data.success) {
                console.log('✓ Sync successful:', data);
                this.showMessage(
                    `✓ ${data.message}`,
                    'success'
                );
                
                // Show summary
                const summary = `Synced ${Object.keys(validation.counts).length} items for "${validation.location}" on ${validation.date}`;
                console.log('Sync summary:', summary);
                
                // Reset form after 2 seconds
                setTimeout(() => {
                    this.resetForm();
                }, 2000);
            } else if (response.status === 401) {
                throw new Error('Unauthorized: Invalid or missing API token. Contact administrator for access.');
            } else {
                throw new Error(data.message || 'Unknown error');
            }
        } catch (error) {
            console.error('Error submitting counts:', error);
            this.showMessage(
                `Sync failed: ${error.message}`,
                'error'
            );
        } finally {
            this.isLoading = false;
            this.elements.submitBtn.disabled = false;
        }
    }

    /**
     * Reset the form to initial state
     */
    resetForm() {
        // Don't reset token - keep it for convenience
        this.elements.location.value = '';
        this.elements.date.value = this.getFormattedDate(new Date());
        
        const inputs = document.querySelectorAll('.product-qty');
        inputs.forEach((input) => {
            input.value = '';
        });

        this.updateStats();
        this.hideMessage();
        
        // Focus on location field
        this.elements.location.focus();
    }

    /**
     * Format date as YYYY-MM-DD
     */
    getFormattedDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    /**
     * Show a message (error, success, or loading)
     */
    showMessage(message, type = 'info') {
        const messageEl = document.createElement('div');
        messageEl.className = `${type}-message`;
        messageEl.textContent = message;
        messageEl.id = 'message';

        // Remove old message
        const oldMessage = this.elements.messageContainer.querySelector('#message');
        if (oldMessage) {
            oldMessage.remove();
        }

        this.elements.messageContainer.appendChild(messageEl);
    }

    /**
     * Hide the message
     */
    hideMessage() {
        const message = this.elements.messageContainer.querySelector('#message');
        if (message) {
            message.remove();
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new MobileInventoryApp();
    
    // Retry loading data if bridge wasn't ready
    setInterval(() => {
        if (!window.app.isBridgeReady && window.app.products.length === 0) {
            window.app.loadInventoryData();
        }
    }, 10000); // Retry every 10 seconds
});
