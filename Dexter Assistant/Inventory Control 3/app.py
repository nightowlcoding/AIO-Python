from flask import jsonify, request
from pathlib import Path
from collections import defaultdict
from bisect import bisect_left, bisect_right
import json
import marshal
import logging
import os
import re
import sys
from urllib import error as urllib_error
from urllib import request as urllib_request
from datetime import date, datetime, timedelta

ROOT = Path(__file__).resolve().parent
DEXTER_ASSISTANT_DIR = ROOT.parent
if str(DEXTER_ASSISTANT_DIR) not in sys.path:
    sys.path.insert(0, str(DEXTER_ASSISTANT_DIR))

from tenant_scope import resolve_tenant_scope

_IC3_DATA_DIR = os.environ.get("IC3_DATA_DIR")
if _IC3_DATA_DIR:
    import shutil as _shutil
    _ic3_data_path = Path(_IC3_DATA_DIR)
    _ic3_data_path.mkdir(parents=True, exist_ok=True)
    _committed_data = ROOT / "data"

    if _committed_data.is_dir() and not _committed_data.is_symlink():
        # Fresh git deploy: committed data/ dir is present.
        # Seed the persistent disk if it is empty, then replace the directory
        # with a symlink so every code path (bytecode, module-level vars,
        # inline calls) transparently reads/writes the persistent disk.
        if not any(_ic3_data_path.iterdir()):
            for _src in _committed_data.iterdir():
                if _src.is_file():
                    _shutil.copy2(_src, _ic3_data_path / _src.name)
            print(f"[ic3] Seeded persistent disk from committed data")
        _shutil.rmtree(str(_committed_data))
        _committed_data.symlink_to(_ic3_data_path)
        print(f"[ic3] data/ -> {_ic3_data_path}")
    elif not _committed_data.exists():
        # data/ was removed but symlink missing — recreate symlink.
        _committed_data.symlink_to(_ic3_data_path)
        print(f"[ic3] Recreated symlink: data/ -> {_ic3_data_path}")
    # If data/ is already a symlink from a previous restart, nothing to do.

INVOICE_IMPORT_LOG_PATH = ROOT / "data" / "invoice_import_log.json"
PRODUCTMIX_SYNC_CACHE_PATH = ROOT / "data" / "productmix_sync_cache.json"
BYTECODE_FILE = ROOT / "app.pyc"
ICON_CANDIDATES = (
    ROOT / "favicon.ico",
    ROOT / "ic3_icon.ico",
    ROOT / "icon.ico",
    ROOT / "ic3_icon.png",
    ROOT / "icon.png",
)

ORDER_CSV_DATE_PREFIX = re.compile(r"^(\d{4})(\d{2})(\d{2})\d+\.csv$", re.IGNORECASE)


def _read_productmix_sync_cache() -> dict:
    try:
        with PRODUCTMIX_SYNC_CACHE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return {}


def _write_productmix_sync_cache(payload: dict) -> None:
    PRODUCTMIX_SYNC_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PRODUCTMIX_SYNC_CACHE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)


def _normalize_productmix_categories(payload: dict) -> dict:
    categories = payload.get("categories") if isinstance(payload, dict) else []
    if not isinstance(categories, list):
        categories = []

    normalized_rows = []
    for row in categories:
        if not isinstance(row, dict):
            continue

        normalized_rows.append(
            {
                "id": row.get("id"),
                "name": str(row.get("name") or "").strip(),
                "case_quantity": row.get("case_quantity"),
                "is_weight_based": bool(row.get("is_weight_based")),
                "oz_per_piece": row.get("oz_per_piece"),
            }
        )

    return {
        "restaurant": payload.get("restaurant") if isinstance(payload, dict) else None,
        "categories": normalized_rows,
        "category_count": len(normalized_rows),
    }


def _sync_productmix_categories_from_remote(base_url: str, timeout_seconds: float = 12.0, headers: dict | None = None) -> dict:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:5050"
    target_url = f"{base}/api/categories"

    request_headers = {
        "Accept": "application/json",
        "User-Agent": "IC3-ProductMix-Sync/1.0",
    }
    for key, value in (headers or {}).items():
        text = str(value or "").strip()
        if text:
            request_headers[key] = text

    req = urllib_request.Request(
        target_url,
        headers=request_headers,
        method="GET",
    )

    with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
        status_code = int(getattr(response, "status", 200) or 200)
        raw_text = response.read().decode("utf-8", errors="replace")

    if status_code >= 400:
        raise RuntimeError(f"ProductMix responded with status {status_code}")

    parsed = json.loads(raw_text or "{}")
    normalized = _normalize_productmix_categories(parsed)

    return {
        "source_url": target_url,
        "synced_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "status": "ok",
        **normalized,
    }

PRODUCTMIX_SYNC_UI_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3ProductMixSyncUiInstalled) return;
    window.__ic3ProductMixSyncUiInstalled = true;

    const styleId = 'ic3-productmix-sync-style';
    if (!document.getElementById(styleId)) {
        const style = document.createElement('style');
        style.id = styleId;
        style.type = 'text/css';
        style.textContent = [
            '#ic3ProductMixSyncPanel { display: flex; align-items: center; gap: 8px; margin: 10px 0; flex-wrap: wrap; }',
            '#ic3ProductMixSyncButton { min-height: 40px; border: 1px solid #1d4ed8; border-radius: 8px; background: #2563eb; color: #ffffff; font-weight: 700; padding: 8px 12px; cursor: pointer; }',
            '#ic3ProductMixSyncButton[disabled] { opacity: 0.65; cursor: default; }',
            '#ic3ProductMixSyncStatus { font-size: 0.9rem; color: #334155; }',
            '@media (max-width: 768px) {',
            '  #ic3ProductMixSyncPanel { display: grid; grid-template-columns: 1fr; gap: 8px; }',
            '  #ic3ProductMixSyncButton { min-height: 44px; width: 100%; font-size: 1rem; }',
            '}'
        ].join('\n');
        (document.head || document.documentElement).appendChild(style);
    }

    function ensurePanel() {
        const inventoryTab = document.getElementById('inventory');
        const controls = document.querySelector('.inventory-controls-panel') || document.getElementById('categoriesContainer');
        if (!inventoryTab || !controls || !controls.parentNode) {
            return null;
        }

        let panel = document.getElementById('ic3ProductMixSyncPanel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'ic3ProductMixSyncPanel';
            panel.innerHTML = [
                '<button id="ic3ProductMixSyncButton" type="button">Sync ProductMix</button>',
                '<span id="ic3ProductMixSyncStatus">Waiting for first sync check...</span>'
            ].join('');

            if (controls.classList && controls.classList.contains('inventory-controls-panel')) {
                controls.parentNode.insertBefore(panel, controls.nextSibling);
            } else {
                controls.parentNode.insertBefore(panel, controls);
            }
        }

        return panel;
    }

    function setStatus(message, isError) {
        const el = document.getElementById('ic3ProductMixSyncStatus');
        if (!el) return;
        el.textContent = message;
        el.style.color = isError ? '#991b1b' : '#334155';
    }

    function formatLastSync(isoText) {
        const raw = String(isoText || '').trim();
        if (!raw) {
            return 'never';
        }
        const dt = new Date(raw);
        if (Number.isNaN(dt.getTime())) {
            return raw;
        }
        return dt.toLocaleString();
    }

    async function refreshStatus() {
        try {
            const response = await fetch('/api/sync/productmix/status');
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || 'Unable to load sync status');
            }
            const count = Number(payload.category_count || 0);
            const lastSync = formatLastSync(payload.last_sync);
            setStatus('Categories: ' + count + ' | Last sync: ' + lastSync, false);
        } catch (error) {
            setStatus('Status error: ' + error.message, true);
        }
    }

    async function runSync() {
        const button = document.getElementById('ic3ProductMixSyncButton');
        if (!button) return;
        button.disabled = true;
        setStatus('Sync in progress...', false);

        try {
            const response = await fetch('/api/sync/productmix/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || ('Sync failed (' + response.status + ')'));
            }

            const count = Number(payload.category_count || 0);
            const lastSync = formatLastSync(payload.synced_at_utc);
            setStatus('Sync complete. Categories: ' + count + ' | Last sync: ' + lastSync, false);
        } catch (error) {
            setStatus('Sync failed: ' + error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function syncSharedLocations() {
        const selectIds = ['reportLocation', 'location', 'inventoryLocation', 'invoiceLocation', 'bulkInvoiceLocation'];
        try {
            const response = await fetch('/api/shared/restaurants');
            const payload = await response.json();
            const restaurants = Array.isArray(payload && payload.restaurants) ? payload.restaurants : [];
            if (!restaurants.length) return;

            function labelOf(row) {
                const name = String((row && row.name) || '').trim();
                const location = String((row && row.location) || '').trim();
                if (name && location) return name + ' - ' + location;
                return name || location;
            }

            for (const id of selectIds) {
                const select = document.getElementById(id);
                if (!select || select.tagName !== 'SELECT') continue;

                const existing = String(select.value || '').trim();
                const options = ['<option value="">Select Location</option>'];
                for (const row of restaurants) {
                    const label = labelOf(row);
                    const locValue = String(row && row.location || '').trim() || label;
                    if (!label) continue;
                    options.push('<option value="' + locValue.replace(/"/g, '&quot;') + '">' + label + '</option>');
                }
                select.innerHTML = options.join('');

                const values = Array.from(select.options).map(function (opt) { return String(opt.value || ''); });
                if (existing && values.includes(existing)) {
                    select.value = existing;
                } else {
                    const first = values.find(function (v) { return v && v.trim(); }) || '';
                    select.value = first;
                }
            }
        } catch (_error) {
            // Keep existing IC3 behavior if shared restaurants endpoint is unavailable.
        }
    }

    function install() {
        const panel = ensurePanel();
        if (!panel) {
            return;
        }

        const button = document.getElementById('ic3ProductMixSyncButton');
        if (button && button.dataset.ic3SyncBound !== '1') {
            button.dataset.ic3SyncBound = '1';
            button.addEventListener('click', function () {
                runSync();
            });
        }

        refreshStatus();
        syncSharedLocations();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }

    const observer = new MutationObserver(function () {
        if (!document.getElementById('ic3ProductMixSyncPanel')) {
            install();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

LOCATION_OPTIONS_SYNC_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3SharedLocationsInstalled) return;
    window.__ic3SharedLocationsInstalled = true;

    const SELECT_IDS = ['reportLocation', 'location', 'inventoryLocation', 'invoiceLocation', 'bulkInvoiceLocation'];
    let refreshTimer = null;
    let inFlight = false;
    let lastAppliedSignature = '';

    function clearLocationInputsForNoCompanyData() {
        window.__ic3ForceNoLocation = true;

        for (const id of SELECT_IDS) {
            const select = document.getElementById(id);
            if (!select || select.tagName !== 'SELECT') continue;
            select.innerHTML = '<option value="">No locations available</option>';
            select.value = '';
        }

        Array.from(document.querySelectorAll('select')).forEach(function (sel) {
            const marker = ((sel.id || '') + ' ' + (sel.name || '') + ' ' + (sel.className || '')).toLowerCase();
            if (!marker.includes('location')) return;
            sel.innerHTML = '<option value="">No locations available</option>';
            sel.value = '';
        });

        const groups = Array.from(document.querySelectorAll('.location-selector'));
        groups.forEach(function (group) {
            group.innerHTML = '';
            const note = document.createElement('div');
            note.style.color = '#6b7280';
            note.style.fontSize = '13px';
            note.style.padding = '4px 0';
            note.textContent = 'No locations available for selected company.';
            group.appendChild(note);
        });
    }

    function buildLabel(row) {
        const name = String(row && row.name || '').trim();
        const location = String(row && row.location || '').trim();
        if (name && location) return name + ' - ' + location;
        return name || location;
    }

    function buildRadioId(groupIndex, optionIndex, label) {
        const slug = String(label || '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '') || ('loc-' + optionIndex);
        return 'ic3-shared-location-' + groupIndex + '-' + optionIndex + '-' + slug;
    }

    function applyToSelect(select, restaurants, preferredValue) {
        if (!select || !restaurants || !restaurants.length) return;
        const existing = String(select.value || '').trim();

        const opts = ['<option value="">Select Location</option>'];
        for (const row of restaurants) {
            const label = buildLabel(row);
            const locValue = String(row && row.location || '').trim() || label;
            if (!locValue) continue;
            opts.push('<option value="' + locValue.replace(/"/g, '&quot;') + '">' + label + '</option>');
        }
        select.innerHTML = opts.join('');

        const values = Array.from(select.options).map(function (o) { return String(o.value || ''); });
        // Use preferred value if given and valid, then existing, then first.
        const preferred = String(preferredValue || '').trim();
        if (preferred && values.includes(preferred)) {
            select.value = preferred;
        } else if (existing && values.includes(existing)) {
            select.value = existing;
        } else {
            const first = values.find(function (v) { return v && v.trim(); }) || '';
            select.value = first;
        }
    }

    function applyToLocationRadios(restaurants, preferredValue) {
        if (!restaurants || !restaurants.length) return;

        const selected = (document.querySelector('input[name="location"][type="radio"]:checked') || {}).value || '';
        const preferred = String(preferredValue || '').trim();
        const groups = Array.from(document.querySelectorAll('.location-selector'));
        if (!groups.length) return;

        groups.forEach(function (group, groupIndex) {
            const existingRadios = group.querySelectorAll('input[name="location"][type="radio"]');
            if (!existingRadios.length) return;

            group.innerHTML = '';
            let hasChecked = false;

            restaurants.forEach(function (row, optionIndex) {
                const label = buildLabel(row);
                // Use just the location field as the value so IC3 internal
                // location lookups (Alice / Kingsville) continue to work.
                const locValue = String(row && row.location || '').trim() || label;
                if (!locValue) return;

                const wrapper = document.createElement('div');
                wrapper.className = 'location-option';

                const input = document.createElement('input');
                input.type = 'radio';
                input.name = 'location';
                input.value = locValue;
                input.id = buildRadioId(groupIndex, optionIndex, locValue);
                if (preferred && preferred === locValue) {
                    input.checked = true;
                    hasChecked = true;
                } else if (selected && selected === locValue) {
                    input.checked = true;
                    hasChecked = true;
                }

                const text = document.createElement('label');
                text.setAttribute('for', input.id);
                text.textContent = '📍 ' + label;

                input.addEventListener('change', function () {
                    if (!input.checked) return;
                    if (typeof window.setLocation === 'function') {
                        try {
                            window.setLocation(locValue);
                        } catch (_err) {
                            // Keep silent - native state still updates from checked radio.
                        }
                    }
                });

                wrapper.appendChild(input);
                wrapper.appendChild(text);
                group.appendChild(wrapper);
            });

            if (!hasChecked) {
                const first = group.querySelector('input[name="location"][type="radio"]');
                if (first) first.checked = true;
            }
        });
    }

    function computeSignature(restaurants) {
        return (restaurants || []).map(function (row) {
            return String(row && row.location || '').trim() || buildLabel(row);
        }).filter(Boolean).join('|');
    }

    async function refreshLocations() {
        if (inFlight) return;
        inFlight = true;
        try {
            let dexterCompanyName = '';
            let dexterPreferredLocation = '';
            try {
                const ctxRes = await fetch('/api/dexter/context');
                const ctx = await ctxRes.json();
                dexterCompanyName = String((ctx && ctx.company_name) || '').trim();
                dexterPreferredLocation = String((ctx && ctx.restaurant_location) || '').trim();
            } catch (_ctxErr) {
                dexterCompanyName = '';
                dexterPreferredLocation = '';
            }

            const res = await fetch('/api/shared/restaurants');
            const payload = await res.json();
            const restaurants = Array.isArray(payload && payload.restaurants) ? payload.restaurants : [];
            if (!restaurants.length) {
                if (dexterCompanyName) {
                    clearLocationInputsForNoCompanyData();
                }
                return;
            }

            window.__ic3ForceNoLocation = false;

            const signature = computeSignature(restaurants);
            const hasAnySelect = SELECT_IDS.some(function (id) {
                const el = document.getElementById(id);
                return el && el.tagName === 'SELECT';
            });
            const hasAnyDynSelect = Array.from(document.querySelectorAll('select')).some(function (sel) {
                const marker = ((sel.id || '') + ' ' + (sel.name || '') + ' ' + (sel.className || '')).toLowerCase();
                return marker.includes('location');
            });
            const hasAnyRadioGroup = !!document.querySelector('.location-selector input[name="location"][type="radio"]');
            if (!hasAnySelect && !hasAnyDynSelect && !hasAnyRadioGroup) return;

            // Skip pointless re-renders when options list has not changed.
            if (signature && signature === lastAppliedSignature) return;

            for (const id of SELECT_IDS) {
                const select = document.getElementById(id);
                if (select && select.tagName === 'SELECT') {
                    applyToSelect(select, restaurants, dexterPreferredLocation);
                }
            }

            // Also sync any other <select> whose id/name/class contains 'location'
            // (catches Analytics, Forecast, and any future dropdowns not in SELECT_IDS).
            // Use the value from the first synced known select as the preferred location.
            const knownIds = new Set(SELECT_IDS);
            let activeLocation = '';
            for (const id of SELECT_IDS) {
                const el = document.getElementById(id);
                if (el && el.tagName === 'SELECT' && String(el.value || '').trim()) {
                    activeLocation = String(el.value || '').trim();
                    break;
                }
            }
            Array.from(document.querySelectorAll('select')).forEach(function (sel) {
                if (!sel.id && !sel.name && !sel.className) return;
                const marker = ((sel.id || '') + ' ' + (sel.name || '') + ' ' + (sel.className || '')).toLowerCase();
                if (marker.includes('location') && !knownIds.has(sel.id)) {
                    applyToSelect(sel, restaurants, activeLocation);
                }
            });

            applyToLocationRadios(restaurants, dexterPreferredLocation);

            lastAppliedSignature = signature || lastAppliedSignature;

            const prefixInput = document.getElementById('renameLocationPrefix');
            if (prefixInput && !String(prefixInput.value || '').trim()) {
                const first = buildLabel(restaurants[0]);
                if (first) prefixInput.value = first;
            }
        } catch (_err) {
            // Keep existing behavior when shared list is unavailable.
        } finally {
            inFlight = false;
        }
    }

    function scheduleRefresh() {
        if (refreshTimer) {
            clearTimeout(refreshTimer);
        }
        refreshTimer = setTimeout(function () {
            refreshTimer = null;
            refreshLocations();
        }, 250);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleRefresh);
    } else {
        scheduleRefresh();
    }

    const observer = new MutationObserver(function () {
        scheduleRefresh();
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

OVERRIDE_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3InvoiceOverrideInstalled) return;
    window.__ic3InvoiceOverrideInstalled = true;

    const LOCAL_API_ORIGINS = [
        'http://localhost:5003',
        'https://localhost:5003',
        'http://127.0.0.1:5003',
        'https://127.0.0.1:5003',
    ];

    function resolveApiOrigin() {
        const pageOrigin = window.location && typeof window.location.origin === 'string'
            ? window.location.origin
            : '';
        if (pageOrigin && /^https?:/i.test(pageOrigin)) {
            return pageOrigin;
        }
        return LOCAL_API_ORIGINS[0];
    }

    function normalizeApiUrl(resource) {
        if (typeof resource !== 'string') {
            return resource;
        }

        const apiOrigin = resolveApiOrigin();
        for (const origin of LOCAL_API_ORIGINS) {
            if (resource.startsWith(origin + '/api/')) {
                return apiOrigin + resource.slice(origin.length);
            }
        }

        if (resource.startsWith('/api/')) {
            return apiOrigin + resource;
        }

        return resource;
    }

    const originalFetch = window.fetch ? window.fetch.bind(window) : null;
    if (originalFetch) {
        window.fetch = function (resource, init) {
            if (typeof resource === 'string') {
                return originalFetch(normalizeApiUrl(resource), init);
            }

            if (resource instanceof Request) {
                return originalFetch(new Request(normalizeApiUrl(resource.url), resource), init);
            }

            return originalFetch(resource, init);
        };
    }

    const originalXhrOpen = window.XMLHttpRequest && window.XMLHttpRequest.prototype
        ? window.XMLHttpRequest.prototype.open
        : null;
    if (originalXhrOpen) {
        window.XMLHttpRequest.prototype.open = function (method, url) {
            const nextUrl = typeof url === 'string' ? normalizeApiUrl(url) : url;
            return originalXhrOpen.apply(this, [method, nextUrl, ...Array.prototype.slice.call(arguments, 2)]);
        };
    }

    const state = {
        bulkInvoices: [],
        selectedInvoiceImportIds: new Set(),
    };

    function parseDateFromFilename(filename) {
        if (!filename) {
            return new Date().toISOString().split('T')[0];
        }

        let match = filename.match(/(\d{4})[-_/.](\d{2})[-_/.](\d{2})/);
        if (match) {
            return match[1] + '-' + match[2] + '-' + match[3];
        }

        match = filename.match(/(?:^|\D)(\d{4})(\d{2})(\d{2})(?:\D|$)/);
        if (match) {
            return match[1] + '-' + match[2] + '-' + match[3];
        }

        return new Date().toISOString().split('T')[0];
    }

    function getBulkStatusDiv() {
        return document.getElementById('bulkUploadStatus');
    }

    function getInventorySearchInput() {
        return document.querySelector('input[placeholder="Search products..."]');
    }

    function getVisibleInventoryRows() {
        return Array.from(document.querySelectorAll('table tbody tr')).filter((row) => {
            if (!(row instanceof HTMLElement)) {
                return false;
            }

            const style = window.getComputedStyle(row);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return false;
            }

            return !!row.querySelector('input[type="number"]');
        });
    }

    function applyInventorySearchFilter() {
        const searchInput = getInventorySearchInput();
        if (!searchInput) {
            return;
        }

        const query = searchInput.value.trim().toLowerCase();
        const rows = getVisibleInventoryRows();
        rows.forEach((row) => {
            const text = row.innerText.toLowerCase();
            row.style.display = !query || text.includes(query) ? '' : 'none';
        });
    }

    function installInventorySearchFilter() {
        const searchInput = getInventorySearchInput();
        if (!searchInput || searchInput.dataset.ic3SearchPatched === 'true') {
            return;
        }

        const applyFilter = () => window.requestAnimationFrame(applyInventorySearchFilter);
        searchInput.addEventListener('input', applyFilter);
        searchInput.addEventListener('change', applyFilter);
        searchInput.dataset.ic3SearchPatched = 'true';
        applyFilter();
    }

    function isInvoiceHistoryTable(table) {
        const headers = Array.from(table.querySelectorAll('thead th')).map((th) => (th.innerText || '').trim().toLowerCase());
        if (!headers.length) {
            return false;
        }
        return headers.includes('import id') && headers.includes('date/time') && headers.includes('filename') && headers.includes('actions');
    }

    function sortInvoiceHistoryTableRows(table) {
        const headerCells = Array.from(table.querySelectorAll('thead th'));
        if (!headerCells.length) {
            return;
        }

        const normalizeHeader = (text) => String(text || '').trim().toLowerCase().replace(/\s+/g, ' ');
        const headers = headerCells.map((th) => normalizeHeader(th.innerText));
        const deliveryDateIndex = headers.indexOf('delivery date');
        const dateTimeIndex = headers.indexOf('date/time');
        if (deliveryDateIndex < 0) {
            return;
        }

        const tbody = table.querySelector('tbody');
        if (!tbody) {
            return;
        }

        const rows = Array.from(tbody.querySelectorAll('tr'));
        if (rows.length < 2) {
            return;
        }

        const toSortableTime = (raw) => {
            const text = String(raw || '').trim();
            if (!text) {
                return Number.NEGATIVE_INFINITY;
            }

            // Keep YYYY-MM-DD parsing stable across browsers/timezones.
            const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
            if (iso) {
                return Date.UTC(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]), 12, 0, 0);
            }

            const parsed = Date.parse(text);
            return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
        };

        rows.sort((a, b) => {
            const aCells = a.querySelectorAll('td');
            const bCells = b.querySelectorAll('td');

            const aDelivery = toSortableTime(aCells[deliveryDateIndex] ? aCells[deliveryDateIndex].innerText : '');
            const bDelivery = toSortableTime(bCells[deliveryDateIndex] ? bCells[deliveryDateIndex].innerText : '');
            if (aDelivery !== bDelivery) {
                return bDelivery - aDelivery;
            }

            const aTime = toSortableTime(dateTimeIndex >= 0 && aCells[dateTimeIndex] ? aCells[dateTimeIndex].innerText : '');
            const bTime = toSortableTime(dateTimeIndex >= 0 && bCells[dateTimeIndex] ? bCells[dateTimeIndex].innerText : '');
            return bTime - aTime;
        });

        rows.forEach((row) => tbody.appendChild(row));
    }

    function updateInvoiceSelectionUi(table) {
        const panel = table.previousElementSibling;
        const countEl = panel && panel.classList.contains('ic3-invoice-bulk-tools')
            ? panel.querySelector('.ic3-selected-count')
            : null;

        const checkboxes = Array.from(table.querySelectorAll('tbody .ic3-import-checkbox'));
        const selectedCount = checkboxes.filter((cb) => cb.checked).length;
        if (countEl) {
            countEl.textContent = selectedCount + ' selected';
        }

        const headerCheckbox = table.querySelector('thead .ic3-import-select-all');
        if (headerCheckbox) {
            if (!checkboxes.length) {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = false;
            } else if (selectedCount === 0) {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = false;
            } else if (selectedCount === checkboxes.length) {
                headerCheckbox.checked = true;
                headerCheckbox.indeterminate = false;
            } else {
                headerCheckbox.checked = false;
                headerCheckbox.indeterminate = true;
            }
        }
    }

    async function bulkDeleteInvoiceImports(table) {
        const checkboxes = Array.from(table.querySelectorAll('tbody .ic3-import-checkbox:checked'));
        const selectedRows = checkboxes
            .map((cb) => ({ importId: String(cb.dataset.importId || '').trim() }))
            .filter((row) => !!row.importId);
        if (!selectedRows.length) {
            alert('Select at least one invoice import to delete.');
            return;
        }

        if (!confirm('Delete ' + selectedRows.length + ' selected invoice import(s)? This cannot be undone.')) {
            return;
        }

        let successCount = 0;
        const failed = [];

        for (const row of selectedRows) {
            const importId = row.importId;
            try {
                const response = await fetch('/api/invoices/import/' + encodeURIComponent(importId), {
                    method: 'DELETE',
                });
                const payload = await response.json();
                if (response.ok && payload && payload.success) {
                    successCount += 1;
                    state.selectedInvoiceImportIds.delete(importId);
                } else {
                    failed.push(importId + (payload && payload.message ? ' (' + payload.message + ')' : ''));
                }
            } catch (error) {
                failed.push(importId + ' (' + error.message + ')');
            }
        }

        if (successCount > 0) {
            if (typeof loadProducts === 'function') {
                loadProducts();
            }
            if (typeof loadInvoiceHistory === 'function') {
                loadInvoiceHistory();
            }
        }

        if (!failed.length) {
            alert('Deleted ' + successCount + ' invoice import(s).');
        } else {
            alert('Deleted ' + successCount + ' import(s). Failed: ' + failed.length + '.\n' + failed.slice(0, 5).join('\n'));
        }
    }

    function installInvoiceBulkDeleteControls() {
        const tables = Array.from(document.querySelectorAll('table')).filter(isInvoiceHistoryTable);
        tables.forEach((table) => {
            const headRow = table.querySelector('thead tr');
            sortInvoiceHistoryTableRows(table);
            const bodyRows = Array.from(table.querySelectorAll('tbody tr'));
            if (!headRow || !bodyRows.length) {
                return;
            }

            if (!table.dataset.ic3InvoiceBulkPatched) {
                const th = document.createElement('th');
                th.style.padding = '8px';
                th.style.textAlign = 'center';
                th.style.width = '44px';
                th.innerHTML = '<input type="checkbox" class="ic3-import-select-all" title="Select all">';
                headRow.insertBefore(th, headRow.firstElementChild);

                bodyRows.forEach((row) => {
                    const firstCell = row.querySelector('td');
                    const importId = firstCell ? (firstCell.innerText || '').trim() : '';
                    row.dataset.importId = importId;

                    const td = document.createElement('td');
                    td.style.padding = '8px';
                    td.style.textAlign = 'center';

                    const checked = importId && state.selectedInvoiceImportIds.has(importId) ? ' checked' : '';
                    td.innerHTML = '<input type="checkbox" class="ic3-import-checkbox" data-import-id="' + escapeHtml(importId) + '"' + checked + '>';
                    row.insertBefore(td, row.firstElementChild);
                });

                table.dataset.ic3InvoiceBulkPatched = '1';
            }

            let panel = table.previousElementSibling;
            if (!(panel && panel.classList && panel.classList.contains('ic3-invoice-bulk-tools'))) {
                panel = document.createElement('div');
                panel.className = 'ic3-invoice-bulk-tools';
                panel.style.display = 'flex';
                panel.style.alignItems = 'center';
                panel.style.gap = '8px';
                panel.style.margin = '8px 0';
                panel.innerHTML = '' +
                    '<button type="button" class="ic3-select-all-btn" style="background:#1565c0;color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer;">Select All</button>' +
                    '<button type="button" class="ic3-clear-all-btn" style="background:#607d8b;color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer;">Clear</button>' +
                    '<button type="button" class="ic3-delete-selected-btn" style="background:#c62828;color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer;">Delete Selected</button>' +
                    '<span class="ic3-selected-count" style="font-weight:600;color:#37474f;">0 selected</span>';
                table.parentElement.insertBefore(panel, table);

                const setAll = (value) => {
                    const checkboxes = Array.from(table.querySelectorAll('tbody .ic3-import-checkbox'));
                    checkboxes.forEach((cb) => {
                        cb.checked = value;
                        if (cb.dataset.importId) {
                            if (value) {
                                state.selectedInvoiceImportIds.add(cb.dataset.importId);
                            } else {
                                state.selectedInvoiceImportIds.delete(cb.dataset.importId);
                            }
                        }
                    });
                    updateInvoiceSelectionUi(table);
                };

                panel.querySelector('.ic3-select-all-btn').addEventListener('click', function () { setAll(true); });
                panel.querySelector('.ic3-clear-all-btn').addEventListener('click', function () { setAll(false); });
                panel.querySelector('.ic3-delete-selected-btn').addEventListener('click', function () { bulkDeleteInvoiceImports(table); });
            }

            const headerCheckbox = table.querySelector('thead .ic3-import-select-all');
            if (headerCheckbox && !headerCheckbox.dataset.ic3Wired) {
                headerCheckbox.addEventListener('change', function () {
                    const all = Array.from(table.querySelectorAll('tbody .ic3-import-checkbox'));
                    all.forEach((cb) => {
                        cb.checked = headerCheckbox.checked;
                        if (cb.dataset.importId) {
                            if (cb.checked) {
                                state.selectedInvoiceImportIds.add(cb.dataset.importId);
                            } else {
                                state.selectedInvoiceImportIds.delete(cb.dataset.importId);
                            }
                        }
                    });
                    updateInvoiceSelectionUi(table);
                });
                headerCheckbox.dataset.ic3Wired = '1';
            }

            const rowCheckboxes = Array.from(table.querySelectorAll('tbody .ic3-import-checkbox'));
            rowCheckboxes.forEach((checkbox) => {
                if (!checkbox.dataset.ic3Wired) {
                    checkbox.addEventListener('change', function () {
                        const importId = checkbox.dataset.importId;
                        if (importId) {
                            if (checkbox.checked) {
                                state.selectedInvoiceImportIds.add(importId);
                            } else {
                                state.selectedInvoiceImportIds.delete(importId);
                            }
                        }
                        updateInvoiceSelectionUi(table);
                    });
                    checkbox.dataset.ic3Wired = '1';
                }

                if (checkbox.dataset.importId && state.selectedInvoiceImportIds.has(checkbox.dataset.importId)) {
                    checkbox.checked = true;
                }
            });

            updateInvoiceSelectionUi(table);
        });
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function installOrderRenameTab() {
        if (document.getElementById('ic3RenameCsvTabButton')) {
            return;
        }

        const tabsContainer = document.querySelector('.tabs');
        const container = document.querySelector('.container');
        if (!tabsContainer || !container) {
            return;
        }

        const tabButton = document.createElement('button');
        tabButton.id = 'ic3RenameCsvTabButton';
        tabButton.className = 'tab';
        tabButton.innerHTML = '&#128194; Rename Order CSVs';
        tabButton.addEventListener('click', function (event) {
            if (typeof showTab === 'function') {
                showTab('renamecsv', event);
            }
        });
        tabsContainer.appendChild(tabButton);

        const tabContent = document.createElement('div');
        tabContent.id = 'renamecsv';
        tabContent.className = 'tab-content';
        tabContent.innerHTML = '' +
            '<div style="max-width: 900px; margin: 0 auto; background: #f8fffb; border: 2px solid #c8e6c9; border-radius: 12px; padding: 22px;">' +
            '<h2 style="margin: 0 0 10px 0; color: #2e7d32;">Rename Order CSVs</h2>' +
            '<p style="margin: 0 0 16px 0; color: #455a64;">Use the same logic as the renamer tool to preview and apply names like <strong>Location_YYYY-MM-DD_order.csv</strong>.</p>' +
            '<div id="renameFolderSection" style="display: grid; grid-template-columns: 1fr 220px; gap: 12px; margin-bottom: 12px;">' +
            '<div>' +
            '<label for="renameFolderPath" style="display: block; margin-bottom: 5px; font-weight: 600;">Folder Path</label>' +
            '<input id="renameFolderPath" type="text" readonly style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; background: #f0f0f0;" />' +
            '<button id="pickFolderBtn" style="margin-top: 8px; padding: 6px 12px; border-radius: 6px; background: #1976d2; color: white; border: none;">Pick Folder</button>' +
            '</div>' +
            '<div>' +
            '<label for="renameLocationPrefix" style="display: block; margin-bottom: 5px; font-weight: 600;">Location Prefix</label>' +
            '<input id="renameLocationPrefix" type="text" value="" placeholder="Auto from shared locations" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />' +
            '</div>' +
            '</div>' +
            '<div id="renameWebSection" style="display: none; margin-bottom: 12px;">' +
            '<div style="display: grid; grid-template-columns: 1fr 220px; gap: 12px;">' +
            '<div>' +
            '<label style="display: block; margin-bottom: 5px; font-weight: 600;">Select CSV Files to Rename</label>' +
            '<input id="renameWebFileInput" type="file" multiple accept=".csv" style="display: block; padding: 8px; border: 2px dashed #a5d6a7; border-radius: 8px; width: 100%; cursor: pointer;" />' +
            '<span id="renameWebFileCount" style="display: block; font-size: 0.9rem; color: #607d8b; margin-top: 5px;"></span>' +
            '</div>' +
            '<div>' +
            '<label for="renameLocationPrefix" style="display: block; margin-bottom: 5px; font-weight: 600;">Location Prefix</label>' +
            '<input id="renameLocationPrefixWeb" type="text" value="" placeholder="Auto from shared locations" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />' +
            '</div>' +
            '</div>' +
            '</div>' +
            '<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px;">' +
            '<button class="btn" style="background: #1976d2; color: white;" onclick="previewOrderCsvRename()">Preview Rename</button>' +
            '<button id="renameApplyBtn" class="btn" style="background: #2e7d32; color: white;" onclick="applyOrderCsvRename()">Apply Rename</button>' +
            '<button id="renameWebDownloadBtn" class="btn" style="background: #6a1b9a; color: white; display: none;" onclick="downloadWebRenameZip()">&#11015; Download Renamed ZIP</button>' +
            '</div>' +
            '<div id="renameCsvStatus" style="display: none; border-radius: 8px; padding: 12px; margin-bottom: 12px;"></div>' +
            '<div id="renameCsvResults" style="max-height: 380px; overflow: auto; border: 1px solid #e0e0e0; border-radius: 8px; background: white; padding: 10px;">' +
            '<p style="color: #607d8b; margin: 0;">Run a preview to see pending file changes.</p>' +
            '</div>' +
            '</div>';

        // Use backend native folder picker so we get a real absolute path.
        setTimeout(function () {
            var pickBtn = document.getElementById('pickFolderBtn');
            if (!pickBtn) {
                return;
            }
            pickBtn.onclick = async function () {
                try {
                    const response = await fetch('/api/tools/select-folder', { method: 'POST' });
                    const payload = await response.json();
                    if (!payload.success) {
                        activateWebRenameMode();
                        return;
                    }
                    if (!payload.folder_path) {
                        renderRenameStatus('Folder selection cancelled.', false);
                        return;
                    }
                    document.getElementById('renameFolderPath').value = payload.folder_path;
                    renderRenameStatus('Selected folder: ' + escapeHtml(payload.folder_path), true);
                } catch (error) {
                    renderRenameStatus('&#10060; Error opening folder picker: ' + escapeHtml(error.message), false);
                }
            };

            // Auto-detect whether local folder picking is available without opening the dialog.
            fetch('/api/tools/select-folder?probe=1', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (payload) {
                    if (!payload.success) {
                        activateWebRenameMode();
                    }
                })
                .catch(function () { activateWebRenameMode(); });
        }, 200);

        container.appendChild(tabContent);
    }

    function activateWebRenameMode() {
        const folderSection = document.getElementById('renameFolderSection');
        if (folderSection) folderSection.style.display = 'none';
        const webSection = document.getElementById('renameWebSection');
        if (webSection) webSection.style.display = 'block';
        const applyBtn = document.getElementById('renameApplyBtn');
        if (applyBtn) applyBtn.style.display = 'none';
        const dlBtn = document.getElementById('renameWebDownloadBtn');
        if (dlBtn) dlBtn.style.display = '';
        const fileInput = document.getElementById('renameWebFileInput');
        if (fileInput && !fileInput.dataset.hooked) {
            fileInput.dataset.hooked = '1';
            fileInput.addEventListener('change', function () {
                const countEl = document.getElementById('renameWebFileCount');
                if (countEl) countEl.textContent = this.files.length ? this.files.length + ' file(s) selected' : '';
            });
        }
    }

    function getWebLocationPrefix() {
        const prefixWeb = document.getElementById('renameLocationPrefixWeb');
        const prefixLocal = document.getElementById('renameLocationPrefix');
        return (prefixWeb && prefixWeb.value.trim()) || (prefixLocal && prefixLocal.value.trim()) || (typeof guessCurrentLocation === 'function' ? guessCurrentLocation() : '') || 'Location';
    }

    window.downloadWebRenameZip = async function () {
        const fileInput = document.getElementById('renameWebFileInput');
        if (!fileInput || !fileInput.files.length) {
            renderRenameStatus('Please select CSV files first.', false);
            return;
        }
        renderRenameStatus('&#8987; Preparing ZIP...', true);
        const fd = new FormData();
        fd.append('mode', 'download');
        fd.append('location', getWebLocationPrefix());
        for (const f of fileInput.files) fd.append('files', f);
        try {
            const r = await fetch('/api/tools/rename-order-csvs-web', { method: 'POST', body: fd });
            if (!r.ok) {
                const p = await r.json().catch(function () { return {}; });
                renderRenameStatus('&#10060; ' + escapeHtml(p.message || 'Download failed.'), false);
                return;
            }
            const blob = await r.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'renamed_order_csvs.zip';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            renderRenameStatus('&#9989; ZIP downloaded with renamed files.', true);
        } catch (e) {
            renderRenameStatus('&#10060; Error: ' + escapeHtml(e.message), false);
        }
    };

    function renderRenameStatus(message, ok) {
        const statusDiv = document.getElementById('renameCsvStatus');
        if (!statusDiv) {
            return;
        }

        statusDiv.style.display = 'block';
        statusDiv.style.background = ok ? '#d4edda' : '#f8d7da';
        statusDiv.style.color = ok ? '#155724' : '#721c24';
        statusDiv.innerHTML = message;
    }

    function renderRenameResults(items) {
        const resultsDiv = document.getElementById('renameCsvResults');
        if (!resultsDiv) {
            return;
        }

        if (!Array.isArray(items) || items.length === 0) {
            resultsDiv.innerHTML = '<p style="color: #607d8b; margin: 0;">No CSV files need renaming.</p>';
            return;
        }

        let html = '<table style="width: 100%; border-collapse: collapse;">';
        html += '<thead><tr style="background: #f1f8e9; border-bottom: 2px solid #dcedc8;">';
        html += '<th style="padding: 8px; text-align: left;">Old Name</th>';
        html += '<th style="padding: 8px; text-align: left;">New Name</th>';
        html += '</tr></thead><tbody>';

        items.forEach((item) => {
            html += '<tr style="border-bottom: 1px solid #eceff1;">';
            html += '<td style="padding: 8px; color: #546e7a;">' + escapeHtml(item.old_name) + '</td>';
            html += '<td style="padding: 8px; color: #1b5e20; font-weight: 600;">' + escapeHtml(item.new_name) + '</td>';
            html += '</tr>';
        });

        html += '</tbody></table>';
        resultsDiv.innerHTML = html;
    }

    async function runOrderCsvRename(applyChanges) {
        const webSection = document.getElementById('renameWebSection');
        const isWebMode = webSection && webSection.style.display !== 'none';

        if (isWebMode) {
            const fileInput = document.getElementById('renameWebFileInput');
            if (!fileInput || !fileInput.files.length) {
                renderRenameStatus('Please select CSV files first.', false);
                return;
            }
            renderRenameStatus('&#8987; Previewing...', true);
            const fd = new FormData();
            fd.append('mode', 'preview');
            fd.append('location', getWebLocationPrefix());
            for (const f of fileInput.files) fd.append('files', f);
            try {
                const r = await fetch('/api/tools/rename-order-csvs-web', { method: 'POST', body: fd });
                const payload = await r.json();
                if (!payload.success) {
                    renderRenameStatus('&#10060; ' + escapeHtml(payload.message || 'Failed.'), false);
                    return;
                }
                const count = (payload.items || []).length;
                renderRenameStatus('&#128270; ' + count + ' file(s) will be renamed. Click "Download Renamed ZIP" to get them.', count > 0);
                renderRenameResults(payload.items || []);
            } catch (e) {
                renderRenameStatus('&#10060; Error: ' + escapeHtml(e.message), false);
            }
            return;
        }

        const folderPath = document.getElementById('renameFolderPath')?.value?.trim();
        const locationPrefix = document.getElementById('renameLocationPrefix')?.value?.trim() || guessCurrentLocation() || 'Location';

        if (!folderPath) {
            renderRenameStatus('Folder path is required.', false);
            return;
        }

        renderRenameStatus((applyChanges ? '&#8987; Applying rename...' : '&#8987; Previewing rename...'), true);

        try {
            const response = await fetch('/api/tools/rename-order-csvs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    folder_path: folderPath,
                    location: locationPrefix,
                    apply: applyChanges,
                }),
            });

            const payload = await response.json();
            if (!response.ok || !payload.success) {
                renderRenameStatus('&#10060; ' + escapeHtml(payload.message || 'Rename failed.'), false);
                return;
            }

            const count = Array.isArray(payload.items) ? payload.items.length : 0;
            if (applyChanges) {
                renderRenameStatus('&#9989; Renamed ' + count + ' file(s).', true);
            } else {
                renderRenameStatus('&#128270; Preview found ' + count + ' file(s) to rename.', true);
            }
            renderRenameResults(payload.items || []);
        } catch (error) {
            renderRenameStatus('&#10060; Error: ' + escapeHtml(error.message), false);
        }
    }

    window.previewOrderCsvRename = function () {
        runOrderCsvRename(false);
    };

    window.applyOrderCsvRename = function () {
        runOrderCsvRename(true);
    };

    function renderBulkInvoiceList() {
        const listDiv = document.getElementById('bulkInvoiceList');
        const countSpan = document.getElementById('invoiceCount');
        if (!listDiv || !countSpan) {
            return;
        }

        countSpan.textContent = state.bulkInvoices.length;

        if (state.bulkInvoices.length === 0) {
            listDiv.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">No invoices added yet. Click "Add Invoice" to get started.</p>';
            return;
        }

        let html = '<table style="width: 100%; border-collapse: collapse;">';
        html += '<thead><tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">';
        html += '<th style="padding: 10px; text-align: left;">#</th>';
        html += '<th style="padding: 10px; text-align: left;">File Name</th>';
        html += '<th style="padding: 10px; text-align: left;">Delivery Date</th>';
        html += '<th style="padding: 10px; text-align: center;">Action</th>';
        html += '</tr></thead><tbody>';

        state.bulkInvoices.forEach((invoice, index) => {
            html += '<tr style="border-bottom: 1px solid #dee2e6;">';
            html += '<td style="padding: 10px;">' + (index + 1) + '</td>';
            html += '<td style="padding: 10px;"><span style="color: #2196f3;">&#128196;</span> ' + invoice.file.name + '</td>';
            html += '<td style="padding: 10px;">';
            html += '<input type="date" value="' + invoice.date + '" onchange="updateInvoiceDate(' + index + ', this.value)" style="padding: 5px; border: 1px solid #dee2e6; border-radius: 4px;">';
            html += '</td>';
            html += '<td style="padding: 10px; text-align: center;">';
            html += '<button onclick="removeBulkInvoice(' + index + ')" style="background: #f44336; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">&#128465; Remove</button>';
            html += '</td>';
            html += '</tr>';
        });

        html += '</tbody></table>';
        listDiv.innerHTML = html;
    }

    function clearBulkUi() {
        state.bulkInvoices = [];
        renderBulkInvoiceList();
        const statusDiv = getBulkStatusDiv();
        if (statusDiv) {
            statusDiv.style.display = 'none';
            statusDiv.innerHTML = '';
        }
        const fileInput = document.getElementById('bulkFileInput');
        if (fileInput) {
            fileInput.value = '';
        }
    }

    window.dateFromFilename = parseDateFromFilename;

    window.showSingleUpload = function () {
        const single = document.getElementById('singleUploadSection');
        const bulk = document.getElementById('bulkUploadSection');
        if (single) single.style.display = 'block';
        if (bulk) bulk.style.display = 'none';
    };

    window.showBulkUpload = function () {
        const single = document.getElementById('singleUploadSection');
        const bulk = document.getElementById('bulkUploadSection');
        if (single) single.style.display = 'none';
        if (bulk) bulk.style.display = 'block';
        clearBulkUi();
    };

    window.addBulkInvoices = function (input) {
        const files = Array.from((input && input.files) || []);
        files.forEach((file) => {
            if (!file.name.toLowerCase().endsWith('.csv')) {
                return;
            }
            state.bulkInvoices.push({
                id: Date.now() + Math.random(),
                file: file,
                date: parseDateFromFilename(file.name),
            });
        });

        if (input) {
            input.value = '';
        }
        renderBulkInvoiceList();
    };

    window.renderBulkInvoiceList = renderBulkInvoiceList;

    window.updateInvoiceDate = function (index, newDate) {
        if (state.bulkInvoices[index]) {
            state.bulkInvoices[index].date = newDate;
        }
    };

    window.removeBulkInvoice = function (index) {
        state.bulkInvoices.splice(index, 1);
        renderBulkInvoiceList();
    };

    window.clearBulkInvoices = function () {
        if (state.bulkInvoices.length > 0 && !confirm('Clear all ' + state.bulkInvoices.length + ' invoice(s)?')) {
            return;
        }
        clearBulkUi();
    };

    window.uploadInvoiceCSV = function () {
        const fileInput = document.getElementById('uploadInvoiceCSV');
        const file = fileInput && fileInput.files ? fileInput.files[0] : null;
        const location = document.getElementById('invoiceLocation')?.value;
        const statusDiv = document.getElementById('invoiceUploadStatus');
        const fileNameSpan = document.getElementById('invoiceFileName');
        const dateField = document.getElementById('deliveryDate');

        if (!file || !statusDiv || !dateField) {
            return;
        }

        const selectedDeliveryDate = (dateField.value || '').trim();
        const parsedDeliveryDate = parseDateFromFilename(file.name);
        const deliveryDate = selectedDeliveryDate || parsedDeliveryDate;
        if (!selectedDeliveryDate) {
            dateField.value = deliveryDate;
        }
        if (fileNameSpan) {
            fileNameSpan.textContent = 'Selected: ' + file.name;
        }

        statusDiv.style.display = 'block';
        statusDiv.style.background = '#d1ecf1';
        statusDiv.style.color = '#0c5460';
        statusDiv.innerHTML = '&#8987; Uploading invoice...';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('location', location || guessCurrentLocation() || 'Kingsville');
        formData.append('delivery_date', deliveryDate);

        fetch('/api/orders/upload-invoice', {
            method: 'POST',
            body: formData,
        })
        .then((response) => response.json())
        .then((result) => {
            if (result.success) {
                statusDiv.style.background = '#d4edda';
                statusDiv.style.color = '#155724';
                statusDiv.innerHTML = '&#9989; ' + result.message;
                if (typeof loadProducts === 'function') loadProducts();
                if (typeof loadInvoiceHistory === 'function') loadInvoiceHistory();
            } else {
                statusDiv.style.background = '#f8d7da';
                statusDiv.style.color = '#721c24';
                statusDiv.innerHTML = '&#10060; Error: ' + result.message;
            }
            fileInput.value = '';
            if (fileNameSpan) fileNameSpan.textContent = '';
        })
        .catch((error) => {
            statusDiv.style.background = '#f8d7da';
            statusDiv.style.color = '#721c24';
            statusDiv.innerHTML = '&#10060; Error uploading file: ' + error.message;
            fileInput.value = '';
            if (fileNameSpan) fileNameSpan.textContent = '';
        });
    };

    window.processBulkUpload = async function () {
        if (state.bulkInvoices.length === 0) {
            alert('Please add at least one invoice first.');
            return;
        }

        const location = document.getElementById('bulkInvoiceLocation')?.value || guessCurrentLocation() || 'Kingsville';
        const statusDiv = getBulkStatusDiv();
        if (!statusDiv) {
            return;
        }

        statusDiv.style.display = 'block';
        statusDiv.style.background = '#d1ecf1';
        statusDiv.style.color = '#0c5460';
        statusDiv.innerHTML = '&#8987; Processing ' + state.bulkInvoices.length + ' invoice(s)...<br><div id="bulkProgress"></div>';

        let successCount = 0;
        let failCount = 0;
        const results = [];

        for (let i = 0; i < state.bulkInvoices.length; i++) {
            const invoice = state.bulkInvoices[i];
            const progressDiv = document.getElementById('bulkProgress');
            if (progressDiv) {
                progressDiv.innerHTML = 'Processing ' + (i + 1) + ' of ' + state.bulkInvoices.length + ': ' + invoice.file.name + '...';
            }

            try {
                const parsedDate = parseDateFromFilename(invoice.file.name);
                invoice.date = invoice.date || parsedDate;

                const formData = new FormData();
                formData.append('file', invoice.file);
                formData.append('location', location);
                formData.append('delivery_date', invoice.date);

                const response = await fetch('/api/orders/upload-invoice', {
                    method: 'POST',
                    body: formData,
                });
                const result = await response.json();

                if (result.success) {
                    successCount++;
                    results.push({ filename: invoice.file.name, date: invoice.date, success: true, matched: result.matched_count, total: result.total_items, newProducts: result.new_products_created || 0 });
                } else {
                    failCount++;
                    results.push({ filename: invoice.file.name, date: invoice.date, success: false, error: result.message });
                }
            } catch (error) {
                failCount++;
                results.push({ filename: invoice.file.name, date: invoice.date, success: false, error: error.message });
            }
        }

        let html = '<h4 style="margin-top: 15px;">&#9989; Bulk Upload Complete!</h4>';
        html += '<p><strong>Successful:</strong> ' + successCount + ' | <strong>Failed:</strong> ' + failCount + '</p>';
        html += '<div style="max-height: 300px; overflow-y: auto; background: white; padding: 10px; border-radius: 5px; margin-top: 10px;">';
        results.forEach((result) => {
            if (result.success) {
                html += '<div style="padding: 8px; margin: 5px 0; background: #d4edda; border-left: 4px solid #28a745; border-radius: 4px;">';
                html += '<strong style="color: #155724;">&#9989; ' + result.filename + '</strong><br>';
                html += '<small>Date: ' + result.date + ' | Matched: ' + result.matched + '/' + result.total + ' products';
                if (result.newProducts > 0) {
                    html += ' | <span style="color: #0056b3;">+' + result.newProducts + ' new</span>';
                }
                html += '</small></div>';
            } else {
                html += '<div style="padding: 8px; margin: 5px 0; background: #f8d7da; border-left: 4px solid #dc3545; border-radius: 4px;">';
                html += '<strong style="color: #721c24;">&#10060; ' + result.filename + '</strong><br>';
                html += '<small>Date: ' + result.date + ' | Error: ' + result.error + '</small></div>';
            }
        });
        html += '</div>';

        statusDiv.style.background = successCount > 0 ? '#d4edda' : '#f8d7da';
        statusDiv.style.color = successCount > 0 ? '#155724' : '#721c24';
        statusDiv.innerHTML = html;

        if (failCount === 0) {
            clearBulkUi();
        }

        if (successCount > 0) {
            if (typeof loadProducts === 'function') loadProducts();
            if (typeof loadInvoiceHistory === 'function') loadInvoiceHistory();
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            renderBulkInvoiceList();
            installInventorySearchFilter();
            installOrderRenameTab();
            installInvoiceBulkDeleteControls();
        });
    } else {
        renderBulkInvoiceList();
        installInventorySearchFilter();
        installOrderRenameTab();
        installInvoiceBulkDeleteControls();
    }

    let ic3UiRefreshScheduled = false;
    const scheduleIc3UiRefresh = function () {
        if (ic3UiRefreshScheduled) {
            return;
        }
        ic3UiRefreshScheduled = true;
        window.setTimeout(function () {
            ic3UiRefreshScheduled = false;
            installInventorySearchFilter();
            applyInventorySearchFilter();
            installOrderRenameTab();
            installInvoiceBulkDeleteControls();
        }, 120);
    };

    const observer = new MutationObserver(() => {
        scheduleIc3UiRefresh();
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

PRODUCT_DETAIL_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3ProductDetailInstalled) return;
    window.__ic3ProductDetailInstalled = true;

    const state = {
        productNumber: '',
        windowKey: 'month',
        location: '',
        locationScope: 'current',
        detailPayload: null,
    };

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getToastContainer() {
        let node = document.getElementById('ic3ToastStack');
        if (node) return node;

        node = document.createElement('div');
        node.id = 'ic3ToastStack';
        node.style.position = 'fixed';
        node.style.top = '18px';
        node.style.right = '18px';
        node.style.zIndex = '99999';
        node.style.display = 'flex';
        node.style.flexDirection = 'column';
        node.style.gap = '8px';
        document.body.appendChild(node);
        return node;
    }

    function showToast(message, kind) {
        const container = getToastContainer();
        const toast = document.createElement('div');
        const palette = kind === 'error'
            ? { bg: '#fee2e2', border: '#ef4444', color: '#7f1d1d' }
            : (kind === 'warn'
                ? { bg: '#fff7ed', border: '#f59e0b', color: '#7c2d12' }
                : { bg: '#dcfce7', border: '#22c55e', color: '#14532d' });

        toast.style.background = palette.bg;
        toast.style.border = '1px solid ' + palette.border;
        toast.style.color = palette.color;
        toast.style.borderRadius = '10px';
        toast.style.padding = '10px 12px';
        toast.style.minWidth = '250px';
        toast.style.maxWidth = '360px';
        toast.style.boxShadow = '0 8px 24px rgba(15,23,42,0.12)';
        toast.style.fontSize = '13px';
        toast.style.fontWeight = '600';
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(function () {
            if (toast.parentElement) toast.parentElement.removeChild(toast);
        }, 2800);
    }

    function guessCurrentLocation() {
        if (window.__ic3ForceNoLocation) {
            return '';
        }

        const selectedRadio = document.querySelector('input[name="location"][type="radio"]:checked');
        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {
            return selectedRadio.value.trim();
        }

        const explicitIds = ['reportLocation', 'location', 'inventoryLocation', 'invoiceLocation', 'bulkInvoiceLocation'];
        for (const id of explicitIds) {
            const el = document.getElementById(id);
            if (el && typeof el.value === 'string' && el.value.trim()) {
                return el.value.trim();
            }
        }

        const selects = Array.from(document.querySelectorAll('select'));
        for (const select of selects) {
            const marker = ((select.id || '') + ' ' + (select.name || '') + ' ' + (select.className || '')).toLowerCase();
            if (marker.includes('location') && String(select.value || '').trim()) {
                return String(select.value || '').trim();
            }
        }

        const anyRadio = document.querySelector('input[name="location"][type="radio"]');
        if (anyRadio && typeof anyRadio.value === 'string' && anyRadio.value.trim()) {
            return anyRadio.value.trim();
        }

        return window.__ic3ForceNoLocation ? '' : 'Kingsville';
    }

    function effectiveLocationParam() {
        if (state.locationScope === 'all') return '__all__';
        return state.location || guessCurrentLocation();
    }

    function isLikelyProductNumber(value) {
        return /^\d{4,}$/.test(String(value || '').trim());
    }

    function findProductColumnIndex(table) {
        const headers = Array.from(table.querySelectorAll('thead th'));
        if (!headers.length) return -1;

        for (let i = 0; i < headers.length; i++) {
            const text = (headers[i].innerText || '').trim().toLowerCase();
            if (text.includes('product #') || text.includes('product number')) {
                return i;
            }
        }
        return -1;
    }

    function installProductLinks() {
        const tables = Array.from(document.querySelectorAll('table'));
        tables.forEach((table) => {
            const idx = findProductColumnIndex(table);
            if (idx < 0) return;

            const rows = Array.from(table.querySelectorAll('tbody tr'));
            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                if (!cells || idx >= cells.length) return;
                const cell = cells[idx];
                if (!cell || cell.dataset.ic3ProductLinked === '1') return;

                const rawText = (cell.innerText || '').trim();
                if (!isLikelyProductNumber(rawText)) return;
                if (cell.querySelector('.ic3-product-link')) {
                    cell.dataset.ic3ProductLinked = '1';
                    return;
                }

                const link = document.createElement('a');
                link.href = '#';
                link.className = 'ic3-product-link';
                link.dataset.productNumber = rawText;
                link.textContent = rawText;
                link.style.fontWeight = '700';
                link.style.color = '#1a4db3';
                link.style.textDecoration = 'underline';

                cell.textContent = '';
                cell.appendChild(link);
                cell.dataset.ic3ProductLinked = '1';
            });
        });
    }

    function installProductNicknameColumn() {
        const table = document.getElementById('productManagementTable');
        const body = document.getElementById('productManagementTableBody');
        if (!table || !body) return;
        if (!table.dataset.ic3NicknameObserver) {
            table.dataset.ic3NicknameObserver = '1';
            const observer = new MutationObserver(() => installProductNicknameColumn());
            observer.observe(body, { childList: true });
        }

        const cachedProducts = window.__ic3ProductsForNickname || [];
        if (!cachedProducts.length && !table.dataset.ic3NicknameLoading) {
            table.dataset.ic3NicknameLoading = '1';
            fetch('/api/products?t=' + Date.now()).then((response) => response.json()).then((products) => {
                window.__ic3ProductsForNickname = Array.isArray(products) ? products : [];
                table.dataset.ic3NicknameLoading = '0';
                installProductNicknameColumn();
                installInventoryNicknameLabels();
            }).catch(() => { table.dataset.ic3NicknameLoading = '0'; });
            return;
        }
        const productsByNumber = {};
        cachedProducts.forEach((product) => {
            const number = String(product['Product Number'] || '').trim();
            if (number) productsByNumber[number] = product;
        });
        const headers = Array.from(table.querySelectorAll('thead th'));
        const descriptionIndex = headers.findIndex((header) => (header.innerText || '').trim().toLowerCase() === 'description');
        if (descriptionIndex < 0) return;
        let nicknameIndex = headers.findIndex((header) => (header.innerText || '').trim().toLowerCase() === 'nickname');
        if (nicknameIndex < 0) {
            const nicknameHeader = document.createElement('th');
            nicknameHeader.textContent = 'Nickname';
            headers[descriptionIndex].after(nicknameHeader);
            nicknameIndex = descriptionIndex + 1;
        }

        const productIndex = headers.findIndex((header) => (header.innerText || '').trim().toLowerCase().includes('product #'));
        Array.from(body.querySelectorAll('tr')).forEach((row) => {
            const cells = Array.from(row.cells || []);
            if (productIndex < 0 || !cells[productIndex]) return;
            const productNumber = String(cells[productIndex].innerText || '').trim();
            const product = productsByNumber[productNumber] || {};
            let nicknameCell = row.cells[nicknameIndex];
            if (!nicknameCell) {
                nicknameCell = document.createElement('td');
                row.cells[descriptionIndex].after(nicknameCell);
            }
            const description = String(product['Product Description'] || '');
            const nickname = String(product['Product Nickname'] || '').trim();
            nicknameCell.title = description;
            nicknameCell.dataset.ic3NicknameCell = '1';
            if (productNumber && !nicknameCell.querySelector('.ic3-inline-nickname-input')) {
                nicknameCell.textContent = '';
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'ic3-inline-nickname-input';
                input.value = nickname;
                input.maxLength = 80;
                input.placeholder = 'Add nickname';
                input.dataset.productNumber = productNumber;
                input.title = description;
                input.style.cssText = 'box-sizing:border-box;width:calc(100% - 4px);min-width:90px;padding:4px 6px;border:1px solid #cbd5e1;border-radius:4px;';
                nicknameCell.appendChild(input);
            }
        });

        const productsTab = document.getElementById('products');
        if (productsTab && !document.getElementById('ic3BulkSaveNicknames')) {
            const saveButton = document.createElement('button');
            saveButton.type = 'button';
            saveButton.id = 'ic3BulkSaveNicknames';
            saveButton.className = 'btn btn-primary';
            saveButton.textContent = 'Save Nicknames';
            saveButton.title = 'Save all nickname fields in the product table';
            saveButton.style.cssText = 'margin:8px 0;padding:8px 14px;';
            saveButton.addEventListener('click', async () => {
                const entries = Array.from(document.querySelectorAll('.ic3-inline-nickname-input')).map((input) => ({
                    product_number: String(input.dataset.productNumber || '').trim(),
                    nickname: String(input.value || '').trim(),
                })).filter((entry) => entry.product_number);
                saveButton.disabled = true;
                saveButton.textContent = 'Saving...';
                try {
                    const response = await fetch('/api/products/update-nicknames', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ updates: entries }),
                    });
                    const result = await response.json();
                    if (!response.ok || !result.success) throw new Error(result.message || 'Unable to save nicknames.');
                    window.__ic3ProductsForNickname = null;
                    saveButton.textContent = 'Saved';
                    setTimeout(() => { saveButton.textContent = 'Save Nicknames'; }, 1200);
                } catch (error) {
                    saveButton.textContent = 'Save Nicknames';
                    window.alert(error.message);
                } finally {
                    saveButton.disabled = false;
                }
            });
            const toolbar = document.getElementById('dexterIc3ListToolbar');
            (toolbar || productsTab).insertBefore(saveButton, (toolbar || productsTab).firstChild);
        }

        const widthByLabel = {
            '#': '5%', 'product #': '9%', 'description': '23%', 'nickname': '17%',
            'brand': '12%', 'package size': '10%', 'category': '9%', 'sub for': '7%', 'case count': '5%', 'actions': '6%'
        };
        const desiredOrder = ['#', 'product #', 'description', 'nickname', 'brand', 'package size', 'category', 'sub for', 'case count', 'actions'];
        const headerRow = table.querySelector('thead tr');
        const headerCells = Array.from(headerRow ? headerRow.children : []);
        const headerNodesByLabel = {};
        headerCells.forEach((header) => {
            const label = (header.innerText || '').trim().toLowerCase();
            if (label) headerNodesByLabel[label] = header;
        });
        const orderedHeaderNodes = desiredOrder.map((label) => headerNodesByLabel[label]).filter(Boolean);
        if (headerRow && orderedHeaderNodes.length === headerCells.length) {
            orderedHeaderNodes.forEach((header) => headerRow.appendChild(header));
            Array.from(body.querySelectorAll('tr')).forEach((row) => {
                const productNumber = String(row.dataset.productNumber || '').trim();
                const product = productsByNumber[productNumber] || {};
                const existingCells = Array.from(row.children);
                const usedCells = new Set();
                const findCell = (predicate) => {
                    const cell = existingCells.find((candidate) => !usedCells.has(candidate) && predicate(candidate));
                    if (cell) usedCells.add(cell);
                    return cell;
                };
                const makeCell = () => document.createElement('td');
                const rowNumberCell = findCell((cell) => /^\s*(?:👆\s*)?#?\s*\d+\s*$/.test(cell.innerText || '')) || makeCell();
                rowNumberCell.textContent = '# ' + String(rowNumberCell.innerText || '').replace(/[^0-9]/g, '');

                let productCell = findCell((cell) => cell.querySelector && cell.querySelector('.ic3-product-link'));
                if (!productCell) productCell = makeCell();
                let productLink = productCell.querySelector('.ic3-product-link');
                if (!productLink) {
                    productLink = document.createElement('a');
                    productLink.href = '#';
                    productLink.className = 'ic3-product-link';
                    productLink.style.cssText = 'font-weight:700;color:#1a4db3;text-decoration:underline;';
                    productCell.textContent = '';
                    productCell.appendChild(productLink);
                }
                productLink.dataset.productNumber = productNumber;
                productLink.textContent = productNumber;

                let descriptionCell = findCell((cell) => String(cell.innerText || '').trim() === String(product['Product Description'] || '').trim()) || makeCell();
                descriptionCell.textContent = String(product['Product Description'] || '');
                let nicknameCell = findCell((cell) => cell.dataset && cell.dataset.ic3NicknameCell === '1') || makeCell();
                nicknameCell.dataset.ic3NicknameCell = '1';
                let nicknameInput = nicknameCell.querySelector('.ic3-inline-nickname-input');
                if (!nicknameInput) {
                    nicknameInput = document.createElement('input');
                    nicknameInput.type = 'text';
                    nicknameInput.className = 'ic3-inline-nickname-input';
                    nicknameInput.maxLength = 80;
                    nicknameInput.placeholder = 'Add nickname';
                    nicknameCell.textContent = '';
                    nicknameCell.appendChild(nicknameInput);
                }
                nicknameInput.dataset.productNumber = productNumber;
                nicknameInput.value = String(product['Product Nickname'] || '').trim();
                nicknameCell.title = String(product['Product Description'] || '');
                const brandCell = findCell((cell) => String(cell.innerText || '').trim() === String(product['Product Brand'] || '').trim()) || makeCell();
                brandCell.textContent = String(product['Product Brand'] || '');
                const packageCell = findCell((cell) => String(cell.innerText || '').trim() === String(product['Product Package Size'] || '').trim()) || makeCell();
                packageCell.textContent = String(product['Product Package Size'] || '');
                const categoryCell = findCell((cell) => cell.querySelector && cell.querySelector('span')) || makeCell();
                categoryCell.innerHTML = '<span style="background:#e9ecef;padding:4px 8px;border-radius:4px;font-size:0.85em;font-weight:600;"></span>';
                categoryCell.querySelector('span').textContent = String(product['Group Name'] || 'OTHER');
                const subCell = findCell((cell) => String(cell.innerText || '').trim() === '-' || String(cell.innerText || '').trim() === '') || makeCell();
                if (!subCell.innerText.trim()) subCell.textContent = '-';
                const caseCell = findCell((cell) => cell.querySelector && cell.querySelector('.case-count-checkbox')) || makeCell();
                const caseCheckbox = caseCell.querySelector('.case-count-checkbox');
                if (caseCheckbox) caseCheckbox.dataset.productNum = productNumber;
                const actionsCell = findCell((cell) => cell.classList && cell.classList.contains('action-buttons')) || makeCell();

                [rowNumberCell, productCell, descriptionCell, nicknameCell, brandCell, packageCell, categoryCell, subCell, caseCell, actionsCell].forEach((cell) => row.appendChild(cell));
            });
        }
        table.style.tableLayout = 'fixed';
        Array.from(table.querySelectorAll('thead th')).forEach((header) => {
            const label = (header.innerText || '').trim().toLowerCase();
            const width = widthByLabel[label];
            if (width) header.style.width = width;
        });
        table.querySelectorAll('.edit-product-btn').forEach((button) => {
            button.style.padding = '3px 6px';
            button.style.fontSize = '11px';
            button.style.minHeight = '26px';
            button.style.whiteSpace = 'nowrap';
        });
        if (!document.getElementById('ic3ProductTableResponsiveStyle')) {
            const style = document.createElement('style');
            style.id = 'ic3ProductTableResponsiveStyle';
            style.textContent = [
                '#productManagementTable { width:100%; table-layout:fixed; }',
                '#productManagementTable th, #productManagementTable td { padding:6px 5px; }',
                '#productManagementTable td:nth-child(3), #productManagementTable td:nth-child(4), #productManagementTable td:nth-child(5), #productManagementTable td:nth-child(6) { overflow:hidden; text-overflow:ellipsis; }',
                '@media (max-width: 768px) {',
                '  #products { overflow-x:hidden; }',
                '  #productManagementTable { min-width:760px; font-size:12px; }',
                '  #productManagementTable th, #productManagementTable td { padding:5px 4px; }',
                '  #productManagementTable .ic3-inline-nickname-input { min-width:72px !important; font-size:12px; padding:3px 4px !important; }',
                '  #productManagementTable .edit-product-btn { padding:2px 5px !important; font-size:10px !important; min-height:24px !important; }',
                '  #productManagementTable th:nth-child(1), #productManagementTable td:nth-child(1) { width:32px !important; }',
                '  #productManagementTable th:nth-child(2), #productManagementTable td:nth-child(2) { width:72px !important; }',
                '  #productManagementTable th:nth-child(3), #productManagementTable td:nth-child(3) { width:190px !important; }',
                '  #productManagementTable th:nth-child(4), #productManagementTable td:nth-child(4) { width:125px !important; }',
                '  #productManagementTable th:nth-child(10), #productManagementTable td:nth-child(10) { width:58px !important; }',
                '}'
            ].join('\n');
            (document.head || document.documentElement).appendChild(style);
        }
        table.querySelectorAll('th, td').forEach((cell) => {
            cell.style.overflow = 'hidden';
            cell.style.textOverflow = 'ellipsis';
            cell.style.whiteSpace = 'nowrap';
        });
    }

    function installInventoryNicknameLabels() {
        const container = document.getElementById('categoriesContainer');
        if (!container) return;
        const products = window.__ic3ProductsForNickname || [];
        if (!products.length) return;
        const productsByNumber = {};
        products.forEach((product) => {
            const number = String(product['Product Number'] || '').trim();
            if (number) productsByNumber[number] = product;
        });

        container.querySelectorAll('tbody tr').forEach((row) => {
            const quantityInput = row.querySelector('input.quantity-input');
            const productNumber = quantityInput ? String(quantityInput.id || '').replace(/^qty_/, '').trim() : '';
            const product = productsByNumber[productNumber];
            const itemCell = row.cells && row.cells[0];
            if (!product || !itemCell || !productNumber) return;
            const description = String(product['Product Description'] || '').trim();
            const nickname = String(product['Product Nickname'] || '').trim();
            const displayName = nickname || description;
            if (!displayName) return;
            if (itemCell.dataset.ic3InventoryLabel !== displayName) {
                itemCell.textContent = displayName;
                itemCell.dataset.ic3InventoryLabel = displayName;
            }
            itemCell.title = nickname ? description : '';
        });
    }

    function ensureProductDetailTab() {
        const tabsContainer = document.querySelector('.tabs');
        const container = document.querySelector('.container');
        if (!tabsContainer || !container) {
            return false;
        }

        if (!document.getElementById('ic3ProductDetailTabButton')) {
            const button = document.createElement('button');
            button.id = 'ic3ProductDetailTabButton';
            button.className = 'tab';
            button.innerHTML = '&#128202; Product Info';
            button.addEventListener('click', function (event) {
                if (typeof showTab === 'function') {
                    showTab('productdetail', event);
                }
            });
            tabsContainer.appendChild(button);
        }

        if (!document.getElementById('productdetail')) {
            const content = document.createElement('div');
            content.id = 'productdetail';
            content.className = 'tab-content';
            content.innerHTML = '' +
                '<div style="max-width: 1250px; margin: 0 auto; padding: 16px;">' +
                '  <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom: 14px;">' +
                '    <div>' +
                '      <h2 style="margin:0; letter-spacing:.2px;">Product Information</h2>' +
                '      <div style="font-size:12px; color:#64748b;">Drilldown history, trends, and quick corrections</div>' +
                '    </div>' +
                '    <button class="btn" id="ic3ProductBackBtn" style="background:#4c566a; color:#fff;">Back to Report</button>' +
                '  </div>' +
                '  <div id="ic3ProductDetailRoot" style="background:linear-gradient(180deg,#ffffff,#f8fafc); border:1px solid #d8dee9; border-radius:14px; padding:16px;">Click any Product # in Report & Analysis to load details.</div>' +
                '</div>';
            container.appendChild(content);
        }

        const backBtn = document.getElementById('ic3ProductBackBtn');
        if (backBtn && backBtn.dataset.bound !== '1') {
            backBtn.dataset.bound = '1';
            backBtn.addEventListener('click', function () {
                const reportTab = document.querySelector('.tab[onclick*="report"]') || document.querySelector('.tab');
                if (reportTab instanceof HTMLElement) {
                    reportTab.click();
                }
            });
        }

        return true;
    }

    function renderChart(canvasId, orderSeries, inventorySeries) {
        const canvas = document.getElementById(canvasId);
        if (!(canvas instanceof HTMLCanvasElement)) return;

        const parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 900;
        canvas.width = Math.max(720, parentWidth - 10);
        canvas.height = 340;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const pad = { left: 64, right: 64, top: 28, bottom: 52 };
        const w = canvas.width - pad.left - pad.right;
        const h = canvas.height - pad.top - pad.bottom;

        const dateSet = new Set();
        (orderSeries || []).forEach((p) => dateSet.add(p.date));
        (inventorySeries || []).forEach((p) => dateSet.add(p.date));
        const dates = Array.from(dateSet).sort();

        if (!dates.length) {
            ctx.fillStyle = '#5e677a';
            ctx.font = '15px sans-serif';
            ctx.fillText('No trend data for selected window.', pad.left, pad.top + 20);
            return;
        }

        const orderMap = new Map((orderSeries || []).map((p) => [p.date, Number(p.value || 0)]));
        const invMap = new Map((inventorySeries || []).map((p) => [p.date, Number(p.value || 0)]));

        const orderValues = dates.map((d) => Number(orderMap.get(d) || 0));
        const invValues = dates.map((d) => Number(invMap.get(d) || 0));
        const orderMax = Math.max(1, ...orderValues);
        const invMax = Math.max(1, ...invValues);

        const xFor = (i) => pad.left + (dates.length === 1 ? (w / 2) : (i * w / (dates.length - 1)));
        const yLeftFor = (v) => pad.top + h - ((v / orderMax) * h);
        const yRightFor = (v) => pad.top + h - ((v / invMax) * h);

        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = pad.top + (h * i / 4);
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(canvas.width - pad.right, y);
            ctx.stroke();
        }

        ctx.strokeStyle = '#475569';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(pad.left, pad.top);
        ctx.lineTo(pad.left, pad.top + h);
        ctx.lineTo(canvas.width - pad.right, pad.top + h);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(canvas.width - pad.right, pad.top);
        ctx.lineTo(canvas.width - pad.right, pad.top + h);
        ctx.stroke();

        function drawSeries(values, yFn, color, fillColor) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2.4;
            ctx.beginPath();
            values.forEach((v, i) => {
                const x = xFor(i);
                const y = yFn(v);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();

            ctx.fillStyle = fillColor;
            values.forEach((v, i) => {
                const x = xFor(i);
                const y = yFn(v);
                ctx.beginPath();
                ctx.arc(x, y, 3.0, 0, Math.PI * 2);
                ctx.fill();
            });
        }

        drawSeries(orderValues, yLeftFor, '#0d6efd', '#93c5fd');
        drawSeries(invValues, yRightFor, '#dc2626', '#fca5a5');

        ctx.fillStyle = '#0d6efd';
        ctx.font = '12px sans-serif';
        ctx.fillText('Orders (left axis)', pad.left + 12, pad.top + 12);
        ctx.fillStyle = '#dc2626';
        ctx.fillText('Inventory (right axis)', pad.left + 150, pad.top + 12);

        ctx.fillStyle = '#475569';
        ctx.font = '11px sans-serif';
        ctx.fillText('0', pad.left - 14, pad.top + h + 4);
        ctx.fillText(String(orderMax.toFixed(1)), pad.left - 44, pad.top + 4);
        ctx.fillText('0', canvas.width - pad.right + 8, pad.top + h + 4);
        ctx.fillText(String(invMax.toFixed(1)), canvas.width - pad.right + 8, pad.top + 4);

        const step = Math.max(1, Math.floor(dates.length / 8));
        for (let i = 0; i < dates.length; i += step) {
            const x = xFor(i);
            const d = dates[i];
            ctx.save();
            ctx.translate(x - 6, pad.top + h + 18);
            ctx.rotate(-0.35);
            ctx.fillStyle = '#64748b';
            ctx.fillText(d.slice(5), 0, 0);
            ctx.restore();
        }
    }

    function currentWindowTitle(key) {
        if (key === 'month') return 'Past Month';
        if (key === 'ytd') return 'Year to Date';
        return 'Past Week';
    }

    function isAllLocationsMode() {
        return state.locationScope === 'all';
    }

    function renderProductDetail(payload) {
        state.detailPayload = payload;
        const root = document.getElementById('ic3ProductDetailRoot');
        if (!root) return;

        const product = payload.product || {};
        const summary = payload.summary || {};
        const orderRows = Array.isArray(payload.order_history) ? payload.order_history : [];
        const inventoryRows = Array.isArray(payload.inventory_history) ? payload.inventory_history : [];
        const caseCountType = String(product.case_count_type || 'No');
        const nickname = String(product.nickname || '');
        const locationLabel = String(payload.location_label || payload.location || state.location || '').trim();
        const editDisabled = isAllLocationsMode();

        let html = '';
        html += '<div style="display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin-bottom:12px;">';
        html += '<div style="border:1px solid #dbe4ef; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Product #</div><div style="font-weight:800; font-size:18px;">' + escapeHtml(product.product_number || state.productNumber) + '</div></div>';
        html += '<div style="border:1px solid #dbe4ef; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Description</div><div style="font-weight:700;">' + escapeHtml(product.description || '-') + '</div></div>';
        html += '<div style="border:1px solid #dbe4ef; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Brand</div><div style="font-weight:700;">' + escapeHtml(product.brand || '-') + '</div></div>';
        html += '<div style="border:1px solid #dbe4ef; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Package Size</div><div style="font-weight:700;">' + escapeHtml(product.package_size || '-') + '</div></div>';
        html += '</div>';

        html += '<div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px;">';
        html += '<button class="btn ic3LocationScopeBtn" data-scope="current" style="background:' + (state.locationScope === 'current' ? '#1f2937' : '#e5e7eb') + '; color:' + (state.locationScope === 'current' ? '#fff' : '#111827') + ';">Current Location</button>';
        html += '<button class="btn ic3LocationScopeBtn" data-scope="all" style="background:' + (state.locationScope === 'all' ? '#1f2937' : '#e5e7eb') + '; color:' + (state.locationScope === 'all' ? '#fff' : '#111827') + ';">All Locations</button>';
        html += '<span style="font-size:12px; color:#64748b;">Scope: <strong>' + escapeHtml(locationLabel || '-') + '</strong></span>';
        html += '</div>';

        html += '<div style="display:flex; align-items:end; gap:8px; flex-wrap:wrap; margin-bottom:12px;">';
        html += '<div><label style="display:block; font-size:12px; color:#64748b;">Nickname</label>';
        html += '<input id="ic3ProductNickname" type="text" maxlength="80" value="' + escapeHtml(nickname) + '" placeholder="Short name (optional)" style="padding:6px 8px; border:1px solid #cbd5e1; border-radius:6px; width:210px;" /></div>';
        html += '<button class="btn" id="ic3SaveNickname" style="background:#059669; color:white;">Save Nickname</button>';
        html += '<span id="ic3NicknameStatus" style="font-size:12px; color:#374151;"></span>';
        html += '</div>';

        html += '<div style="display:flex; align-items:end; gap:8px; flex-wrap:wrap; margin-bottom:12px;">';
        html += '<div><label style="display:block; font-size:12px; color:#64748b;">Case Count Type</label>';
        html += '<select id="ic3CaseCountType" style="padding:6px; border:1px solid #cbd5e1; border-radius:6px;">';
        html += '<option value="No"' + (caseCountType.toLowerCase() === 'no' ? ' selected' : '') + '>No</option>';
        html += '<option value="Yes"' + (caseCountType.toLowerCase() === 'yes' ? ' selected' : '') + '>Yes</option>';
        html += '</select></div>';
        html += '<button class="btn" id="ic3SaveCaseCountType" style="background:#2563eb; color:white;">Save Case Count Type</button>';
        html += '<span id="ic3CaseCountStatus" style="font-size:12px; color:#374151;"></span>';
        html += '</div>';

        html += '<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">';
        ['week', 'month', 'ytd'].forEach((key) => {
            const active = state.windowKey === key;
            const label = key === 'week' ? 'Past Week' : (key === 'month' ? 'Past Month' : 'YTD');
            html += '<button class="btn ic3WindowBtn" data-window="' + key + '" style="background:' + (active ? '#0f172a' : '#e2e8f0') + '; color:' + (active ? '#fff' : '#0f172a') + ';">' + label + '</button>';
        });
        html += '<span style="align-self:center; color:#64748b; font-size:12px;">Showing: ' + escapeHtml(currentWindowTitle(state.windowKey)) + '</span>';
        html += '</div>';

        if (editDisabled) {
            html += '<div style="border:1px solid #f59e0b; background:#fffbeb; color:#78350f; border-radius:8px; padding:8px 10px; margin-bottom:12px; font-size:12px;">Quick edit for order/inventory quantities is disabled in All Locations mode. Switch to Current Location to edit.</div>';
        }

        html += '<div style="border:1px solid #dbe2ea; border-radius:10px; padding:10px; margin-bottom:14px; background:#f8fafc;">';
        html += '  <canvas id="ic3TrendCanvas"></canvas>';
        html += '</div>';

        html += '<div style="display:grid; grid-template-columns: repeat(auto-fit,minmax(190px,1fr)); gap:10px; margin-bottom:14px;">';
        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Order Rows</div><div style="font-size:20px; font-weight:700;">' + escapeHtml(summary.order_rows || 0) + '</div></div>';
        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Inventory Rows</div><div style="font-size:20px; font-weight:700;">' + escapeHtml(summary.inventory_rows || 0) + '</div></div>';
        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Total Ordered</div><div style="font-size:20px; font-weight:700;">' + escapeHtml((summary.total_order_qty || 0).toFixed ? summary.total_order_qty.toFixed(2) : summary.total_order_qty || 0) + '</div></div>';
        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; padding:10px; background:#fff;"><div style="font-size:12px;color:#64748b;">Latest Inventory</div><div style="font-size:20px; font-weight:700;">' + escapeHtml(summary.latest_inventory_qty != null ? Number(summary.latest_inventory_qty).toFixed(2) : '-') + '</div></div>';
        html += '</div>';

        html += '<div style="display:grid; grid-template-columns: 1fr; gap:14px;">';

        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; overflow:auto; background:#fff;">';
        html += '<div style="padding:10px; font-weight:700; background:#f8fafc; border-bottom:1px solid #e5e7eb;">Order History (Quick Edit)</div>';
        html += '<table style="width:100%; border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8fafc;">';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Date</th>';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Location</th>';
        html += '<th style="padding:8px; text-align:right; border-bottom:1px solid #e5e7eb;">Qty</th>';
        html += '<th style="padding:8px; text-align:right; border-bottom:1px solid #e5e7eb;">Unit Price</th>';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Action</th>';
        html += '</tr></thead><tbody>';
        if (!orderRows.length) {
            html += '<tr><td colspan="5" style="padding:10px; color:#6b7280;">No order history in this window.</td></tr>';
        } else {
            orderRows.forEach((row, idx) => {
                const inputId = 'ic3OrderQty_' + idx;
                const dateValue = escapeHtml(row.date || '');
                const locValue = escapeHtml(row.location || '-');
                html += '<tr>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;">' + dateValue + '</td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;">' + locValue + '</td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7; text-align:right;"><input id="' + inputId + '" type="number" step="any" value="' + escapeHtml(row.quantity) + '" style="width:100px; text-align:right;"/></td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7; text-align:right;">' + (row.unit_price == null ? '-' : Number(row.unit_price).toFixed(2)) + '</td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;"><button class="btn ic3SaveOrderBtn" data-location="' + locValue + '" data-date="' + dateValue + '" data-input="' + inputId + '" style="background:#047857; color:#fff;"' + (editDisabled ? ' disabled' : '') + '>Save</button></td>';
                html += '</tr>';
            });
        }
        html += '</tbody></table></div>';

        html += '<div style="border:1px solid #e5e7eb; border-radius:10px; overflow:auto; background:#fff;">';
        html += '<div style="padding:10px; font-weight:700; background:#f8fafc; border-bottom:1px solid #e5e7eb;">Inventory History (Quick Edit)</div>';
        html += '<table style="width:100%; border-collapse:collapse;">';
        html += '<thead><tr style="background:#f8fafc;">';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Date</th>';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Location</th>';
        html += '<th style="padding:8px; text-align:right; border-bottom:1px solid #e5e7eb;">On Hand Qty</th>';
        html += '<th style="padding:8px; text-align:left; border-bottom:1px solid #e5e7eb;">Action</th>';
        html += '</tr></thead><tbody>';
        if (!inventoryRows.length) {
            html += '<tr><td colspan="4" style="padding:10px; color:#6b7280;">No inventory history in this window.</td></tr>';
        } else {
            inventoryRows.forEach((row, idx) => {
                const inputId = 'ic3InvQty_' + idx;
                const dateValue = escapeHtml(row.date || '');
                const locValue = escapeHtml(row.location || '-');
                html += '<tr>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;">' + dateValue + '</td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;">' + locValue + '</td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7; text-align:right;"><input id="' + inputId + '" type="number" step="any" value="' + escapeHtml(row.quantity) + '" style="width:100px; text-align:right;"/></td>';
                html += '<td style="padding:8px; border-bottom:1px solid #eef2f7;"><button class="btn ic3SaveInventoryBtn" data-location="' + locValue + '" data-date="' + dateValue + '" data-input="' + inputId + '" style="background:#b45309; color:#fff;"' + (editDisabled ? ' disabled' : '') + '>Save</button></td>';
                html += '</tr>';
            });
        }
        html += '</tbody></table></div>';
        html += '</div>';

        root.innerHTML = html;
        renderChart('ic3TrendCanvas', payload.chart_series?.orders || [], payload.chart_series?.inventory || []);
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Request failed');
        }
        return data;
    }

    async function loadProductDetail(productNumber, windowKey) {
        if (!productNumber) return;
        state.productNumber = String(productNumber || '').trim();
        state.windowKey = windowKey || state.windowKey || 'month';
        state.location = guessCurrentLocation();

        ensureProductDetailTab();
        const btn = document.getElementById('ic3ProductDetailTabButton');
        if (btn) btn.click();

        const root = document.getElementById('ic3ProductDetailRoot');
        if (root) {
            root.innerHTML = '<div style="padding:14px; color:#374151;">Loading product detail...</div>';
        }

        const requestedLocation = effectiveLocationParam();
        const url = '/api/products/' + encodeURIComponent(state.productNumber) + '/detail?location=' + encodeURIComponent(requestedLocation) + '&window=' + encodeURIComponent(state.windowKey);
        try {
            const response = await fetch(url);
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || 'Unable to load product detail.');
            }
            renderProductDetail(payload);
        } catch (error) {
            if (root) {
                root.innerHTML = '<div style="padding:14px; color:#991b1b;">' + escapeHtml(error.message) + '</div>';
            }
            showToast('Failed loading product detail: ' + error.message, 'error');
        }
    }

    document.addEventListener('click', function (event) {
        const nicknameButton = event.target && event.target.closest ? event.target.closest('.ic3-inline-nickname') : null;
        if (nicknameButton) {
            event.preventDefault();
            event.stopPropagation();
            const productNumber = String(nicknameButton.dataset.productNumber || '').trim();
            const current = nicknameButton.parentElement ? String(nicknameButton.parentElement.innerText || '').replace(/Edit\s*$/, '').trim() : '';
            const nextNickname = window.prompt('Nickname (leave blank to use description):', current === '-' ? '' : current);
            if (nextNickname === null || !productNumber) return;
            fetch('/api/products/update-nickname', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_number: productNumber, nickname: nextNickname.trim() })
            }).then((response) => response.json()).then((result) => {
                if (!result.success) throw new Error(result.message || 'Unable to save nickname.');
                window.__ic3ProductsForNickname = null;
                installProductNicknameColumn();
            }).catch((error) => window.alert(error.message));
            return;
        }
        const link = event.target && event.target.closest ? event.target.closest('.ic3-product-link') : null;
        if (link) {
            event.preventDefault();
            const productNumber = String(link.dataset.productNumber || '').trim();
            if (productNumber) {
                loadProductDetail(productNumber, 'week');
            }
            return;
        }

        const scopeBtn = event.target && event.target.closest ? event.target.closest('.ic3LocationScopeBtn') : null;
        if (scopeBtn) {
            event.preventDefault();
            state.locationScope = String(scopeBtn.dataset.scope || 'current').trim() || 'current';
            if (state.productNumber) {
                loadProductDetail(state.productNumber, state.windowKey);
            }
            return;
        }

        const windowBtn = event.target && event.target.closest ? event.target.closest('.ic3WindowBtn') : null;
        if (windowBtn) {
            event.preventDefault();
            const nextWindow = String(windowBtn.dataset.window || 'week').trim();
            loadProductDetail(state.productNumber, nextWindow);
            return;
        }

        if (event.target && event.target.id === 'ic3SaveCaseCountType') {
            event.preventDefault();
            const select = document.getElementById('ic3CaseCountType');
            const status = document.getElementById('ic3CaseCountStatus');
            const value = select ? String(select.value || '').trim() : '';
            if (!state.productNumber || !value) return;
            if (status) status.textContent = 'Saving...';

            postJson('/api/products/update-case-count-type', {
                product_number: state.productNumber,
                case_count_type: value,
            }).then(() => {
                if (status) status.textContent = 'Saved.';
                showToast('Case count type saved.', 'success');
                loadProductDetail(state.productNumber, state.windowKey);
            }).catch((error) => {
                if (status) status.textContent = 'Error: ' + error.message;
                showToast('Case count update failed: ' + error.message, 'error');
            });
            return;
        }

        if (event.target && event.target.id === 'ic3SaveNickname') {
            event.preventDefault();
            const input = document.getElementById('ic3ProductNickname');
            const status = document.getElementById('ic3NicknameStatus');
            if (!state.productNumber) return;
            if (status) status.textContent = 'Saving...';
            postJson('/api/products/update-nickname', {
                product_number: state.productNumber,
                nickname: input ? String(input.value || '').trim() : '',
            }).then(() => {
                if (status) status.textContent = 'Saved.';
                showToast('Nickname saved.', 'success');
                loadProductDetail(state.productNumber, state.windowKey);
            }).catch((error) => {
                if (status) status.textContent = 'Error: ' + error.message;
                showToast('Nickname update failed: ' + error.message, 'error');
            });
            return;
        }

        const orderBtn = event.target && event.target.closest ? event.target.closest('.ic3SaveOrderBtn') : null;
        if (orderBtn) {
            event.preventDefault();
            const date = String(orderBtn.dataset.date || '').trim();
            const rowLocation = String(orderBtn.dataset.location || '').trim() || state.location;
            const inputId = String(orderBtn.dataset.input || '').trim();
            const input = document.getElementById(inputId);
            const qty = input ? Number(input.value) : NaN;
            if (!state.productNumber || !date || Number.isNaN(qty)) return;
            orderBtn.disabled = true;

            postJson('/api/products/update-order-quantity', {
                location: rowLocation,
                date: date,
                product_number: state.productNumber,
                quantity: qty,
            }).then(() => {
                showToast('Order quantity saved.', 'success');
                loadProductDetail(state.productNumber, state.windowKey);
            }).catch((error) => {
                showToast('Order save failed: ' + error.message, 'error');
            }).finally(() => {
                orderBtn.disabled = false;
            });
            return;
        }

        const invBtn = event.target && event.target.closest ? event.target.closest('.ic3SaveInventoryBtn') : null;
        if (invBtn) {
            event.preventDefault();
            const date = String(invBtn.dataset.date || '').trim();
            const rowLocation = String(invBtn.dataset.location || '').trim() || state.location;
            const inputId = String(invBtn.dataset.input || '').trim();
            const input = document.getElementById(inputId);
            const qty = input ? Number(input.value) : NaN;
            if (!state.productNumber || !date || Number.isNaN(qty)) return;
            invBtn.disabled = true;

            postJson('/api/products/update-inventory-quantity', {
                location: rowLocation,
                date: date,
                product_number: state.productNumber,
                quantity: qty,
            }).then(() => {
                showToast('Inventory quantity saved.', 'success');
                loadProductDetail(state.productNumber, state.windowKey);
            }).catch((error) => {
                showToast('Inventory save failed: ' + error.message, 'error');
            }).finally(() => {
                invBtn.disabled = false;
            });
            return;
        }
    });

    const runInstall = function () {
        ensureProductDetailTab();
        installProductLinks();
        setTimeout(installProductNicknameColumn, 250);
        setTimeout(installInventoryNicknameLabels, 300);
        const categories = document.getElementById('categoriesContainer');
        if (categories && !categories.dataset.ic3NicknameObserver) {
            categories.dataset.ic3NicknameObserver = '1';
            const observer = new MutationObserver(() => installInventoryNicknameLabels());
            observer.observe(categories, { childList: true, subtree: true });
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runInstall);
    } else {
        runInstall();
    }

    let ic3ProductDetailRefreshScheduled = false;
    const scheduleProductDetailRefresh = function () {
        if (ic3ProductDetailRefreshScheduled) {
            return;
        }
        ic3ProductDetailRefreshScheduled = true;
        window.setTimeout(function () {
            ic3ProductDetailRefreshScheduled = false;
            installProductLinks();
            ensureProductDetailTab();
        }, 120);
    };

    const observer = new MutationObserver(() => {
        scheduleProductDetailRefresh();
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""

MOBILE_UI_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3MobileUiInstalled) return;
    window.__ic3MobileUiInstalled = true;

    const styleId = 'ic3-mobile-enhancement-style';
    if (document.getElementById(styleId)) {
        return;
    }

    const style = document.createElement('style');
    style.id = styleId;
    style.type = 'text/css';
    style.textContent = [
        '.tabs { overflow-x: auto !important; -webkit-overflow-scrolling: touch; }',
        '.tab { flex-shrink: 0 !important; font-size: 0.82rem !important; padding: 12px 10px !important; }',
        '.tab img, .tab .tab-icon { width: 16px !important; height: 16px !important; }',
        '@media (max-width: 768px) {',
        '  html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }',
        '  body { font-size: 16px !important; line-height: 1.45; }',
        '  .container { border-radius: 0 !important; }',
        '  .header { padding: 18px 12px !important; }',
        '  .header h1 { font-size: 2rem !important; line-height: 1.2 !important; }',
        '  .header p { font-size: 1.05rem !important; margin-top: 6px !important; }',
        '  .tabs { display: flex !important; overflow-x: auto !important; scroll-snap-type: x mandatory; }',
        '  .tab { flex: 0 0 auto !important; min-width: 130px !important; padding: 14px 14px !important; font-size: 1rem !important; line-height: 1.2 !important; scroll-snap-align: start; }',
        '  .tab-content { padding: 14px !important; }',
        '  .location-selector, .date-selector { display: grid !important; grid-template-columns: 1fr !important; gap: 10px !important; align-items: stretch !important; }',
        '  .location-option { min-height: 52px; padding: 10px 12px !important; }',
        '  .location-option label { font-size: 1rem !important; }',
        '  .location-option input[type="radio"] { width: 20px; height: 20px; }',
        '  .date-selector label { font-size: 1rem !important; font-weight: 600; }',
        '  .date-selector input, .date-selector button, .date-selector .btn { width: 100% !important; min-height: 46px !important; font-size: 1rem !important; }',
        '  .inventory-controls-panel { grid-template-columns: 1fr !important; gap: 10px !important; padding: 12px !important; }',
        '  .control-group label { font-size: 1rem !important; }',
        '  .search-box, .control-group select { min-height: 44px !important; font-size: 1rem !important; padding: 10px 12px !important; }',
        '  .btn { min-height: 46px !important; font-size: 1rem !important; padding: 10px 14px !important; }',
        '  .quantity-input { width: 84px !important; min-height: 40px !important; font-size: 1rem !important; }',
        '  .category-header { font-size: 1.15rem !important; padding: 10px !important; }',
        '  .categories-container { padding: 8px !important; }',
        '  .category-table { table-layout: fixed !important; width: 100% !important; }',
        '  .category-table th, .category-table td { font-size: 0.9rem !important; padding: 8px 6px !important; overflow-wrap: anywhere; }',
        '  .category-table th:nth-child(1), .category-table td:nth-child(1) { width: 42% !important; }',
        '  .category-table th:nth-child(2), .category-table td:nth-child(2) { width: 24% !important; }',
        '  .category-table th:nth-child(3), .category-table td:nth-child(3) { width: 14% !important; text-align: center !important; }',
        '  .category-table th:nth-child(4), .category-table td:nth-child(4) { width: 20% !important; }',
        '  .row-controls { align-items: flex-start !important; }',
        '  .edit-btn { min-height: 34px !important; font-size: 0.85rem !important; }',
        '  div[style*="text-align: center; margin: 20px 0;"] { display: grid !important; grid-template-columns: 1fr !important; gap: 8px !important; }',
        '  #ic3MobileViewToggle { display: grid !important; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0 12px 0; }',
        '  #ic3MobileViewToggle button { min-height: 44px; border: 1px solid #d1d5db; border-radius: 8px; background: #f8fafc; color: #1f2937; font-size: 0.95rem; font-weight: 700; }',
        '  #ic3MobileViewToggle button.active { background: #2563eb; border-color: #1d4ed8; color: #ffffff; }',
        '  #ic3MobileCards { display: none; gap: 10px; margin-top: 8px; }',
        '  #ic3MobileCards.cards-visible { display: grid !important; grid-template-columns: 1fr; }',
        '  .ic3-mobile-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; border: 1px solid #dbe4f0; background: #ffffff; border-radius: 10px; padding: 10px; box-shadow: 0 2px 6px rgba(15,23,42,0.06); }',
        '  .ic3-mobile-info { min-width: 0; }',
        '  .ic3-mobile-category { font-size: 0.78rem; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 4px; }',
        '  .ic3-mobile-item { font-size: 0.95rem; font-weight: 700; color: #111827; line-height: 1.25; margin-bottom: 4px; }',
        '  .ic3-mobile-meta { font-size: 0.82rem; color: #6b7280; margin-bottom: 8px; }',
        '  .ic3-mobile-controls { display: flex; flex-direction: column; gap: 6px; align-items: stretch; min-width: 94px; }',
        '  .ic3-mobile-controls input { min-height: 40px; font-size: 1rem; width: 100%; padding: 6px 10px; border: 2px solid #d1d5db; border-radius: 8px; }',
        '  .ic3-mobile-controls button { min-height: 38px; font-size: 0.82rem; border-radius: 8px; }',
        '  .ic3-table-hidden-mobile { display: none !important; }',
        '}',
        '@media (max-width: 480px) {',
        '  .tab { min-width: 116px !important; font-size: 0.95rem !important; }',
        '  .header h1 { font-size: 1.75rem !important; }',
        '  .category-table th, .category-table td { font-size: 0.84rem !important; }',
        '}'
    ].join('\n');

    const head = document.head || document.getElementsByTagName('head')[0] || document.documentElement;
    head.appendChild(style);

    const mobileQuery = window.matchMedia('(max-width: 768px)');
    const storageKey = 'ic3-mobile-view-mode';
    const state = {
        mode: 'cards',
        scheduled: false,
    };

    function isMobile() {
        return !!mobileQuery.matches;
    }

    function ensureMobileHosts() {
        const inventoryTab = document.getElementById('inventory');
        const categories = document.getElementById('categoriesContainer');
        if (!inventoryTab || !categories) {
            return null;
        }

        let toggle = document.getElementById('ic3MobileViewToggle');
        if (!toggle) {
            toggle = document.createElement('div');
            toggle.id = 'ic3MobileViewToggle';
            toggle.innerHTML = [
                '<button type="button" data-mode="cards">Card View</button>',
                '<button type="button" data-mode="table">Table View</button>'
            ].join('');
            categories.parentNode.insertBefore(toggle, categories);
            toggle.addEventListener('click', function (event) {
                const button = event.target.closest('button[data-mode]');
                if (!button) return;
                state.mode = button.getAttribute('data-mode') || 'cards';
                localStorage.setItem(storageKey, state.mode);
                applyMode();
            });
        }

        let cards = document.getElementById('ic3MobileCards');
        if (!cards) {
            cards = document.createElement('div');
            cards.id = 'ic3MobileCards';
            categories.parentNode.insertBefore(cards, categories.nextSibling);
        }

        return { toggle: toggle, cards: cards, categories: categories };
    }

    function safeText(value) {
        return String(value || '').replace(/\s+/g, ' ').trim();
    }

    function buildCardDataFromRow(row) {
        const cells = Array.from(row.cells || []);
        const qtyInput = row.querySelector('input.quantity-input');
        if (!qtyInput || !cells.length) {
            return null;
        }

        const productId = safeText((qtyInput.id || '').replace(/^qty_/, ''));
        const section = row.closest('.category-section');
        const sectionHeader = section ? section.querySelector('.category-header') : null;
        let category = safeText(sectionHeader ? sectionHeader.innerText : '');

        const firstBadge = cells[0] ? cells[0].querySelector('span') : null;
        const hasListBadge = !!firstBadge;
        if (hasListBadge) {
            category = safeText(firstBadge.innerText) || category;
        }

        let itemText = '';
        let sizeText = '';
        if (hasListBadge) {
            itemText = safeText(cells[1] ? cells[1].innerText : '');
            sizeText = safeText(cells[2] ? cells[2].innerText : '');
        } else {
            itemText = safeText(cells[0] ? cells[0].innerText : '');
            sizeText = safeText(cells[1] ? cells[1].innerText : '');
        }

        const editButton = row.querySelector('button.edit-btn');
        return {
            category: category || 'Uncategorized',
            item: itemText || ('Product ' + productId),
            size: sizeText || '',
            productId: productId,
            qtyInput: qtyInput,
            editButton: editButton,
        };
    }

    function selectQuantityOnFocus(input) {
        if (!input || input.dataset.ic3SelectAllBound === '1') return;
        input.dataset.ic3SelectAllBound = '1';
        input.addEventListener('focus', function () {
            window.requestAnimationFrame(function () {
                try { input.select(); } catch (_) {}
            });
        });
        input.addEventListener('click', function () {
            try { input.select(); } catch (_) {}
        });
    }

    function installQuantitySelectAll() {
        document.querySelectorAll('input.quantity-input, #ic3MobileCards input[type="number"]').forEach(selectQuantityOnFocus);
    }

    function renderCards() {
        const hosts = ensureMobileHosts();
        if (!hosts) {
            return;
        }

        const cardsRoot = hosts.cards;
        cardsRoot.innerHTML = '';

        const rows = Array.from(hosts.categories.querySelectorAll('tbody tr'));
        const visibleRows = rows.filter(function (row) {
            const input = row.querySelector('input.quantity-input');
            if (!input) return false;
            const styleInfo = window.getComputedStyle(row);
            if (styleInfo.display === 'none' || styleInfo.visibility === 'hidden') return false;
            return true;
        });

        if (!visibleRows.length) {
            cardsRoot.innerHTML = '<div class="ic3-mobile-card"><div class="ic3-mobile-item">No items match the current filters.</div></div>';
            return;
        }

        visibleRows.forEach(function (row) {
            const data = buildCardDataFromRow(row);
            if (!data) return;

            const card = document.createElement('div');
            card.className = 'ic3-mobile-card';

            const category = document.createElement('div');
            category.className = 'ic3-mobile-category';
            category.textContent = data.category;

            const item = document.createElement('div');
            item.className = 'ic3-mobile-item';
            item.textContent = data.item;

            const meta = document.createElement('div');
            meta.className = 'ic3-mobile-meta';
            meta.textContent = (data.size ? data.size + ' | ' : '') + 'ID: ' + data.productId;

            const controls = document.createElement('div');
            controls.className = 'ic3-mobile-controls';

            const cardQty = document.createElement('input');
            cardQty.type = 'number';
            cardQty.min = data.qtyInput.min || '0';
            cardQty.step = data.qtyInput.step || '0.25';
            cardQty.value = data.qtyInput.value || '0';
            cardQty.setAttribute('inputmode', 'decimal');
            cardQty.addEventListener('input', function () {
                data.qtyInput.value = cardQty.value;
                data.qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
            });
            cardQty.addEventListener('change', function () {
                data.qtyInput.value = cardQty.value;
                data.qtyInput.dispatchEvent(new Event('change', { bubbles: true }));
            });
            selectQuantityOnFocus(cardQty);

            controls.appendChild(cardQty);

            const actionWrap = document.createElement('div');
            if (data.editButton) {
                const editAction = document.createElement('button');
                editAction.type = 'button';
                editAction.className = 'btn';
                editAction.textContent = 'Edit';
                editAction.addEventListener('click', function () {
                    data.editButton.click();
                });
                actionWrap.appendChild(editAction);
            }
            controls.appendChild(actionWrap);

            const info = document.createElement('div');
            info.className = 'ic3-mobile-info';
            info.appendChild(category);
            info.appendChild(item);
            info.appendChild(meta);
            card.appendChild(info);
            card.appendChild(controls);
            cardsRoot.appendChild(card);
        });
    }

    function applyMode() {
        const hosts = ensureMobileHosts();
        if (!hosts) {
            return;
        }

        const buttons = Array.from(hosts.toggle.querySelectorAll('button[data-mode]'));
        buttons.forEach(function (button) {
            const isActive = button.getAttribute('data-mode') === state.mode;
            button.classList.toggle('active', isActive);
        });

        if (!isMobile()) {
            hosts.toggle.style.display = 'none';
            hosts.cards.classList.remove('cards-visible');
            hosts.categories.classList.remove('ic3-table-hidden-mobile');
            return;
        }

        hosts.toggle.style.display = 'grid';
        const activeElement = document.activeElement;
        const editingQuantity = activeElement && activeElement.matches && activeElement.matches('#ic3MobileCards input[type="number"]');
        if (!editingQuantity) {
            renderCards();
        }
        const showCards = state.mode === 'cards';
        hosts.cards.classList.toggle('cards-visible', showCards);
        hosts.categories.classList.toggle('ic3-table-hidden-mobile', showCards);
    }

    function scheduleRefresh() {
        const activeElement = document.activeElement;
        if (activeElement && activeElement.matches && activeElement.matches('#ic3MobileCards input[type="number"]')) {
            return;
        }
        if (state.scheduled) {
            return;
        }
        state.scheduled = true;
        window.requestAnimationFrame(function () {
            state.scheduled = false;
            applyMode();
        });
    }

    function installRefreshHooks() {
        const ids = ['searchBox', 'sortBy', 'viewMode', 'showEditButtons'];
        ids.forEach(function (id) {
            const el = document.getElementById(id);
            if (!el || el.dataset.ic3MobileHooked === '1') {
                return;
            }
            el.dataset.ic3MobileHooked = '1';
            el.addEventListener('input', scheduleRefresh);
            el.addEventListener('change', scheduleRefresh);
        });
        installQuantitySelectAll();

        if (!document.body.dataset.ic3MobileObserverInstalled) {
            const observer = new MutationObserver(function () {
                const activeElement = document.activeElement;
                if (activeElement && activeElement.matches && activeElement.matches('#ic3MobileCards input[type="number"]')) {
                    return;
                }
                scheduleRefresh();
            });
            observer.observe(document.body, { childList: true, subtree: true });
            document.body.dataset.ic3MobileObserverInstalled = '1';
        }
    }

    function defaultShowEditButtonsOff() {
        const toggle = document.getElementById('showEditButtons');
        if (!toggle || toggle.dataset.ic3DefaultApplied === '1') {
            return;
        }
        toggle.dataset.ic3DefaultApplied = '1';
        if (toggle.checked) {
            toggle.checked = false;
            toggle.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    if (mobileQuery && typeof mobileQuery.addEventListener === 'function') {
        mobileQuery.addEventListener('change', scheduleRefresh);
    } else if (mobileQuery && typeof mobileQuery.addListener === 'function') {
        mobileQuery.addListener(scheduleRefresh);
    }

    const runInstall = function () {
        defaultShowEditButtonsOff();
        installRefreshHooks();
        applyMode();
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runInstall);
    } else {
        runInstall();
    }

    // Mobile smoke checklist:
    // 1) Tabs readable + horizontally scrollable.
    // 2) Location/date/search/sort controls are tap-friendly.
    // 3) Card/Table toggle works and quantity edits stay in sync.
    // 4) Quantity inputs and save/load buttons are easy to tap.
    // 5) Desktop layout remains unchanged above 768px.
})();
</script>
"""


def _rewrite_bulk_upload_text(payload: str) -> str:
    literal_replacements = (
        ("Bulk Upload (Up to 20)", "Bulk Upload"),
        ("Add up to 20 invoices at once. Each invoice can have its own delivery date.", "Add as many invoices as needed. Each invoice can have its own delivery date."),
        ("Invoice List (<span id=\"invoiceCount\">0</span>/20)", "Invoice List (<span id=\"invoiceCount\">0</span>)"),
        ("Maximum is 20 total.", "No maximum limit."),
        ("const remaining = 20 - bulkInvoices.length;", "const remaining = Number.POSITIVE_INFINITY;"),
        ("const deliveryDate = dateField.value;", "const selectedDeliveryDate = (dateField.value || '').trim();\n            const parsedDeliveryDate = dateFromFilename(file.name);\n            const deliveryDate = selectedDeliveryDate || parsedDeliveryDate;\n            if (!selectedDeliveryDate) {\n                dateField.value = deliveryDate;\n            }"),
        ("formData.append('delivery_date', invoice.date);", "formData.append('delivery_date', invoice.date || dateFromFilename(invoice.file.name));"),
        ("http://localhost:5003/api/", "/api/"),
        ("https://localhost:5003/api/", "/api/"),
        ("http://127.0.0.1:5003/api/", "/api/"),
        ("https://127.0.0.1:5003/api/", "/api/"),
        (
            "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n    }\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
            "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
        ),
    )

    updated = payload
    for old, new in literal_replacements:
        updated = updated.replace(old, new)

    updated = re.sub(
        r"if\s*\(files\.length\s*>\s*remaining\)\s*\{\s*alert\(`You can only add \$\{remaining\} more invoice\(s\)\. Maximum is 20 total\.`\);\s*files\.splice\(remaining\);\s*\}",
        "",
        updated,
        flags=re.DOTALL,
    )
    updated = re.sub(
        r"(const\s+selectedRadio\s*=\s*document\.querySelector\('input\[name=\"location\"\]\[type=\"radio\"\]:checked'\);\s*)\}\s*(if\s*\(selectedRadio)",
        r"\1\2",
        updated,
        flags=re.DOTALL,
    )
    updated = re.sub(
        r'(<input[^>]*id=["\']showEditButtons["\'][^>]*?)\schecked(?:=(?:"[^"]*"|\'[^\']*\'|[^\s>]+))?',
        r"\1",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r"function\s+dateFromFilename\(filename\)\s*\{[\s\S]*?return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
        "function dateFromFilename(filename) {\\n            const m = filename.match(/(\\\\d{4})[-_\\/](\\\\d{2})[-_\\/](\\\\d{2})|^(\\\\d{4})(\\\\d{2})(\\\\d{2})/);\\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\\n            return new Date().toISOString().split('T')[0];\\n        }",
        updated,
        flags=re.DOTALL,
    )
    updated = re.sub(
        r"function\s+showBulkUpload\(\)\s*\{[\s\S]*?\}",
        "function showBulkUpload() {\\n            document.getElementById('singleUploadSection').style.display = 'none';\\n            document.getElementById('bulkUploadSection').style.display = 'block';\\n            bulkInvoices = [];\\n            renderBulkInvoiceList();\\n            const bulkStatus = document.getElementById('bulkUploadStatus');\\n            if (bulkStatus) bulkStatus.style.display = 'none';\\n        }",
        updated,
        flags=re.DOTALL,
    )
    updated = re.sub(
        r"function\s+dateFromFilename\(filename\)\s*\{\s*const\s+m\s*=\s*filename\.match\(/\^\\\(\\d\{4\}\\\)\\\(\\d\{2\}\\\)\\\(\\d\{2\}\\\)/\);\s*if\s*\(m\)\s*return\s*`\$\{m\[1\]\}-\$\{m\[2\]\}-\$\{m\[3\]\}`;\s*return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
        "function dateFromFilename(filename) {\\n            const m = filename.match(/(\\\\d{4})[-_\\/](\\\\d{2})[-_\\/](\\\\d{2})|^(\\\\d{4})(\\\\d{2})(\\\\d{2})/);\\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\\n            return new Date().toISOString().split('T')[0];\\n        }",
        updated,
        flags=re.DOTALL,
    )
    if "__ic3InvoiceOverrideInstalled" not in updated and "</body>" in updated:
        updated = updated.replace("</body>", OVERRIDE_SCRIPT + "\n</body>", 1)

    if "__ic3ProductDetailInstalled" not in updated and "</body>" in updated:
        updated = updated.replace("</body>", PRODUCT_DETAIL_SCRIPT + "\n</body>", 1)

    if "__ic3MobileUiInstalled" not in updated and "</body>" in updated:
        updated = updated.replace("</body>", MOBILE_UI_SCRIPT + "\n</body>", 1)

    if "__ic3ProductMixSyncUiInstalled" not in updated and "</body>" in updated:
        updated = updated.replace(
            "</body>",
            PRODUCTMIX_SYNC_UI_SCRIPT + "\n" + LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>",
            1,
        )

    if "__ic3SharedLocationsInstalled" not in updated and "</body>" in updated:
        updated = updated.replace("</body>", LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>", 1)

    updated = updated.replace(
        "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n    }\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
        "const selectedRadio = document.querySelector('input[name=\"location\"][type=\"radio\"]:checked');\n        if (selectedRadio && typeof selectedRadio.value === 'string' && selectedRadio.value.trim()) {",
    )

    updated = re.sub(
        r"(const\s+selectedRadio\s*=\s*document\.querySelector\('input\[name=\"location\"\]\[type=\"radio\"\]:checked'\);\s*)\}\s*(if\s*\(selectedRadio)",
        r"\1\2",
        updated,
        flags=re.DOTALL,
    )

    return updated


def _build_order_csv_target_name(path: Path, location: str, seen_per_day: dict[str, int]) -> str | None:
    match = ORDER_CSV_DATE_PREFIX.match(path.name)
    if not match:
        return None

    yyyy, mm, dd = match.group(1), match.group(2), match.group(3)
    day_key = f"{yyyy}-{mm}-{dd}"
    seen_per_day[day_key] = seen_per_day.get(day_key, 0) + 1
    suffix = "" if seen_per_day[day_key] == 1 else f"_part{seen_per_day[day_key]}"
    return f"{location}_{day_key}_order{suffix}.csv"


def _plan_order_csv_renames(folder: Path, location: str) -> list[dict[str, str]]:
    seen_per_day: dict[str, int] = {}
    existing_names = {path.name.lower() for path in folder.glob("*.csv")}
    planned_targets: set[str] = set()
    planned: list[dict[str, str]] = []

    for path in sorted(folder.glob("*.csv")):
        new_name = _build_order_csv_target_name(path, location, seen_per_day)
        if not new_name or new_name == path.name:
            continue

        stem = Path(new_name).stem
        suffix = Path(new_name).suffix
        candidate = new_name
        counter = 1

        while True:
            candidate_key = candidate.lower()
            conflicts_existing = candidate_key in existing_names and candidate_key != path.name.lower()
            conflicts_planned = candidate_key in planned_targets
            if not conflicts_existing and not conflicts_planned:
                break
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1

        planned.append({"old_name": path.name, "new_name": candidate})
        planned_targets.add(candidate.lower())

    return planned


def _canonical_product_number(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    if re.fullmatch(r"\d+\.0+", text):
        try:
            return str(int(float(text)))
        except Exception:
            return text

    return text


def _safe_parse_date(date_str: str | None):
    text = str(date_str or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _window_start_date(window_key: str, today_value=None):
    today_day = today_value or date.today()
    key = str(window_key or "week").strip().lower()
    if key == "ytd":
        return date(today_day.year, 1, 1)
    if key == "month":
        return today_day - timedelta(days=29)
    return today_day - timedelta(days=13)  # "week" = 2 weeks to avoid data boundary gaps


def _window_filter_dates(items, window_key):
    today_day = date.today()
    start_day = _window_start_date(window_key, today_day)
    filtered = []

    for item in (items or []):
        day = _safe_parse_date(item.get("date"))
        if not day:
            continue
        if start_day <= day <= today_day:
            filtered.append(item)

    return sorted(filtered, key=lambda row: str(row.get("date") or ""))


def _usage_parse_bool(raw_value, default=False) -> bool:
    if raw_value is None:
        return bool(default)
    text = str(raw_value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return bool(default)


def _usage_to_float(raw_value, default=0.0) -> float:
    try:
        return float(raw_value)
    except Exception:
        return float(default)


def _usage_iter_days(start_day, end_day):
    current = start_day
    while current <= end_day:
        yield current
        current += timedelta(days=1)


def _usage_group_by_product_inventory(location_name: str) -> dict[str, dict[str, float]]:
    inventory_data_obj = globals().get("inventory_data") or {}
    by_product: dict[str, dict[str, float]] = defaultdict(dict)
    by_date = inventory_data_obj.get(location_name, {}) if isinstance(inventory_data_obj, dict) else {}

    if not isinstance(by_date, dict):
        return {}

    for date_key, snapshot in by_date.items():
        if not isinstance(snapshot, dict):
            continue
        date_str = str(date_key or "").strip()
        if not date_str:
            continue
        for raw_product_num, raw_qty in snapshot.items():
            product_num = _canonical_product_number(raw_product_num)
            if not product_num:
                continue
            by_product[product_num][date_str] = _usage_to_float(raw_qty, 0.0)

    return dict(by_product)


def _usage_group_by_product_receipts(location_name: str) -> dict[str, dict[str, float]]:
    log_rows = globals().get("invoice_import_log") or []
    by_product: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for entry in log_rows if isinstance(log_rows, list) else []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("location") or "").strip() != location_name:
            continue

        date_str = str(entry.get("delivery_date") or "").strip()
        if not date_str:
            continue

        products_map = entry.get("products")
        if isinstance(products_map, dict):
            for raw_product_num, raw_qty in products_map.items():
                product_num = _canonical_product_number(raw_product_num)
                if not product_num:
                    continue
                by_product[product_num][date_str] += _usage_to_float(raw_qty, 0.0)
            continue

        line_items = entry.get("line_items")
        if isinstance(line_items, list):
            for row in line_items:
                if not isinstance(row, dict):
                    continue
                product_num = _canonical_product_number(
                    row.get("canonical_product_number")
                    or row.get("raw_product_number")
                    or row.get("product_number")
                )
                if not product_num:
                    continue
                by_product[product_num][date_str] += _usage_to_float(row.get("quantity"), 0.0)

    return {k: dict(v) for k, v in by_product.items()}


def _usage_snapshot_value(inv_map: dict[str, float], target_day, direction: str):
    exact_key = target_day.isoformat()
    if exact_key in inv_map:
        return inv_map[exact_key], exact_key, True

    dated_values = []
    for date_key, qty in inv_map.items():
        day = _safe_parse_date(date_key)
        if day is None:
            continue
        dated_values.append((day, date_key, _usage_to_float(qty, 0.0)))

    if not dated_values:
        return 0.0, "", False

    if direction == "backward":
        prior = [row for row in dated_values if row[0] <= target_day]
        if prior:
            row = max(prior, key=lambda r: r[0])
            return row[2], row[1], False
        row = min(dated_values, key=lambda r: r[0])
        return row[2], row[1], False

    ahead = [row for row in dated_values if row[0] >= target_day]
    if ahead:
        row = min(ahead, key=lambda r: r[0])
        return row[2], row[1], False
    row = max(dated_values, key=lambda r: r[0])
    return row[2], row[1], False


def _usage_prepare_inventory(inv_map: dict[str, float]):
    dated_values = []
    for date_key, qty in (inv_map or {}).items():
        day = _safe_parse_date(date_key)
        if day is None:
            continue
        dated_values.append((day, str(date_key), _usage_to_float(qty, 0.0)))

    dated_values.sort(key=lambda row: row[0])
    days = [row[0] for row in dated_values]
    exact_lookup = {row[1]: row[2] for row in dated_values}
    return {
        "dated_values": dated_values,
        "days": days,
        "exact_lookup": exact_lookup,
    }


def _usage_snapshot_value_prepared(prepared_inv, target_day, direction: str):
    exact_key = target_day.isoformat()
    exact_lookup = prepared_inv.get("exact_lookup", {}) if isinstance(prepared_inv, dict) else {}
    if exact_key in exact_lookup:
        return _usage_to_float(exact_lookup[exact_key], 0.0), exact_key, True

    dated_values = prepared_inv.get("dated_values", []) if isinstance(prepared_inv, dict) else []
    days = prepared_inv.get("days", []) if isinstance(prepared_inv, dict) else []
    if not dated_values or not days:
        return 0.0, "", False

    if direction == "backward":
        idx = bisect_right(days, target_day) - 1
        if idx < 0:
            idx = 0
        row = dated_values[idx]
        return row[2], row[1], False

    idx = bisect_left(days, target_day)
    if idx >= len(dated_values):
        idx = len(dated_values) - 1
    row = dated_values[idx]
    return row[2], row[1], False


def _usage_daily_series_for_product(inv_map: dict[str, float], receipt_map: dict[str, float], start_day, end_day, prepared_inv=None):
    rows = []
    weekday_usage = defaultdict(list)
    if prepared_inv is None:
        prepared_inv = _usage_prepare_inventory(inv_map)

    for day in _usage_iter_days(start_day, end_day):
        next_day = day + timedelta(days=1)
        opening_qty, opening_date_key, opening_exact = _usage_snapshot_value_prepared(prepared_inv, day, "backward")
        closing_qty, closing_date_key, closing_exact = _usage_snapshot_value_prepared(prepared_inv, next_day, "forward")

        receipts_qty = _usage_to_float(receipt_map.get(day.isoformat()), 0.0)
        usage_qty = opening_qty + receipts_qty - closing_qty
        weekday_name = day.strftime("%A")

        calc_mode = "count_to_count" if (opening_exact and closing_exact) else "estimated_fallback"
        weekday_usage[weekday_name].append(usage_qty)
        rows.append(
            {
                "date": day.isoformat(),
                "weekday": weekday_name,
                "opening_inventory": round(opening_qty, 4),
                "receipts": round(receipts_qty, 4),
                "closing_inventory": round(closing_qty, 4),
                "usage": round(usage_qty, 4),
                "calculation_mode": calc_mode,
                "opening_inventory_date": opening_date_key,
                "closing_inventory_date": closing_date_key,
            }
        )

    weekday_avg = {}
    for weekday_name in ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
        values = weekday_usage.get(weekday_name, [])
        weekday_avg[weekday_name.lower()] = round(sum(values) / len(values), 4) if values else 0.0

    return rows, weekday_avg


def _register_usage_reports_endpoints(flask_app) -> None:
    if flask_app is None:
        return

    def _usage_velocity_profile(avg_daily_usage: float):
        profile_fn = globals().get("_velocity_profile")
        if callable(profile_fn):
            try:
                band, target_days, upper_days = profile_fn(avg_daily_usage)
                return str(band), float(target_days), float(upper_days)
            except Exception:
                pass

        if avg_daily_usage >= 1.0:
            return "fast", 7.0, 10.0
        if avg_daily_usage >= 0.25:
            return "medium", 10.0, 14.0
        return "slow", 15.0, 20.0

    def _usage_latest_unit_cost(location_name: str, product_num: str, as_of_day):
        latest_cost = 0.0
        latest_date = None
        log_rows = globals().get("invoice_import_log") or []
        for entry in log_rows if isinstance(log_rows, list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("location") or "").strip() != location_name:
                continue
            date_key = str(entry.get("delivery_date") or "").strip()
            day = _safe_parse_date(date_key)
            if day is None or day > as_of_day:
                continue

            price_map = entry.get("product_prices")
            if not isinstance(price_map, dict):
                continue

            for raw_num, raw_price in price_map.items():
                if _canonical_product_number(raw_num) != product_num:
                    continue
                price = _usage_to_float(raw_price, 0.0)
                if latest_date is None or day >= latest_date:
                    latest_date = day
                    latest_cost = price
        return round(latest_cost, 4)

    def api_product_activity_usage_runtime():
        location_name = str(request.args.get("location") or _effective_runtime_location()).strip()
        start_day = _safe_parse_date(request.args.get("start_date"))
        end_day = _safe_parse_date(request.args.get("end_date"))
        include_zero_rows = _usage_parse_bool(request.args.get("include_zero_rows"), default=False)

        if not location_name:
            return jsonify({"success": False, "message": "location is required"}), 400
        if not start_day or not end_day:
            return jsonify({"success": False, "message": "start_date and end_date are required (YYYY-MM-DD)"}), 400
        if start_day > end_day:
            return jsonify({"success": False, "message": "start_date cannot be after end_date"}), 400

        inventory_by_product = _usage_group_by_product_inventory(location_name)
        receipts_by_product = _usage_group_by_product_receipts(location_name)
        products = globals().get("products_list") or []
        if not isinstance(products, list):
            products = []

        rows = []
        for product_index, product in enumerate(products):
            if not isinstance(product, dict):
                continue

            product_num = _canonical_product_number(product.get("Product Number"))
            if not product_num:
                continue

            inv_map = inventory_by_product.get(product_num, {})
            receipt_map = receipts_by_product.get(product_num, {})
            daily_rows, weekday_avg = _usage_daily_series_for_product(inv_map, receipt_map, start_day, end_day)

            total_usage = round(sum(_usage_to_float(row.get("usage"), 0.0) for row in daily_rows), 2)
            total_receipts = round(sum(_usage_to_float(row.get("receipts"), 0.0) for row in daily_rows), 2)
            begin_inv = _usage_to_float(daily_rows[0].get("opening_inventory"), 0.0) if daily_rows else 0.0
            ending_inv = _usage_to_float(daily_rows[-1].get("closing_inventory"), 0.0) if daily_rows else 0.0

            inventory_dates = []
            for date_key, qty in sorted(inv_map.items()):
                day = _safe_parse_date(date_key)
                if day is None or day < start_day or day > end_day:
                    continue
                inventory_dates.append({"date": date_key, "location": location_name, "quantity": round(_usage_to_float(qty, 0.0), 4)})

            order_dates = []
            for date_key, qty in sorted(receipt_map.items()):
                day = _safe_parse_date(date_key)
                if day is None or day < start_day or day > end_day:
                    continue
                order_dates.append({"date": date_key, "location": location_name, "quantity": round(_usage_to_float(qty, 0.0), 4)})

            if (not include_zero_rows) and abs(total_usage) < 1e-9 and abs(total_receipts) < 1e-9 and not inventory_dates:
                continue

            row = {
                "product_order_index": product_index,
                "product_number": product_num,
                "description": str(product.get("Product Description") or ""),
                "brand": str(product.get("Product Brand") or ""),
                "package_size": str(product.get("Product Package Size") or ""),
                "group": str(product.get("Group Name") or ""),
                "case_count_type": str(product.get("Case Count Type") or "No"),
                "member_product_numbers": [product_num],
                "rolled_up_sub_count": 0,
                "beginning_inventory": round(begin_inv, 2),
                "beginning_inventory_meta": {"date": start_day.isoformat(), "location": location_name},
                "ending_inventory": round(ending_inv, 2),
                "ending_inventory_meta": {"date": (end_day + timedelta(days=1)).isoformat(), "location": location_name},
                "total_orders": round(total_receipts, 2),
                "total_orders_meta": {"source": "invoice_import_log"},
                "usage": round(total_usage, 2),
                "cases_required": round(max(0.0, total_usage - ending_inv), 2),
                "inventory_count": len(inventory_dates),
                "order_count": len(order_dates),
                "total_activity": len(inventory_dates) + len(order_dates),
                "inventory_dates": inventory_dates,
                "order_dates": order_dates,
                "weekday_usage_avg": weekday_avg,
                "usage_daily": daily_rows,
            }
            rows.append(row)

        rows.sort(key=lambda r: int(r.get("product_order_index") or 0))
        return jsonify(
            {
                "success": True,
                "location": location_name,
                "date_range": {"start": start_day.isoformat(), "end": end_day.isoformat()},
                "products": rows,
                "total_products": len(rows),
                "usage_model": {
                    "week_start": "Sunday",
                    "formula": "opening_inventory + receipts - next_day_closing_inventory",
                    "receipts_source": "invoice_import_log",
                    "negative_usage_allowed": True,
                },
            }
        )

    def api_weekly_usage_runtime():
        location_name = str(request.args.get("location") or _effective_runtime_location()).strip()
        start_day = _safe_parse_date(request.args.get("start_date"))
        end_day = _safe_parse_date(request.args.get("end_date"))
        include_zero_rows = _usage_parse_bool(request.args.get("include_zero_rows"), default=False)

        if not location_name:
            return jsonify({"success": False, "message": "location is required"}), 400
        if not start_day or not end_day:
            return jsonify({"success": False, "message": "start_date and end_date are required (YYYY-MM-DD)"}), 400
        if start_day > end_day:
            return jsonify({"success": False, "message": "start_date cannot be after end_date"}), 400

        inventory_by_product = _usage_group_by_product_inventory(location_name)
        receipts_by_product = _usage_group_by_product_receipts(location_name)
        products = globals().get("products_list") or []
        if not isinstance(products, list):
            products = []

        days_back_to_sunday = (start_day.weekday() + 1) % 7
        first_sunday = start_day - timedelta(days=days_back_to_sunday)

        windows = []
        cursor = first_sunday
        while cursor <= end_day:
            window_start = cursor
            window_end_marker = cursor + timedelta(days=8)
            windows.append((window_start, window_end_marker))
            cursor += timedelta(days=7)

        rows = []
        usage_history_by_product = defaultdict(list)
        windows_skipped = 0

        prepared_inventory_by_product = {
            product_num: _usage_prepare_inventory(inventory_by_product.get(product_num, {}))
            for product_num in set(list(inventory_by_product.keys()) + list(receipts_by_product.keys()))
        }
        product_activity_bounds = {}
        for product_num, prepared_inv in prepared_inventory_by_product.items():
            inv_days = prepared_inv.get("days", []) if isinstance(prepared_inv, dict) else []
            receipt_days = []
            for date_key in (receipts_by_product.get(product_num, {}) or {}).keys():
                day = _safe_parse_date(date_key)
                if day is not None:
                    receipt_days.append(day)

            all_days = list(inv_days) + receipt_days
            if all_days:
                product_activity_bounds[product_num] = (min(all_days), max(all_days))

        for window_start, window_end_marker in windows:
            daily_end = window_end_marker - timedelta(days=1)

            for product_index, product in enumerate(products):
                if not isinstance(product, dict):
                    continue

                product_num = _canonical_product_number(product.get("Product Number"))
                if not product_num:
                    continue

                inv_map = inventory_by_product.get(product_num, {})
                receipt_map = receipts_by_product.get(product_num, {})
                if not inv_map and not receipt_map:
                    continue

                bounds = product_activity_bounds.get(product_num)
                if bounds:
                    activity_min, activity_max = bounds
                    if daily_end < activity_min or window_start > (activity_max + timedelta(days=1)):
                        continue

                prepared_inv = prepared_inventory_by_product.get(product_num) or _usage_prepare_inventory(inv_map)
                daily_rows, weekday_avg = _usage_daily_series_for_product(inv_map, receipt_map, window_start, daily_end, prepared_inv=prepared_inv)

                if not daily_rows:
                    continue

                begin_inv = _usage_to_float(daily_rows[0].get("opening_inventory"), 0.0)
                ending_inv = _usage_to_float(daily_rows[-1].get("closing_inventory"), 0.0)
                total_orders = sum(_usage_to_float(row.get("receipts"), 0.0) for row in daily_rows)
                usage = sum(_usage_to_float(row.get("usage"), 0.0) for row in daily_rows)

                usage_history_by_product[product_num].append(usage)
                trailing = usage_history_by_product[product_num][-4:]
                avg_weekly_usage = (sum(trailing) / len(trailing)) if trailing else 0.0
                avg_daily_usage = avg_weekly_usage / 8.0 if avg_weekly_usage else 0.0

                velocity_band, target_dos, upper_dos = _usage_velocity_profile(avg_daily_usage)
                days_of_supply = (ending_inv / avg_daily_usage) if avg_daily_usage > 0 else 0.0
                reorder_point = avg_daily_usage * 3.0
                target_stock = avg_daily_usage * target_dos
                on_order_qty = 0.0
                suggested_order_qty = max(0.0, target_stock - ending_inv - on_order_qty)
                do_not_order = bool(avg_daily_usage > 0 and days_of_supply > upper_dos)

                unit_cost = _usage_latest_unit_cost(location_name, product_num, window_end_marker)
                on_hand_value = ending_inv * unit_cost
                excess_qty = max(0.0, ending_inv - target_stock)
                excess_value = excess_qty * unit_cost

                if (not include_zero_rows) and abs(usage) < 1e-9 and abs(total_orders) < 1e-9 and abs(begin_inv) < 1e-9 and abs(ending_inv) < 1e-9:
                    windows_skipped += 1
                    continue

                row = {
                    "row_order": len(rows),
                    "product_order_index": product_index,
                    "product_number": product_num,
                    "description": str(product.get("Product Description") or ""),
                    "brand": str(product.get("Product Brand") or ""),
                    "package_size": str(product.get("Product Package Size") or ""),
                    "group": str(product.get("Group Name") or ""),
                    "case_count_type": str(product.get("Case Count Type") or "No"),
                    "member_product_numbers": [product_num],
                    "rolled_up_sub_count": 0,
                    "window_start": window_start.isoformat(),
                    "window_end": window_end_marker.isoformat(),
                    "start_snapshot_date": str(daily_rows[0].get("opening_inventory_date") or ""),
                    "end_snapshot_date": str(daily_rows[-1].get("closing_inventory_date") or ""),
                    "start_snapshot_offset_days": 0,
                    "end_snapshot_offset_days": 0,
                    "window_days": 8,
                    "beginning_inventory": round(begin_inv, 2),
                    "total_orders": round(total_orders, 2),
                    "ending_inventory": round(ending_inv, 2),
                    "usage": round(usage, 2),
                    "avg_8day_usage_4w": round(avg_weekly_usage, 2),
                    "avg_weekly_usage_4w": round(avg_weekly_usage, 2),
                    "avg_daily_usage_4w": round(avg_daily_usage, 4),
                    "velocity_band": velocity_band,
                    "days_of_supply": round(days_of_supply, 2),
                    "target_days_of_supply": round(target_dos, 2),
                    "reorder_point": round(reorder_point, 2),
                    "target_stock": round(target_stock, 2),
                    "on_order_qty": round(on_order_qty, 2),
                    "suggested_order_qty": round(suggested_order_qty, 2),
                    "do_not_order": do_not_order,
                    "unit_cost": round(unit_cost, 4),
                    "on_hand_value": round(on_hand_value, 2),
                    "excess_qty": round(excess_qty, 2),
                    "excess_value": round(excess_value, 2),
                    "weekday_usage_avg": weekday_avg,
                    "avg_sunday_usage": round(weekday_avg.get("sunday", 0.0), 4),
                    "avg_monday_usage": round(weekday_avg.get("monday", 0.0), 4),
                    "avg_tuesday_usage": round(weekday_avg.get("tuesday", 0.0), 4),
                    "avg_wednesday_usage": round(weekday_avg.get("wednesday", 0.0), 4),
                    "avg_thursday_usage": round(weekday_avg.get("thursday", 0.0), 4),
                    "avg_friday_usage": round(weekday_avg.get("friday", 0.0), 4),
                    "avg_saturday_usage": round(weekday_avg.get("saturday", 0.0), 4),
                    "usage_daily": daily_rows,
                }
                rows.append(row)

        rows.sort(key=lambda r: (str(r.get("window_start") or ""), int(r.get("product_order_index") or 0)))
        return jsonify(
            {
                "success": True,
                "location": location_name,
                "start_date": start_day.isoformat(),
                "end_date": end_day.isoformat(),
                "rows": rows,
                "total_rows": len(rows),
                "total_products": len({str(r.get("product_number") or "") for r in rows}),
                "windows_used": len(windows),
                "windows_skipped": windows_skipped,
                "usage_model": {
                    "week_start": "Sunday",
                    "day_formula": "opening_inventory + receipts - next_day_closing_inventory",
                    "averaging": "same_weekday_across_weeks",
                    "receipts_source": "invoice_import_log",
                    "negative_usage_allowed": True,
                },
                "assumptions": {
                    "week_start": "Sunday",
                    "window_days": 8,
                    "formula": "opening_inventory + receipts - next_day_closing_inventory",
                    "receipts_source": "invoice_import_log",
                    "negative_usage_allowed": True,
                },
            }
        )

    def api_period_usage_runtime():
        payload = request.get_json(silent=True) if request.method != "GET" else {}
        if not isinstance(payload, dict):
            payload = {}

        def _pick(name, fallback=""):
            if request.method == "GET":
                return request.args.get(name, fallback)
            return payload.get(name, request.form.get(name, fallback))

        location_name = str(_pick("location", _effective_runtime_location())).strip()
        from_day = _safe_parse_date(_pick("from_date", ""))
        to_day = _safe_parse_date(_pick("to_date", ""))
        include_zero_rows = _usage_parse_bool(_pick("include_zero_rows", False), default=False)

        if not location_name:
            return jsonify({"success": False, "message": "location is required"}), 400
        if not from_day or not to_day:
            return jsonify({"success": False, "message": "from_date and to_date are required (YYYY-MM-DD)"}), 400
        if from_day > to_day:
            return jsonify({"success": False, "message": "from_date cannot be after to_date"}), 400

        inventory_by_product = _usage_group_by_product_inventory(location_name)
        receipts_by_product = _usage_group_by_product_receipts(location_name)
        products = globals().get("products_list") or []
        if not isinstance(products, list):
            products = []

        count_dates = set()
        for inv_map in inventory_by_product.values():
            for date_key in inv_map.keys():
                day = _safe_parse_date(date_key)
                if day is None:
                    continue
                if from_day <= day <= to_day:
                    count_dates.add(day)

        count_days_sorted = sorted(count_dates)
        count_dates_found = [d.isoformat() for d in count_days_sorted]

        period_pairs = []
        for idx in range(len(count_days_sorted) - 1):
            period_from = count_days_sorted[idx]
            period_to = count_days_sorted[idx + 1]
            if period_to <= period_from:
                continue
            period_pairs.append((period_from, period_to))

        rows = []
        product_summary = {}

        for product_index, product in enumerate(products):
            if not isinstance(product, dict):
                continue
            product_num = _canonical_product_number(product.get("Product Number"))
            if not product_num:
                continue

            inv_map = inventory_by_product.get(product_num, {})
            receipt_map = receipts_by_product.get(product_num, {})
            product_rows = []

            for period_from, period_to in period_pairs:
                open_qty, _, _ = _usage_snapshot_value(inv_map, period_from, "backward")
                end_qty, _, _ = _usage_snapshot_value(inv_map, period_to, "forward")

                orders_received = 0.0
                cursor = period_from
                while cursor < period_to:
                    orders_received += _usage_to_float(receipt_map.get(cursor.isoformat()), 0.0)
                    cursor += timedelta(days=1)

                raw_usage = open_qty + orders_received - end_qty
                usage = raw_usage
                days_in_period = max(1, (period_to - period_from).days)
                daily_rate = usage / float(days_in_period)
                discrepancy_flag = raw_usage < -0.001

                if (not include_zero_rows) and abs(raw_usage) < 1e-9 and abs(orders_received) < 1e-9 and abs(open_qty) < 1e-9 and abs(end_qty) < 1e-9:
                    continue

                row = {
                    "product_order_index": product_index,
                    "product_number": product_num,
                    "description": str(product.get("Product Description") or ""),
                    "brand": str(product.get("Product Brand") or ""),
                    "package_size": str(product.get("Product Package Size") or ""),
                    "group": str(product.get("Group Name") or ""),
                    "member_product_numbers": [product_num],
                    "rolled_up_sub_count": 0,
                    "period_from": period_from.isoformat(),
                    "period_to": period_to.isoformat(),
                    "days_in_period": int(days_in_period),
                    "beginning_inventory": round(open_qty, 2),
                    "orders_received": round(orders_received, 2),
                    "ending_inventory": round(end_qty, 2),
                    "raw_usage": round(raw_usage, 2),
                    "usage": round(usage, 2),
                    "daily_rate": round(daily_rate, 4),
                    "avg_daily_rate": round(daily_rate, 4),
                    "discrepancy_flag": bool(discrepancy_flag),
                    "discrepancy_note": "Negative usage detected" if discrepancy_flag else "",
                    "calculation_mode": "count_to_count",
                }
                rows.append(row)
                product_rows.append(row)

            if product_rows:
                product_summary[product_num] = {
                    "periods": len(product_rows),
                    "total_usage": round(sum(_usage_to_float(r.get("usage"), 0.0) for r in product_rows), 2),
                    "avg_daily_rate": round(sum(_usage_to_float(r.get("daily_rate"), 0.0) for r in product_rows) / len(product_rows), 4),
                }

        rows.sort(key=lambda r: (str(r.get("period_from") or ""), int(r.get("product_order_index") or 0)))
        periods_payload = [
            {
                "period_from": p_from.isoformat(),
                "period_to": p_to.isoformat(),
                "days_in_period": max(1, (p_to - p_from).days),
            }
            for p_from, p_to in period_pairs
        ]

        return jsonify(
            {
                "success": True,
                "location": location_name,
                "from_date": from_day.isoformat(),
                "to_date": to_day.isoformat(),
                "count_dates_found": count_dates_found,
                "periods": periods_payload,
                "total_periods": len(period_pairs),
                "rows": rows,
                "total_rows": len(rows),
                "product_summary": product_summary,
                "usage_model": {
                    "week_start": "Sunday",
                    "formula": "opening_inventory + receipts - next_day_closing_inventory",
                    "receipts_source": "invoice_import_log",
                    "negative_usage_allowed": True,
                },
            }
        )

    installed_product_activity = False
    installed_weekly_usage = False
    installed_period_usage_get = False
    installed_period_usage_post = False
    for rule in flask_app.url_map.iter_rules():
        if rule.rule == "/api/reports/product-activity" and "GET" in rule.methods:
            flask_app.view_functions[rule.endpoint] = api_product_activity_usage_runtime
            installed_product_activity = True
        if rule.rule == "/api/reports/weekly-usage" and "GET" in rule.methods:
            flask_app.view_functions[rule.endpoint] = api_weekly_usage_runtime
            installed_weekly_usage = True
        if rule.rule == "/api/reports/period-usage":
            if "GET" in rule.methods or "POST" in rule.methods:
                flask_app.view_functions[rule.endpoint] = api_period_usage_runtime
            if "GET" in rule.methods:
                installed_period_usage_get = True
            if "POST" in rule.methods:
                installed_period_usage_post = True

    if not installed_product_activity:
        flask_app.add_url_rule(
            "/api/reports/product-activity",
            endpoint="ic3_product_activity_usage_runtime",
            view_func=api_product_activity_usage_runtime,
            methods=["GET"],
        )

    if not installed_weekly_usage:
        flask_app.add_url_rule(
            "/api/reports/weekly-usage",
            endpoint="ic3_weekly_usage_runtime",
            view_func=api_weekly_usage_runtime,
            methods=["GET"],
        )

    missing_period_methods = []
    if not installed_period_usage_get:
        missing_period_methods.append("GET")
    if not installed_period_usage_post:
        missing_period_methods.append("POST")

    if missing_period_methods:
        flask_app.add_url_rule(
            "/api/reports/period-usage",
            endpoint="ic3_period_usage_runtime_" + "_".join(missing_period_methods).lower(),
            view_func=api_period_usage_runtime,
            methods=missing_period_methods,
        )


def _runtime_location_names() -> list[str]:
    names: set[str] = set()

    for source in (globals().get("inventory_data") or {}, globals().get("order_data") or {}):
        if isinstance(source, dict):
            for raw in source.keys():
                value = str(raw or "").strip()
                if value:
                    names.add(value)

    return sorted(names)


def _runtime_default_location(fallback: str = "Kingsville") -> str:
    names = _runtime_location_names()
    if names:
        return names[0]
    return fallback


def _normalize_runtime_location_text(raw_value) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""
    normalized = text.lower()
    compact = re.sub(r"[^a-z0-9]+", "", normalized)

    # Dexter headers may include extended labels (for example, "Kingsville Main"),
    # while IC3 request payloads often send just "Kingsville" or "Alice".
    if "kingsville" in compact:
        return "kingsville"
    if "alice" in compact:
        return "alice"

    return re.sub(r"\s+", " ", normalized)


def _dexter_selected_location_from_headers() -> str:
    location_text = str(request.headers.get("X-Dexter-Restaurant-Location") or "").strip()
    if location_text:
        return location_text
    return str(request.headers.get("X-Dexter-Restaurant-Name") or "").strip()


def _dexter_selected_restaurant_id_from_headers() -> int | None:
    raw_id = str(request.headers.get("X-Dexter-Restaurant-Id") or "").strip()
    if not raw_id:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _effective_runtime_location(fallback: str = "Kingsville") -> str:
    dexter_location = _dexter_selected_location_from_headers()
    if dexter_location:
        return dexter_location
    return _runtime_default_location(fallback)


def _collect_requested_location_values() -> set[str]:
    # Rename tools use "location" as a filename prefix, not as tenant location scope.
    if request.path in {
        "/api/tools/rename-order-csvs",
        "/api/tools/rename-order-csvs-web",
        "/api/tools/select-folder",
    }:
        return set()

    requested_values: set[str] = set()
    selected_restaurant_id = _dexter_selected_restaurant_id_from_headers()
    selected_location = _normalize_runtime_location_text(_dexter_selected_location_from_headers())

    for key in ("location",):
        for raw_value in request.args.getlist(key):
            normalized = _normalize_runtime_location_text(raw_value)
            if normalized:
                requested_values.add(normalized)

    for key in ("location",):
        for raw_value in request.form.getlist(key):
            normalized = _normalize_runtime_location_text(raw_value)
            if normalized:
                requested_values.add(normalized)

    # Some forms submit numeric location/restaurant IDs while Dexter scope is a location label.
    # Treat matching IDs as in-scope and only fail on explicit ID mismatch.
    for key in ("location_id", "restaurant_id"):
        for raw_value in request.args.getlist(key) + request.form.getlist(key):
            text_value = str(raw_value or "").strip()
            if not text_value:
                continue
            try:
                requested_id = int(text_value)
            except (TypeError, ValueError):
                normalized = _normalize_runtime_location_text(text_value)
                if normalized:
                    requested_values.add(normalized)
                continue

            if selected_restaurant_id is not None and requested_id == selected_restaurant_id:
                if selected_location:
                    requested_values.add(selected_location)
            else:
                requested_values.add(f"__id_mismatch__{requested_id}")

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            normalized = _normalize_runtime_location_text(payload.get("location"))
            if normalized:
                requested_values.add(normalized)

            for key in ("location_id", "restaurant_id"):
                raw_value = payload.get(key)
                text_value = str(raw_value or "").strip()
                if not text_value:
                    continue
                try:
                    requested_id = int(text_value)
                except (TypeError, ValueError):
                    normalized = _normalize_runtime_location_text(text_value)
                    if normalized:
                        requested_values.add(normalized)
                    continue

                if selected_restaurant_id is not None and requested_id == selected_restaurant_id:
                    if selected_location:
                        requested_values.add(selected_location)
                else:
                    requested_values.add(f"__id_mismatch__{requested_id}")

    return requested_values


def _find_product_record_by_number(products_list_obj, product_number: str):
    target = _canonical_product_number(product_number)
    for product in (products_list_obj or []):
        candidate = _canonical_product_number(
            product.get("Product Number")
            if isinstance(product, dict)
            else None
        )
        if candidate == target:
            return product
    return None


def _next_global_product_number(products_list_obj):
    used_numbers = set()
    for product in products_list_obj or []:
        if isinstance(product, dict):
            number = _canonical_product_number(product.get("Product Number"))
            if number:
                used_numbers.add(number)
    inventory_data_obj = globals().get("inventory_data") or {}
    for location_data in inventory_data_obj.values() if isinstance(inventory_data_obj, dict) else []:
        for day_data in location_data.values() if isinstance(location_data, dict) else []:
            if isinstance(day_data, dict):
                used_numbers.update(
                    number for number in (_canonical_product_number(key) for key in day_data) if number
                )

    candidate = max((int(number) for number in used_numbers if number.isdigit()), default=0) + 1
    while str(candidate) in used_numbers:
        candidate += 1
    return str(candidate)


def _persist_products_runtime(products_list_obj):
    save_products = globals().get("save_products_to_csv")
    if callable(save_products):
        try:
            save_products()
        except Exception:
            logging.exception("Legacy IC3 product save failed")
    try:
        path = ROOT / "data" / "products_list.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(products_list_obj, handle, ensure_ascii=True, indent=2)
        return True
    except Exception:
        logging.exception("Failed to persist IC3 products")
        return False


def _register_product_detail_endpoints(flask_app) -> None:
    if "get_product_detail_runtime" in flask_app.view_functions:
        return

    try:
        from flask import jsonify, request
    except Exception:
        return

    @flask_app.route("/api/products/<product_number>/detail", methods=["GET"])
    def get_product_detail_runtime(product_number):
        requested_location = _effective_runtime_location()
        window_key = str(request.args.get("window") or "week").strip().lower()

        products_list_obj = globals().get("products_list") or []
        inventory_data_obj = globals().get("inventory_data") or {}
        order_data_obj = globals().get("order_data") or {}
        invoice_import_log_obj = globals().get("invoice_import_log") or []

        canonical_num = _canonical_product_number(product_number)
        if not canonical_num:
            return jsonify({"success": False, "message": "Product number is required."}), 400

        available_locations = sorted(
            {
                *(str(key) for key in (inventory_data_obj or {}).keys()),
                *(str(key) for key in (order_data_obj or {}).keys()),
            }
        )

        all_mode = requested_location in {"__all__", "all", "*"}
        if all_mode:
            locations_to_scan = available_locations if available_locations else [_runtime_default_location()]
            location_label = "All Locations"
        else:
            locations_to_scan = [requested_location]
            location_label = requested_location

        product = _find_product_record_by_number(products_list_obj, canonical_num)
        product_payload = {
            "product_number": canonical_num,
            "description": str((product or {}).get("Product Description") or ""),
            "nickname": str((product or {}).get("Product Nickname") or ""),
            "brand": str((product or {}).get("Product Brand") or ""),
            "package_size": str((product or {}).get("Product Package Size") or ""),
            "group_name": str((product or {}).get("Group Name") or ""),
            "case_count_type": str((product or {}).get("Case Count Type") or "No"),
        }

        price_by_date = {}
        for entry in (invoice_import_log_obj or []):
            entry_location = str(entry.get("location") or "").strip()
            if entry_location not in locations_to_scan:
                continue
            date_str = str(entry.get("delivery_date") or "").strip()
            if not date_str:
                continue
            prices = entry.get("product_prices") or {}
            for key, raw_price in prices.items():
                if _canonical_product_number(key) != canonical_num:
                    continue
                try:
                    value = float(raw_price)
                except Exception:
                    continue
                bucket = price_by_date.setdefault(date_str, [])
                bucket.append(value)

        avg_price_by_date = {}
        for date_str, price_values in price_by_date.items():
            if price_values:
                avg_price_by_date[date_str] = sum(price_values) / len(price_values)

        order_rows = []
        for location in locations_to_scan:
            for date_str, per_day_values in (order_data_obj.get(location, {}) or {}).items():
                if not isinstance(per_day_values, dict):
                    continue
                for key, raw_qty in per_day_values.items():
                    if _canonical_product_number(key) != canonical_num:
                        continue
                    try:
                        quantity = float(raw_qty)
                    except Exception:
                        quantity = 0.0
                    order_rows.append(
                        {
                            "date": str(date_str),
                            "location": str(location),
                            "quantity": quantity,
                            "unit_price": avg_price_by_date.get(str(date_str)),
                        }
                    )

        inventory_rows = []
        for location in locations_to_scan:
            for date_str, snapshot in (inventory_data_obj.get(location, {}) or {}).items():
                if not isinstance(snapshot, dict):
                    continue
                for key, raw_qty in snapshot.items():
                    if _canonical_product_number(key) != canonical_num:
                        continue
                    try:
                        quantity = float(raw_qty)
                    except Exception:
                        quantity = 0.0
                    inventory_rows.append(
                        {
                            "date": str(date_str),
                            "location": str(location),
                            "quantity": quantity,
                        }
                    )

        filtered_orders = _window_filter_dates(order_rows, window_key)
        filtered_inventory = _window_filter_dates(inventory_rows, window_key)

        filtered_orders = sorted(filtered_orders, key=lambda row: (str(row.get("date") or ""), str(row.get("location") or "")))
        filtered_inventory = sorted(filtered_inventory, key=lambda row: (str(row.get("date") or ""), str(row.get("location") or "")))

        def _aggregate_series(rows):
            by_day = {}
            for row in (rows or []):
                day_key = str(row.get("date") or "").strip()
                if not day_key:
                    continue
                by_day[day_key] = by_day.get(day_key, 0.0) + float(row.get("quantity") or 0.0)
            return [
                {"date": day_key, "value": by_day[day_key]}
                for day_key in sorted(by_day.keys())
            ]

        orders_series = _aggregate_series(filtered_orders)
        inventory_series = _aggregate_series(filtered_inventory)

        latest_inventory_qty = None
        if filtered_inventory:
            latest_inventory_qty = filtered_inventory[-1].get("quantity")

        return jsonify(
            {
                "success": True,
                "location": requested_location,
                "location_label": location_label,
                "window": window_key,
                "product": product_payload,
                "summary": {
                    "order_rows": len(filtered_orders),
                    "inventory_rows": len(filtered_inventory),
                    "total_order_qty": sum(float(row.get("quantity") or 0) for row in filtered_orders),
                    "latest_inventory_qty": latest_inventory_qty,
                },
                "order_history": filtered_orders,
                "inventory_history": filtered_inventory,
                "chart_series": {
                    "orders": orders_series,
                    "inventory": inventory_series,
                },
            }
        )

    @flask_app.route("/api/products/update-case-count-type", methods=["POST"])
    def update_case_count_type_runtime():
        payload = request.get_json(silent=True) or {}
        product_number = _canonical_product_number(payload.get("product_number"))
        case_count_type = str(payload.get("case_count_type") or "").strip().lower()
        case_count_type = "Yes" if case_count_type == "yes" else "No"

        if not product_number:
            return jsonify({"success": False, "message": "product_number is required."}), 400

        products_list_obj = globals().get("products_list") or []
        product = _find_product_record_by_number(products_list_obj, product_number)
        if not product:
            return jsonify({"success": False, "message": "Product not found."}), 404

        product["Case Count Type"] = case_count_type

        save_products = globals().get("save_products_to_csv")
        if callable(save_products):
            save_ok = bool(save_products())
            if not save_ok:
                return jsonify({"success": False, "message": "Failed to persist case count type."}), 500

        return jsonify({"success": True, "message": "Case count type updated."})

    @flask_app.route("/api/products/update-nickname", methods=["POST"])
    def update_nickname_runtime():
        payload = request.get_json(silent=True) or {}
        product_number = _canonical_product_number(payload.get("product_number"))
        nickname = str(payload.get("nickname") or "").strip()[:80]
        if not product_number:
            return jsonify({"success": False, "message": "product_number is required."}), 400
        products_list_obj = globals().get("products_list") or []
        product = _find_product_record_by_number(products_list_obj, product_number)
        if not product:
            return jsonify({"success": False, "message": "Product not found."}), 404
        product["Product Nickname"] = nickname
        if not _persist_products_runtime(products_list_obj):
            return jsonify({"success": False, "message": "Failed to persist nickname."}), 500
        return jsonify({"success": True, "nickname": nickname})

    @flask_app.route("/api/products/update-order-quantity", methods=["POST"])
    def update_order_quantity_runtime():
        payload = request.get_json(silent=True) or {}
        location = _effective_runtime_location()
        date_str = str(payload.get("date") or "").strip()
        product_number = _canonical_product_number(payload.get("product_number"))

        try:
            quantity = float(payload.get("quantity"))
        except Exception:
            return jsonify({"success": False, "message": "quantity must be numeric."}), 400

        if not date_str or not _safe_parse_date(date_str):
            return jsonify({"success": False, "message": "Valid date is required."}), 400
        if not product_number:
            return jsonify({"success": False, "message": "product_number is required."}), 400

        order_data_obj = globals().setdefault("order_data", {})
        location_map = order_data_obj.setdefault(location, {})
        day_map = location_map.setdefault(date_str, {})

        matching_key = None
        for key in day_map.keys():
            if _canonical_product_number(key) == product_number:
                matching_key = key
                break
        if matching_key is None:
            matching_key = product_number

        day_map[matching_key] = quantity

        invoice_import_log_obj = globals().get("invoice_import_log") or []
        for entry in invoice_import_log_obj:
            if str(entry.get("location") or "").strip() != location:
                continue
            if str(entry.get("delivery_date") or "").strip() != date_str:
                continue

            products_map = entry.get("products")
            if isinstance(products_map, dict):
                for key in list(products_map.keys()):
                    if _canonical_product_number(key) == product_number:
                        products_map[key] = quantity

            line_items = entry.get("line_items")
            if isinstance(line_items, list):
                for row in line_items:
                    key = _canonical_product_number(row.get("canonical_product_number") or row.get("raw_product_number"))
                    if key == product_number:
                        row["quantity"] = quantity

        save_orders = globals().get("save_orders_database")
        if callable(save_orders):
            save_orders()

        save_invoice_log = globals().get("save_invoice_import_log")
        if callable(save_invoice_log):
            save_invoice_log()

        return jsonify({"success": True, "message": "Order quantity updated."})

    @flask_app.route("/api/products/update-inventory-quantity", methods=["POST"])
    def update_inventory_quantity_runtime():
        payload = request.get_json(silent=True) or {}
        location = _effective_runtime_location()
        date_str = str(payload.get("date") or "").strip()
        product_number = _canonical_product_number(payload.get("product_number"))

        try:
            quantity = float(payload.get("quantity"))
        except Exception:
            return jsonify({"success": False, "message": "quantity must be numeric."}), 400

        if not date_str or not _safe_parse_date(date_str):
            return jsonify({"success": False, "message": "Valid date is required."}), 400
        if not product_number:
            return jsonify({"success": False, "message": "product_number is required."}), 400

        inventory_data_obj = globals().setdefault("inventory_data", {})
        location_map = inventory_data_obj.setdefault(location, {})
        day_map = location_map.setdefault(date_str, {})

        matching_key = None
        for key in day_map.keys():
            if _canonical_product_number(key) == product_number:
                matching_key = key
                break
        if matching_key is None:
            matching_key = product_number

        day_map[matching_key] = quantity

        save_inventory = globals().get("save_inventory_database")
        if callable(save_inventory):
            save_inventory()

        return jsonify({"success": True, "message": "Inventory quantity updated."})


def _install_product_detail_api_patch() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_product_detail_patch_installed", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _register_product_detail_endpoints(self)
        except Exception:
            pass

    Flask.__init__ = patched_init
    Flask._ic3_product_detail_patch_installed = True

    existing_app = globals().get("app")
    if existing_app is not None:
        try:
            _register_product_detail_endpoints(existing_app)
        except Exception:
            pass


def _register_order_csv_rename_endpoint(flask_app) -> None:
    if "rename_order_csvs" in flask_app.view_functions:
        return

    try:
        from flask import jsonify, request
    except Exception:
        return

    @flask_app.post("/api/tools/rename-order-csvs")
    def rename_order_csvs():
        payload = request.get_json(silent=True) or {}
        folder_path = str(payload.get("folder_path") or "").strip()
        location = _effective_runtime_location("Location")
        apply_changes = bool(payload.get("apply"))

        if not folder_path:
            return jsonify({"success": False, "message": "Folder path is required."}), 400

        folder = Path(folder_path).expanduser()
        if not folder.exists() or not folder.is_dir():
            return jsonify({"success": False, "message": f"Folder not found: {folder}"}), 400

        planned = _plan_order_csv_renames(folder, location)
        if not apply_changes:
            return jsonify({"success": True, "mode": "dry-run", "items": planned, "count": len(planned)})

        applied: list[dict[str, str]] = []
        for item in planned:
            source = folder / item["old_name"]
            target = folder / item["new_name"]
            if not source.exists():
                continue
            source.rename(target)
            applied.append(item)

        return jsonify({"success": True, "mode": "apply", "items": applied, "count": len(applied)})

    @flask_app.post("/api/tools/select-folder")
    def select_folder_dialog():
        probe_only = str(request.args.get("probe") or "").strip().lower() in {"1", "true", "yes"}
        try:
            import tkinter as tk
            from tkinter import filedialog

            if probe_only:
                return jsonify({"success": True, "probe": True, "picker_available": True, "folder_path": ""})

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Select Folder for Order CSV Rename")
            root.destroy()

            if not selected:
                return jsonify({"success": True, "folder_path": "", "message": "Folder selection cancelled."})

            return jsonify({"success": True, "folder_path": selected})
        except ImportError:
            return jsonify({"success": False, "message": "Folder picker is only available when running locally. Please type the folder path manually."}), 200
        except Exception as exc:
            return jsonify({"success": False, "message": f"Folder picker unavailable: {exc}"}), 200

    @flask_app.post("/api/tools/rename-order-csvs-web")
    def rename_order_csvs_web():
        import io
        import zipfile as _zipfile
        from flask import send_file

        location = _effective_runtime_location("Location")
        mode = str(request.form.get("mode") or "preview").strip()
        uploaded_files = request.files.getlist("files")

        if not uploaded_files or not any(f.filename for f in uploaded_files):
            return jsonify({"success": False, "message": "No files uploaded."}), 400

        seen_per_day: dict[str, int] = {}
        planned_targets: set[str] = set()
        planned = []
        unchanged = []

        for f in sorted(uploaded_files, key=lambda x: (x.filename or "")):
            fname = Path(f.filename).name if f.filename else ""
            if not fname:
                continue
            new_name = _build_order_csv_target_name(Path(fname), location, seen_per_day)
            if not new_name or new_name == fname:
                unchanged.append(f)
                continue
            stem = Path(new_name).stem
            suffix = Path(new_name).suffix
            candidate = new_name
            counter = 1
            while candidate.lower() in planned_targets:
                candidate = f"{stem}_{counter}{suffix}"
                counter += 1
            planned.append({"old_name": fname, "new_name": candidate, "file_obj": f})
            planned_targets.add(candidate.lower())

        if mode == "preview":
            return jsonify({
                "success": True,
                "items": [{"old_name": p["old_name"], "new_name": p["new_name"]} for p in planned],
                "unchanged_count": len(unchanged),
            })

        buf = io.BytesIO()
        with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
            for item in planned:
                item["file_obj"].stream.seek(0)
                zf.writestr(item["new_name"], item["file_obj"].stream.read())
            for f in unchanged:
                f.stream.seek(0)
                zf.writestr(Path(f.filename).name, f.stream.read())
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="renamed_order_csvs.zip")


def _register_invoice_import_log_endpoint(flask_app) -> None:
    if flask_app is None:
        return

    existing_rules = {rule.rule for rule in flask_app.url_map.iter_rules()}
    if "/api/invoices/import-log" in existing_rules:
        return

    @flask_app.route("/api/invoices/import-log", methods=["GET"])
    def api_invoices_import_log():
        try:
            imports_payload = globals().get("invoice_import_log")
            if imports_payload is None:
                with INVOICE_IMPORT_LOG_PATH.open("r", encoding="utf-8") as handle:
                    imports_payload = json.load(handle)
            return jsonify({"success": True, "imports": imports_payload or []})
        except FileNotFoundError:
            return jsonify({"success": True, "imports": []})
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500


def _register_productmix_sync_endpoints(flask_app) -> None:
    if flask_app is None:
        return

    def api_productmix_sync_status():
        cache = _read_productmix_sync_cache()
        return jsonify(
            {
                "success": True,
                "configured_base_url": os.getenv("IC3_PRODUCTMIX_BASE_URL", "http://127.0.0.1:5050"),
                "has_cache": bool(cache),
                "last_sync": cache.get("synced_at_utc") if isinstance(cache, dict) else None,
                "category_count": int((cache or {}).get("category_count") or 0),
                "source_url": (cache or {}).get("source_url"),
            }
        )

    def api_productmix_categories_sync():
        if request.method == "GET":
            cache = _read_productmix_sync_cache()
            if not cache:
                return jsonify({"success": True, "cached": False, "categories": [], "category_count": 0})
            return jsonify({"success": True, "cached": True, **cache})

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}

        base_url = str(payload.get("base_url") or os.getenv("IC3_PRODUCTMIX_BASE_URL", "http://127.0.0.1:5050")).strip()
        timeout_seconds = payload.get("timeout_seconds", 12)
        try:
            timeout_seconds = float(timeout_seconds)
            if timeout_seconds <= 0:
                timeout_seconds = 12.0
            timeout_seconds = min(timeout_seconds, 60.0)
        except (TypeError, ValueError):
            timeout_seconds = 12.0

        dexter_headers = {
            "X-Dexter-Auth": request.headers.get("X-Dexter-Auth", ""),
            "X-Dexter-Company-Name": request.headers.get("X-Dexter-Company-Name", ""),
            "X-Dexter-Restaurant-Id": request.headers.get("X-Dexter-Restaurant-Id", ""),
            "X-Dexter-Restaurant-Location": request.headers.get("X-Dexter-Restaurant-Location", ""),
            "X-Dexter-Restaurant-Name": request.headers.get("X-Dexter-Restaurant-Name", ""),
        }

        try:
            synced = _sync_productmix_categories_from_remote(
                base_url,
                timeout_seconds=timeout_seconds,
                headers=dexter_headers,
            )
        except urllib_error.HTTPError as exc:
            return jsonify({"success": False, "message": f"ProductMix HTTP error: {exc.code}", "source_url": base_url}), 502
        except urllib_error.URLError as exc:
            return jsonify({"success": False, "message": f"ProductMix connection error: {exc.reason}", "source_url": base_url}), 502
        except json.JSONDecodeError as exc:
            return jsonify({"success": False, "message": f"Invalid JSON from ProductMix: {exc}"}), 502
        except Exception as exc:
            return jsonify({"success": False, "message": str(exc)}), 500

        _write_productmix_sync_cache(synced)
        return jsonify({"success": True, **synced})

    status_get_installed = False
    categories_methods_installed = set()
    for rule in flask_app.url_map.iter_rules():
        if rule.rule == "/api/sync/productmix/status" and "GET" in rule.methods:
            flask_app.view_functions[rule.endpoint] = api_productmix_sync_status
            status_get_installed = True

        if rule.rule == "/api/sync/productmix/categories":
            if "GET" in rule.methods or "POST" in rule.methods:
                flask_app.view_functions[rule.endpoint] = api_productmix_categories_sync
            if "GET" in rule.methods:
                categories_methods_installed.add("GET")
            if "POST" in rule.methods:
                categories_methods_installed.add("POST")

    if not status_get_installed:
        flask_app.add_url_rule(
            "/api/sync/productmix/status",
            endpoint="ic3_productmix_sync_status_runtime",
            view_func=api_productmix_sync_status,
            methods=["GET"],
        )

    missing_methods = [m for m in ("GET", "POST") if m not in categories_methods_installed]
    if missing_methods:
        flask_app.add_url_rule(
            "/api/sync/productmix/categories",
            endpoint="ic3_productmix_categories_sync_runtime_" + "_".join(missing_methods).lower(),
            view_func=api_productmix_categories_sync,
            methods=missing_methods,
        )


def _install_productmix_sync_api_patch() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_productmix_sync_patch_installed", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _register_productmix_sync_endpoints(self)
        except Exception:
            pass

    Flask.__init__ = patched_init
    Flask._ic3_productmix_sync_patch_installed = True

    existing_app = globals().get("app")
    if existing_app is not None:
        try:
            _register_productmix_sync_endpoints(existing_app)
        except Exception:
            pass


def _install_usage_reports_patch() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_usage_reports_patch_installed", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _register_usage_reports_endpoints(self)
        except Exception:
            pass

    Flask.__init__ = patched_init
    Flask._ic3_usage_reports_patch_installed = True

    existing_app = globals().get("app")
    if existing_app is not None:
        try:
            _register_usage_reports_endpoints(existing_app)
        except Exception:
            pass


def _api_products_add_runtime():
    payload = request.get_json(silent=True) or {}
    description = str(payload.get("description") or "").strip()
    if not description:
        return jsonify({"success": False, "message": "Description is required."}), 400

    products = globals().get("products_list") or []
    requested_number = _canonical_product_number(payload.get("product_number"))
    product_number = requested_number or _next_global_product_number(products)
    if _find_product_record_by_number(products, product_number):
        return jsonify({"success": False, "message": "That Product # is already in use."}), 409

    product = {
        "Product Number": product_number,
        "Product Nickname": str(payload.get("nickname") or "").strip()[:80],
        "Product Description": description,
        "Product Brand": str(payload.get("brand") or "").strip(),
        "Product Package Size": str(payload.get("package_size") or "").strip(),
        "Group Name": str(payload.get("group_name") or "OTHER").strip() or "OTHER",
        "Case Count Type": "Yes" if str(payload.get("case_count_type") or "").strip().lower() == "yes" else "No",
    }
    insert_position = payload.get("insert_position")
    if isinstance(insert_position, int) and insert_position > 0:
        products.insert(min(insert_position - 1, len(products)), product)
    else:
        products.append(product)
    if not _persist_products_runtime(products):
        products.remove(product)
        return jsonify({"success": False, "message": "Failed to persist product."}), 500

    return jsonify(
        {
            "success": True,
            "message": f"Product {product_number} added.",
            "product_number": product_number,
            "product": product,
        }
    )


def _api_products_update_nickname_runtime():
    payload = request.get_json(silent=True) or {}
    product_number = _canonical_product_number(payload.get("product_number"))
    nickname = str(payload.get("nickname") or "").strip()[:80]
    if not product_number:
        return jsonify({"success": False, "message": "product_number is required."}), 400
    products = globals().get("products_list") or []
    product = _find_product_record_by_number(products, product_number)
    if not product:
        return jsonify({"success": False, "message": "Product not found."}), 404
    product["Product Nickname"] = nickname
    if not _persist_products_runtime(products):
        return jsonify({"success": False, "message": "Failed to persist nickname."}), 500
    return jsonify({"success": True, "nickname": nickname})


def _api_products_update_nicknames_runtime():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates") if isinstance(payload, dict) else []
    if not isinstance(updates, list):
        return jsonify({"success": False, "message": "updates must be a list."}), 400

    products = globals().get("products_list") or []
    normalized_updates = []
    seen_numbers = set()
    for update in updates:
        if not isinstance(update, dict):
            return jsonify({"success": False, "message": "Each nickname update must be an object."}), 400
        product_number = _canonical_product_number(update.get("product_number"))
        if not product_number or product_number in seen_numbers:
            return jsonify({"success": False, "message": "Each update needs a unique product_number."}), 400
        product = _find_product_record_by_number(products, product_number)
        if not product:
            return jsonify({"success": False, "message": f"Product {product_number} was not found."}), 404
        seen_numbers.add(product_number)
        normalized_updates.append((product, str(update.get("nickname") or "").strip()[:80]))

    for product, nickname in normalized_updates:
        product["Product Nickname"] = nickname
    if normalized_updates and not _persist_products_runtime(products):
        return jsonify({"success": False, "message": "Failed to persist nickname batch."}), 500
    return jsonify({"success": True, "count": len(normalized_updates), "message": "Nicknames saved."})


def _install_nickname_runtime_patch() -> None:
    target_app = globals().get("app")
    if target_app is None or getattr(target_app, "_ic3_nickname_runtime_patch", False):
        return
    update_rules = [rule for rule in target_app.url_map.iter_rules() if rule.rule == "/api/products/update-nickname"]
    if update_rules:
        target_app.view_functions[update_rules[0].endpoint] = _api_products_update_nickname_runtime
    else:
        target_app.add_url_rule(
            "/api/products/update-nickname",
            "api_products_update_nickname_runtime",
            _api_products_update_nickname_runtime,
            methods=["POST"],
        )
    bulk_rules = [rule for rule in target_app.url_map.iter_rules() if rule.rule == "/api/products/update-nicknames"]
    if bulk_rules:
        target_app.view_functions[bulk_rules[0].endpoint] = _api_products_update_nicknames_runtime
    else:
        target_app.add_url_rule(
            "/api/products/update-nicknames",
            "api_products_update_nicknames_runtime",
            _api_products_update_nicknames_runtime,
            methods=["POST"],
        )

    @target_app.after_request
    def _inject_nickname_into_detail(response):
        if request.path.startswith("/api/products/") and request.path.endswith("/detail") and "json" in (response.content_type or "").lower():
            try:
                payload = response.get_json(silent=True)
                if isinstance(payload, dict) and isinstance(payload.get("product"), dict):
                    number = _canonical_product_number(payload["product"].get("product_number"))
                    product = _find_product_record_by_number(globals().get("products_list") or [], number)
                    payload["product"]["nickname"] = str((product or {}).get("Product Nickname") or "")
                    response.set_data(json.dumps(payload))
                    response.headers.pop("Content-Length", None)
            except Exception:
                pass
        return response

    target_app._ic3_nickname_runtime_patch = True


def _register_compat_inventory_endpoints(flask_app) -> None:
    if flask_app is None:
        return

    existing_rules = {rule.rule for rule in flask_app.url_map.iter_rules()}

    product_add_rules = [rule for rule in flask_app.url_map.iter_rules() if rule.rule == "/api/products/add"]
    if product_add_rules:
        flask_app.view_functions[product_add_rules[0].endpoint] = _api_products_add_runtime
    else:
        flask_app.add_url_rule("/api/products/add", "api_products_add_runtime", _api_products_add_runtime, methods=["POST"])

    if "/api/products" not in existing_rules:
        @flask_app.route("/api/products", methods=["GET"])
        def api_products_runtime():
            products = globals().get("products_list") or []
            if not isinstance(products, list):
                products = []
            return jsonify(products)

    if "/api/inventory/list" not in existing_rules:
        @flask_app.route("/api/inventory/list", methods=["GET"])
        def api_inventory_list_runtime():
            inventory_data_obj = globals().get("inventory_data") or {}
            enforced_location = _normalize_runtime_location_text(_dexter_selected_location_from_headers())
            items = []

            if isinstance(inventory_data_obj, dict):
                for location, by_date in inventory_data_obj.items():
                    if enforced_location and _normalize_runtime_location_text(location) != enforced_location:
                        continue
                    if not isinstance(by_date, dict):
                        continue
                    for date_key, day_map in by_date.items():
                        count = len(day_map) if isinstance(day_map, dict) else 0
                        items.append(
                            {
                                "location": str(location),
                                "date": str(date_key),
                                "item_count": int(count),
                            }
                        )

            items.sort(key=lambda row: (row.get("location", ""), row.get("date", "")), reverse=True)
            return jsonify(items)

    if "/api/dexter/context" not in existing_rules:
        @flask_app.route("/api/dexter/context", methods=["GET"])
        def api_dexter_context_runtime():
            tenant_scope = resolve_tenant_scope(
                request.headers,
                app_name="ic3",
                logger=logging.getLogger("ic3"),
                request_path=request.path,
                method=request.method,
            )
            return jsonify(
                {
                    "success": True,
                    "is_dexter_proxy": bool(tenant_scope.get("is_dexter_proxy")),
                    "company_name": str(tenant_scope.get("company_name") or ""),
                    "restaurant_name": str(tenant_scope.get("restaurant_name") or ""),
                    "restaurant_location": str(tenant_scope.get("restaurant_location") or ""),
                }
            )

    if "/api/shared/inventory-default-groups" not in existing_rules:
        @flask_app.route("/api/shared/inventory-default-groups", methods=["GET"])
        def api_inventory_default_groups_runtime():
            # Compatibility endpoint used by portal shell patches. Returning
            # a stable empty payload avoids noisy 404s when no shared default
            # groups are configured.
            return jsonify(
                {
                    "ok": False,
                    "groups": [],
                    "default_group_id": "",
                    "message": "No shared inventory default groups configured",
                }
            )


def _install_dexter_location_guard_patch() -> None:
    app = globals().get("app")
    if app is None:
        return
    if getattr(app, "_ic3_dexter_location_guard_installed", False):
        return

    @app.before_request
    def _enforce_dexter_selected_location_scope():
        dexter_location = _normalize_runtime_location_text(_dexter_selected_location_from_headers())
        if not dexter_location:
            return None

        requested_locations = _collect_requested_location_values()
        if not requested_locations:
            return None

        for requested in requested_locations:
            if requested != dexter_location:
                return jsonify({"success": False, "message": "Forbidden location scope"}), 403
        return None

    app._ic3_dexter_location_guard_installed = True


def _install_order_csv_rename_api_patch() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_order_csv_rename_patch_installed", False):
        return

    original_init = Flask.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            _register_order_csv_rename_endpoint(self)
        except Exception:
            pass

    Flask.__init__ = patched_init
    Flask._ic3_order_csv_rename_patch_installed = True

    existing_app = globals().get("app")
    if existing_app is not None:
        try:
            _register_order_csv_rename_endpoint(existing_app)
        except Exception:
            pass


def _install_global_flask_response_patch() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_bulk_patch_installed", False):
        return

    original_process_response = Flask.process_response
    rewrite_func = _rewrite_bulk_upload_text

    def patched_process_response(self, response):
        # Let Flask and app-specific after_request hooks produce the final
        # response first, then apply our runtime HTML rewrites last.
        response = original_process_response(self, response)

        try:
            response.headers["X-IC3-BulkPatch"] = "active"
            content_type = (response.content_type or "").lower()
            if "text/html" in content_type or "javascript" in content_type:
                if response.direct_passthrough:
                    response.direct_passthrough = False

                body = response.get_data(as_text=True)
                rewritten = rewrite_func(body)
                if rewritten != body:
                    response.set_data(rewritten)
                    if "Content-Length" in response.headers:
                        response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass

        return response

    Flask.process_response = patched_process_response
    Flask._ic3_bulk_patch_installed = True

def _exec_bytecode() -> None:
    if not BYTECODE_FILE.exists():
        # Bytecode missing — run from source instead
        return

    try:
        data = BYTECODE_FILE.read_bytes()
        if len(data) < 16:
            raise ValueError(f"Invalid bytecode file header: {BYTECODE_FILE}")

        code = marshal.loads(data[16:])
        exec(code, globals(), globals())
        # The data/ directory is now a symlink to the persistent disk, so all path
        # lookups in the bytecode (ROOT/"data", DATA_DIR, inline paths, etc.) resolve
        # correctly without any post-exec patching.
    except Exception as exc:
        print(f"[ic3] Bytecode exec failed ({exc}), continuing from source")
        return


def _load_json_if_present(path: Path):
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _find_latest_products_backup() -> Path | None:
    backup_dir = ROOT / "backups" / "product_lists"
    if not backup_dir.exists():
        return None
    candidates = sorted(backup_dir.glob("products_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _restore_runtime_data_fallbacks() -> None:
    # If compiled runtime started with empty globals, hydrate from persisted data.
    products_obj = globals().get("products_list")
    products_from_data = _load_json_if_present(ROOT / "data" / "products_list.json")
    if isinstance(products_from_data, list) and products_from_data:
        globals()["products_list"] = products_from_data
        print(f"[ic3] Loaded products_list from data file ({len(products_from_data)} items)")
    elif not isinstance(products_obj, list) or len(products_obj) == 0:
        if isinstance(products_from_data, list) and products_from_data:
            globals()["products_list"] = products_from_data
            print(f"[ic3] Restored products_list from data file ({len(products_from_data)} items)")
        else:
            latest_products_backup = _find_latest_products_backup()
            products_from_backup = _load_json_if_present(latest_products_backup) if latest_products_backup else None
            if isinstance(products_from_backup, list) and products_from_backup:
                globals()["products_list"] = products_from_backup
                print(
                    "[ic3] Restored products_list from backup "
                    f"{latest_products_backup.name} ({len(products_from_backup)} items)"
                )

    invoice_obj = globals().get("invoice_import_log")
    if not isinstance(invoice_obj, list) or len(invoice_obj) == 0:
        invoice_from_disk = _load_json_if_present(INVOICE_IMPORT_LOG_PATH)
        if isinstance(invoice_from_disk, list) and invoice_from_disk:
            globals()["invoice_import_log"] = invoice_from_disk
            print(f"[ic3] Restored invoice_import_log from disk ({len(invoice_from_disk)} entries)")

    inventory_obj = globals().get("inventory_data")
    if not isinstance(inventory_obj, dict) or len(inventory_obj) == 0:
        inventory_from_disk = _load_json_if_present(ROOT / "data" / "inventory_database.json")
        if isinstance(inventory_from_disk, dict) and inventory_from_disk:
            globals()["inventory_data"] = inventory_from_disk
            print(f"[ic3] Restored inventory_data from disk ({len(inventory_from_disk)} locations)")

    orders_from_disk = _load_json_if_present(ROOT / "data" / "orders_database.json")
    if isinstance(orders_from_disk, dict) and orders_from_disk:
        if not isinstance(globals().get("orders_data"), dict) or not globals().get("orders_data"):
            globals()["orders_data"] = orders_from_disk
        if not isinstance(globals().get("orders_database"), dict) or not globals().get("orders_database"):
            globals()["orders_database"] = orders_from_disk
        if not isinstance(globals().get("order_data"), dict) or not globals().get("order_data"):
            globals()["order_data"] = orders_from_disk
            print(f"[ic3] Restored order_data from disk ({len(orders_from_disk)} locations)")


def _force_production_flask_run() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_run_patched", False):
        return

    original_run = Flask.run

    def _ensure_shared_locations_hook(flask_app) -> None:
        if getattr(flask_app, "_ic3_shared_locations_run_hook", False):
            return

        @flask_app.after_request
        def _inject_shared_locations_on_run(response):
            content_type = (response.content_type or "").lower()
            if "text/html" not in content_type:
                return response

            if response.direct_passthrough:
                response.direct_passthrough = False

            body = response.get_data(as_text=True)
            if "__ic3SharedLocationsInstalled" in body or "</body>" not in body:
                return response

            updated = body.replace("</body>", LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>", 1)
            response.set_data(updated)
            if "Content-Length" in response.headers:
                response.headers["Content-Length"] = str(len(response.get_data()))
            return response

        flask_app._ic3_shared_locations_run_hook = True

    def _run_with_safe_defaults(self, *args, **kwargs):
        _ensure_shared_locations_hook(self)

        force_prod = os.getenv("IC3_FORCE_PROD", "1").strip().lower() not in {"0", "false", "no"}
        if force_prod:
            # Prevent Flask reloader/debug from forking and causing manager pid churn.
            kwargs["debug"] = False
            kwargs["use_reloader"] = False
            kwargs.setdefault("host", "127.0.0.1")
            kwargs.setdefault("port", 5003)
        return original_run(self, *args, **kwargs)

    Flask.run = _run_with_safe_defaults
    Flask._ic3_run_patched = True


def _find_icon_file() -> Path | None:
    for candidate in ICON_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _patch_favicon_endpoint() -> None:
    icon_file = _find_icon_file()
    if not icon_file:
        return

    app = globals().get("app")
    if app is None:
        return

    try:
        from flask import send_file
    except Exception:
        return

    def _favicon_response():
        mimetype = "image/x-icon" if icon_file.suffix.lower() == ".ico" else "image/png"
        return send_file(icon_file, mimetype=mimetype)

    # The compiled app defines endpoint 'favicon'. Override it if present.
    if "favicon" in app.view_functions:
        app.view_functions["favicon"] = _favicon_response
    else:
        app.add_url_rule("/favicon.ico", "favicon", _favicon_response)


def _patch_bulk_upload_limit_runtime() -> None:
    app = globals().get("app")
    if app is None:
        return

    literal_replacements = (
        ("Bulk Upload (Up to 20)", "Bulk Upload"),
        ("Add up to 20 invoices at once. Each invoice can have its own delivery date.", "Add as many invoices as needed. Each invoice can have its own delivery date."),
        ("Invoice List (<span id=\"invoiceCount\">0</span>/20)", "Invoice List (<span id=\"invoiceCount\">0</span>)"),
        ("Maximum is 20 total.", "No maximum limit."),
        ("const deliveryDate = dateField.value;", "const selectedDeliveryDate = (dateField.value || '').trim();\n            const parsedDeliveryDate = dateFromFilename(file.name);\n            const deliveryDate = selectedDeliveryDate || parsedDeliveryDate;\n            if (!selectedDeliveryDate) {\n                dateField.value = deliveryDate;\n            }"),
        ("formData.append('delivery_date', invoice.date);", "formData.append('delivery_date', invoice.date || dateFromFilename(invoice.file.name));"),
    )

    regex_replacements = (
        (
            r"const\s+remaining\s*=\s*20\s*-\s*bulkInvoices\.length\s*;",
            lambda m: "const remaining = Number.POSITIVE_INFINITY;",
        ),
        (
            r"if\s*\(files\.length\s*>\s*remaining\)\s*\{\s*alert\(`You can only add \$\{remaining\} more invoice\(s\)\. Maximum is 20 total\.`\);\s*files\.splice\(remaining\);\s*\}",
            lambda m: "",
        ),
        (
            r'(<input[^>]*id=["\']showEditButtons["\'][^>]*?)\schecked(?:=(?:"[^"]*"|\'[^\']*\'|[^\s>]+))?',
            lambda m: m.group(1),
        ),
        (
            r"function\s+dateFromFilename\(filename\)\s*\{[\s\S]*?return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
            lambda m: "function dateFromFilename(filename) {\n            const m = filename.match(/(\\d{4})[-_\\/](\\d{2})[-_\\/](\\d{2})|^(\\d{4})(\\d{2})(\\d{2})/);\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\n            return new Date().toISOString().split('T')[0];\n        }",
        ),
        (
            r"function\s+showBulkUpload\(\)\s*\{[\s\S]*?\}",
            lambda m: "function showBulkUpload() {\n            document.getElementById('singleUploadSection').style.display = 'none';\n            document.getElementById('bulkUploadSection').style.display = 'block';\n            bulkInvoices = [];\n            renderBulkInvoiceList();\n            const bulkStatus = document.getElementById('bulkUploadStatus');\n            if (bulkStatus) bulkStatus.style.display = 'none';\n        }",
        ),
        (
            r"function\s+dateFromFilename\(filename\)\s*\{\s*const\s+m\s*=\s*filename\.match\(/\^\\\(\\d\{4\}\\\)\\\(\\d\{2\}\\\)\\\(\\d\{2\}\\\)/\);\s*if\s*\(m\)\s*return\s*`\$\{m\[1\]\}-\$\{m\[2\]\}-\$\{m\[3\]\}`;\s*return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
            lambda m: "function dateFromFilename(filename) {\n            const m = filename.match(/(\\d{4})[-_\\/](\\d{2})[-_\\/](\\d{2})|^(\\d{4})(\\d{2})(\\d{2})/);\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\n            return new Date().toISOString().split('T')[0];\n        }",
        ),
    )

    @app.after_request
    def _rewrite_bulk_upload_cap(response):
        content_type = (response.content_type or "").lower()
        response.headers["X-IC3-BulkPatch"] = "active"
        if "text/html" not in content_type and "javascript" not in content_type:
            return response

        if response.direct_passthrough:
            return response

        body = response.get_data(as_text=True)
        updated = body
        for old, new in literal_replacements:
            updated = updated.replace(old, new)

        for pattern, replacement in regex_replacements:
            updated = re.sub(pattern, replacement, updated, flags=re.DOTALL)

        if "__ic3ProductDetailInstalled" not in updated and "</body>" in updated:
            updated = updated.replace("</body>", PRODUCT_DETAIL_SCRIPT + "\n</body>", 1)

        if "__ic3MobileUiInstalled" not in updated and "</body>" in updated:
            updated = updated.replace("</body>", MOBILE_UI_SCRIPT + "\n</body>", 1)

        if "__ic3ProductMixSyncUiInstalled" not in updated and "</body>" in updated:
            updated = updated.replace(
                "</body>",
                PRODUCTMIX_SYNC_UI_SCRIPT + "\n" + LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>",
                1,
            )

        if "__ic3SharedLocationsInstalled" not in updated and "</body>" in updated:
            updated = updated.replace("</body>", LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>", 1)

        if updated != body:
            response.set_data(updated)
            if "Content-Length" in response.headers:
                response.headers["Content-Length"] = str(len(response.get_data()))

        return response


_install_global_flask_response_patch()
_install_order_csv_rename_api_patch()
_install_product_detail_api_patch()
_install_productmix_sync_api_patch()
_install_usage_reports_patch()
_force_production_flask_run()
_original_module_name = globals().get("__name__", "__main__")
if _original_module_name == "__main__":
    globals()["__name__"] = "__ic3_runtime_wrapper__"
try:
    _exec_bytecode()
finally:
    globals()["__name__"] = _original_module_name
_restore_runtime_data_fallbacks()
_register_compat_inventory_endpoints(globals().get("app"))
_install_nickname_runtime_patch()
_register_invoice_import_log_endpoint(globals().get("app"))
_register_productmix_sync_endpoints(globals().get("app"))
_register_usage_reports_endpoints(globals().get("app"))
_install_dexter_location_guard_patch()
_patch_favicon_endpoint()
_patch_bulk_upload_limit_runtime()


def _install_shared_locations_failsafe_patch() -> None:
    target_app = globals().get("app")
    if target_app is None:
        return

    @target_app.after_request
    def _inject_shared_locations_failsafe(response):
        content_type = (response.content_type or "").lower()
        if "text/html" not in content_type:
            return response

        # Some IC3 routes stream templated HTML with passthrough enabled;
        # disable it so we can append the shared-locations script.
        if response.direct_passthrough:
            response.direct_passthrough = False

        body = response.get_data(as_text=True)
        if "__ic3SharedLocationsInstalled" in body:
            return response
        if "</body>" not in body:
            return response

        updated = body.replace("</body>", LOCATION_OPTIONS_SYNC_SCRIPT + "\n</body>", 1)
        response.set_data(updated)
        if "Content-Length" in response.headers:
            response.headers["Content-Length"] = str(len(response.get_data()))
        return response


_install_shared_locations_failsafe_patch()


IC3_INVENTORY_OPPORTUNITY_SCRIPT = r"""
<script>
(function () {
    if (window.__ic3InventoryOpportunityInstalled) return;
    window.__ic3InventoryOpportunityInstalled = true;

    function toNum(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function detectForecastPayload(payload) {
        if (!payload || !Array.isArray(payload.results) || !payload.results.length) {
            return null;
        }
        const sample = payload.results[0] || {};
        const hasDemand = Object.prototype.hasOwnProperty.call(sample, 'predicted_demand');
        const hasInventory = Object.prototype.hasOwnProperty.call(sample, 'current_inventory');
        if (!hasDemand || !hasInventory) {
            return null;
        }
        return payload;
    }

    function classifyOpportunity(row) {
        const itemId = String(row.product_number || row.product_id || row.id || '').trim();
        const itemName = String(row.description || row.product_name || itemId || 'Unknown item').trim();
        const actual = Math.max(0, toNum(row.current_inventory));
        const predicted = Math.max(0, toNum(row.predicted_demand));
        const incoming = Math.max(0, toNum(row.recommended_order_rounded || row.recommended_order));

        // Target inventory aims to cover the next cycle with a small safety buffer.
        const target = Math.max(0.25, predicted * 1.15);
        const projectedEnd = Math.max(0, actual + incoming - predicted);
        const variance = actual - target;
        const variancePct = target > 0 ? (variance / target) : 0;

        let opportunity = 'watch';
        if (predicted > 0 && actual <= 0) {
            opportunity = 'missing-count';
        } else if (variancePct <= -0.20) {
            opportunity = 'understock';
        } else if (variancePct >= 0.35) {
            opportunity = 'overstock';
        }

        const impactScore = Math.abs(variancePct) * Math.max(predicted, 1);
        return {
            itemId: itemId,
            itemName: itemName,
            actual: actual,
            predicted: predicted,
            incoming: incoming,
            projectedEnd: projectedEnd,
            target: target,
            variance: variance,
            variancePct: variancePct,
            opportunity: opportunity,
            impactScore: impactScore,
        };
    }

    function analyze(rows) {
        const items = [];
        let understock = 0;
        let overstock = 0;
        let missingCount = 0;

        for (const row of (rows || [])) {
            const modeled = classifyOpportunity(row || {});
            items.push(modeled);
            if (modeled.opportunity === 'understock') understock++;
            if (modeled.opportunity === 'overstock') overstock++;
            if (modeled.opportunity === 'missing-count') missingCount++;
        }

        items.sort(function (a, b) {
            return b.impactScore - a.impactScore;
        });

        return {
            total: items.length,
            understock: understock,
            overstock: overstock,
            missingCount: missingCount,
            topItems: items.slice(0, 12),
        };
    }

    function badge(label, bg, fg) {
        return '<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;background:' + bg + ';color:' + fg + ';">' + label + '</span>';
    }

    function render(model) {
        const host = document.getElementById('reportContent') || document.getElementById('content') || document.body;
        if (!host) return;

        let panel = document.getElementById('ic3OpportunityPanel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'ic3OpportunityPanel';
            panel.style.margin = '14px 0';
            panel.style.border = '1px solid #cbd5e1';
            panel.style.borderRadius = '10px';
            panel.style.padding = '12px';
            panel.style.background = '#ffffff';
            panel.style.boxShadow = '0 1px 3px rgba(15,23,42,0.08)';
            if (host.firstChild) {
                host.insertBefore(panel, host.firstChild);
            } else {
                host.appendChild(panel);
            }
        }

        const rowsHtml = model.topItems.map(function (item) {
            let label = badge('watch', '#e2e8f0', '#334155');
            if (item.opportunity === 'understock') label = badge('understock', '#fee2e2', '#991b1b');
            if (item.opportunity === 'overstock') label = badge('overstock', '#fef3c7', '#92400e');
            if (item.opportunity === 'missing-count') label = badge('missing count', '#dbeafe', '#1e40af');

            return '<tr>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;">' + escapeHtml(item.itemId || '-') + '</td>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;">' + escapeHtml(item.itemName) + '</td>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">' + item.actual.toFixed(2) + '</td>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">' + item.target.toFixed(2) + '</td>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">' + (item.variancePct * 100).toFixed(1) + '%</td>' +
                '<td style="padding:6px 8px;border:1px solid #e2e8f0;text-align:center;">' + label + '</td>' +
                '</tr>';
        }).join('');

        panel.innerHTML =
            '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;">' +
                '<h4 style="margin:0;color:#0f172a;">Inventory Opportunity Signals (Estimated vs Actual)</h4>' +
                '<div style="font-size:12px;color:#64748b;">Uses forecast demand + order plan + current inventory.</div>' +
            '</div>' +
            '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">' +
                badge('understock: ' + model.understock, '#fee2e2', '#991b1b') +
                badge('overstock: ' + model.overstock, '#fef3c7', '#92400e') +
                badge('missing count: ' + model.missingCount, '#dbeafe', '#1e40af') +
                badge('items analyzed: ' + model.total, '#e2e8f0', '#334155') +
            '</div>' +
            '<div style="overflow-x:auto;margin-top:10px;">' +
                '<table style="width:100%;border-collapse:collapse;font-size:12px;table-layout:auto;">' +
                    '<thead><tr style="background:#f8fafc;">' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:left;">Product #</th>' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:left;">Description</th>' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">Actual Inv</th>' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">Target Inv</th>' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:right;">Variance %</th>' +
                        '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:center;">Opportunity</th>' +
                    '</tr></thead>' +
                    '<tbody>' + rowsHtml + '</tbody>' +
                '</table>' +
            '</div>';

            const table = panel.querySelector('table');
            if (table && table.dataset.ic3OrderLock !== '1') {
                table.dataset.ic3OrderLock = '1';
                const headerCells = Array.from(table.querySelectorAll('thead th'));
                headerCells.forEach(function (th) {
                    th.style.cursor = 'default';
                    th.style.userSelect = 'none';
                    th.setAttribute('aria-sort', 'none');
                    th.addEventListener('click', function (event) {
                        event.preventDefault();
                        event.stopPropagation();
                    }, true);
                });
            }
    }

    function processForecastPayload(payload) {
        const candidate = detectForecastPayload(payload);
        if (!candidate) return;
        try {
            const model = analyze(candidate.results || []);
            if (model.total > 0) {
                render(model);
            }
        } catch (_err) {
            // Keep this non-blocking for IC3 runtime.
        }
    }

    const originalFetch = window.fetch;
    window.fetch = function () {
        return originalFetch.apply(this, arguments).then(function (response) {
            try {
                const contentType = String((response.headers && response.headers.get('content-type')) || '').toLowerCase();
                if (contentType.indexOf('application/json') === -1) {
                    return response;
                }
                response.clone().json().then(function (payload) {
                    processForecastPayload(payload);
                }).catch(function () {});
            } catch (_err) {}
            return response;
        });
    };

    // Fallback when compiled IC3 stores result data in a global.
    setInterval(function () {
        if (window.lastForecastData && window.lastForecastData !== window.__ic3LastForecastSeen) {
            window.__ic3LastForecastSeen = window.lastForecastData;
            processForecastPayload(window.lastForecastData);
        }
    }, 1200);
})();
</script>
"""


def _install_dexter_ui_patch() -> None:
    """Inject Dexter Assistant brand assets + theme JS into IC3 HTML responses.

    IC3 is loaded from compiled bytecode and has no on-disk templates, so we
    use the same after_request hook pattern the rest of this shim uses to
    splice tokens.css / components.css into <head> and theme.js before </body>.
    """
    target_app = globals().get("app")
    if target_app is None:
        return

    from flask import send_from_directory

    dexter_ui_dir = ROOT / "dexter-ui"
    if not dexter_ui_dir.exists():
        # Fall back to the canonical workspace source if local sync hasn't run.
        candidate = ROOT.parent.parent / "Tools" / "dexter_ui"
        if candidate.exists():
            dexter_ui_dir = candidate

    # Serve /dexter-ui/<filename> and /dexter-ui/brand/<filename>
    def _dexter_ui_static(filename):
        return send_from_directory(str(dexter_ui_dir), filename, max_age=3600)

    def _dexter_ui_brand(filename):
        return send_from_directory(str(dexter_ui_dir / "brand"), filename, max_age=3600)

    # Avoid re-registering on hot reload.
    existing = {r.rule for r in target_app.url_map.iter_rules()}
    if "/dexter-ui/<path:filename>" not in existing:
        target_app.add_url_rule(
            "/dexter-ui/<path:filename>",
            endpoint="_dexter_ui_static",
            view_func=_dexter_ui_static,
        )
    if "/dexter-ui/brand/<path:filename>" not in existing:
        target_app.add_url_rule(
            "/dexter-ui/brand/<path:filename>",
            endpoint="_dexter_ui_brand",
            view_func=_dexter_ui_brand,
        )

    head_block = (
        '<meta name="theme-color" content="#22427A">'
        # Mark the document as embedded BEFORE body paints so the redundant
        # in-app hero header is hidden by components.css without a flash.
        '<script>try{if(window.top!==window.self){document.documentElement.classList.add("dx-embedded");}}catch(e){document.documentElement.classList.add("dx-embedded");}</script>'
        '<link rel="icon" type="image/x-icon" href="/dexter-ui/brand/favicon.ico">'
        '<link rel="icon" type="image/png" sizes="32x32" href="/dexter-ui/brand/favicon-32.png">'
        '<link rel="apple-touch-icon" sizes="180x180" href="/dexter-ui/brand/apple-touch-icon.png">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
        '<link rel="stylesheet" href="/dexter-ui/tokens.css">'
        '<link rel="stylesheet" href="/dexter-ui/components.css">'
        "<style>"
        # Tiny IC3-only bridge: keep the existing IC3 background gradient/cards alive but recolor key elements.
        "body{font-family:var(--dx-font-sans)!important;background:var(--dx-bg)!important;color:var(--dx-text)!important;}"
        ".navbar,.app-navbar,header.navbar,nav.navbar{background:var(--dx-primary)!important;}"
        ".navbar-brand,.navbar a,.navbar .nav-link{color:var(--dx-primary-contrast)!important;}"
        ".btn-primary{background:var(--dx-primary)!important;border-color:var(--dx-primary)!important;color:var(--dx-primary-contrast)!important;}"
        ".btn-primary:hover{background:var(--dx-navy-2)!important;border-color:var(--dx-navy-2)!important;}"
        ".card,.panel,.box,.modal-content{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
        ".table{color:var(--dx-text)!important;}"
        ".table thead{background:var(--dx-surface-2)!important;color:var(--dx-text-muted)!important;}"
        ".form-control,.form-select{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
        ".form-control:focus,.form-select:focus{box-shadow:var(--dx-ring)!important;border-color:var(--dx-primary)!important;}"
        "table{width:100%!important;table-layout:fixed!important;font-size:11.5px!important;}"
        "table th,table td{padding:4px 6px!important;overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important;vertical-align:middle!important;}"
        "table th:nth-child(1),table td:nth-child(1){width:8%!important;}"
        "table th:nth-child(2),table td:nth-child(2){width:22%!important;}"
        "table th:nth-child(3),table td:nth-child(3){width:15%!important;}"
        "table th:nth-child(4),table td:nth-child(4){width:10%!important;}"
        # Product Activity report: reduce wide sticky columns and fix sticky left offsets.
        # Widths: Product#=120px, Description=180px, Brand=120px, PackageSize=90px.
        # min-width:0!important overrides the compiled inline min-width (300/220/160px).
        # left:Xpx!important fixes sticky offsets that were calculated from the old widths.
        "#reportContent table th:nth-child(2){width:180px!important;min-width:0!important;max-width:180px!important;}"
        "#reportContent table th:nth-child(3){width:120px!important;min-width:0!important;max-width:120px!important;left:300px!important;}"
        "#reportContent table td:nth-child(3){left:300px!important;}"
        "#reportContent table th:nth-child(4){width:90px!important;min-width:0!important;max-width:90px!important;left:420px!important;}"
        "#reportContent table td:nth-child(4){left:420px!important;}"
        "#reportContent table th:nth-child(2),#reportContent table th:nth-child(3),#reportContent table th:nth-child(4),"
        "#reportContent table td:nth-child(2),#reportContent table td:nth-child(3),#reportContent table td:nth-child(4)"
        "{white-space:normal!important;word-break:break-word!important;text-overflow:clip!important;overflow:hidden!important;vertical-align:top!important;}"
        "</style>"
    )

    body_block = (
        # Deduplicate /api/shared/restaurants fetch calls + minimal scroll
        # diagnostics. Function-level throttle and MutationObserver wrapping
        # are disabled because Object.defineProperty setter traps interfere
        # with IC3's function-declaration globals (causes "Enter Inventory"
        # product list to vanish).
        '<script>'
        '(function(){'
        # ---- fetch dedup (15s TTL) ----
        'var _F=window.fetch,_c={};'
        'window.fetch=function(input,init){'
        'var url=typeof input==="string"?input:(input&&input.url)||String(input);'
        'if(url.indexOf("/api/shared/restaurants")!==-1){'
        'var now=Date.now(),e=_c[url];'
        'if(e&&e.p&&(now-e.ts<15000))return e.p;'
        'var p=_F.apply(this,arguments).then(function(r){'
        'return r.text().then(function(t){'
        '_c[url]={p:Promise.resolve(new Response(t,{status:200,headers:{"Content-Type":"application/json"}})),ts:Date.now()};'
        'return new Response(t,{status:200,headers:{"Content-Type":"application/json"}});'
        '});'
        '})["catch"](function(e){delete _c[url];throw e;});'
        '_c[url]={p:p,ts:now};return p;'
        '}'
        'return _F.apply(this,arguments);'
        '};'
        '})();'
        '</script>'
        # ---- on-screen debug overlay (mobile-friendly) ----
        '<style>'
        '#dx-dbg{position:fixed;right:6px;bottom:48px;width:55vw;max-width:340px;height:38vh;max-height:300px;'
        'background:rgba(0,0,0,0.82);color:#9fe;font:10px/1.25 ui-monospace,Menlo,monospace;'
        'padding:6px 8px;border-radius:8px;overflow-y:auto;z-index:99999;border:1px solid #2a6;'
        'pointer-events:auto;white-space:pre-wrap;word-break:break-all;}'
        '#dx-dbg.hidden{display:none;}'
        '#dx-dbg-toggle{position:fixed;right:6px;bottom:6px;width:36px;height:36px;border-radius:50%;'
        'background:#22427A;color:#fff;border:0;z-index:100000;font:bold 12px sans-serif;display:none;}'
        '</style>'
        '<button id="dx-dbg-toggle" onclick="(function(){var d=document.getElementById(\'dx-dbg\');if(d){d.classList.toggle(\'hidden\');if(d.classList.contains(\'hidden\'))document.getElementById(\'dx-dbg-toggle\').style.display=\'none\';}})()">DBG</button>'
        '<div id="dx-dbg" class="hidden" onclick="this.innerHTML=\'\'"></div>'
        '<script>'
        '(function(){'
        'var dbg=null,buf=[],last=0;function flush(){'
        'if(!dbg)dbg=document.getElementById("dx-dbg");if(!dbg||!buf.length)return;'
        'dbg.innerHTML+=buf.join("");buf=[];dbg.scrollTop=dbg.scrollHeight;}'
        'setInterval(flush,400);'
        'function log(m){'
        'var t=new Date();var hh=String(t.getHours()).padStart(2,"0");'
        'var mm=String(t.getMinutes()).padStart(2,"0");var ss=String(t.getSeconds()).padStart(2,"0");'
        'var ms=String(t.getMilliseconds()).padStart(3,"0");'
        'buf.push("["+hh+":"+mm+":"+ss+"."+ms+"] "+m+"\\n");'
        '}window.dxLog=log;'
        # log all fetches (debounced via buffered flush)
        'var _F3=window.fetch;window.fetch=function(i,n){'
        'var u=typeof i==="string"?i:(i&&i.url)||String(i);'
        'if(u.indexOf("/dexter-ui/")===-1)log("fetch "+u.replace(/^https?:\\/\\/[^\\/]+/,""));'
        'return _F3.apply(this,arguments);};'
        # log scroll resets only (no MO wrap)
        'var lastY=0,lastT=0;window.addEventListener("scroll",function(){'
        'var y=window.scrollY||document.documentElement.scrollTop;'
        'if(lastY>40&&y<5&&(Date.now()-lastT<1500)){log("SCROLL RESET y="+lastY+"->"+y);}'
        'lastY=y;lastT=Date.now();},{passive:true});'
        'log("dx-debug ready");'
        '})();'
        '</script>'
        + IC3_INVENTORY_OPPORTUNITY_SCRIPT +
        '<script src="/dexter-ui/theme.js" defer></script>'
        '<div class="dx-version-badge" aria-hidden="true">2026 Dexter Assist v0.9</div>'
    )

    marker = "__dexter_ui_installed"

    @target_app.after_request
    def _inject_dexter_ui(response):
        content_type = (response.content_type or "").lower()
        if "text/html" not in content_type:
            return response
        if response.direct_passthrough:
            response.direct_passthrough = False
        try:
            body = response.get_data(as_text=True)
        except UnicodeDecodeError:
            return response

        if marker in body:
            return response
        if "</head>" not in body and "</body>" not in body:
            return response

        updated = body
        if "</head>" in updated:
            updated = updated.replace(
                "</head>",
                head_block + f'<meta name="dexter-ui" content="1" data-{marker}="1"></head>',
                1,
            )
        else:
            updated = head_block + updated
        if "</body>" in updated:
            updated = updated.replace("</body>", body_block + "</body>", 1)
        else:
            updated = updated + body_block

        response.set_data(updated)
        if "Content-Length" in response.headers:
            response.headers["Content-Length"] = str(len(response.get_data()))
        return response


_install_dexter_ui_patch()


if __name__ == "__main__":
    # Start mobile sync bridge in a separate daemon thread
    try:
        from mobile_sync_bridge import start_mobile_sync_bridge_thread
        start_mobile_sync_bridge_thread()
        print("[ic3] Mobile sync bridge started on port 5004")
    except ImportError:
        print("[ic3] Warning: mobile_sync_bridge not found - mobile sync disabled")
    except Exception as e:
        print(f"[ic3] Warning: Failed to start mobile sync bridge: {e}")

    runtime_app = globals().get("app")
    if runtime_app is not None:
        host = os.getenv("IC3_HOST", "127.0.0.1")
        port = int(os.getenv("IC3_PORT", "5003"))
        force_prod = os.getenv("IC3_FORCE_PROD", "1").strip().lower() not in {"0", "false", "no"}
        use_waitress = os.getenv("IC3_USE_WAITRESS", "1").strip().lower() not in {"0", "false", "no"}

        if force_prod and use_waitress:
            try:
                from waitress import serve  # type: ignore[import]
                waitress_threads = int(os.getenv("IC3_WAITRESS_THREADS", "8"))
                print(f"[ic3] Running via waitress on {host}:{port} (threads={waitress_threads})")
                serve(runtime_app, host=host, port=port, threads=waitress_threads)
            except ImportError:
                print("[ic3] waitress not installed — falling back to Flask dev server.")
                runtime_app.run(host=host, port=port, debug=False, use_reloader=False)
        else:
            runtime_app.run(host=host, port=port)
