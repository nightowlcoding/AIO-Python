from flask import jsonify, request
from pathlib import Path
import json
import marshal
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request
from datetime import date, datetime, timedelta

ROOT = Path(__file__).resolve().parent
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


def _sync_productmix_categories_from_remote(base_url: str, timeout_seconds: float = 12.0) -> dict:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:5050"
    target_url = f"{base}/api/categories"

    req = urllib_request.Request(
        target_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "IC3-ProductMix-Sync/1.0",
        },
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
            '<div style="display: grid; grid-template-columns: 1fr 220px; gap: 12px; margin-bottom: 12px;">' +
            '<div>' +
            '<label for="renameFolderPath" style="display: block; margin-bottom: 5px; font-weight: 600;">Folder Path</label>' +
            '<input id="renameFolderPath" type="text" readonly style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px; background: #f0f0f0;" />' +
            '<button id="pickFolderBtn" style="margin-top: 8px; padding: 6px 12px; border-radius: 6px; background: #1976d2; color: white; border: none;">Pick Folder</button>' +
            '</div>' +
            '<div>' +
            '<label for="renameLocationPrefix" style="display: block; margin-bottom: 5px; font-weight: 600;">Location Prefix</label>' +
            '<input id="renameLocationPrefix" type="text" value="Alice" style="width: 100%; padding: 10px; border: 2px solid #dee2e6; border-radius: 8px;" />' +
            '</div>' +
            '</div>' +
            '<div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px;">' +
            '<button class="btn" style="background: #1976d2; color: white;" onclick="previewOrderCsvRename()">Preview Rename</button>' +
            '<button class="btn" style="background: #2e7d32; color: white;" onclick="applyOrderCsvRename()">Apply Rename</button>' +
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
                    if (!response.ok || !payload.success) {
                        renderRenameStatus('&#10060; ' + escapeHtml(payload.message || 'Unable to open folder picker.'), false);
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
        }, 100);

        container.appendChild(tabContent);
    }

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
        const folderPath = document.getElementById('renameFolderPath')?.value?.trim();
        const locationPrefix = document.getElementById('renameLocationPrefix')?.value?.trim() || 'Alice';

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
        formData.append('location', location || 'Kingsville');
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

        const location = document.getElementById('bulkInvoiceLocation')?.value || 'Kingsville';
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
        windowKey: 'week',
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

        return 'Kingsville';
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
        state.windowKey = windowKey || state.windowKey || 'week';
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
        '  .ic3-mobile-card { border: 1px solid #dbe4f0; background: #ffffff; border-radius: 10px; padding: 10px; box-shadow: 0 2px 6px rgba(15,23,42,0.06); }',
        '  .ic3-mobile-category { font-size: 0.78rem; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 4px; }',
        '  .ic3-mobile-item { font-size: 0.95rem; font-weight: 700; color: #111827; line-height: 1.25; margin-bottom: 4px; }',
        '  .ic3-mobile-meta { font-size: 0.82rem; color: #6b7280; margin-bottom: 8px; }',
        '  .ic3-mobile-controls { display: grid; grid-template-columns: minmax(94px, 120px) 1fr; gap: 8px; align-items: center; }',
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
        mode: localStorage.getItem(storageKey) === 'table' ? 'table' : 'cards',
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

            card.appendChild(category);
            card.appendChild(item);
            card.appendChild(meta);
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
        renderCards();
        const showCards = state.mode === 'cards';
        hosts.cards.classList.toggle('cards-visible', showCards);
        hosts.categories.classList.toggle('ic3-table-hidden-mobile', showCards);
    }

    function scheduleRefresh() {
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

        if (!document.body.dataset.ic3MobileObserverInstalled) {
            const observer = new MutationObserver(function () {
                scheduleRefresh();
            });
            observer.observe(document.body, { childList: true, subtree: true, attributes: true });
            document.body.dataset.ic3MobileObserverInstalled = '1';
        }
    }

    if (mobileQuery && typeof mobileQuery.addEventListener === 'function') {
        mobileQuery.addEventListener('change', scheduleRefresh);
    } else if (mobileQuery && typeof mobileQuery.addListener === 'function') {
        mobileQuery.addListener(scheduleRefresh);
    }

    const runInstall = function () {
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
        updated = updated.replace("</body>", PRODUCTMIX_SYNC_UI_SCRIPT + "\n</body>", 1)

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
    return today_day - timedelta(days=6)


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


def _register_product_detail_endpoints(flask_app) -> None:
    if "get_product_detail_runtime" in flask_app.view_functions:
        return

    try:
        from flask import jsonify, request
    except Exception:
        return

    @flask_app.route("/api/products/<product_number>/detail", methods=["GET"])
    def get_product_detail_runtime(product_number):
        requested_location = str(request.args.get("location") or "Kingsville").strip() or "Kingsville"
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
            locations_to_scan = available_locations if available_locations else ["Kingsville"]
            location_label = "All Locations"
        else:
            locations_to_scan = [requested_location]
            location_label = requested_location

        product = _find_product_record_by_number(products_list_obj, canonical_num)
        product_payload = {
            "product_number": canonical_num,
            "description": str((product or {}).get("Product Description") or ""),
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

    @flask_app.route("/api/products/update-order-quantity", methods=["POST"])
    def update_order_quantity_runtime():
        payload = request.get_json(silent=True) or {}
        location = str(payload.get("location") or "Kingsville").strip() or "Kingsville"
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
        location = str(payload.get("location") or "Kingsville").strip() or "Kingsville"
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
        location = str(payload.get("location") or "Alice").strip() or "Alice"
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
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Select Folder for Order CSV Rename")
            root.destroy()

            if not selected:
                return jsonify({"success": True, "folder_path": "", "message": "Folder selection cancelled."})

            return jsonify({"success": True, "folder_path": selected})
        except Exception as exc:
            return jsonify({"success": False, "message": f"Folder picker unavailable: {exc}"}), 500


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

        try:
            synced = _sync_productmix_categories_from_remote(base_url, timeout_seconds=timeout_seconds)
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


def _register_compat_inventory_endpoints(flask_app) -> None:
    if flask_app is None:
        return

    existing_rules = {rule.rule for rule in flask_app.url_map.iter_rules()}

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
            items = []

            if isinstance(inventory_data_obj, dict):
                for location, by_date in inventory_data_obj.items():
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

    def patched_process_response(self, response):
        try:
            response.headers["X-IC3-BulkPatch"] = "active"
            content_type = (response.content_type or "").lower()
            if "text/html" in content_type or "javascript" in content_type:
                if not response.direct_passthrough:
                    body = response.get_data(as_text=True)
                    rewritten = _rewrite_bulk_upload_text(body)
                    if rewritten != body:
                        response.set_data(rewritten)
                        if "Content-Length" in response.headers:
                            response.headers["Content-Length"] = str(len(response.get_data()))
        except Exception:
            pass

        return original_process_response(self, response)

    Flask.process_response = patched_process_response
    Flask._ic3_bulk_patch_installed = True

def _exec_bytecode() -> None:
    if not BYTECODE_FILE.exists():
        raise FileNotFoundError(f"Missing compiled app bytecode: {BYTECODE_FILE}")

    data = BYTECODE_FILE.read_bytes()
    if len(data) < 16:
        raise ValueError(f"Invalid bytecode file header: {BYTECODE_FILE}")

    code = marshal.loads(data[16:])
    exec(code, globals(), globals())


def _force_production_flask_run() -> None:
    try:
        from flask import Flask
    except Exception:
        return

    if getattr(Flask, "_ic3_run_patched", False):
        return

    original_run = Flask.run

    def _run_with_safe_defaults(self, *args, **kwargs):
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
            "const remaining = Number.POSITIVE_INFINITY;",
        ),
        (
            r"if\s*\(files\.length\s*>\s*remaining\)\s*\{\s*alert\(`You can only add \$\{remaining\} more invoice\(s\)\. Maximum is 20 total\.`\);\s*files\.splice\(remaining\);\s*\}",
            "",
        ),
        (
            r"function\s+dateFromFilename\(filename\)\s*\{[\s\S]*?return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
            "function dateFromFilename(filename) {\\n            const m = filename.match(/(\\\\d{4})[-_\\/](\\\\d{2})[-_\\/](\\\\d{2})|^(\\\\d{4})(\\\\d{2})(\\\\d{2})/);\\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\\n            return new Date().toISOString().split('T')[0];\\n        }",
        ),
        (
            r"function\s+showBulkUpload\(\)\s*\{[\s\S]*?\}",
            "function showBulkUpload() {\\n            document.getElementById('singleUploadSection').style.display = 'none';\\n            document.getElementById('bulkUploadSection').style.display = 'block';\\n            bulkInvoices = [];\\n            renderBulkInvoiceList();\\n            const bulkStatus = document.getElementById('bulkUploadStatus');\\n            if (bulkStatus) bulkStatus.style.display = 'none';\\n        }",
        ),
        (
            r"function\s+dateFromFilename\(filename\)\s*\{\s*const\s+m\s*=\s*filename\.match\(/\^\\\(\\d\{4\}\\\)\\\(\\d\{2\}\\\)\\\(\\d\{2\}\\\)/\);\s*if\s*\(m\)\s*return\s*`\$\{m\[1\]\}-\$\{m\[2\]\}-\$\{m\[3\]\}`;\s*return\s+new\s+Date\(\)\.toISOString\(\)\.split\('T'\)\[0\];\s*\}",
            "function dateFromFilename(filename) {\\n            const m = filename.match(/(\\\\d{4})[-_\\/](\\\\d{2})[-_\\/](\\\\d{2})|^(\\\\d{4})(\\\\d{2})(\\\\d{2})/);\\n            if (m) return (m[1] || m[4]) + '-' + (m[2] || m[5]) + '-' + (m[3] || m[6]);\\n            return new Date().toISOString().split('T')[0];\\n        }",
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
            updated = updated.replace("</body>", PRODUCTMIX_SYNC_UI_SCRIPT + "\n</body>", 1)

        if updated != body:
            response.set_data(updated)
            if "Content-Length" in response.headers:
                response.headers["Content-Length"] = str(len(response.get_data()))

        return response


_install_global_flask_response_patch()
_install_order_csv_rename_api_patch()
_install_product_detail_api_patch()
_install_productmix_sync_api_patch()
_force_production_flask_run()
_exec_bytecode()
_register_compat_inventory_endpoints(globals().get("app"))
_register_invoice_import_log_endpoint(globals().get("app"))
_register_productmix_sync_endpoints(globals().get("app"))
_patch_favicon_endpoint()
_patch_bulk_upload_limit_runtime()
