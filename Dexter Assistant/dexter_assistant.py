# --- Place at the very end of the file, after all other routes and logic ---



from __future__ import annotations

import json
import os
import re
import sqlite3
import socket
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import requests
from flask import Flask, Response, jsonify, redirect, render_template_string, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "dexter_assistant_config.json"
RUNTIME_LOG_DIR = ROOT / "runtime_logs"
FRONT_DOOR_FAVICON = ROOT / "favicon.svg"
BRANDING_LOGO_PATH = ROOT / "dexter_logo.png"
LEGACY_BRANDING_LOGO_PATH = ROOT.parent / "Restaurant Management" / "Manager App" / "static" / "img" / "Dexter.png"
AUTH_USERS_PATH = ROOT / "dexter_assistant_users.json"
RBAC_DB_PATH = ROOT / "dexter_assistant_rbac.db"
SESSION_USER_KEY = "dexter_user"


DASHBOARD_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\" />
        <title>Dexter Ops</title>
        <style>
                :root {
                    --bg:#f3f4f6;
                        --panel:#ffffff;
                        --ink:#1f2937;
                        --muted:#6b7280;
                        --ok:#166534;
                        --bad:#991b1b;
                    --accent:#22427A;
                    --accent2:#1A335F;
                        --edge:#d1d5db;
                        --left:#f8fafc;
                        --left2:#f3f4f6;
                }
                * { box-sizing: border-box; }
                html, body { -webkit-text-size-adjust: 100%; }
                body {
                        margin: 0;
                        font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
                        color: var(--ink);
                            display: flex;
                            flex-direction: column;
                            min-height: 0;
                    background: linear-gradient(145deg, #f8fafc 0%, #f9fafb 45%, #eef2ff 100%);
                        min-height: 100vh;
                        min-height: 100dvh;
                        -webkit-overflow-scrolling: touch;
                        overflow-x: hidden;
                }
                .shell {
                        display: grid;
                        grid-template-columns: 220px 220px minmax(0, 1fr);
                        height: 100dvh;
                }
                .left-primary,
                .left-sub {
                    border-right: 1px solid var(--edge);
                    overflow: auto;
                }
                .left-primary {
                    background: var(--left);
                    padding: 12px 10px;
                }
                .left-sub {
                    background: var(--left2);
                    padding: 0;
                    width: 0;
                    overflow: hidden;
                    opacity: 0;
                    pointer-events: none;
                }
                .brand-row {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 14px;
                    gap: 8px;
                }
                .brand {
                    font-size: 23px;
                    font-weight: 800;
                    color: #0f172a;
                }
                .brand-mark {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    min-width: 0;
                }
                .brand-logo {
                    width: 34px;
                    height: 34px;
                    object-fit: contain;
                    border-radius: 8px;
                    background: #fff;
                    border: 1px solid #e5e7eb;
                    padding: 2px;
                    flex-shrink: 0;
                }
                .menu-btn {
                    border: 1px solid var(--edge);
                    background: #fff;
                    color: #334155;
                    border-radius: 10px;
                    width: 36px;
                    height: 36px;
                    cursor: pointer;
                }
                .primary-menu,
                .sub-menu {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }
                .primary-menu button,
                .sub-menu button {
                    border: 1px solid transparent;
                    background: transparent;
                    text-align: left;
                    color: #1f2937;
                    border-radius: 10px;
                    padding: 9px 10px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 600;
                }
                .primary-menu button:hover,
                .sub-menu button:hover {
                    background: #e5e7eb;
                }
                .primary-menu button.active,
                .sub-menu button.active {
                    background: var(--accent);
                    border-color: var(--accent2);
                    color: #fff;
                }
                .sub-head {
                    font-size: 11px;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    color: #64748b;
                    margin: 4px 8px;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                }
                .sub-toggle-btn {
                    border: 1px solid var(--edge)!important;
                    background: #fff!important;
                    color: #64748b!important;
                    border-radius: 6px!important;
                    width: 22px!important; height: 22px!important;
                    min-width: 0!important;
                    padding: 0!important;
                    font-size: 11px!important;
                    cursor: pointer!important;
                    flex-shrink: 0;
                }
                .sub-show-btn {
                    display: none;
                    border: 1px solid var(--edge);
                    background: #fff;
                    color: #64748b;
                    border-radius: 6px;
                    width: 26px; height: 26px;
                    min-width: 0;
                    padding: 0;
                    font-size: 12px;
                    cursor: pointer;
                    margin-top: 6px;
                    align-self: center;
                    width: 100%;
                }
                body.sub-hidden .sub-show-btn { display: flex; align-items:center; justify-content:center; }
                .shell.group-open {
                    grid-template-columns: 220px 220px minmax(0, 1fr);
                }
                body.collapsed .shell.group-open {
                    grid-template-columns: 72px 220px minmax(0, 1fr);
                }
                body.sub-hidden .shell.group-open {
                    grid-template-columns: 220px 0 minmax(0, 1fr);
                }
                body.collapsed.sub-hidden .shell.group-open {
                    grid-template-columns: 72px 0 minmax(0, 1fr);
                }
                body.sub-hidden .left-sub {
                    width: 0!important; padding:0!important; border:0!important;
                    overflow:hidden!important; opacity:0!important; pointer-events:none!important;
                }
                .shell.group-open .left-sub {
                    width: auto;
                    padding: 14px 10px;
                    border-left: 1px solid var(--edge);
                    overflow: auto;
                    opacity: 1;
                    pointer-events: auto;
                }
                .primary-menu button,
                .sub-menu button {
                        border: 1px solid transparent;
                        background: transparent;
                        text-align: left;
                        color: #1f2937;
                        border-radius: 10px;
                        padding: 9px 10px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 600;
                }
                .primary-menu button:hover,
                .sub-menu button:hover {
                        background: #e5e7eb;
                }
                .primary-menu button.active,
                .sub-menu button.active {
                    background: var(--accent);
                    border-color: var(--accent2);
                    color: #fff;
                }
                .sub-head {
                        font-size: 11px;
                        text-transform: uppercase;
                        letter-spacing: 0.08em;
                        color: #64748b;
                        margin: 4px 8px;
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                }
                body.collapsed .shell {
                    grid-template-columns: 72px 0 minmax(0, 1fr);
                }
                body.collapsed .brand {
                        display: none;
                }
                body.collapsed .brand-logo {
                    width: 28px;
                    height: 28px;
                }
                body.collapsed .left-sub {
                    width: 0;
                    padding: 0;
                    border-right: 0;
                    border-left: 0;
                    overflow: hidden;
                    opacity: 0;
                    pointer-events: none;
                }
                body.collapsed .primary-menu button {
                        font-size: 0;
                        min-height: 38px;
                        position: relative;
                }
                body.collapsed .primary-menu button::before {
                        content: attr(data-short);
                        font-size: 13px;
                        font-weight: 700;
                        color: #334155;
                }
                .mobile-top {
                        display: none;
                        padding: 10px 10px 0;
                }
                .main {
                        min-width: 0;
                        padding: 20px;
                    display: flex;
                    flex-direction: column;
                    min-height: 0;
                    overflow-y: auto;
                }
                .viewer-pane {
                    display: flex;
                    flex: 1;
                    min-height: 0;
                    padding: 0;
                    overflow: hidden;
                }
                .app-frame {
                    width: 100%;
                    height: 100%;
                    border: 0;
                    display: block;
                    flex: 1;
                    min-height: 0;
                    background: #fff;
                    border-radius: 16px;
                }
                .topbar {
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        gap: 12px;
                        flex-wrap: wrap;
                        margin-bottom: 14px;
                }
                .title {
                        margin: 0;
                        font-size: 34px;
                        font-weight: 800;
                        color: #111827;
                }
                .subtitle {
                        margin: 6px 0 0;
                        color: var(--muted);
                }
                .actions {
                        display: flex;
                        flex-wrap: wrap;
                        gap: 8px;
                }
                button,
                a.btn {
                        border: 1px solid #cbd5e1;
                        background: #fff;
                        color: #1f2937;
                        border-radius: 10px;
                        padding: 8px 12px;
                        font-size: 13px;
                        cursor: pointer;
                        text-decoration: none;
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        min-width: 88px;
                        font-weight: 600;
                }
                .primary { background: var(--accent); color: #fff; border-color: var(--accent2); }
                .warning { background: #7c3aed; color: #fff; border-color: #6d28d9; }
                .secondary { background: var(--accent2); color: #fff; border-color: #122443; }
                button:disabled { opacity: 0.55; cursor: not-allowed; }
                .pane {
                        display: none;
                        background: var(--panel);
                        border: 1px solid var(--edge);
                        border-radius: 16px;
                        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
                        padding: 16px;
                }
                .pane.active { display: block; }
                    .viewer-pane {
                        display: flex;
                        flex: 1;
                        min-height: 0;
                        padding: 0;
                        overflow: hidden;
                    }
                    .app-frame {
                        width: 100%;
                        height: 100%;
                        border: 0;
                        display: block;
                        flex: 1;
                        min-height: 0;
                        background: #fff;
                        border-radius: 16px;
                    }
                .banner {
                    border: 1px solid #bfdbfe;
                    background: #eff6ff;
                    color: #1d4ed8;
                        border-radius: 12px;
                        padding: 10px 12px;
                        margin-bottom: 14px;
                }
                .stats {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                        gap: 10px;
                        margin-bottom: 14px;
                }
                .stat {
                        border: 1px solid var(--edge);
                        border-radius: 12px;
                        padding: 12px;
                        background: #f9fafb;
                }
                .stat .label {
                        color: #64748b;
                        font-size: 12px;
                        margin-bottom: 6px;
                }
                .stat .value {
                        font-size: 24px;
                        font-weight: 800;
                        color: #0f172a;
                }
                .grid {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                        gap: 12px;
                }
                .card {
                        border: 1px solid var(--edge);
                        border-radius: 14px;
                        padding: 14px;
                        background: var(--panel);
                        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
                }
                .row {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        gap: 8px;
                }
                .name {
                        font-size: 20px;
                        font-weight: 700;
                        color: #0f172a;
                }
                .pill {
                        border-radius: 999px;
                        padding: 4px 10px;
                        font-size: 12px;
                        font-weight: 600;
                        border: 1px solid transparent;
                }
                .running { color: var(--ok); background: #dcfce7; border-color: #86efac; }
                .stopped { color: #78350f; background: #ffedd5; border-color: #fed7aa; }
                .error { color: var(--bad); background: #fee2e2; border-color: #fecaca; }
                .meta {
                        color: var(--muted);
                        font-size: 13px;
                        margin: 8px 0 10px;
                        word-break: break-word;
                }
                .btns {
                        display: flex;
                        gap: 8px;
                        flex-wrap: wrap;
                }
                .list {
                        border: 1px solid var(--edge);
                        border-radius: 12px;
                        overflow: hidden;
                }
                .list-row {
                        display: grid;
                        grid-template-columns: 1.3fr 0.8fr 1fr;
                        gap: 8px;
                        padding: 10px 12px;
                        border-bottom: 1px solid #e5e7eb;
                        align-items: center;
                        font-size: 13px;
                }
                .list-row:last-child { border-bottom: 0; }
                .list-head {
                    background: #e8eef5;
                        font-weight: 700;
                    color: #22427A;
                }
                .footer {
                        margin-top: 14px;
                        color: var(--muted);
                        font-size: 12px;
                }
                pre {
                        margin-top: 12px;
                        border-radius: 10px;
                        border: 1px solid #334155;
                        background: #1e293b;
                        color: #e2e8f0;
                        padding: 10px 12px;
                        max-height: 300px;
                        overflow: auto;
                        font-size: 11.5px;
                        font-family: 'Cascadia Code', 'Consolas', monospace;
                        line-height: 1.5;
                        white-space: pre-wrap;
                        word-break: break-all;
                }
                .stat.ok-stat { border-left: 4px solid #86efac; }
                .stat.bad-stat { border-left: 4px solid #fca5a5; }
                .stat.warn-stat { border-left: 4px solid #fcd34d; }
                .toast-wrap { position:fixed; bottom:22px; right:22px; display:flex; flex-direction:column; gap:8px; z-index:9999; pointer-events:none; }
                .toast { background:#1f2937; color:#fff; border-radius:10px; padding:11px 18px; font-size:13px; font-weight:600; opacity:0; transform:translateY(10px); transition:opacity 0.2s,transform 0.2s; pointer-events:none; max-width:340px; box-shadow:0 4px 16px rgba(0,0,0,0.18); }
                .toast.show { opacity:1; transform:translateY(0); }
                .toast.error { background:#991b1b; }
                .toast.ok { background:#166534; }
                .status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--edge); margin-left:5px; vertical-align:middle; transition:background .3s; }
                .status-dot.dot-ok { background:#86efac; }
                .status-dot.dot-warn { background:#fcd34d; }
                .status-dot.dot-bad { background:#fca5a5; }
                @media (max-width: 980px) {
                        html, body { overflow-x: hidden; }
                        body { min-height: 100vh; min-height: 100dvh; }
                        .shell {
                                grid-template-columns: minmax(0, 1fr);
                                min-height: auto;
                        }
                        .left-primary,
                        .left-sub {
                                position: fixed;
                                top: 0;
                                bottom: 0;
                                z-index: 20;
                                transform: translateX(-100%);
                                transition: transform 0.2s ease;
                                -webkit-overflow-scrolling: touch;
                        }
                        .left-primary {
                                width: 230px;
                                left: 0;
                        }
                        .left-sub {
                                width: 220px;
                                left: 230px;
                                border-left: 1px solid var(--edge);
                        }
                        .shell.menu-open .left-primary {
                                transform: translateX(0);
                        }
                        .shell.menu-open.group-open .left-sub {
                                transform: translateX(0);
                        }
                        .mobile-top { display: flex; position: sticky; top: 0; z-index: 10; background: rgba(248,250,252,0.92); backdrop-filter: blur(6px); }
                        .main { padding: 12px; min-height: auto; }
                        .title { font-size: 28px; }
                        .list-row { grid-template-columns: 1fr; gap: 2px; }
                        /* iOS-safe scroll wrapper: pane-viewer is the scroll surface, iframe grows to content. */
                        .viewer-pane,
                        #pane-viewer.active {
                                display: block !important;
                                overflow-y: auto !important;
                                overflow-x: hidden !important;
                                -webkit-overflow-scrolling: touch !important;
                                height: calc(100vh - 56px) !important;
                                height: calc(100dvh - 56px) !important;
                                max-height: calc(100dvh - 56px) !important;
                                min-height: 0 !important;
                                padding: 0 !important;
                                position: relative !important;
                                overscroll-behavior: contain;
                                touch-action: pan-y;
                        }
                        .app-frame {
                                width: 100% !important;
                                height: auto !important;
                                min-height: 100% !important;
                                display: block !important;
                                border: 0 !important;
                        }
                }
                #pane-home { display: none; }
                #pane-home.active { display: block; }
                #pane-viewer { display: none; }
                #pane-viewer.active { display: flex; flex: 1; min-height: 0; padding: 0; overflow: hidden; }
        </style>
</head>
<body>
        <div class="mobile-top">
                <button class="menu-btn" onclick="toggleMobileMenu()">Menu</button>
        </div>

        <div id="shell" class="shell">
        <div class="toast-wrap" id="toastWrap"></div>
                <aside class="left-primary">
                        <div class="brand-row">
                        <div class="brand-mark">
                            <img class="brand-logo" src="/branding/logo" alt="Dexter logo" />
                            <div class="brand">Dexter Ops</div>
                        </div>
                                <button class="menu-btn" onclick="toggleCollapsed()" title="Collapse sidebar">||</button>
                        </div>
                        <nav id="primaryNav" class="primary-menu">
                        <button data-short="HM" data-section="home" class="active" onclick="openHome()">Home</button>
                        <button data-short="IC" data-section="inventory" onclick="setSection('inventory')">Inventory Control <span class="status-dot" id="dot-ic3"></span></button>
                        <button data-short="PM" data-section="productmix" onclick="setSection('productmix')">Product Mix <span class="status-dot" id="dot-productmix"></span></button>
                        <button data-short="MG" data-section="managerapp" onclick="setSection('managerapp')">Daily Log <span class="status-dot" id="dot-managerapp"></span></button>
                        <button data-short="AD" data-section="admin" onclick="setSection('admin')">Admin</button>
                        </nav>
                </aside>

                <aside class="left-sub">
                    <div class="sub-head" id="subHead"><span id="subHeadLabel">Sub Menu</span><button class="sub-toggle-btn" onclick="toggleSubSidebar()" title="Hide panel">&#8249;</button></div>
                        <nav id="subNav" class="sub-menu"></nav>
                </aside>

                <main class="main">
                        <div class="topbar">
                                <div>
                            <h1 id="pageTitle" class="title">Home</h1>
                            <p id="pageSubtitle" class="subtitle">Overview of all operations.</p>
                                </div>
                                <div class="actions">
                                        <a class="btn" href="/auth/logout">Logout</a>
                                </div>
                        </div>

                        <section id="pane-home" class="pane active">
                            <div class="stats">
                                <div class="stat" id="statOpenTasks"><div class="label">Open Tasks</div><div class="value" style="font-size:28px">—</div></div>
                                <div class="stat" id="statAppsRunning"><div class="label">Apps Running</div><div class="value" style="font-size:28px">—</div></div>
                                <div class="stat" id="statTopSeller"><div class="label">Top Seller</div><div class="value" style="font-size:18px;line-height:1.2">—</div></div>
                            </div>
                            <div class="grid" id="homeAppCards" style="margin-bottom:14px;"></div>
                            <div style="margin-bottom:14px;">
                                <div class="sub-head" style="margin-bottom:8px;">Quick Actions</div>
                                <div class="btns">
                                    <button class="primary" onclick="openAppById('ic3-home')">Inventory Control</button>
                                    <button class="secondary" onclick="openAppById('mgr-daily-log')">Daily Log</button>
                                    <button onclick="openAppById('pm-production')">Production Report</button>
                                    <button onclick="openAppById('mgr-employees')">Employees</button>
                                </div>
                            </div>
                            <div>
                                <div class="sub-head" style="margin-bottom:8px;">Top Sellers (latest period)</div>
                                <div class="list" id="homeTopSellers">
                                    <div class="list-row list-head"><span>Item</span><span>Qty Sold</span></div>
                                    <div class="list-row" style="color:var(--muted)"><span>Loading...</span><span></span></div>
                                </div>
                            </div>
                        </section>
                        <section id="pane-viewer" class="pane viewer-pane">
                                <iframe id="appFrame" class="app-frame" src="about:blank"></iframe>
                        </section>
                </main>
        </div>

        <script>
            const menuGroups = {
                inventory: {
                    title: 'Inventory Control',
                    subtitle: 'Inventory apps and operational tools for the inventory workflow.',
                    items: [
                        { id: 'ic3-home', label: 'Inventory Control 3', url: '/app/ic3/' },
                        { id: 'ic3-enter', label: 'Enter Inventory', url: '/app/ic3/', ic3TabText: 'Enter Inventory' },
                        { id: 'ic3-saved', label: 'Saved Inventories', url: '/app/ic3/', ic3TabText: 'Saved Inventories' },
                        { id: 'ic3-est-vs-act', label: 'Estimated vs Actual', url: '/app/ic3/', ic3TabText: 'Estimated vs Actual' },
                        { id: 'ic3-orders', label: 'Orders', url: '/app/ic3/', ic3TabText: 'Orders' },
                        { id: 'ic3-manage', label: 'Manage Products', url: '/app/ic3/', ic3TabText: 'Manage Products' },
                        { id: 'ic3-forecast', label: 'Forecast', url: '/app/ic3/', ic3TabText: 'Forecast' },
                        { id: 'ic3-reports', label: 'Reports', url: '/app/ic3/', ic3TabText: 'Reports' },
                        { id: 'ic3-analytics', label: 'Analytics', url: '/app/ic3/', ic3TabText: 'Analytics' },
                        { id: 'ic3-usage', label: 'Usage History', url: '/app/ic3/', ic3TabText: 'Usage History' }
                    ]
                },
                productmix: {
                    title: 'Product Mix',
                    subtitle: 'Product mix reporting and production planning tools.',
                    items: [
                        { id: 'pm-home', label: 'Product Mix Home', url: '/app/productmix/product-mix' },
                        { id: 'pm-reports', label: 'Reports Overview', url: '/app/productmix/reports' },
                        { id: 'pm-production', label: 'Production Report', url: '/app/productmix/reports/production' },
                        { id: 'pm-categories', label: 'Categories', url: '/app/productmix/categories' },
                        { id: 'pm-production-list', label: 'Production List', url: '/app/productmix/production-list' }
                    ]
                },
                managerapp: {
                    title: 'Daily Log',
                    subtitle: 'Restaurant manager dashboard and operations workspace.',
                    items: [
                        { id: 'mgr-home', label: 'Home', url: '/app/managerapp/dashboard' },
                        { id: 'mgr-daily-log', label: 'Daily Log', url: '/app/managerapp/daily-log' },
                        { id: 'mgr-cash-manager', label: 'Cash Manager', url: '/app/managerapp/cash-manager' },
                        { id: 'mgr-employees', label: 'Employees', url: '/app/managerapp/employees' },
                        { id: 'mgr-reports', label: 'Reports', url: '/app/managerapp/reports' }
                    ]
                },
                admin: {
                    title: 'Admin',
                    subtitle: 'Company administration, user roles, task controls, and audit records.',
                    items: [
                        { id: 'admin-users', label: 'User Management', url: '/admin/users' },
                        { id: 'admin-tasks', label: 'Operational Tasks', url: '/admin/tasks' },
                        { id: 'admin-audit', label: 'Audit Logs', url: '/admin/audit-logs' },
                        { id: 'admin-location-management', label: 'Location Management', url: '/app/productmix/restaurant-setup' },
                        { id: 'admin-productmix-dashboard', label: 'ProductMix Admin Dashboard', url: '/app/productmix/admin' }
                    ]
                }
            };

            let activeGroup = 'managerapp';
            let activeApp = 'mgr-home';

            function normalizeLabel(value) {
                return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
            }

            function activateIc3Tab(item, attemptsLeft) {
                var frame = document.getElementById('appFrame');
                if (!frame || !item || !item.ic3TabText) return;
                if (typeof attemptsLeft !== 'number') attemptsLeft = 12;

                try {
                    var win = frame.contentWindow;
                    var doc = win ? win.document : null;
                    if (!doc || !doc.body) throw new Error('Frame not ready');

                    var target = normalizeLabel(item.ic3TabText);
                    var candidates = Array.prototype.slice.call(
                        doc.querySelectorAll('.tab, button, [role="tab"], .nav-link, a')
                    );
                    var btn = candidates.find(function(el) {
                        return normalizeLabel(el.textContent).indexOf(target) !== -1;
                    });

                    if (btn) {
                        btn.click();
                        return;
                    }
                } catch (e) {
                    // Frame still loading; retry below.
                }

                if (attemptsLeft > 0) {
                    setTimeout(function() {
                        activateIc3Tab(item, attemptsLeft - 1);
                    }, 180);
                }
            }

            function htmlEscape(value) {
                return String(value || '').replace(/[<>&]/g, function(m) {
                    if (m === '<') return '&lt;';
                    if (m === '>') return '&gt;';
                    return '&amp;';
                });
            }

            function showToast(msg, type) {
                var wrap = document.getElementById('toastWrap');
                var t = document.createElement('div');
                t.className = 'toast' + (type ? ' ' + type : '');
                t.textContent = msg;
                wrap.appendChild(t);
                requestAnimationFrame(function() { t.classList.add('show'); });
                setTimeout(function() {
                    t.classList.remove('show');
                    setTimeout(function() { t.remove(); }, 300);
                }, 3200);
            }

            async function act(url, body, btn) {
                if (btn) { btn.disabled = true; var origText = btn.textContent; btn.textContent = '...'; }
                try {
                    var res = await fetch(url, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: body ? JSON.stringify(body) : '{}'
                    });
                    if (!res.ok) {
                        var txt = await res.text();
                        showToast('Action failed: ' + txt, 'error');
                    } else {
                        showToast('Done.', 'ok');
                    }
                } catch (e) {
                    showToast('Request failed: ' + e.message, 'error');
                } finally {
                    if (btn) { btn.disabled = false; btn.textContent = origText; }
                }
                await refreshState();
            }

            function badgeClass(state) {
                if (state.running && state.healthy) return 'pill running';
                if (state.running && !state.healthy) return 'pill error';
                return 'pill stopped';
            }

            function badgeText(state) {
                if (state.running && state.healthy) return 'Running';
                if (state.running && !state.healthy) return 'Running (unhealthy)';
                return 'Stopped';
            }

            function toggleCollapsed() {
                document.body.classList.toggle('collapsed');
                try { localStorage.setItem('dexterSidebarCollapsed', document.body.classList.contains('collapsed') ? '1' : '0'); } catch(e) {}
            }

            function toggleSubSidebar() {
                document.body.classList.toggle('sub-hidden');
                var hidden = document.body.classList.contains('sub-hidden');
                try { localStorage.setItem('dexterSubHidden', hidden ? '1' : '0'); } catch(e) {}
                var btn = document.querySelector('.sub-toggle-btn');
                if (btn) btn.textContent = hidden ? '\u203a' : '\u2039';
            }

            (function() {
                try {
                    if (localStorage.getItem('dexterSidebarCollapsed') === '1') document.body.classList.add('collapsed');
                    if (localStorage.getItem('dexterSubHidden') === '1') {
                        document.body.classList.add('sub-hidden');
                        var btn = document.querySelector('.sub-toggle-btn');
                        if (btn) btn.textContent = '\u203a';
                    }
                } catch(e) {}
            })();

            function toggleMobileMenu() {
                document.getElementById('shell').classList.toggle('menu-open');
            }

            function setSection(section) {
                if (!menuGroups[section]) return;
                activeGroup = section;
                document.querySelectorAll('#primaryNav button').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.section === section);
                });

                const title = document.getElementById('pageTitle');
                const subtitle = document.getElementById('pageSubtitle');
                title.textContent = menuGroups[section].title;
                subtitle.textContent = menuGroups[section].subtitle;
                document.getElementById('shell').classList.add('group-open');
                renderSubmenu(section);
                openApp(menuGroups[section].items[0]);
            }

            function openApp(item) {
                if (!item) return;
                activeApp = item.id;
                try { localStorage.setItem('dexterNav', JSON.stringify({group: activeGroup, app: activeApp})); } catch(e) {}
                switchToViewerPane();
                var frame = document.getElementById('appFrame');
                var nextUrl = item.url || '/app/ic3/';
                var currentUrl = frame.getAttribute('src') || '';
                var isIc3Loaded = currentUrl.indexOf('/app/ic3/') !== -1;

                if (item.ic3TabText) {
                    if (!isIc3Loaded) {
                        frame.onload = function() {
                            activateIc3Tab(item, 12);
                        };
                        frame.src = '/app/ic3/';
                    } else {
                        frame.onload = null;
                        activateIc3Tab(item, 12);
                    }
                } else {
                    frame.onload = null;
                    if (currentUrl !== nextUrl) {
                        frame.src = nextUrl;
                    }
                }

                document.querySelectorAll('#subNav button').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.app === item.id);
                });
                if (window.innerWidth <= 980) {
                    document.getElementById('shell').classList.remove('menu-open');
                    document.getElementById('shell').classList.remove('group-open');
                }
            }

            function renderSubmenu(section) {
                const nav = document.getElementById('subNav');
                const head = document.getElementById('subHead');
                nav.innerHTML = '';
                head.textContent = menuGroups[section].title;
                (menuGroups[section].items || []).forEach(function(item) {
                    const btn = document.createElement('button');
                    btn.textContent = item.label;
                    btn.dataset.app = item.id;
                    btn.classList.toggle('active', item.id === activeApp);
                    btn.onclick = function() { openApp(item); };
                    nav.appendChild(btn);
                });
            }

            var _pollTimer = null;
            function startPoll() {
                if (_pollTimer) return;
                _pollTimer = setInterval(refreshState, 2500);
            }
            function stopPoll() {
                if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
            }
            document.addEventListener('visibilitychange', function() {
                if (document.hidden) { stopPoll(); } else { refreshState(); startPoll(); }
            });

            async function refreshState() {
                try {
                    var res = await fetch('/api/status');
                    if (!res.ok) return;
                    var data = await res.json();
                    updateStatusDots(data.apps || {});
                } catch (e) { /* network hiccup — skip silently */ }
            }

            function updateStatusDots(apps) {
                var dotMap = {ic3: 'ic3', productmix: 'productmix', managerapp: 'managerapp'};
                Object.keys(dotMap).forEach(function(key) {
                    var dot = document.getElementById('dot-' + dotMap[key]);
                    if (!dot) return;
                    var s = apps[key] || {};
                    dot.className = 'status-dot';
                    if (s.running && s.healthy) dot.className += ' dot-ok';
                    else if (s.running) dot.className += ' dot-warn';
                    else dot.className += ' dot-bad';
                });
            }

            var _dashPollTimer = null;
            function openHome() {
                try { localStorage.setItem('dexterNav', JSON.stringify({home: true})); } catch(e) {}
                if (_dashPollTimer) { clearInterval(_dashPollTimer); _dashPollTimer = null; }
                document.getElementById('pane-viewer').classList.remove('active');
                document.getElementById('pane-home').classList.add('active');
                document.querySelectorAll('#primaryNav button').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.section === 'home');
                });
                document.getElementById('shell').classList.remove('group-open');
                document.getElementById('pageTitle').textContent = 'Home';
                document.getElementById('pageSubtitle').textContent = 'Overview of all operations.';
                loadHomeDashboard();
                _dashPollTimer = setInterval(loadHomeDashboard, 30000);
            }

            function switchToViewerPane() {
                if (_dashPollTimer) { clearInterval(_dashPollTimer); _dashPollTimer = null; }
                document.getElementById('pane-home').classList.remove('active');
                document.getElementById('pane-viewer').classList.add('active');
            }

            function openAppById(appId) {
                for (var g in menuGroups) {
                    var items = menuGroups[g].items || [];
                    for (var i = 0; i < items.length; i++) {
                        if (items[i].id === appId) { setSection(g); openApp(items[i]); return; }
                    }
                }
            }

            async function loadHomeDashboard() {
                try {
                    var res = await fetch('/api/dashboard');
                    if (!res.ok) return;
                    var data = await res.json();
                    renderHomeDashboard(data);
                } catch(e) {}
            }

            function renderHomeDashboard(data) {
                var statOT = document.getElementById('statOpenTasks');
                var statAR = document.getElementById('statAppsRunning');
                var statTS = document.getElementById('statTopSeller');
                if (statOT) {
                    statOT.querySelector('.value').textContent = data.open_tasks != null ? data.open_tasks : '—';
                    statOT.className = 'stat' + (data.open_tasks > 0 ? ' warn-stat' : ' ok-stat');
                }
                if (statAR) {
                    var running = data.apps_running != null ? data.apps_running : '?';
                    var total = data.total_apps != null ? data.total_apps : '?';
                    statAR.querySelector('.value').textContent = running + ' / ' + total;
                    statAR.className = 'stat' + (data.apps_running === data.total_apps ? ' ok-stat' : ' warn-stat');
                }
                var sellers = data.top_sellers || [];
                if (statTS) {
                    statTS.querySelector('.value').textContent = sellers.length > 0 ? sellers[0].name : '—';
                    statTS.className = 'stat';
                }
                var cardsEl = document.getElementById('homeAppCards');
                if (cardsEl && data.app_status) {
                    var appLabels = {ic3: 'Inventory Control', productmix: 'ProductMix', managerapp: 'Daily Log'};
                    cardsEl.innerHTML = Object.keys(appLabels).map(function(key) {
                        var s = (data.app_status || {})[key] || {};
                        var cls = s.running && s.healthy ? 'pill running' : s.running ? 'pill error' : 'pill stopped';
                        var txt = s.running && s.healthy ? 'Running' : s.running ? 'Unhealthy' : 'Stopped';
                        var url = s.url || '';
                        return '<div class="card"><div class="row"><span class="name" style="font-size:15px;">' + htmlEscape(appLabels[key]) + '</span><span class="' + cls + '">' + txt + '</span></div>' + (url ? '<div class="meta">' + htmlEscape(url) + '</div>' : '') + '</div>';
                    }).join('');
                }
                var listEl = document.getElementById('homeTopSellers');
                if (listEl) {
                    listEl.innerHTML = '<div class="list-row list-head"><span>Item</span><span>Qty Sold</span></div>' +
                        (sellers.length === 0
                            ? '<div class="list-row" style="color:var(--muted)"><span>No data available</span><span></span></div>'
                            : sellers.map(function(s, i) {
                                return '<div class="list-row"><span>' + (i+1) + '. ' + htmlEscape(s.name) + '</span><span>' + (Math.round(s.qty * 10) / 10) + '</span></div>';
                            }).join(''));
                }
            }

            (function() {
                var saved = null;
                try { saved = JSON.parse(localStorage.getItem('dexterNav') || 'null'); } catch(e) {}
                if (saved && saved.home) {
                    openHome();
                } else if (saved && menuGroups[saved.group]) {
                    setSection(saved.group);
                    if (saved.app) {
                        var items = menuGroups[saved.group].items || [];
                        for (var i = 0; i < items.length; i++) {
                            if (items[i].id === saved.app) { openApp(items[i]); break; }
                        }
                    }
                } else {
                    openHome();
                }
                refreshState();
                startPoll();
            })();

            // ---- Mobile iframe height sizing so pane-viewer scrolls (fixes iOS bounce) ----
            // KEY RULE: NEVER set frame height on a recurring interval — that causes mid-scroll
            // layout reflow which snaps iOS Safari back to the top.
            (function() {
                var frame = document.getElementById('appFrame');
                if (!frame) return;
                var _resizeTimer = null;
                function resizeFrameToContent() {
                    if (window.innerWidth > 980) {
                        // Desktop: fixed-pane layout — let CSS control height
                        frame.style.height = '';
                        frame.style.minHeight = '';
                        return;
                    }
                    // Mobile: measure content and set height ONCE so pane-viewer can scroll.
                    // scrolling=no is set as HTML attribute so iOS never creates inner scroll surface.
                    try {
                        var doc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
                        if (!doc || !doc.body) return;
                        var h = Math.max(
                            doc.body.scrollHeight,
                            doc.documentElement ? doc.documentElement.scrollHeight : 0
                        );
                        if (h && h > 80) {
                            frame.style.height = h + 'px';
                        }
                    } catch (e) { /* cross-origin */ }
                }
                function scheduleResize(delay) {
                    clearTimeout(_resizeTimer);
                    _resizeTimer = setTimeout(resizeFrameToContent, delay || 0);
                }
                frame.addEventListener('load', function() {
                    scheduleResize(100);
                    scheduleResize(600);
                    scheduleResize(1500);
                    try {
                        var doc = frame.contentDocument;
                        // ResizeObserver: debounced so rapid changes don't keep reflowing during scroll
                        if (doc && window.ResizeObserver) {
                            var ro = new ResizeObserver(function() { scheduleResize(400); });
                            ro.observe(doc.documentElement);
                            if (doc.body) ro.observe(doc.body);
                        }
                        // Re-measure after user taps a tab inside the app (content changes)
                        if (doc) {
                            doc.addEventListener('click', function() { scheduleResize(400); }, true);
                        }
                    } catch (e) { /* cross-origin */ }
                });
                // Re-measure on orientation change / window resize but NOT on a recurring interval
                window.addEventListener('resize', function() { scheduleResize(300); });
            })();
        </script>
</body>
</html>
"""
PORTAL_HOME_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\" />
    <title>Dexter Ops Portal</title>
    <style>
        :root {
            --accent:#ea580c;
            --accent2:#0f766e;
            --ink:#1f2937;
            --muted:#6b7280;
            --bg:linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#eef2ff 100%);
            --panel:#ffffff;
            --edge:#d1d5db;
            --ok:#166534;
            --bad:#991b1b;
        }
        * { box-sizing: border-box; }
        html, body { -webkit-text-size-adjust: 100%; overflow-x: hidden; }
        body {
            margin: 0;
            font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
            color: var(--ink);
            background: var(--bg);
            min-height: 100vh;
            min-height: 100dvh;
            -webkit-overflow-scrolling: touch;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 18px;
            border-bottom: 1px solid var(--edge);
            background: #ffffff;
            position: sticky;
            top: 0;
            z-index: 5;
            box-shadow: 0 1px 4px rgba(15,23,42,0.06);
        }
        .brand { font-size: 20px; font-weight: 800; color: #0f172a; letter-spacing: 0.2px; }
        .brand-wrap { display: flex; align-items: center; gap: 10px; }
        .brand-logo { width: 30px; height: 30px; object-fit: contain; border-radius: 8px; background: #fff; border: 1px solid var(--edge); padding: 2px; }
        .nav { display: flex; gap: 8px; flex-wrap: wrap; }
        .nav a, .nav button {
            border: 1px solid var(--edge);
            background: #fff;
            color: var(--ink);
            border-radius: 10px;
            padding: 8px 13px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }
        .nav a:hover, .nav button:hover { background: #f1f5f9; }
        .nav .primary { background: var(--accent); color: #fff; border-color: #c2410c; }
        .nav .primary:hover { background: #c2410c; }
        .nav .danger { background: var(--bad); color: #fff; border-color: #7f1d1d; }
        .nav .danger:hover { background: #7f1d1d; }
        .nav button:disabled { opacity: 0.55; cursor: not-allowed; }
        .wrap { max-width: 1120px; margin: 0 auto; padding: 28px 18px 36px; }
        h1 { margin: 0 0 6px; font-size: 34px; font-weight: 800; color: #111827; }
        .subtitle { color: var(--muted); margin: 0 0 18px; }
        .banner {
            border: 1px solid #fed7aa;
            background: #fff7ed;
            border-radius: 12px;
            padding: 10px 14px;
            color: #9a3412;
            margin-bottom: 18px;
            font-size: 13px;
        }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
        .card {
            background: var(--panel);
            border: 1px solid var(--edge);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 8px 24px rgba(15,23,42,0.07);
        }
        .card h2 { margin: 0 0 6px; font-size: 21px; font-weight: 700; color: #0f172a; }
        .card p { margin: 0 0 14px; color: var(--muted); font-size: 14px; }
        .actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .actions a {
            border: 1px solid var(--edge);
            background: #fff;
            color: var(--ink);
            border-radius: 10px;
            padding: 8px 13px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 600;
        }
        .actions a:hover { background: #f1f5f9; }
        .actions a.primary { background: var(--accent); color: #fff; border-color: #c2410c; }
        .actions a.primary:hover { background: #c2410c; }
        .actions a.secondary { background: var(--accent2); color: #fff; border-color: #0c5b55; }
        .footer { margin-top: 18px; color: var(--muted); font-size: 12px; }
        .toast-wrap { position:fixed; bottom:20px; right:20px; display:flex; flex-direction:column; gap:8px; z-index:9999; pointer-events:none; }
        .toast { background:#1f2937; color:#fff; border-radius:10px; padding:10px 16px; font-size:13px; font-weight:600; opacity:0; transform:translateY(10px); transition:opacity 0.2s,transform 0.2s; pointer-events:none; max-width:320px; }
        .toast.show { opacity:1; transform:translateY(0); }
        .toast.error { background:#991b1b; }
        .toast.ok { background:#166534; }
        @media (max-width: 700px) {
            .wrap { padding: 12px 10px 18px; }
            h1 { font-size: 1.5rem; }
            .cards { gap: 10px; }
            .card { padding: 12px; }
            .topbar { flex-wrap: wrap; gap: 8px; }
        }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand-wrap">
            <img class="brand-logo" src="/branding/logo" alt="Dexter logo" />
            <div class="brand">Dexter Ops Portal</div>
        </div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/portal/productmix">ProductMix</a>
            <a href="/portal/ic3">Inventory Control 3</a>
            <a href="/portal/managerapp">Daily Log</a>
            <button class="primary" id="btnStartAll" onclick="act('/api/start-all', this)">Start All</button>
            <button class="danger" id="btnStopAll" onclick="act('/api/stop-all', this)">Stop All</button>
            <a href="/auth/logout">Logout</a>
        </div>
    </div>
    <div class="toast-wrap" id="toastWrap"></div>
    <div class="wrap">
        <h1>Restaurant Management</h1>
        <p class="subtitle">Run both systems under one portal and switch between them from shared navigation.</p>
        <div class="banner">Both copied apps are hosted behind this portal. Original source folders remain untouched.</div>
        <div class="cards">
            <div class="card">
                <h2>ProductMixRestaurantDB</h2>
                <p>Upload and analyze product mixes, production lists, and report views.</p>
                <div class="actions">
                    <a class="primary" href="/portal/productmix">Open ProductMix</a>
                    <a class="secondary" href="/app/productmix/" target="_blank" rel="noopener">Open Raw</a>
                </div>
            </div>
            <div class="card">
                <h2>Inventory Control 3</h2>
                <p>Inventory tracking, invoice imports, and usage analytics for locations.</p>
                <div class="actions">
                    <a class="primary" href="/portal/ic3">Open IC3</a>
                    <a class="secondary" href="/app/ic3/" target="_blank" rel="noopener">Open Raw</a>
                </div>
            </div>
            <div class="card">
                <h2>Daily Log</h2>
                <p>Manager workflows for daily logs, employees, and operational reports.</p>
                <div class="actions">
                    <a class="primary" href="/portal/managerapp">Open Daily Log</a>
                    <a class="secondary" href="/app/managerapp/" target="_blank" rel="noopener">Open Raw</a>
                </div>
            </div>
        </div>
        <div class="footer">Front door: {{ host }}:{{ port }}</div>
    </div>
    <script>
        function showToast(msg, type) {
            var wrap = document.getElementById('toastWrap');
            var t = document.createElement('div');
            t.className = 'toast' + (type ? ' ' + type : '');
            t.textContent = msg;
            wrap.appendChild(t);
            requestAnimationFrame(function() { t.classList.add('show'); });
            setTimeout(function() {
                t.classList.remove('show');
                setTimeout(function() { t.remove(); }, 300);
            }, 3200);
        }
        async function act(url, btn) {
            if (btn) { btn.disabled = true; var orig = btn.textContent; btn.textContent = '...'; }
            try {
                var res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
                if (!res.ok) {
                    var txt = await res.text();
                    showToast('Action failed: ' + txt, 'error');
                } else {
                    showToast('Done.', 'ok');
                }
            } catch (e) {
                showToast('Request failed: ' + e.message, 'error');
            } finally {
                if (btn) { btn.disabled = false; btn.textContent = orig; }
            }
        }
    </script>
</body>
</html>
"""


RBAC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE CHECK (name IN ('Super Admin', 'Manager', 'Employee')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in-progress', 'completed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    created_by INTEGER NOT NULL,
    assigned_to INTEGER,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (assigned_to) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS migration_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at DESC);
"""


def get_rbac_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(RBAC_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_default_roles(conn: sqlite3.Connection) -> None:
    for role_name in ("Super Admin", "Manager", "Employee"):
        conn.execute("INSERT OR IGNORE INTO roles (name) VALUES (?)", (role_name,))


def initialize_rbac_db() -> None:
    conn = get_rbac_db_connection()
    try:
        conn.executescript(RBAC_SCHEMA_SQL)
        seed_default_roles(conn)
        conn.commit()
    finally:
        conn.close()


def _get_role_id(conn: sqlite3.Connection, role_name: str) -> int:
    row = conn.execute("SELECT id FROM roles WHERE name = ? LIMIT 1", (role_name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown role: {role_name}")
    return int(row["id"])


def _get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT u.id, u.username, u.password_hash, u.is_active, u.last_login, r.name AS role_name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE LOWER(u.username) = LOWER(?)
        LIMIT 1
        """,
        (username,),
    ).fetchone()


def _mark_migration_complete(conn: sqlite3.Connection, key: str) -> None:
    conn.execute(
        """
        INSERT INTO migration_meta (key, value, updated_at)
        VALUES (?, '1', datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key,),
    )


def _is_migration_complete(conn: sqlite3.Connection, key: str) -> bool:
    row = conn.execute("SELECT value FROM migration_meta WHERE key = ? LIMIT 1", (key,)).fetchone()
    return bool(row and str(row["value"]) == "1")


def migrate_legacy_json_users_to_sqlite() -> None:
    migration_key = "json_users_migrated_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return

        users = load_auth_users()
        for username, payload in users.items():
            if not isinstance(payload, dict):
                continue

            normalized_username = str(username or "").strip()
            password_hash = str(payload.get("password_hash") or "").strip()
            if not normalized_username or not password_hash:
                continue

            role_name = "Super Admin" if bool(payload.get("is_admin", False)) else "Employee"
            role_id = _get_role_id(conn, role_name)
            created_at = payload.get("created_at") or datetime.now().isoformat(timespec="seconds")
            last_login = payload.get("last_login")

            existing = _get_user_by_username(conn, normalized_username)
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?,
                        role_id = ?,
                        is_active = 1,
                        updated_at = datetime('now'),
                        last_login = COALESCE(?, last_login)
                    WHERE id = ?
                    """,
                    (password_hash, role_id, last_login, int(existing["id"])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, is_active, created_at, updated_at, last_login)
                    VALUES (?, ?, ?, 1, ?, datetime('now'), ?)
                    """,
                    (normalized_username, password_hash, role_id, created_at, last_login),
                )

        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()


def migrate_add_task_fields_v1() -> None:
    migration_key = "tasks_due_date_priority_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
        except Exception:
            pass  # column already exists
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        except Exception:
            pass  # column already exists
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()


def migrate_add_password_reset_fields_v1() -> None:
    migration_key = "users_password_reset_v1"
    conn = get_rbac_db_connection()
    try:
        if _is_migration_complete(conn, migration_key):
            return
        try:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_token TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN password_reset_expires TEXT")
        except Exception:
            pass
        _mark_migration_complete(conn, migration_key)
        conn.commit()
    finally:
        conn.close()


def ensure_default_super_admin_user() -> None:
    admin_username = os.environ.get("DEXTER_ADMIN_USER", "").strip()
    admin_password = os.environ.get("DEXTER_ADMIN_PASS", "").strip()
    if not admin_username or not admin_password:
        return

    conn = get_rbac_db_connection()
    try:
        role_id = _get_role_id(conn, "Super Admin")
        existing = _get_user_by_username(conn, admin_username)
        if existing:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, role_id = ?, is_active = 1, updated_at = datetime('now')
                WHERE id = ?
                """,
                (generate_password_hash(admin_password), role_id, int(existing["id"])),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, role_id, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
                """,
                (admin_username, generate_password_hash(admin_password), role_id),
            )
        conn.commit()
    finally:
        conn.close()


def find_auth_user(identifier: str) -> tuple[str | None, dict[str, Any] | None]:
    normalized = str(identifier or "").strip()
    if not normalized:
        return None, None

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.password_hash, u.is_active, u.last_login, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE LOWER(u.username) = LOWER(?)
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()
        if not row:
            return None, None
        return str(row["username"]), dict(row)
    finally:
        conn.close()


def update_user_last_login(user_id: int) -> None:
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            "UPDATE users SET last_login = datetime('now'), updated_at = datetime('now') WHERE id = ?",
            (int(user_id),),
        )
        conn.commit()
    finally:
        conn.close()


def current_user_id() -> int | None:
    raw_id = (session.get(SESSION_USER_KEY) or {}).get("user_id")
    if raw_id is None:
        return None
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def current_role_name() -> str:
    user = session.get(SESSION_USER_KEY) or {}
    role_name = str(user.get("role_name") or "").strip()
    if role_name:
        return role_name
    if bool(user.get("is_admin")):
        return "Super Admin"
    return "Employee"


def user_has_role(user_id: int, allowed_roles: tuple[str, ...]) -> bool:
    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ? AND u.is_active = 1
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        if not row:
            return False
        return str(row["role_name"]) in allowed_roles
    finally:
        conn.close()


def can_user_create_task(user_id: int) -> bool:
    """Allow task creation only for Super Admin or Manager roles."""
    return user_has_role(int(user_id), ("Super Admin", "Manager"))


def add_audit_log(actor_user_id: int, action: str, target_table: str, target_id: int | None = None, details: str | None = None) -> None:
    conn = get_rbac_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_logs (actor_user_id, action, target_table, target_id, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(actor_user_id), str(action), str(target_table), int(target_id) if target_id is not None else None, details),
        )
        conn.commit()
    finally:
        conn.close()


def role_required(*allowed_roles: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if current_role_name() in allowed_roles:
                return view_func(*args, **kwargs)
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "message": "Forbidden"}), 403
            return jsonify({"ok": False, "message": "Forbidden"}), 403

        return wrapped

    return decorator


def list_users_with_roles() -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.is_active, u.created_at, u.updated_at, u.last_login, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            ORDER BY LOWER(u.username) ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _active_super_admin_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.is_active = 1 AND r.name = 'Super Admin'
        """
    ).fetchone()
    return int(row["total"] if row else 0)


def create_user_account(actor_user_id: int, username: str, password: str, role_name: str = "Employee") -> tuple[bool, str]:
    normalized_username = str(username or "").strip()
    if len(normalized_username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password or "") < 8:
        return False, "Password must be at least 8 characters."
    if role_name not in {"Super Admin", "Manager", "Employee"}:
        return False, "Invalid role name."

    conn = get_rbac_db_connection()
    try:
        exists = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (normalized_username,),
        ).fetchone()
        if exists:
            return False, "Username already exists."

        role_id = _get_role_id(conn, role_name)
        cur = conn.execute(
            """
            INSERT INTO users (username, password_hash, role_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
            """,
            (normalized_username, generate_password_hash(password), role_id),
        )
        conn.commit()
        add_audit_log(actor_user_id, "create_user", "users", int(cur.lastrowid), json.dumps({"username": normalized_username, "role": role_name}))
        return True, "User created."
    finally:
        conn.close()


def set_user_active_state(actor_user_id: int, target_user_id: int, is_active: bool) -> tuple[bool, str]:
    conn = get_rbac_db_connection()
    try:
        target = conn.execute(
            """
            SELECT u.id, u.username, u.is_active, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(target_user_id),),
        ).fetchone()
        if not target:
            return False, "User not found."

        if int(actor_user_id) == int(target["id"]) and not is_active:
            return False, "You cannot deactivate your own account."

        if str(target["role_name"]) == "Super Admin" and not is_active and _active_super_admin_count(conn) <= 1:
            return False, "Cannot deactivate the last active Super Admin."

        conn.execute(
            "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if is_active else 0, int(target_user_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "activate_user" if is_active else "deactivate_user",
            "users",
            int(target_user_id),
            json.dumps({"username": str(target["username"]), "role": str(target["role_name"])}),
        )
        return True, "User updated."
    finally:
        conn.close()


def set_user_role_name(actor_user_id: int, target_user_id: int, role_name: str) -> tuple[bool, str]:
    if role_name not in {"Super Admin", "Manager", "Employee"}:
        return False, "Invalid role name."

    conn = get_rbac_db_connection()
    try:
        target = conn.execute(
            """
            SELECT u.id, u.username, u.is_active, r.name AS role_name
            FROM users u
            JOIN roles r ON r.id = u.role_id
            WHERE u.id = ?
            LIMIT 1
            """,
            (int(target_user_id),),
        ).fetchone()
        if not target:
            return False, "User not found."

        if str(target["role_name"]) == "Super Admin" and role_name != "Super Admin" and _active_super_admin_count(conn) <= 1:
            return False, "Cannot demote the last active Super Admin."

        role_id = _get_role_id(conn, role_name)
        conn.execute(
            "UPDATE users SET role_id = ?, updated_at = datetime('now') WHERE id = ?",
            (role_id, int(target_user_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "change_role",
            "users",
            int(target_user_id),
            json.dumps({"username": str(target["username"]), "from": str(target["role_name"]), "to": role_name}),
        )
        return True, "Role updated."
    finally:
        conn.close()


def create_task_record(
    actor_user_id: int,
    title: str,
    description: str,
    assigned_to: int | None,
    due_date: str | None = None,
    priority: str = "normal",
) -> tuple[bool, str]:
    if not can_user_create_task(int(actor_user_id)):
        return False, "Only Super Admin or Manager can create tasks."

    cleaned_title = str(title or "").strip()
    if not cleaned_title:
        return False, "Task title is required."

    valid_priorities = {"urgent", "high", "normal", "low"}
    cleaned_priority = str(priority or "normal").strip().lower()
    if cleaned_priority not in valid_priorities:
        cleaned_priority = "normal"

    cleaned_due_date: str | None = str(due_date or "").strip() or None

    conn = get_rbac_db_connection()
    try:
        assigned_user_id = int(assigned_to) if assigned_to is not None else None
        if assigned_user_id is not None:
            assigned_row = conn.execute(
                "SELECT id, is_active FROM users WHERE id = ? LIMIT 1",
                (assigned_user_id,),
            ).fetchone()
            if not assigned_row or int(assigned_row["is_active"]) != 1:
                return False, "Assigned user must be an active user."

        cur = conn.execute(
            """
            INSERT INTO tasks (title, description, status, created_by, assigned_to, due_date, priority, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                cleaned_title,
                str(description or "").strip() or None,
                int(actor_user_id),
                assigned_user_id,
                cleaned_due_date,
                cleaned_priority,
            ),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "create_task",
            "tasks",
            int(cur.lastrowid),
            json.dumps({"title": cleaned_title, "assigned_to": assigned_user_id, "priority": cleaned_priority}),
        )
        return True, "Task created."
    finally:
        conn.close()


def update_task_status(actor_user_id: int, task_id: int, status: str) -> tuple[bool, str]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"pending", "in-progress", "completed"}:
        return False, "Invalid status value."

    conn = get_rbac_db_connection()
    try:
        row = conn.execute("SELECT id, title FROM tasks WHERE id = ? LIMIT 1", (int(task_id),)).fetchone()
        if not row:
            return False, "Task not found."

        completed_at = "datetime('now')" if normalized_status == "completed" else "NULL"
        conn.execute(
            f"""
            UPDATE tasks
            SET status = ?,
                updated_at = datetime('now'),
                completed_at = {completed_at}
            WHERE id = ?
            """,
            (normalized_status, int(task_id)),
        )
        conn.commit()
        add_audit_log(
            actor_user_id,
            "update_task_status",
            "tasks",
            int(task_id),
            json.dumps({"status": normalized_status, "title": str(row["title"])}),
        )
        return True, "Task status updated."
    finally:
        conn.close()


def list_tasks(limit: int = 200, status_filter: str | None = None) -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        if status_filter and status_filter in {"pending", "in-progress", "completed"}:
            rows = conn.execute(
                """
                SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                       t.created_at, t.updated_at, t.completed_at,
                       creator.username AS created_by_username,
                       assignee.username AS assigned_to_username
                FROM tasks t
                JOIN users creator ON creator.id = t.created_by
                LEFT JOIN users assignee ON assignee.id = t.assigned_to
                WHERE t.status = ?
                ORDER BY
                    CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                    t.due_date ASC NULLS LAST,
                    t.id DESC
                LIMIT ?
                """,
                (status_filter, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT t.id, t.title, t.description, t.status, t.due_date, t.priority,
                       t.created_at, t.updated_at, t.completed_at,
                       creator.username AS created_by_username,
                       assignee.username AS assigned_to_username
                FROM tasks t
                JOIN users creator ON creator.id = t.created_by
                LEFT JOIN users assignee ON assignee.id = t.assigned_to
                ORDER BY
                    CASE t.status WHEN 'pending' THEN 1 WHEN 'in-progress' THEN 2 ELSE 3 END,
                    CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END,
                    t.due_date ASC NULLS LAST,
                    t.id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_audit_logs(limit: int = 300) -> list[dict[str, Any]]:
    conn = get_rbac_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.action, a.target_table, a.target_id, a.details, a.created_at,
                   u.username AS actor_username
            FROM audit_logs a
            JOIN users u ON u.id = a.actor_user_id
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


ADMIN_USERS_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>User Management — Dexter Ops</title>
  <style>
    :root{--accent:#ea580c;--edge:#d1d5db;--ink:#1f2937;--muted:#6b7280;--panel:#fff;--bg:#f3f4f6}
    *{box-sizing:border-box}
    body{font-family:'Segoe UI','Trebuchet MS',sans-serif;margin:0;padding:20px 24px;background:var(--bg);color:var(--ink)}
    h1{font-size:1.3rem;font-weight:700;margin:0 0 18px}
    form.row{background:var(--panel);border-radius:12px;padding:16px 18px;margin-bottom:18px;box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--edge);display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
    input,select{padding:8px 11px;border:1px solid var(--edge);border-radius:8px;font-size:.93rem;background:#fff;color:var(--ink)}
    input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px rgba(234,88,12,.15)}
    button[type=submit]{padding:8px 16px;border-radius:8px;border:none;cursor:pointer;font-size:.88rem;font-weight:600;background:var(--accent);color:#fff;transition:opacity .15s}
    button[type=submit]:hover{opacity:.88}
    .inline{display:inline-flex;gap:6px;align-items:center}
    .inline button[type=submit]{padding:5px 11px;font-size:.82rem;border-radius:6px;border:1px solid var(--edge);background:#fff;color:var(--ink)}
    .inline button[type=submit]:hover{background:var(--bg);opacity:1}
    .table-card{background:var(--panel);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--edge);overflow:hidden}
    table{width:100%;border-collapse:collapse;font-size:.9rem}
    th{text-align:left;padding:9px 12px;font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:2px solid var(--edge)}
    td{padding:10px 12px;border-bottom:1px solid var(--edge);vertical-align:middle}
    tr:last-child td{border-bottom:none}
    .pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.78rem;font-weight:600}
    .pill-sa{background:#dbeafe;color:#1e40af}
    .pill-mgr{background:#d1fae5;color:#065f46}
    .pill-emp{background:#f3f4f6;color:#374151}
    .pill-on{background:#dcfce7;color:#166534}
    .pill-off{background:#fee2e2;color:#991b1b}
    .msg{padding:9px 14px;border-radius:8px;margin-bottom:14px;font-size:.9rem;border:1px solid}
    .ok{background:#dcfce7;color:#166534;border-color:#bbf7d0}
    .err{background:#fee2e2;color:#991b1b;border-color:#fecaca}
  </style>
</head>
<body>
  <h1>User Management</h1>
  {% if message %}<div class=\"msg ok\">{{ message }}</div>{% endif %}
  {% if error %}<div class=\"msg err\">{{ error }}</div>{% endif %}

  <form method=\"post\" action=\"/admin/users/create\" class=\"row\">
    <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
    <input name=\"username\" placeholder=\"Username\" required />
    <input name=\"password\" placeholder=\"Password (min 8)\" type=\"password\" required />
    <select name=\"role_name\">
      <option>Employee</option>
      <option>Manager</option>
      <option>Super Admin</option>
    </select>
    <button type=\"submit\">Create User</button>
  </form>

  <div class="table-card">
  <table>
    <thead>
      <tr>
        <th>ID</th><th>Username</th><th>Role</th><th>Active</th><th>Last Login</th><th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {% for u in users %}
      <tr>
        <td>{{ u.id }}</td>
        <td>{{ u.username }}</td>
        <td>{% if u.role_name == 'Super Admin' %}<span class="pill pill-sa">Super Admin</span>{% elif u.role_name == 'Manager' %}<span class="pill pill-mgr">Manager</span>{% else %}<span class="pill pill-emp">Employee</span>{% endif %}</td>
        <td>{% if u.is_active %}<span class="pill pill-on">Active</span>{% else %}<span class="pill pill-off">Inactive</span>{% endif %}</td>
        <td>{{ u.last_login or '-' }}</td>
        <td>
          <form method=\"post\" action=\"/admin/users/{{ u.id }}/role\" class=\"inline\">
            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
            <select name=\"role_name\">
              <option {% if u.role_name == 'Employee' %}selected{% endif %}>Employee</option>
              <option {% if u.role_name == 'Manager' %}selected{% endif %}>Manager</option>
              <option {% if u.role_name == 'Super Admin' %}selected{% endif %}>Super Admin</option>
            </select>
            <button type=\"submit\">Set Role</button>
          </form>
          <form method=\"post\" action=\"/admin/users/{{ u.id }}/active\" class=\"inline\">
            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
            <input type=\"hidden\" name=\"is_active\" value=\"{{ 0 if u.is_active else 1 }}\" />
            <button type=\"submit\">{{ 'Deactivate' if u.is_active else 'Activate' }}</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  </div>
</body>
</html>
"""


ADMIN_TASKS_HTML = """
<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
<title>Operational Tasks — Dexter Ops</title>
<style>:root{--accent:#ea580c;--edge:#d1d5db;--ink:#1f2937;--muted:#6b7280;--panel:#fff;--bg:#f3f4f6;--ok:#166534;--warn:#854d0e}*{box-sizing:border-box}body{font-family:'Segoe UI','Trebuchet MS',sans-serif;margin:0;padding:20px 24px;background:var(--bg);color:var(--ink)}h1{font-size:1.3rem;font-weight:700;margin:0 0 12px}form.row{background:var(--panel);border-radius:12px;padding:16px 18px;margin-bottom:14px;box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--edge);display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}input,select{padding:8px 11px;border:1px solid var(--edge);border-radius:8px;font-size:.93rem;background:#fff;color:var(--ink)}input[type=date]{color-scheme:light}input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 2px rgba(234,88,12,.15)}button[type=submit]{padding:8px 16px;border-radius:8px;border:none;cursor:pointer;font-size:.88rem;font-weight:600;background:var(--accent);color:#fff;transition:opacity .15s}button[type=submit]:hover{opacity:.88}.tabs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}.tab{padding:6px 14px;border-radius:8px;border:1px solid var(--edge);background:#fff;color:var(--ink);font-size:.85rem;font-weight:600;cursor:pointer;text-decoration:none}.tab:hover{background:#f1f5f9}.tab.active{background:var(--accent);color:#fff;border-color:#c2410c}.table-card{background:var(--panel);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--edge);overflow:hidden}table{width:100%;border-collapse:collapse;font-size:.9rem}th{text-align:left;padding:9px 12px;font-weight:600;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:2px solid var(--edge)}td{padding:10px 12px;border-bottom:1px solid var(--edge);vertical-align:middle}tr:last-child td{border-bottom:none}.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.78rem;font-weight:600}.pill-pend{background:#fef9c3;color:#854d0e}.pill-prog{background:#dbeafe;color:#1e40af}.pill-done{background:#dcfce7;color:#166534}.pill-canc{background:#f3f4f6;color:var(--muted)}.pri-urgent{background:#fee2e2;color:#991b1b}.pri-high{background:#ffedd5;color:#9a3412}.pri-normal{background:#f3f4f6;color:var(--muted)}.pri-low{background:#f0fdf4;color:#166534}.msg{padding:9px 14px;border-radius:8px;margin-bottom:14px;font-size:.9rem;border:1px solid}.ok{background:#dcfce7;color:#166534;border-color:#bbf7d0}.err{background:#fee2e2;color:#991b1b;border-color:#fecaca}</style>
</head><body>
<h1>Operational Tasks</h1>
{% if message %}<div class=\"msg ok\">{{ message }}</div>{% endif %}
{% if error %}<div class=\"msg err\">{{ error }}</div>{% endif %}
<form method=\"post\" action=\"/admin/tasks/create\" class=\"row\">
  <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
  <input name=\"title\" placeholder=\"Task title\" required style=\"min-width:180px\" />
  <input name=\"description\" placeholder=\"Description\" style=\"min-width:160px\" />
  <select name=\"assigned_to\"><option value=\"\">Unassigned</option>{% for u in active_users %}<option value=\"{{ u.id }}\">{{ u.username }}</option>{% endfor %}</select>
  <select name=\"priority\"><option value=\"normal\" selected>Normal</option><option value=\"urgent\">Urgent</option><option value=\"high\">High</option><option value=\"low\">Low</option></select>
  <input type=\"date\" name=\"due_date\" title=\"Due date\" />
  <button type=\"submit\">Create Task</button>
</form>
<div class=\"tabs\">
  <a class=\"tab{% if not status_filter %} active{% endif %}\" href=\"/admin/tasks\">All</a>
  <a class=\"tab{% if status_filter == 'pending' %} active{% endif %}\" href=\"/admin/tasks?status=pending\">Pending</a>
  <a class=\"tab{% if status_filter == 'in-progress' %} active{% endif %}\" href=\"/admin/tasks?status=in-progress\">In Progress</a>
  <a class=\"tab{% if status_filter == 'completed' %} active{% endif %}\" href=\"/admin/tasks?status=completed\">Completed</a>
</div>
<div class=\"table-card\"><table><thead><tr><th>ID</th><th>Title</th><th>Priority</th><th>Status</th><th>Assigned To</th><th>Due</th><th>Created</th></tr></thead>
<tbody>{% for t in tasks %}<tr>
  <td style=\"color:var(--muted);font-size:.82rem\">{{ t.id }}</td>
  <td><strong>{{ t.title }}</strong>{% if t.description %}<br><small style=\"color:var(--muted)\">{{ t.description }}</small>{% endif %}</td>
  <td>{% if t.priority == 'urgent' %}<span class=\"pill pri-urgent\">Urgent</span>{% elif t.priority == 'high' %}<span class=\"pill pri-high\">High</span>{% elif t.priority == 'low' %}<span class=\"pill pri-low\">Low</span>{% else %}<span class=\"pill pri-normal\">Normal</span>{% endif %}</td>
  <td>{% if t.status == 'completed' %}<span class=\"pill pill-done\">Completed</span>{% elif t.status == 'in-progress' %}<span class=\"pill pill-prog\">In Progress</span>{% elif t.status == 'cancelled' %}<span class=\"pill pill-canc\">Cancelled</span>{% else %}<span class=\"pill pill-pend\">Pending</span>{% endif %}</td>
  <td>{{ t.assigned_to_username or '—' }}</td>
  <td style=\"color:var(--muted);font-size:.82rem;white-space:nowrap\">{{ t.due_date or '—' }}</td>
  <td style=\"color:var(--muted);font-size:.82rem\">{{ t.created_at[:10] if t.created_at else '—' }}</td>
</tr>{% endfor %}</tbody></table></div>
</body></html>
"""


ADMIN_AUDIT_HTML = """
<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
<title>Audit Logs — Dexter Ops</title>
<style>:root{--accent:#ea580c;--edge:#d1d5db;--ink:#1f2937;--muted:#6b7280;--panel:#fff;--bg:#f3f4f6}*{box-sizing:border-box}body{font-family:'Segoe UI','Trebuchet MS',sans-serif;margin:0;padding:20px 24px;background:var(--bg);color:var(--ink)}h1{font-size:1.3rem;font-weight:700;margin:0 0 18px}.table-card{background:var(--panel);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--edge);overflow:hidden}table{width:100%;border-collapse:collapse;font-size:.88rem}th{text-align:left;padding:9px 12px;font-weight:600;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:2px solid var(--edge)}td{padding:9px 12px;border-bottom:1px solid var(--edge);vertical-align:top}tr:last-child td{border-bottom:none}.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.76rem;font-weight:600}.pill-act{background:#ede9fe;color:#5b21b6}.mono{font-family:'Consolas','Courier New',monospace;font-size:.8rem;color:var(--muted)}</style>
</head><body>
<h1>Audit Logs</h1>
<div class="table-card"><table><thead><tr><th>ID</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th><th>At</th></tr></thead>
<tbody>{% for row in logs %}<tr><td style="color:var(--muted);font-size:.8rem">{{ row.id }}</td><td><strong>{{ row.actor_username }}</strong></td><td><span class="pill pill-act">{{ row.action }}</span></td><td class="mono">{{ row.target_table }}{% if row.target_id %}#{{ row.target_id }}{% endif %}</td><td style="max-width:260px;word-break:break-word;color:var(--muted);font-size:.82rem">{{ row.details or '—' }}</td><td style="color:var(--muted);font-size:.82rem;white-space:nowrap">{{ row.created_at }}</td></tr>{% endfor %}</tbody></table></div>
</body></html>
"""


PORTAL_APP_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\" />
    <title>{{ app_title }} - Dexter Ops</title>
    <style>
        :root {
            --accent:#ea580c;
            --accent2:#0f766e;
            --ink:#1f2937;
            --muted:#6b7280;
            --panel:#ffffff;
            --edge:#d1d5db;
            --bad:#991b1b;
        }
        * { box-sizing: border-box; }
        html, body { -webkit-text-size-adjust: 100%; }
        body {
            margin: 0;
            font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
            color: var(--ink);
            background: linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#eef2ff 100%);
            min-height: 100vh;
            min-height: 100dvh;
            -webkit-overflow-scrolling: touch;
            overflow-x: hidden;
        }
        .topbar {
            position: sticky;
            top: 0;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 11px 16px;
            border-bottom: 1px solid var(--edge);
            background: #ffffff;
            box-shadow: 0 1px 4px rgba(15,23,42,0.06);
        }
        .brand { font-size: 17px; font-weight: 800; color: #0f172a; }
        .brand-wrap { display: flex; align-items: center; gap: 9px; }
        .brand-logo { width: 26px; height: 26px; object-fit: contain; border-radius: 7px; background: #fff; border: 1px solid var(--edge); padding: 2px; }
        .nav { display: flex; gap: 7px; flex-wrap: wrap; }
        .nav a, .nav button {
            border: 1px solid var(--edge);
            background: #fff;
            color: var(--ink);
            border-radius: 10px;
            padding: 7px 12px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }
        .nav a:hover, .nav button:hover { background: #f1f5f9; }
        .nav .primary { background: var(--accent); color: #fff; border-color: #c2410c; }
        .nav .primary:hover { background: #c2410c; }
        .nav .secondary { background: var(--accent2); color: #fff; border-color: #0c5b55; }
        .nav button:disabled { opacity: 0.55; cursor: not-allowed; }
        .subbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--edge);
            background: #f9fafb;
            padding: 7px 16px;
            color: var(--muted);
            font-size: 12px;
        }
        .subbar a { color: var(--accent2); font-weight: 600; text-decoration: none; }
        .subbar a:hover { text-decoration: underline; }
        iframe {
            width: 100%;
            border: 0;
            background: #fff;
            display: block;
        }
        .toast-wrap { position:fixed; bottom:20px; right:20px; display:flex; flex-direction:column; gap:8px; z-index:9999; pointer-events:none; }
        .toast { background:#1f2937; color:#fff; border-radius:10px; padding:10px 16px; font-size:13px; font-weight:600; opacity:0; transform:translateY(10px); transition:opacity 0.2s,transform 0.2s; pointer-events:none; max-width:320px; }
        .toast.show { opacity:1; transform:translateY(0); }
        .toast.error { background:#991b1b; }
        .toast.ok { background:#166534; }
        @media (max-width: 700px) {
            .topbar { flex-wrap: wrap; gap: 8px; padding: 8px 10px; }
            .brand { font-size: 1rem; }
            .nav { gap: 4px; }
        }
    </style>
</head>
<body>
    <div class="topbar" id="topbar">
        <div class="brand-wrap">
            <img class="brand-logo" src="/branding/logo" alt="Dexter logo" />
            <div class="brand">{{ app_title }}</div>
        </div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/portal/productmix">ProductMix</a>
            <a href="/portal/ic3">IC3</a>
            <a href="/portal/managerapp">Daily Log</a>
            <button class="primary" id="btnRestart" onclick="doRestart(this)">Restart App</button>
            <a href="/auth/logout">Logout</a>
        </div>
    </div>
    <div class="subbar" id="subbar">
        <span>Embedded via Dexter Ops portal routing &mdash; {{ app_title }}</span>
        <a href="{{ raw_url }}" target="_blank" rel="noopener">Open Raw &rarr;</a>
    </div>
    <div class="toast-wrap" id="toastWrap"></div>
    <iframe id="appFrame" src="{{ raw_url }}"></iframe>
    <script>
        function showToast(msg, type) {
            var wrap = document.getElementById('toastWrap');
            var t = document.createElement('div');
            t.className = 'toast' + (type ? ' ' + type : '');
            t.textContent = msg;
            wrap.appendChild(t);
            requestAnimationFrame(function() { t.classList.add('show'); });
            setTimeout(function() {
                t.classList.remove('show');
                setTimeout(function() { t.remove(); }, 300);
            }, 3200);
        }
        function setFrameHeight() {
            var frame = document.getElementById('appFrame');
            if (!frame) return;
            var tb = document.getElementById('topbar');
            var sb = document.getElementById('subbar');
            var used = (tb ? tb.offsetHeight : 0) + (sb ? sb.offsetHeight : 0);
            var vh = window.innerHeight - used;
            var isMobile = window.innerWidth <= 820;
            if (isMobile) {
                // Disable iframe internal scroll so iOS can't trap touches inside it.
                frame.setAttribute('scrolling', 'no');
            } else {
                frame.removeAttribute('scrolling');
            }
            // Try to size the iframe to its content (same-origin), so the OUTER
            // page scrolls naturally on mobile instead of trapping touches
            // inside the iframe (which iOS rubber-bands back).
            try {
                var doc = frame.contentDocument || (frame.contentWindow && frame.contentWindow.document);
                if (doc && doc.body) {
                    var contentH = Math.max(
                        doc.body.scrollHeight,
                        doc.documentElement ? doc.documentElement.scrollHeight : 0
                    );
                    if (contentH && contentH > 50) {
                        frame.style.height = Math.max(contentH, isMobile ? 0 : vh) + 'px';
                        return;
                    }
                }
            } catch (e) { /* cross-origin or not ready */ }
            frame.style.height = vh + 'px';
        }
        setFrameHeight();
        window.addEventListener('resize', setFrameHeight);
        // Re-measure after the iframe loads and on a short interval to catch
        // dynamic content height changes inside the embedded app.
        (function() {
            var frame = document.getElementById('appFrame');
            var isMobile = window.matchMedia('(max-width: 820px)').matches;
            function injectMobileCss(doc) {
                if (!doc || doc.getElementById('__dexter_mobile_css')) return;
                var style = doc.createElement('style');
                style.id = '__dexter_mobile_css';
                style.textContent = [
                    '@media (max-width: 820px){',
                    '  html,body{height:auto!important;min-height:0!important;overflow:visible!important;-webkit-overflow-scrolling:auto!important;}',
                    '  .container,.wrap,.shell,.main,.tab-content,.tab-content.active,.viewer-pane,.page,.app-shell{overflow:visible!important;height:auto!important;max-height:none!important;min-height:0!important;}',
                    '  table{display:block;overflow-x:auto;max-width:100%;}',
                    '}'
                ].join('\\n');
                (doc.head || doc.documentElement).appendChild(style);
            }
            if (frame) {
                frame.addEventListener('load', function() {
                    try { injectMobileCss(frame.contentDocument); } catch (e) {}
                    setFrameHeight();
                    setTimeout(setFrameHeight, 300);
                    setTimeout(setFrameHeight, 1000);
                    try {
                        var doc = frame.contentDocument;
                        if (doc && window.ResizeObserver) {
                            var ro = new ResizeObserver(function() { setFrameHeight(); });
                            ro.observe(doc.documentElement);
                            if (doc.body) ro.observe(doc.body);
                        }
                        // Click-based SPA tab switches inside IC3 etc. — re-measure
                        if (doc) {
                            doc.addEventListener('click', function() {
                                setTimeout(setFrameHeight, 150);
                                setTimeout(setFrameHeight, 600);
                            }, true);
                        }
                    } catch (e) { /* cross-origin */ }
                });
            }
            setInterval(setFrameHeight, 1500);
        })();
        async function doRestart(btn) {
            btn.disabled = true;
            var orig = btn.textContent;
            btn.textContent = '...';
            try {
                var res = await fetch('/api/apps/{{ app_key }}/restart', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
                if (!res.ok) {
                    var txt = await res.text();
                    showToast('Restart failed: ' + txt, 'error');
                } else {
                    showToast('Restarting...', 'ok');
                    setTimeout(function() { window.location.reload(); }, 1400);
                }
            } catch (e) {
                showToast('Request error: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = orig;
            }
        }
    </script>
</body>
</html>
"""


FORGOT_PASSWORD_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
    <title>Reset Password — Dexter Ops</title>
    <style>
        :root{--accent:#ea580c;--accent-dark:#c2410c;--ink:#1f2937;--muted:#6b7280;--edge:#d1d5db;--panel:#fff;--danger:#991b1b;--ok:#166534}
        *{box-sizing:border-box}body{margin:0;font-family:'Segoe UI','Trebuchet MS',sans-serif;color:var(--ink);min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#fff7ed 100%);padding:24px 8px}
        .card{background:var(--panel);border:1.5px solid var(--edge);border-radius:18px;padding:30px 26px 24px;box-shadow:0 12px 40px rgba(15,23,42,.10);width:100%;max-width:400px}
        h2{margin:0 0 6px;font-size:1.5rem;font-weight:800;color:#0f172a}p{margin:0 0 16px;color:var(--muted);font-size:14px}
        label{display:block;margin:10px 0 5px;font-size:13px;font-weight:600;color:#374151}
        input{width:100%;padding:11px 13px;border:1px solid var(--edge);border-radius:10px;font-size:15px;outline:none;transition:border-color .15s}
        input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(234,88,12,.12)}
        button[type=submit]{margin-top:16px;width:100%;border:none;background:var(--accent);color:#fff;border-radius:10px;padding:12px 0;font-size:1rem;font-weight:700;cursor:pointer;transition:background .15s}
        button[type=submit]:hover{background:var(--accent-dark)}
        .msg{margin:12px 0 0;padding:9px 14px;border-radius:8px;font-size:.9rem;border:1px solid}
        .ok-msg{background:#dcfce7;color:var(--ok);border-color:#bbf7d0}
        .err-msg{background:#fee2e2;color:var(--danger);border-color:#fecaca}
        .reset-url{word-break:break-all;font-family:monospace;font-size:.85rem;background:#f1f5f9;padding:10px 12px;border-radius:8px;margin-top:10px;border:1px solid var(--edge)}
        .links{margin-top:14px;font-size:13px;color:var(--muted);text-align:center}
        .links a{color:var(--accent);text-decoration:underline;font-weight:600}
    </style>
</head>
<body>
    <div class=\"card\">
        <h2>Forgot Password</h2>
        <p>Enter your username to generate a password reset link.</p>
        {% if reset_url %}
        <div class=\"msg ok-msg\">Reset link generated. Share this link with the user (it expires in 1 hour):</div>
        <div class=\"reset-url\">{{ reset_url }}</div>
        {% else %}
        <form method=\"post\" action=\"/auth/forgot-password\">
            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
            <label>Username</label>
            <input type=\"text\" name=\"username\" required autofocus autocomplete=\"username\" />
            <button type=\"submit\">Generate Reset Link</button>
            {% if error %}<div class=\"msg err-msg\">{{ error }}</div>{% endif %}
        </form>
        {% endif %}
        <div class=\"links\"><a href=\"/auth/login\">Back to Sign In</a></div>
    </div>
</body>
</html>
"""


RESET_PASSWORD_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
    <title>Set New Password — Dexter Ops</title>
    <style>
        :root{--accent:#ea580c;--accent-dark:#c2410c;--ink:#1f2937;--muted:#6b7280;--edge:#d1d5db;--panel:#fff;--danger:#991b1b;--ok:#166534}
        *{box-sizing:border-box}body{margin:0;font-family:'Segoe UI','Trebuchet MS',sans-serif;color:var(--ink);min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#fff7ed 100%);padding:24px 8px}
        .card{background:var(--panel);border:1.5px solid var(--edge);border-radius:18px;padding:30px 26px 24px;box-shadow:0 12px 40px rgba(15,23,42,.10);width:100%;max-width:400px}
        h2{margin:0 0 6px;font-size:1.5rem;font-weight:800;color:#0f172a}p{margin:0 0 16px;color:var(--muted);font-size:14px}
        label{display:block;margin:10px 0 5px;font-size:13px;font-weight:600;color:#374151}
        input{width:100%;padding:11px 13px;border:1px solid var(--edge);border-radius:10px;font-size:15px;outline:none;transition:border-color .15s}
        input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(234,88,12,.12)}
        button[type=submit]{margin-top:16px;width:100%;border:none;background:var(--accent);color:#fff;border-radius:10px;padding:12px 0;font-size:1rem;font-weight:700;cursor:pointer;transition:background .15s}
        button[type=submit]:hover{background:var(--accent-dark)}
        .msg{margin:10px 0 0;padding:9px 14px;border-radius:8px;font-size:.9rem;border:1px solid}
        .ok-msg{background:#dcfce7;color:var(--ok);border-color:#bbf7d0}
        .err-msg{background:#fee2e2;color:var(--danger);border-color:#fecaca}
        .links{margin-top:14px;font-size:13px;color:var(--muted);text-align:center}
        .links a{color:var(--accent);text-decoration:underline;font-weight:600}
    </style>
</head>
<body>
    <div class=\"card\">
        <h2>Set New Password</h2>
        <p>Enter a new password for your account.</p>
        {% if done %}
        <div class=\"msg ok-msg\">Password updated. You can now sign in.</div>
        <div class=\"links\"><a href=\"/auth/login\">Sign In</a></div>
        {% else %}
        <form method=\"post\">
            <input type=\"hidden\" name=\"csrf_token\" value=\"{{ csrf_token() }}\" />
            <label>New Password</label>
            <input type=\"password\" name=\"password\" required autocomplete=\"new-password\" />
            <label>Confirm Password</label>
            <input type=\"password\" name=\"confirm\" required autocomplete=\"new-password\" />
            <button type=\"submit\">Update Password</button>
            {% if error %}<div class=\"msg err-msg\">{{ error }}</div>{% endif %}
        </form>
        <div class=\"links\"><a href=\"/auth/login\">Back to Sign In</a></div>
        {% endif %}
    </div>
</body>
</html>
"""


LOGIN_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
    <title>Dexter Ops &mdash; Sign In</title>
    <style>
        :root {
            --accent:#ea580c;
            --accent-dark:#c2410c;
            --accent2:#0f766e;
            --ink:#1f2937;
            --muted:#6b7280;
            --edge:#d1d5db;
            --panel:#ffffff;
            --danger:#991b1b;
        }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: 'Segoe UI', 'Trebuchet MS', sans-serif; color: var(--ink); }
        .wrap {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px 8px;
            background: linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#fff7ed 100%);
        }
        .container {
            display: flex;
            flex-direction: row;
            gap: 40px;
            width: 100%;
            max-width: 900px;
            align-items: center;
            justify-content: center;
        }
        .marketing {
            flex: 1 1 0;
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            justify-content: center;
            padding: 32px 0;
        }
        .logo {
            width: 80px;
            height: 80px;
            margin-bottom: 18px;
            object-fit: contain;
            border-radius: 14px;
            border: 1px solid var(--edge);
            background: #fff;
            padding: 5px;
        }
        .hero-title {
            font-size: 2.3rem;
            font-weight: 900;
            margin: 0 0 10px;
            color: #0f172a;
            letter-spacing: 0.3px;
        }
        .hero-accent { color: var(--accent); }
        .hero-tagline {
            font-size: 1.1rem;
            color: var(--muted);
            margin-bottom: 20px;
            line-height: 1.5;
        }
        .features { list-style: none; padding: 0; margin: 0 0 20px; }
        .features li {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 0.97rem;
            margin-bottom: 10px;
            color: var(--ink);
        }
        .features svg { width: 20px; height: 20px; color: var(--accent); flex-shrink: 0; }
        .contact-link { font-size: 0.9rem; color: var(--accent2); text-decoration: underline; }
        .card {
            flex: 1 1 0;
            min-width: 0;
            max-width: 400px;
            background: var(--panel);
            border: 1.5px solid var(--edge);
            border-radius: 18px;
            padding: 30px 26px 24px;
            box-shadow: 0 12px 40px rgba(15,23,42,0.10);
            display: flex;
            flex-direction: column;
            align-items: stretch;
        }
        .card h2 { margin: 0 0 6px; font-size: 1.65rem; font-weight: 800; color: #0f172a; }
        .card p { margin: 0 0 18px; color: var(--muted); font-size: 14px; }
        label { display: block; margin: 10px 0 5px; font-size: 13px; font-weight: 600; color: #374151; }
        input[type=text], input[type=password] {
            width: 100%;
            padding: 11px 13px;
            border: 1px solid var(--edge);
            border-radius: 10px;
            font-size: 15px;
            outline: none;
            transition: border-color 0.15s;
        }
        input[type=text]:focus, input[type=password]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(234,88,12,0.12); }
        .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
        .check { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--muted); cursor: pointer; }
        .check input { width: auto; margin: 0; cursor: pointer; }
        button[type=submit] {
            margin-top: 18px;
            width: 100%;
            border: none;
            background: var(--accent);
            color: #fff;
            border-radius: 10px;
            padding: 12px 0;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.15s;
            letter-spacing: 0.2px;
        }
        button[type=submit]:hover { background: var(--accent-dark); }
        .error { margin: 10px 0 0; color: var(--danger); font-size: 13px; font-weight: 600; }
        .links { margin-top: 14px; font-size: 13px; color: var(--muted); text-align: center; }
        .links a { color: var(--accent); text-decoration: underline; font-weight: 600; }
        @media (max-width: 860px) {
            .container { flex-direction: column; gap: 20px; align-items: stretch; }
            .marketing, .card { max-width: 100%; }
        }
        @media (max-width: 520px) {
            .wrap { padding: 10px 4px; }
            .hero-title { font-size: 1.5rem; }
            .card { padding: 20px 12px 16px; border-radius: 12px; }
        }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="container">
            <div class="marketing">
                <img class="logo" src="/branding/logo" alt="Dexter Ops logo" />
                <div class="hero-title">Dexter <span class="hero-accent">Assistant</span></div>
                <div class="hero-tagline">The all-in-one operations platform<br>built for restaurant teams.</div>
                <ul class="features">
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Inventory Control — track invoices, orders &amp; stock levels in real time</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Product Mix &amp; Production Reports — upload sales data and plan production by location</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Daily Log — log cash, labor and shift notes from any device</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Live dashboard — top sellers, open tasks and app health at a glance</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Role-based access for owners, managers &amp; employees — works on any device</li>
                </ul>
                <a class="contact-link" href="mailto:info@dexterassist.com">Contact us / Learn more</a>
            </div>
            <form class="card" method="post" action="{{ action_url }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
                <h2>Sign In</h2>
                <p>Access your dashboard and manage your apps.</p>
                <label>Username</label>
                <input id="login-username" type="text" name="username" required autofocus autocomplete="username" />
                <label>Password</label>
                <input id="login-password" type="password" name="password" required autocomplete="current-password" />
                <div class="row">
                    <label class="check"><input id="show-password" type="checkbox" /> Show password</label>
                    <label class="check"><input id="save-password" type="checkbox" /> Remember username</label>
                </div>
                <button type="submit">Sign In</button>
                {% if error %}<div class="error">{{ error }}</div>{% endif %}
                <div class="links">No account yet? <a href="{{ register_url }}{% if next_path %}?next={{ next_path }}{% endif %}">Create one</a> &bull; <a href="/auth/forgot-password">Forgot password?</a></div>
            </form>
        </div>
    </div>
    <script>
        (function () {
            var usernameInput = document.getElementById('login-username');
            var passwordInput = document.getElementById('login-password');
            var showPassword = document.getElementById('show-password');
            var savePassword = document.getElementById('save-password');
            var storageKey = 'dexterAssistantLogin';
            try {
                var saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
                if (saved && typeof saved === 'object') {
                    if (typeof saved.username === 'string') usernameInput.value = saved.username;
                    showPassword.checked = !!saved.showPassword;
                    savePassword.checked = !!saved.savePassword;
                    if (showPassword.checked) passwordInput.type = 'text';
                }
            } catch (e) {}
            showPassword.addEventListener('change', function() {
                passwordInput.type = showPassword.checked ? 'text' : 'password';
            });
            document.querySelector('form.card').addEventListener('submit', function() {
                if (savePassword.checked) {
                    localStorage.setItem(storageKey, JSON.stringify({
                        username: usernameInput.value,
                        showPassword: showPassword.checked,
                        savePassword: true
                    }));
                } else {
                    localStorage.removeItem(storageKey);
                }
            });
        })();
    </script>
</body>
</html>
"""


REGISTER_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Dexter Ops &mdash; Create Account</title>
    <style>
        :root {
            --accent:#ea580c;
            --accent-dark:#c2410c;
            --accent2:#0f766e;
            --ink:#1f2937;
            --muted:#6b7280;
            --edge:#d1d5db;
            --panel:#ffffff;
            --danger:#991b1b;
        }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: 'Segoe UI', 'Trebuchet MS', sans-serif; color: var(--ink); }
        .wrap {
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 24px 8px;
            background: linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#fff7ed 100%);
        }
        .card {
            width: 100%;
            max-width: 460px;
            background: var(--panel);
            border: 1.5px solid var(--edge);
            border-radius: 18px;
            padding: 28px 26px 22px;
            box-shadow: 0 12px 40px rgba(15,23,42,0.10);
        }
        .brand-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
        .brand-logo { width: 34px; height: 34px; object-fit: contain; border-radius: 8px; background: #fff; border: 1px solid var(--edge); padding: 2px; }
        h1 { margin: 0; font-size: 1.7rem; font-weight: 800; color: #0f172a; }
        p { margin: 0 0 18px; color: var(--muted); font-size: 14px; }
        label { display: block; margin: 10px 0 5px; font-size: 13px; font-weight: 600; color: #374151; }
        input[type=text], input[type=password] {
            width: 100%;
            padding: 11px 13px;
            border: 1px solid var(--edge);
            border-radius: 10px;
            font-size: 15px;
            outline: none;
            transition: border-color 0.15s;
        }
        input[type=text]:focus, input[type=password]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(234,88,12,0.12); }
        .row { display: flex; align-items: center; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
        .check { display: flex; align-items: center; gap: 7px; font-size: 13px; color: var(--muted); cursor: pointer; }
        .check input { width: auto; margin: 0; cursor: pointer; }
        button[type=submit] {
            margin-top: 18px;
            width: 100%;
            border: none;
            background: var(--accent);
            color: #fff;
            border-radius: 10px;
            padding: 12px 0;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.15s;
        }
        button[type=submit]:hover { background: var(--accent-dark); }
        .error { margin: 10px 0 0; color: var(--danger); font-size: 13px; font-weight: 600; }
        .links { margin-top: 14px; font-size: 13px; color: var(--muted); }
        .links a { color: var(--accent); text-decoration: underline; font-weight: 600; }
        @media (max-width: 520px) {
            .wrap { padding: 10px 4px; }
            .card { padding: 20px 12px 16px; border-radius: 12px; }
        }
    </style>
</head>
<body>
    <div class="wrap">
        <form class="card" method="post" action="{{ action_url }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
            <div class="brand-head">
                <img class="brand-logo" src="/branding/logo" alt="Dexter logo" />
                <h1>Create Account</h1>
            </div>
            <p>Create your Dexter Ops account.</p>
            <label>Username</label>
            <input type="text" name="username" required minlength="3" autofocus autocomplete="username" />
            <label>Password</label>
            <input id="register-password" type="password" name="password" required minlength="8" autocomplete="new-password" />
            <label>Confirm Password</label>
            <input id="register-confirm-password" type="password" name="confirm_password" required minlength="8" autocomplete="new-password" />
            <div class="row">
                <label class="check"><input id="register-show-password" type="checkbox" /> Show password</label>
            </div>
            <button type="submit">Create Account</button>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <div class="links">Already have an account? <a href="{{ login_url }}{% if next_path %}?next={{ next_path }}{% endif %}">Sign in</a></div>
        </form>
    </div>
    <script>
        (function () {
            var showPassword = document.getElementById('register-show-password');
            var passwordInput = document.getElementById('register-password');
            var confirmInput = document.getElementById('register-confirm-password');
            showPassword.addEventListener('change', function() {
                var t = showPassword.checked ? 'text' : 'password';
                passwordInput.type = t;
                confirmInput.type = t;
            });
        })();
    </script>
</body>
</html>
"""


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_auth_users() -> dict[str, Any]:
    if not AUTH_USERS_PATH.exists():
        return {}
    try:
        with AUTH_USERS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def ensure_default_admin_user() -> None:
    admin_username = os.environ.get("DEXTER_ADMIN_USER", "").strip()
    admin_password = os.environ.get("DEXTER_ADMIN_PASS", "").strip()
    if not admin_username or not admin_password:
        print(
            "[dexter] WARNING: DEXTER_ADMIN_USER / DEXTER_ADMIN_PASS env vars not set. "
            "Default admin account will NOT be created automatically.",
            file=sys.stderr,
        )
        return
    users = load_auth_users()
    current = users.get(admin_username)
    if not current or not current.get("is_admin"):
        users[admin_username] = {
            "password_hash": generate_password_hash(admin_password),
            "created_at": current.get("created_at") if isinstance(current, dict) else datetime.now().isoformat(timespec="seconds"),
            "last_login": current.get("last_login") if isinstance(current, dict) else None,
            "is_admin": True,
            "email": admin_username,
        }
        save_auth_users(users)


def save_auth_users(users: dict[str, Any]) -> None:
    with AUTH_USERS_PATH.open("w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def get_next_path(default_path: str = "/admin") -> str:
    next_path = (request.args.get("next") or request.form.get("next") or "").strip()
    if not next_path.startswith("/") or next_path.startswith("//"):
        return default_path
    return next_path


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if session.get(SESSION_USER_KEY):
            return view_func(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": "Authentication required"}), 401
        return redirect(url_for("auth_login", next=request.full_path.rstrip("?")))

    return wrapped


def is_port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def is_port_free(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def open_url_in_chrome(url: str) -> bool:
    """Best-effort open in Google Chrome, with sensible fallbacks."""
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]

    for chrome_exe in chrome_candidates:
        if chrome_exe and chrome_exe.exists():
            try:
                subprocess.Popen([str(chrome_exe), url])
                return True
            except Exception:
                pass

    # Fall back to whatever the system maps as "chrome" on PATH.
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "chrome", url])
        return True
    except Exception:
        pass

    # Final fallback: open in default system browser.
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def check_health(url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(url, timeout=timeout):
            return True
    except (URLError, TimeoutError, ValueError):
        return False


class AppManager:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[Any] | None] = {
            name: None for name in config["apps"].keys()
        }
        RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _app_cfg(self, name: str) -> dict[str, Any]:
        name = self.resolve_name(name)
        if not name:
            raise KeyError(f"Unknown app: {name}")
        return self.config["apps"][name]

    def resolve_name(self, name: str) -> str | None:
        candidate = (name or "").strip().lower()
        if not candidate:
            return None
        if candidate in self.config["apps"]:
            return candidate

        # Backward-compatible app key aliases.
        alias_pairs = {
            "manager": "managerapp",
            "managerapp": "manager",
        }
        alias = alias_pairs.get(candidate)
        if alias and alias in self.config["apps"]:
            return alias
        return None

    def _parse_host_port(self, base_url: str) -> tuple[str, int]:
        parts = base_url.replace("http://", "").replace("https://", "").split("/")[0]
        host, port = parts.split(":", 1)
        return host, int(port)

    def _log_file(self, name: str) -> Path:
        return RUNTIME_LOG_DIR / f"{name}.log"

    def _tail_log(self, name: str, max_lines: int = 40) -> str:
        log_file = self._log_file(name)
        if not log_file.exists():
            return ""
        with log_file.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])

    def _rotate_log(self, name: str) -> None:
        log_file = self._log_file(name)
        if log_file.exists() and log_file.stat().st_size > 200 * 1024:
            old = log_file.with_suffix(".log.old")
            try:
                log_file.rename(old)
            except OSError:
                pass

    def status(self) -> dict[str, Any]:
        # Snapshot process states under the lock — do NOT call check_health() under lock
        # because HTTP calls may block and prevent start/stop from acquiring the lock.
        snapshots: dict[str, dict[str, Any]] = {}
        with self._lock:
            for name, app in self.config["apps"].items():
                proc = self._procs.get(name)
                running = proc is not None and proc.poll() is None
                snapshots[name] = {
                    "display_name": app["display_name"],
                    "base_url": app["base_url"],
                    "health_url": urljoin(app["base_url"], app.get("health_path", "/")),
                    "running": running,
                    "pid": proc.pid if running else None,
                    "log_tail": self._tail_log(name),
                }

        # Health checks outside the lock — safe to block here
        out: dict[str, Any] = {}
        for name, snap in snapshots.items():
            healthy = check_health(snap["health_url"]) if snap["running"] else False
            out[name] = {
                "display_name": snap["display_name"],
                "base_url": snap["base_url"],
                "running": snap["running"],
                "healthy": healthy,
                "pid": snap["pid"],
                "log_tail": snap["log_tail"],
            }
        return out

    def preflight(self) -> dict[str, Any]:
        issues: dict[str, list[str]] = {}
        for name, app in self.config["apps"].items():
            app_issues: list[str] = []
            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not cwd.exists():
                app_issues.append(f"Missing folder: {cwd}")
            if not entry.exists():
                app_issues.append(f"Missing entrypoint: {entry}")
            host, port = self._parse_host_port(app["base_url"])
            if not is_port_open(host, port) and not is_port_free(host, port):
                app_issues.append(f"Port unavailable: {host}:{port}")
            if app_issues:
                issues[name] = app_issues
        return {"ok": len(issues) == 0, "issues": issues}

    def start(self, name: str) -> dict[str, Any]:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return {"ok": False, "message": f"Unknown app: {name}"}

        with self._lock:
            app = self._app_cfg(resolved_name)
            proc = self._procs.get(resolved_name)
            if proc is not None and proc.poll() is None:
                return {"ok": True, "message": f"{resolved_name} already running"}

            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not entry.exists():
                return {"ok": False, "message": f"Entrypoint not found: {entry}"}

            host, port = self._parse_host_port(app["base_url"])
            if not is_port_open(host, port) and not is_port_free(host, port):
                return {"ok": False, "message": f"Port in use by another process: {host}:{port}"}

            env = os.environ.copy()
            env.update(app.get("env", {}))
            log_file = self._log_file(resolved_name)
            self._rotate_log(resolved_name)
            with log_file.open("a", encoding="utf-8") as lf:
                lf.write(f"\n=== START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

            stdout_stream = log_file.open("a", encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(entry)],
                cwd=str(cwd),
                env=env,
                stdout=stdout_stream,
                stderr=subprocess.STDOUT,
            )
            self._procs[resolved_name] = proc
            return {"ok": True, "message": f"Started {resolved_name}", "pid": proc.pid}

    def stop(self, name: str) -> dict[str, Any]:
        resolved_name = self.resolve_name(name)
        if not resolved_name:
            return {"ok": False, "message": f"Unknown app: {name}"}

        with self._lock:
            proc = self._procs.get(resolved_name)
            if proc is None or proc.poll() is not None:
                self._procs[resolved_name] = None
                return {"ok": True, "message": f"{resolved_name} already stopped"}

            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self._procs[resolved_name] = None
            return {"ok": True, "message": f"Stopped {resolved_name}"}

    def restart(self, name: str) -> dict[str, Any]:
        self.stop(name)
        return self.start(name)

    def start_all(self) -> dict[str, Any]:
        preflight = self.preflight()
        if not preflight["ok"]:
            return {"ok": False, "message": "Preflight failed", "preflight": preflight}

        results = {name: self.start(name) for name in self.config["apps"].keys()}
        return {"ok": True, "results": results}

    def stop_all(self) -> dict[str, Any]:
        results = {name: self.stop(name) for name in self.config["apps"].keys()}
        return {"ok": True, "results": results}

    def start_watchdog(self, interval: int = 30) -> None:
        """Start a daemon thread that restarts crashed apps every `interval` seconds."""

        def _watch() -> None:
            while True:
                time.sleep(interval)
                for name in list(self.config["apps"].keys()):
                    proc = self._procs.get(name)
                    if proc is not None and proc.poll() is not None:
                        print(
                            f"[dexter watchdog] '{name}' has exited (rc={proc.returncode}). Restarting…",
                            file=sys.stderr,
                        )
                        try:
                            self.start(name)
                        except Exception as exc:  # noqa: BLE001
                            print(
                                f"[dexter watchdog] Failed to restart '{name}': {exc}",
                                file=sys.stderr,
                            )

        t = threading.Thread(target=_watch, name="dexter-watchdog", daemon=True)
        t.start()
        print("[dexter watchdog] Started — checking every %ds." % interval, file=sys.stderr)


CONFIG = load_config()
MANAGER = AppManager(CONFIG)
app = Flask(__name__, static_folder=None)
_secret = os.environ.get("DEXTER_SECRET_KEY") or os.environ.get("SECRET_KEY")
if not _secret:
    _secret = os.urandom(32)
    print(
        "[dexter] WARNING: DEXTER_SECRET_KEY env var not set. "
        "Using a random secret — all sessions will be invalidated on restart.",
        file=sys.stderr,
    )
app.secret_key = _secret
app.config["WTF_CSRF_SECRET_KEY"] = _secret
_session_hours = int(CONFIG.get("front_door", {}).get("session_hours", 8))
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=_session_hours)
csrf = CSRFProtect(app)


# ----- Dexter UI brand injection -------------------------------------------
# Serve canonical Dexter UI assets (tokens.css/components.css/theme.js/brand)
# and splice the brand <head>/<body> tags into every HTML response so the
# launcher matches the rest of the Dexter Assistant suite (PM-DB / Manager
# App / IC3). See Tools\dexter_ui\sync_dexter_ui.ps1 for the canonical source.
_DEXTER_UI_DIR = ROOT / "dexter-ui"


def _dexter_ui_static(filename: str):
    return send_file(_DEXTER_UI_DIR / filename, max_age=3600)


def _dexter_ui_brand(filename: str):
    return send_file(_DEXTER_UI_DIR / "brand" / filename, max_age=3600)


if _DEXTER_UI_DIR.exists():
    app.add_url_rule(
        "/dexter-ui/<path:filename>",
        endpoint="_dexter_ui_static",
        view_func=_dexter_ui_static,
    )
    app.add_url_rule(
        "/dexter-ui/brand/<path:filename>",
        endpoint="_dexter_ui_brand",
        view_func=_dexter_ui_brand,
    )

_DEXTER_UI_HEAD = (
    '<meta name="theme-color" content="#22427A">'
    '<link rel="icon" type="image/x-icon" href="/dexter-ui/brand/favicon.ico">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/dexter-ui/brand/favicon-32.png">'
    '<link rel="apple-touch-icon" sizes="180x180" href="/dexter-ui/brand/apple-touch-icon.png">'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
    '<link rel="stylesheet" href="/dexter-ui/tokens.css">'
    '<link rel="stylesheet" href="/dexter-ui/components.css">'
    "<style>"
    "body{font-family:var(--dx-font-sans)!important;background:var(--dx-bg)!important;color:var(--dx-text)!important;}"
    ".navbar,header.navbar,nav.navbar{background:var(--dx-primary)!important;}"
    ".navbar-brand,.navbar a,.navbar .nav-link{color:var(--dx-primary-contrast)!important;}"
    ".btn-primary{background:var(--dx-primary)!important;border-color:var(--dx-primary)!important;color:var(--dx-primary-contrast)!important;}"
    ".btn-primary:hover{background:var(--dx-navy-2)!important;border-color:var(--dx-navy-2)!important;}"
    ".card,.panel,.box,.modal-content{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
    ".form-control,.form-select,input,select,textarea{background:var(--dx-surface)!important;color:var(--dx-text)!important;border-color:var(--dx-border-soft)!important;}"
    "</style>"
)
_DEXTER_UI_BODY = (
    '<script src="/dexter-ui/theme.js" defer></script>'
    '<div class="dx-version-badge" aria-hidden="true">Dexter · Launcher · v0.9-demo</div>'
)
_DEXTER_UI_MARKER = "__dexter_ui_installed"


@app.after_request
def _inject_dexter_ui(response: Response) -> Response:
    content_type = (response.content_type or "").lower()
    if "text/html" not in content_type:
        return response
    if response.direct_passthrough:
        response.direct_passthrough = False
    try:
        body = response.get_data(as_text=True)
    except UnicodeDecodeError:
        return response
    if _DEXTER_UI_MARKER in body:
        return response
    if "</head>" not in body and "</body>" not in body:
        return response

    updated = body
    if "</head>" in updated:
        updated = updated.replace(
            "</head>",
            _DEXTER_UI_HEAD + f'<meta name="dexter-ui" content="1" data-{_DEXTER_UI_MARKER}="1"></head>',
            1,
        )
    else:
        updated = _DEXTER_UI_HEAD + updated
    if "</body>" in updated:
        updated = updated.replace("</body>", _DEXTER_UI_BODY + "</body>", 1)
    else:
        updated = updated + _DEXTER_UI_BODY

    response.set_data(updated)
    if "Content-Length" in response.headers:
        response.headers["Content-Length"] = str(len(response.get_data()))
    return response
# ----- /Dexter UI brand injection -------------------------------------------


def _rate_limit_key() -> str:
    """Rate-limit key aware of proxy headers.

    Prefer the forwarded user identity when present; fall back to IP.
    """
    dexter_user = (request.headers.get("X-Dexter-User") or "").strip().lower()
    if dexter_user:
        return f"dexter-user:{dexter_user}"
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded_for:
        return f"ip:{forwarded_for}"
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=_rate_limit_key,
    app=app,
    default_limits=[],
)

initialize_rbac_db()
migrate_legacy_json_users_to_sqlite()
migrate_add_task_fields_v1()
migrate_add_password_reset_fields_v1()
ensure_default_super_admin_user()


@app.before_request
def require_auth_for_protected_routes() -> Response | None:
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/auth/forgot-password",
        "/auth/reset-password/",
        "/branding/logo",
        "/dexter-ui/",
        "/favicon.ico",
        "/api/health",
    )
    if request.path.startswith(public_prefixes):
        return None
    if session.get(SESSION_USER_KEY):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": "Authentication required"}), 401
    return redirect(url_for("auth_login", next=request.full_path.rstrip("?")))


@app.route("/auth/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def auth_login() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(get_next_path("/"))

    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key, user = find_auth_user(username)
        if user and int(user.get("is_active", 1)) == 1 and check_password_hash(str(user.get("password_hash", "")), password):
            update_user_last_login(int(user["id"]))
            role_name = str(user.get("role_name") or "Employee")
            session[SESSION_USER_KEY] = {
                "username": key or username,
                "user_id": int(user["id"]),
                "role_name": role_name,
                "is_admin": role_name == "Super Admin",
                "email": key or username,
            }
            session.permanent = True
            if role_name in ("Super Admin", "Manager"):
                MANAGER.start_all()
            return redirect(get_next_path("/"))
        error = "Invalid username or password."

    return Response(
        render_template_string(
            LOGIN_HTML,
            error=error,
            next_path=request.args.get("next", ""),
            action_url=url_for("auth_login"),
            register_url=url_for("auth_register"),
        )
    )


@app.route("/auth/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def auth_register() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(get_next_path("/"))

    if not CONFIG.get("front_door", {}).get("registration_open", False):
        return Response(
            render_template_string(
                REGISTER_HTML,
                error="Self-registration is currently disabled. Contact your administrator.",
                next_path="",
                action_url=url_for("auth_register"),
                login_url=url_for("auth_login"),
            )
        )

    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if len(username) < 3:
            error = "Username must be at least 3 characters."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            conn = get_rbac_db_connection()
            try:
                existing = conn.execute(
                    "SELECT id FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
                    (username,),
                ).fetchone()
                if existing:
                    error = "Username already exists."
                else:
                    employee_role_id = _get_role_id(conn, "Employee")
                    cur = conn.execute(
                        """
                        INSERT INTO users (username, password_hash, role_id, is_active, created_at, updated_at)
                        VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
                        """,
                        (username, generate_password_hash(password), employee_role_id),
                    )
                    conn.commit()
                    session[SESSION_USER_KEY] = {
                        "username": username,
                        "user_id": int(cur.lastrowid),
                        "role_name": "Employee",
                        "is_admin": False,
                        "email": username,
                    }
                    session.permanent = True
                    return redirect(get_next_path("/"))
            finally:
                conn.close()

    return Response(
        render_template_string(
            REGISTER_HTML,
            error=error,
            next_path=request.args.get("next", ""),
            action_url=url_for("auth_register"),
            login_url=url_for("auth_login"),
        )
    )


@app.route("/auth/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def auth_forgot_password() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect("/")

    error = ""
    reset_url = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        if not username:
            error = "Please enter your username."
        else:
            conn = get_rbac_db_connection()
            try:
                row = conn.execute(
                    "SELECT id FROM users WHERE LOWER(username) = LOWER(?) AND is_active = 1 LIMIT 1",
                    (username,),
                ).fetchone()
                if row:
                    token = secrets.token_urlsafe(32)
                    expires = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
                    conn.execute(
                        "UPDATE users SET password_reset_token = ?, password_reset_expires = ? WHERE id = ?",
                        (token, expires, int(row["id"])),
                    )
                    conn.commit()
                    base_url = request.host_url.rstrip("/")
                    reset_url = f"{base_url}/auth/reset-password/{token}"
                else:
                    # Don't reveal if username exists — show a generic success look
                    error = "If that username exists, a reset link has been generated. Ask an admin."
            finally:
                conn.close()

    return Response(
        render_template_string(
            FORGOT_PASSWORD_HTML,
            error=error,
            reset_url=reset_url,
        )
    )


@app.route("/auth/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def auth_reset_password(token: str) -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect("/")

    token = str(token or "").strip()
    error = ""
    done = False

    conn = get_rbac_db_connection()
    try:
        row = conn.execute(
            """
            SELECT id, password_reset_expires FROM users
            WHERE password_reset_token = ? AND is_active = 1
            LIMIT 1
            """,
            (token,),
        ).fetchone()

        if not row:
            return Response(
                render_template_string(RESET_PASSWORD_HTML, error="Invalid or expired reset link.", done=False)
            )

        expires_str = str(row["password_reset_expires"] or "")
        try:
            expires_dt = datetime.fromisoformat(expires_str)
        except ValueError:
            expires_dt = datetime.min

        if datetime.now() > expires_dt:
            conn.execute(
                "UPDATE users SET password_reset_token = NULL, password_reset_expires = NULL WHERE id = ?",
                (int(row["id"]),),
            )
            conn.commit()
            return Response(
                render_template_string(RESET_PASSWORD_HTML, error="Reset link has expired. Please request a new one.", done=False)
            )

        if request.method == "POST":
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""
            if len(password) < 8:
                error = "Password must be at least 8 characters."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?,
                        password_reset_token = NULL,
                        password_reset_expires = NULL,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (generate_password_hash(password), int(row["id"])),
                )
                conn.commit()
                done = True
    finally:
        conn.close()

    return Response(render_template_string(RESET_PASSWORD_HTML, error=error, done=done))


@app.route("/auth/logout", methods=["POST", "GET"])
def auth_logout() -> Response:
    session.pop(SESSION_USER_KEY, None)
    return redirect(url_for("auth_login"))


@app.route("/favicon.ico")
def front_door_favicon() -> Response:
    if FRONT_DOOR_FAVICON.exists():
        return send_file(FRONT_DOOR_FAVICON, mimetype="image/svg+xml", max_age=3600)
    return jsonify({"ok": False, "message": "Not found"}), 404


@app.route("/branding/logo")
def branding_logo() -> Response:
    if BRANDING_LOGO_PATH.exists():
        return send_file(BRANDING_LOGO_PATH, mimetype="image/png", max_age=3600)
    if LEGACY_BRANDING_LOGO_PATH.exists():
        return send_file(LEGACY_BRANDING_LOGO_PATH, mimetype="image/png", max_age=3600)
    if FRONT_DOOR_FAVICON.exists():
        return send_file(FRONT_DOOR_FAVICON, mimetype="image/svg+xml", max_age=3600)
    return jsonify({"ok": False, "message": "Not found"}), 404


@app.route("/")
@login_required
def index() -> str:
    referer = request.headers.get("Referer", "")
    if "/app/productmix/" in referer or "/portal/productmix" in referer:
        return _proxy("productmix", "")

    fd = CONFIG.get("front_door", {})
    return render_template_string(
        DASHBOARD_HTML,
        host=fd.get("host", "127.0.0.1"),
        port=fd.get("port", 5080),
    )


@app.route("/admin")
@login_required
def admin() -> str:
    return redirect("/admin/users")


@app.route("/admin/users")
@login_required
@role_required("Super Admin")
def admin_users_page() -> Response:
    return Response(
        render_template_string(
            ADMIN_USERS_HTML,
            users=list_users_with_roles(),
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )


@app.route("/admin/users/create", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_users_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=(request.form.get("username") or ""),
        password=(request.form.get("password") or ""),
        role_name=(request.form.get("role_name") or "Employee"),
    )
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")


@app.route("/admin/users/<int:user_id>/active", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_users_active(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    is_active = str(request.form.get("is_active", "1")).strip() == "1"
    ok, msg = set_user_active_state(actor_id, int(user_id), is_active)
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@login_required
@role_required("Super Admin")
def admin_users_role(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/users?error=Session+expired")

    role_name = str(request.form.get("role_name") or "Employee").strip()
    ok, msg = set_user_role_name(actor_id, int(user_id), role_name)
    key = "message" if ok else "error"
    return redirect(f"/admin/users?{key}={requests.utils.quote(msg)}")


@app.route("/admin/tasks")
@login_required
@role_required("Super Admin", "Manager")
def admin_tasks_page() -> Response:
    status_filter = (request.args.get("status") or "").strip().lower() or None
    if status_filter not in {None, "pending", "in-progress", "completed"}:
        status_filter = None
    users = [u for u in list_users_with_roles() if int(u.get("is_active", 0)) == 1]
    return Response(
        render_template_string(
            ADMIN_TASKS_HTML,
            active_users=users,
            tasks=list_tasks(status_filter=status_filter),
            status_filter=status_filter,
            message=request.args.get("message", ""),
            error=request.args.get("error", ""),
        )
    )


@app.route("/admin/tasks/create", methods=["POST"])
@login_required
@role_required("Super Admin", "Manager")
def admin_tasks_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return redirect("/admin/tasks?error=Session+expired")

    assigned_to_raw = (request.form.get("assigned_to") or "").strip()
    assigned_to = int(assigned_to_raw) if assigned_to_raw.isdigit() else None
    ok, msg = create_task_record(
        actor_user_id=actor_id,
        title=(request.form.get("title") or ""),
        description=(request.form.get("description") or ""),
        assigned_to=assigned_to,
        due_date=(request.form.get("due_date") or "").strip() or None,
        priority=(request.form.get("priority") or "normal"),
    )
    key = "message" if ok else "error"
    return redirect(f"/admin/tasks?{key}={requests.utils.quote(msg)}")


@app.route("/admin/audit-logs")
@login_required
@role_required("Super Admin", "Manager")
def admin_audit_logs_page() -> Response:
    return Response(render_template_string(ADMIN_AUDIT_HTML, logs=list_audit_logs()))


@app.route("/api/admin/users", methods=["GET"])
@login_required
@role_required("Super Admin")
def api_admin_users_list() -> Response:
    return jsonify({"ok": True, "users": list_users_with_roles()})


@app.route("/api/admin/users", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def api_admin_users_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    ok, msg = create_user_account(
        actor_user_id=actor_id,
        username=str(payload.get("username") or ""),
        password=str(payload.get("password") or ""),
        role_name=str(payload.get("role_name") or "Employee"),
    )
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": msg}), code


@app.route("/api/admin/users/<int:user_id>/role", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def api_admin_users_role(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    ok, msg = set_user_role_name(actor_id, int(user_id), str(payload.get("role_name") or ""))
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": msg}), code


@app.route("/api/admin/users/<int:user_id>/active", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin")
def api_admin_users_active(user_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    value = payload.get("is_active", True)
    is_active = bool(value)
    ok, msg = set_user_active_state(actor_id, int(user_id), is_active)
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": msg}), code


@app.route("/api/admin/tasks", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_list() -> Response:
    return jsonify({"ok": True, "tasks": list_tasks()})


@app.route("/api/admin/tasks", methods=["POST"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_create() -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    assigned_to = payload.get("assigned_to")
    assigned_to_id = int(assigned_to) if str(assigned_to or "").isdigit() else None
    ok, msg = create_task_record(
        actor_user_id=actor_id,
        title=str(payload.get("title") or ""),
        description=str(payload.get("description") or ""),
        assigned_to=assigned_to_id,
        due_date=str(payload.get("due_date") or "").strip() or None,
        priority=str(payload.get("priority") or "normal"),
    )
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": msg}), code


@app.route("/api/admin/tasks/<int:task_id>/status", methods=["PATCH"])
@csrf.exempt
@login_required
@role_required("Super Admin", "Manager")
def api_admin_tasks_status(task_id: int) -> Response:
    actor_id = current_user_id()
    if actor_id is None:
        return jsonify({"ok": False, "message": "Session expired"}), 401

    payload = request.get_json(silent=True) or {}
    ok, msg = update_task_status(actor_id, int(task_id), str(payload.get("status") or ""))
    code = 200 if ok else 400
    return jsonify({"ok": ok, "message": msg}), code


@app.route("/api/admin/audit-logs", methods=["GET"])
@login_required
@role_required("Super Admin", "Manager")
def api_admin_audit_logs() -> Response:
    return jsonify({"ok": True, "audit_logs": list_audit_logs()})


@app.route("/portal")
@login_required
def portal_home() -> str:
    fd = CONFIG.get("front_door", {})
    return render_template_string(
        PORTAL_HOME_HTML,
        host=fd.get("host", "127.0.0.1"),
        port=fd.get("port", 5080),
    )


@app.route("/portal/<name>")
@login_required
def portal_app(name: str) -> Response:
    resolved_name = MANAGER.resolve_name(name)
    if not resolved_name:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    MANAGER.start(resolved_name)
    app_cfg = CONFIG["apps"][resolved_name]
    return render_template_string(
        PORTAL_APP_HTML,
        app_key=resolved_name,
        app_title=app_cfg["display_name"],
        raw_url=f"/app/{resolved_name}/",
    )


@app.route("/productmix")
@login_required
def portal_productmix_alias() -> Response:
    return redirect("/portal/productmix")


@app.route("/inventory")
@login_required
def portal_ic3_alias() -> Response:
    return redirect("/portal/ic3")


@app.route("/manager")
@login_required
def portal_manager_alias() -> Response:
    return redirect("/portal/managerapp")


@app.route("/api/health")
def api_health() -> Response:
    return jsonify({"ok": True})


@app.route("/api/status")
@login_required
def api_status() -> Response:
    return jsonify({"apps": MANAGER.status(), "preflight": MANAGER.preflight()})


@app.route("/api/shared/restaurants")
@login_required
def api_shared_restaurants() -> Response:
    """Shared restaurant source of truth for all embedded apps.

    Reads ProductMix restaurants directly from product_mix.db so IC3 and
    Manager App can reuse one master list managed from Restaurant Setup.
    """
    productmix_cfg = CONFIG.get("apps", {}).get("productmix", {})
    productmix_cwd = str(productmix_cfg.get("cwd") or "ProductMixRestaurantDB").strip() or "ProductMixRestaurantDB"
    pm_db_path = ROOT / productmix_cwd / "product_mix.db"
    if not pm_db_path.exists():
        return jsonify({"ok": False, "message": f"Shared restaurant DB not found: {pm_db_path}"}), 404

    conn = sqlite3.connect(pm_db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, name, location, city, state
            FROM restaurants
            ORDER BY id ASC
            """
        ).fetchall()
    except sqlite3.Error as exc:
        return jsonify({"ok": False, "message": f"Failed reading shared restaurants: {exc}"}), 500
    finally:
        conn.close()

    restaurants: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["name"] or "").strip()
        location = str(row["location"] or "").strip()
        label = f"{name} - {location}" if location else name
        restaurants.append(
            {
                "id": int(row["id"]),
                "name": name,
                "location": location,
                "city": str(row["city"] or "").strip(),
                "state": str(row["state"] or "").strip(),
                "label": label,
            }
        )

    return jsonify({"ok": True, "restaurants": restaurants, "count": len(restaurants)})


@app.route("/api/dashboard")
@login_required
def api_dashboard() -> Response:
    open_tasks = 0
    try:
        conn = get_rbac_db_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM tasks WHERE status IN ('pending', 'in-progress')"
        ).fetchone()
        conn.close()
        open_tasks = int(row["cnt"]) if row else 0
    except Exception:
        pass

    top_sellers: list[dict[str, Any]] = []
    try:
        productmix_cfg = CONFIG.get("apps", {}).get("productmix", {})
        productmix_cwd = str(productmix_cfg.get("cwd") or "ProductMixRestaurantDB").strip() or "ProductMixRestaurantDB"
        _pm_db_dir_env = os.environ.get("PM_DB_DIR")
        if _pm_db_dir_env:
            pm_db_path = Path(_pm_db_dir_env) / "product_mix.db"
        else:
            pm_db_path = ROOT / productmix_cwd / "product_mix.db"
        if pm_db_path.exists():
            pm_conn = sqlite3.connect(pm_db_path)
            pm_conn.row_factory = sqlite3.Row
            try:
                date_row = pm_conn.execute(
                    "SELECT MAX(report_start_date) AS latest FROM product_mix_items"
                ).fetchone()
                latest_date = date_row["latest"] if date_row else None
                if latest_date:
                    rows = pm_conn.execute(
                        """
                        SELECT item_name, SUM(qty_sold) AS total_sold
                        FROM product_mix_items
                        WHERE report_start_date = ?
                        GROUP BY item_name
                        ORDER BY total_sold DESC
                        LIMIT 5
                        """,
                        (latest_date,),
                    ).fetchall()
                    top_sellers = [
                        {"name": str(r["item_name"]), "qty": float(r["total_sold"] or 0)}
                        for r in rows
                    ]
            finally:
                pm_conn.close()
    except Exception:
        pass

    app_status = MANAGER.status()
    apps_running = sum(1 for s in app_status.values() if s.get("running") and s.get("healthy"))
    total_apps = len(app_status)
    return jsonify({
        "ok": True,
        "open_tasks": open_tasks,
        "top_sellers": top_sellers,
        "app_status": app_status,
        "apps_running": apps_running,
        "total_apps": total_apps,
    })


@app.route("/api/start-all", methods=["POST"])
@csrf.exempt
@login_required
def api_start_all() -> Response:
    result = MANAGER.start_all()
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/stop-all", methods=["POST"])
@csrf.exempt
@login_required
def api_stop_all() -> Response:
    return jsonify(MANAGER.stop_all())


@app.route("/api/apps/<name>/start", methods=["POST"])
@csrf.exempt
@login_required
def api_start(name: str) -> Response:
    result = MANAGER.start(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/apps/<name>/stop", methods=["POST"])
@csrf.exempt
@login_required
def api_stop(name: str) -> Response:
    result = MANAGER.stop(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/apps/<name>/restart", methods=["POST"])
@csrf.exempt
@login_required
def api_restart(name: str) -> Response:
    result = MANAGER.restart(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


def _proxy(name: str, path: str) -> Response:
    resolved_name = MANAGER.resolve_name(name)
    if not resolved_name:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    status = MANAGER.status()[resolved_name]
    if not status["running"]:
        MANAGER.start(resolved_name)
        # Poll until the sub-app port is accepting connections (up to 10 s).
        _app_host, _app_port = MANAGER._parse_host_port(CONFIG["apps"][resolved_name]["base_url"])
        for _ in range(20):
            time.sleep(0.5)
            if is_port_open(_app_host, _app_port):
                break

    upstream_base = CONFIG["apps"][resolved_name]["base_url"].rstrip("/") + "/"
    upstream_origin = urlparse(upstream_base)

    def rewrite_location_header(location: str) -> str:
        # Keep upstream redirects inside Dexter's proxied app namespace so
        # absolute locations like /login become /app/<name>/login.
        if not location:
            return location
        if location.startswith("/"):
            # Preserve cross-app routes already in Dexter namespace.
            if location.startswith("/app/"):
                return location
            if location.startswith(f"/app/{resolved_name}/"):
                return location
            if location == "/":
                return f"/app/{resolved_name}/"
            return f"/app/{resolved_name}{location}"

        parsed = urlparse(location)
        if parsed.scheme and parsed.netloc and parsed.netloc == upstream_origin.netloc:
            proxied_path = parsed.path or "/"
            if proxied_path == "/":
                new_location = f"/app/{resolved_name}/"
            else:
                new_location = f"/app/{resolved_name}{proxied_path}"
            if parsed.query:
                new_location = f"{new_location}?{parsed.query}"
            if parsed.fragment:
                new_location = f"{new_location}#{parsed.fragment}"
            return new_location

        return location

    target = urljoin(upstream_base, path)
    if request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8', errors='ignore')}"

    excluded_req_headers = {
        "host",
        "content-length",
        "connection",
        "accept-encoding",
    }
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in excluded_req_headers
    }
    if resolved_name in {"managerapp", "manager"}:
        dexter_user = session.get(SESSION_USER_KEY) or {}
        if dexter_user:
            forward_headers["X-Dexter-Auth"] = "1"
            forward_headers["X-Dexter-User"] = str(dexter_user.get("username", ""))
            forward_headers["X-Dexter-Email"] = str(dexter_user.get("email", ""))
            forward_headers["X-Dexter-Is-Admin"] = "1" if dexter_user.get("is_admin") else "0"

    def _request_upstream() -> requests.Response:
        return requests.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
        )

    try:
        upstream = _request_upstream()
    except requests.RequestException as exc:
        # A brief restart/retry protects the shell UI from transient local app drops.
        try:
            MANAGER.restart(resolved_name)
            # Wait for restart to bind its port (up to 8 s).
            _app_host2, _app_port2 = MANAGER._parse_host_port(CONFIG["apps"][resolved_name]["base_url"])
            for _ in range(16):
                time.sleep(0.5)
                if is_port_open(_app_host2, _app_port2):
                    break
            upstream = _request_upstream()
        except requests.RequestException:
            return jsonify({"ok": False, "message": f"Upstream request failed: {exc}"}), 502

    excluded_resp_headers = {
        "content-encoding",
        "transfer-encoding",
        "connection",
    }

    content_type = upstream.headers.get("Content-Type", "")
    response_body = upstream.content
    # Inject mobile-friendly CSS into ANY proxied embedded app HTML so that on
    # small viewports the page flows naturally (no internal scroll containers
    # that trap touch on iOS Safari, no fixed 100vh sections).
    if "text/html" in content_type.lower():
        try:
            _html_text = upstream.content.decode(upstream.encoding or "utf-8", errors="replace")
            _mobile_patch = (
                "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">"
                "<style id=\"__dexter_mobile_patch\">"
                "@media (max-width: 820px){"
                "html,body{height:auto!important;min-height:0!important;"
                "overflow:visible!important;overflow-x:hidden!important;"
                "-webkit-overflow-scrolling:auto!important;"
                "position:static!important;}"
                ".container,.wrap,.shell,.main,.tab-content,.tab-content.active,"
                ".viewer-pane,.page,.app-shell,.content,.dashboard{"
                "overflow:visible!important;height:auto!important;"
                "max-height:none!important;min-height:0!important;position:static!important;}"
                "table{display:block;overflow-x:auto;max-width:100%;}"
                "}"
                "</style>"
            )
            if "</head>" in _html_text.lower():
                # Case-insensitive insert before </head>
                _html_text = re.sub(
                    r"</head>",
                    _mobile_patch + "</head>",
                    _html_text,
                    count=1,
                    flags=re.IGNORECASE,
                )
            elif "<body" in _html_text.lower():
                _html_text = re.sub(
                    r"<body",
                    _mobile_patch + "<body",
                    _html_text,
                    count=1,
                    flags=re.IGNORECASE,
                )
            response_body = _html_text.encode("utf-8")
        except Exception:
            response_body = upstream.content
    if resolved_name in {"managerapp", "manager"} and "text/html" in content_type.lower():
        try:
            html = (response_body if isinstance(response_body, bytes) else upstream.content).decode(upstream.encoding or "utf-8", errors="replace")

            def _rewrite_attr(match: re.Match[str]) -> str:
                attr = match.group("attr")
                quoted_path = match.group("path")
                if quoted_path.startswith("/app/managerapp/"):
                    return f"{attr}{quoted_path}"
                if quoted_path == "/":
                    return f"{attr}/app/managerapp/"
                return f"{attr}/app/managerapp{quoted_path}"

            # Keep root-absolute links/forms/scripts in proxied manager namespace.
            html = re.sub(
                r'(?P<attr>\b(?:href|src|action)\s*=\s*["\'])(?P<path>/[^"\']*)',
                _rewrite_attr,
                html,
                flags=re.IGNORECASE,
            )
            response_body = html.encode("utf-8")
        except Exception:
            response_body = upstream.content

    response_headers: list[tuple[str, str]] = []
    for (k, v) in upstream.headers.items():
        k_lower = k.lower()
        if k_lower in excluded_resp_headers:
            continue
        if k_lower == "content-length":
            continue
        if k_lower == "location":
            v = rewrite_location_header(v)
        response_headers.append((k, v))

    return Response(response_body, upstream.status_code, response_headers)


@app.route("/app/<name>/")
@login_required
def app_root(name: str) -> Response:
    return _proxy(name, "")


@app.route(
    "/app/<name>/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@csrf.exempt
def app_proxy(name: str, path: str) -> Response:
    return _proxy(name, path)


@app.route("/open/<name>")
@login_required
def open_app(name: str) -> Response:
    return redirect(f"/app/{name}/")


@app.route("/static/<path:path>")
@login_required
def contextual_static_proxy(path: str) -> Response:
    # Embedded apps may request absolute /static/... URLs.
    referer = request.headers.get("Referer", "")
    if "/app/managerapp/" in referer or "/portal/managerapp" in referer:
        return _proxy("managerapp", f"static/{path}")
    if "/app/ic3/" in referer or "/portal/ic3" in referer:
        return _proxy("ic3", f"static/{path}")
    return _proxy("productmix", f"static/{path}")


@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@csrf.exempt
def contextual_proxy(path: str) -> Response:
    # Some upstream apps emit absolute root paths (for example /product-mix).
    # This fallback keeps those routes inside the expected proxied app context.
    reserved_prefixes = (
        "app/",
        "portal/",
        "open/",
        "admin",
        "productmix",
        "inventory",
        "manager",
        "static/",
    )
    if path.startswith(reserved_prefixes):
        return jsonify({"ok": False, "message": "Not found"}), 404

    referer = request.headers.get("Referer", "")
    productmix_prefixes = (
        "product-mix",
        "reports",
        "item/",
        "categories",
        "production-list",
        "restaurant-setup",
        "upload",
        "export",
        "auth/",
    )
    if path.startswith("api/"):
        if "/app/managerapp/" in referer or "/portal/managerapp" in referer:
            return _proxy("managerapp", path)
        if "/app/productmix/" in referer or "/portal/productmix" in referer:
            return _proxy("productmix", path)
        if "/app/ic3/" in referer or "/portal/ic3" in referer:
            return _proxy("ic3", path)

        # Default IC3 API passthrough for direct calls from the inventory UI.
        if path.startswith(("api/products", "api/inventory", "api/invoices")):
            return _proxy("ic3", path)
        if path.startswith("api/restaurants"):
            return _proxy("productmix", path)
        return jsonify({"ok": False, "message": "Not found"}), 404

    if "/app/productmix/" in referer or path.startswith(productmix_prefixes):
        return _proxy("productmix", path)
    if "/app/ic3/" in referer:
        return _proxy("ic3", path)
    if "/app/managerapp/" in referer:
        return _proxy("managerapp", path)

    return jsonify({"ok": False, "message": "Not found"}), 404


if __name__ == "__main__":
    front = CONFIG.get("front_door", {})
    # Allow overriding the bind host via env var (e.g. DEXTER_HOST=0.0.0.0
    # to expose the launcher to phones / other devices on the LAN).
    host = os.environ.get("DEXTER_HOST") or front.get("host", "127.0.0.1")
    port = int(os.environ.get("DEXTER_PORT") or front.get("port", 5080))
    auto_open_browser = bool(front.get("auto_open_browser", True))
    open_path = str(front.get("open_path", "/")).strip() or "/"
    if not open_path.startswith("/"):
        open_path = f"/{open_path}"

    startup_result = MANAGER.start_all()
    if not startup_result.get("ok"):
        print("Dexter Assistant preflight warning:", startup_result)

    MANAGER.start_watchdog()

    if auto_open_browser:
        startup_url = f"http://{host}:{port}{open_path}"
        threading.Timer(1.0, lambda: open_url_in_chrome(startup_url)).start()

    debug_mode = os.environ.get("PM_DEBUG", "0") == "1"
    if debug_mode:
        print(f"[dexter] Running in DEBUG mode on {host}:{port}", file=sys.stderr)
        app.run(host=host, port=port, debug=True)
    else:
        try:
            from waitress import serve  # type: ignore[import]
            print(f"[dexter] Running via waitress on {host}:{port} (threads=8)", file=sys.stderr)
            serve(app, host=host, port=port, threads=8)
        except ImportError:
            print("[dexter] waitress not installed — falling back to Flask dev server.", file=sys.stderr)
            app.run(host=host, port=port, debug=False)
