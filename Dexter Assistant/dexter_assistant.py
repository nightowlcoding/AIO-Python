# --- Place at the very end of the file, after all other routes and logic ---



from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

import requests
from flask import Flask, Response, jsonify, redirect, render_template_string, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "dexter_assistant_config.json"
RUNTIME_LOG_DIR = ROOT / "runtime_logs"
FRONT_DOOR_FAVICON = ROOT / "favicon.svg"
BRANDING_LOGO_PATH = ROOT / "dexter_logo.png"
LEGACY_BRANDING_LOGO_PATH = ROOT.parent / "Restaurant Management" / "Manager App" / "static" / "img" / "Dexter.png"
AUTH_USERS_PATH = ROOT / "dexter_assistant_users.json"
SESSION_USER_KEY = "dexter_user"


DASHBOARD_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
        <title>Dexter Assistant Control Center</title>
        <style>
                :root {
                    --bg:#f3f4f6;
                        --panel:#ffffff;
                        --ink:#1f2937;
                        --muted:#6b7280;
                        --ok:#166534;
                        --bad:#991b1b;
                    --accent:#ea580c;
                    --accent2:#0f766e;
                        --edge:#d1d5db;
                        --left:#f8fafc;
                        --left2:#f3f4f6;
                }
                * { box-sizing: border-box; }
                body {
                        margin: 0;
                        font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
                        color: var(--ink);
                    background: linear-gradient(145deg, #f8fafc 0%, #f9fafb 45%, #eef2ff 100%);
                        min-height: 100vh;
                }
                .shell {
                        display: grid;
                        grid-template-columns: 220px 220px minmax(0, 1fr);
                        min-height: 100vh;
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
                        padding: 14px 10px;
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
                    background: #ffedd5;
                    border-color: #fed7aa;
                    color: #c2410c;
                }
                .sub-head {
                        font-size: 11px;
                        text-transform: uppercase;
                        letter-spacing: 0.08em;
                        color: #64748b;
                        margin: 4px 8px;
                }
                body.collapsed .shell {
                        grid-template-columns: 72px 220px minmax(0, 1fr);
                }
                body.collapsed .brand {
                        display: none;
                }
                body.collapsed .brand-logo {
                    width: 28px;
                    height: 28px;
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
                .primary { background: var(--accent); color: #fff; border-color: #c2410c; }
                .warning { background: #9a3412; color: #fff; border-color: #7c2d12; }
                .secondary { background: var(--accent2); color: #fff; border-color: #115e59; }
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
                .banner {
                    border: 1px solid #fed7aa;
                    background: #fff7ed;
                    color: #9a3412;
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
                    background: #fff7ed;
                        font-weight: 700;
                    color: #7c2d12;
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
                @media (max-width: 980px) {
                        .shell {
                                grid-template-columns: minmax(0, 1fr);
                        }
                        .left-primary,
                        .left-sub {
                                position: fixed;
                                top: 0;
                                bottom: 0;
                                z-index: 20;
                                transform: translateX(-100%);
                                transition: transform 0.2s ease;
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
                        .shell.menu-open .left-primary,
                        .shell.menu-open .left-sub {
                                transform: translateX(0);
                        }
                        .mobile-top { display: flex; }
                        .main { padding: 12px; }
                        .title { font-size: 28px; }
                        .list-row { grid-template-columns: 1fr; gap: 2px; }
                }
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
                                <button class="menu-btn" onclick="toggleCollapsed()">||</button>
                        </div>
                        <nav id="primaryNav" class="primary-menu">
                                <button data-short="HM" data-section="overview" class="active" onclick="setSection('overview')">Home</button>
                                <button data-short="AP" data-section="apps" onclick="setSection('apps')">Apps</button>
                                <button data-short="OP" data-section="operations" onclick="setSection('operations')">Operations</button>
                        </nav>
                </aside>

                <aside class="left-sub">
                        <div class="sub-head">Sub Menu</div>
                        <nav id="subNav" class="sub-menu"></nav>
                </aside>

                <main class="main">
                        <div class="topbar">
                                <div>
                                        <h1 id="pageTitle" class="title">Control Center</h1>
                                        <p class="subtitle">Left menus control context. Main display lives on the right, with quick app actions.</p>
                                </div>
                                <div class="actions">
                                        <button class="primary" onclick="act('/api/start-all', null, this)">Start All</button>
                                        <button class="warning" onclick="act('/api/stop-all', null, this)">Stop All</button>
                                        <button onclick="refreshState()">Refresh</button>
                                        <a class="btn secondary" href="/portal/ic3">Open IC3 View</a>
                                        <a class="btn" href="/auth/logout">Logout</a>
                                </div>
                        </div>

                        <section id="pane-overview" class="pane active">
                                <div class="banner">Original source folders stay untouched. This dashboard controls copied apps in this Dexter Assistant directory.</div>
                                <div class="stats">
                                        <div class="stat"><div class="label">Total Apps</div><div id="statTotal" class="value">0</div></div>
                                        <div class="stat"><div class="label">Running</div><div id="statRunning" class="value">0</div></div>
                                        <div class="stat"><div class="label">Healthy</div><div id="statHealthy" class="value">0</div></div>
                                        <div class="stat"><div class="label">Unhealthy</div><div id="statUnhealthy" class="value">0</div></div>
                                </div>
                                <div class="footer">Front door: {{ host }}:{{ port }}</div>
                        </section>

                        <section id="pane-apps" class="pane">
                                <div id="grid" class="grid"></div>
                        </section>

                        <section id="pane-operations" class="pane">
                                <div class="list">
                                        <div class="list-row list-head">
                                                <div>Application</div>
                                                <div>Status</div>
                                                <div>Endpoint</div>
                                        </div>
                                        <div id="opsRows"></div>
                                </div>
                                <pre id="opsLog">No runtime log yet.</pre>
                        </section>
                </main>
        </div>

        <script>
            const subMenus = {
                overview: [
                    { id: 'overview', label: 'Summary' },
                    { id: 'apps', label: 'Quick App Cards' }
                ],
                apps: [
                    { id: 'apps', label: 'All Applications' },
                    { id: 'operations', label: 'Status Matrix' }
                ],
                operations: [
                    { id: 'operations', label: 'Operations Board' },
                    { id: 'apps', label: 'Card Controls' }
                ]
            };

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
            }

            function toggleMobileMenu() {
                document.getElementById('shell').classList.toggle('menu-open');
            }

            function setSection(section) {
                document.querySelectorAll('#primaryNav button').forEach(function(b) {
                    b.classList.toggle('active', b.dataset.section === section);
                });
                document.querySelectorAll('.pane').forEach(function(pane) {
                    pane.classList.toggle('active', pane.id === ('pane-' + section));
                });

                const title = document.getElementById('pageTitle');
                const titles = {
                    overview: 'Control Center',
                    apps: 'Applications',
                    operations: 'Operations'
                };
                title.textContent = titles[section] || 'Control Center';
                renderSubmenu(section);

                if (window.innerWidth <= 980) {
                    document.getElementById('shell').classList.remove('menu-open');
                }
            }

            function setPaneFromSubmenu(targetPane) {
                const mapped = targetPane === 'operations' ? 'operations' : (targetPane === 'apps' ? 'apps' : 'overview');
                setSection(mapped);
            }

            function renderSubmenu(section) {
                const nav = document.getElementById('subNav');
                nav.innerHTML = '';
                (subMenus[section] || []).forEach(function(item) {
                    const btn = document.createElement('button');
                    btn.textContent = item.label;
                    btn.classList.toggle('active', item.id === section);
                    btn.onclick = function() { setPaneFromSubmenu(item.id); };
                    nav.appendChild(btn);
                });
            }

            function renderCard(name, state) {
                const card = document.createElement('div');
                card.className = 'card';
                const safeLog = htmlEscape(state.log_tail || '');
                const pid = state.pid || 'n/a';
                const disabledStart = state.running ? 'disabled' : '';
                const disabledStop = state.running ? '' : 'disabled';

                card.innerHTML =
                    '<div class="row">' +
                        '<div class="name">' + htmlEscape(state.display_name) + '</div>' +
                        '<div class="' + badgeClass(state) + '">' + badgeText(state) + '</div>' +
                    '</div>' +
                    '<div class="meta">key: ' + htmlEscape(name) + ' | url: ' + htmlEscape(state.base_url) + ' | pid: ' + htmlEscape(pid) + '</div>' +
                    '<div class="btns">' +
                        '<button class="primary" onclick="act(\\'/api/apps/' + htmlEscape(name) + '/start\\')" ' + disabledStart + '>Start</button>' +
                        '<button onclick="act(\\'/api/apps/' + htmlEscape(name) + '/restart\\')">Restart</button>' +
                        '<button class="warning" onclick="act(\\'/api/apps/' + htmlEscape(name) + '/stop\\')" ' + disabledStop + '>Stop</button>' +
                        '<a class="btn secondary" href="/portal/' + htmlEscape(name) + '">Open</a>' +
                        '<a class="btn" href="/app/' + htmlEscape(name) + '/" target="_blank" rel="noopener">Raw</a>' +
                    '</div>' +
                    '<pre>' + (safeLog || 'No runtime log yet.') + '</pre>';

                return card;
            }

            function renderOpsRows(apps) {
                const rows = document.getElementById('opsRows');
                rows.innerHTML = '';
                const combinedLogs = [];

                Object.entries(apps).forEach(function(entry) {
                    const name = entry[0];
                    const state = entry[1];
                    const row = document.createElement('div');
                    row.className = 'list-row';
                    row.innerHTML =
                        '<div><strong>' + htmlEscape(state.display_name) + '</strong><br/><span style="color:#64748b">' + htmlEscape(name) + '</span></div>' +
                        '<div><span class="' + badgeClass(state) + '">' + badgeText(state) + '</span></div>' +
                        '<div>' + htmlEscape(state.base_url) + '</div>';
                    rows.appendChild(row);

                    if (state.log_tail) {
                        combinedLogs.push('=== ' + state.display_name + ' ===\\n' + state.log_tail);
                    }
                });

                document.getElementById('opsLog').textContent = combinedLogs.length ? combinedLogs.join('\\n\\n') : 'No runtime log yet.';
            }

            function renderStats(apps) {
                const values = Object.values(apps);
                const total = values.length;
                const running = values.filter(function(s) { return s.running; }).length;
                const healthy = values.filter(function(s) { return s.running && s.healthy; }).length;
                const unhealthy = values.filter(function(s) { return s.running && !s.healthy; }).length;

                document.getElementById('statTotal').textContent = String(total);
                document.getElementById('statRunning').textContent = String(running);
                document.getElementById('statHealthy').textContent = String(healthy);
                document.getElementById('statUnhealthy').textContent = String(unhealthy);

                var statTotal = document.getElementById('statTotal').closest('.stat');
                var statRunning = document.getElementById('statRunning').closest('.stat');
                var statHealthy = document.getElementById('statHealthy').closest('.stat');
                var statUnhealthy = document.getElementById('statUnhealthy').closest('.stat');

                statRunning.className = 'stat' + (running > 0 ? ' ok-stat' : '');
                statHealthy.className = 'stat' + (healthy > 0 ? ' ok-stat' : '');
                statUnhealthy.className = 'stat' + (unhealthy > 0 ? ' bad-stat' : '');
                statTotal.className = 'stat';
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
                    var apps = data.apps || {};
                    var grid = document.getElementById('grid');
                    grid.innerHTML = '';
                    Object.entries(apps).forEach(function(entry) {
                        grid.appendChild(renderCard(entry[0], entry[1]));
                    });
                    renderStats(apps);
                    renderOpsRows(apps);
                } catch (e) { /* network hiccup — skip silently */ }
            }

            renderSubmenu('overview');
            setSection('overview');
            refreshState();
            startPoll();
        </script>
</body>
</html>
"""
PORTAL_HOME_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
    <title>Dexter Assistant Portal</title>
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
        body {
            margin: 0;
            font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
            color: var(--ink);
            background: var(--bg);
            min-height: 100vh;
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


PORTAL_APP_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
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
        body {
            margin: 0;
            font-family: 'Segoe UI', 'Trebuchet MS', sans-serif;
            color: var(--ink);
            background: linear-gradient(145deg,#f8fafc 0%,#f9fafb 45%,#eef2ff 100%);
            min-height: 100vh;
            display: grid;
            grid-template-rows: auto auto 1fr;
        }
        .topbar {
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
            var tb = document.getElementById('topbar');
            var sb = document.getElementById('subbar');
            var used = (tb ? tb.offsetHeight : 0) + (sb ? sb.offsetHeight : 0);
            document.getElementById('appFrame').style.height = (window.innerHeight - used) + 'px';
        }
        setFrameHeight();
        window.addEventListener('resize', setFrameHeight);
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


LOGIN_HTML = """
<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=0\" />
    <title>Dexter Assistant &mdash; Sign In</title>
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
                <img class="logo" src="/branding/logo" alt="Dexter Assistant Logo" />
                <div class="hero-title">Dexter <span class="hero-accent">Assistant</span></div>
                <div class="hero-tagline">All your restaurant management apps,<br>one secure ops dashboard.</div>
                <ul class="features">
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Start, stop, and monitor apps instantly</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Secure, password-protected access</li>
                    <li><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/><path d="M8 12.5l2.5 2.5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> Works on any device, anywhere</li>
                </ul>
                <a class="contact-link" href="mailto:info@dexterassist.com">Contact us / Learn more</a>
            </div>
            <form class="card" method="post" action="{{ action_url }}">
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
                <div class="links">No account yet? <a href="{{ register_url }}{% if next_path %}?next={{ next_path }}{% endif %}">Create one</a></div>
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
    <title>Dexter Assistant &mdash; Register</title>
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
            <div class="brand-head">
                <img class="brand-logo" src="/branding/logo" alt="Dexter logo" />
                <h1>Create Account</h1>
            </div>
            <p>Create your Dexter Assistant login.</p>
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


def find_auth_user(identifier: str) -> tuple[str | None, dict[str, Any] | None]:
    users = load_auth_users()
    normalized = identifier.strip().lower()
    if not normalized:
        return None, None

    direct = users.get(identifier)
    if isinstance(direct, dict):
        return identifier, direct

    for username, user in users.items():
        if not isinstance(user, dict):
            continue
        if username.lower() == normalized or str(user.get("email", "")).strip().lower() == normalized:
            return username, user

    return None, None


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
        if name not in self.config["apps"]:
            raise KeyError(f"Unknown app: {name}")
        return self.config["apps"][name]

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
        with self._lock:
            app = self._app_cfg(name)
            proc = self._procs.get(name)
            if proc is not None and proc.poll() is None:
                return {"ok": True, "message": f"{name} already running"}

            cwd = ROOT / app["cwd"]
            entry = cwd / app["entrypoint"]
            if not entry.exists():
                return {"ok": False, "message": f"Entrypoint not found: {entry}"}

            host, port = self._parse_host_port(app["base_url"])
            if not is_port_open(host, port) and not is_port_free(host, port):
                return {"ok": False, "message": f"Port in use by another process: {host}:{port}"}

            env = os.environ.copy()
            env.update(app.get("env", {}))
            log_file = self._log_file(name)
            self._rotate_log(name)
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
            self._procs[name] = proc
            return {"ok": True, "message": f"Started {name}", "pid": proc.pid}

    def stop(self, name: str) -> dict[str, Any]:
        with self._lock:
            proc = self._procs.get(name)
            if proc is None or proc.poll() is not None:
                self._procs[name] = None
                return {"ok": True, "message": f"{name} already stopped"}

            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            self._procs[name] = None
            return {"ok": True, "message": f"Stopped {name}"}

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
ensure_default_admin_user()


@app.before_request
def require_auth_for_protected_routes() -> Response | None:
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/branding/logo",
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
def auth_login() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(get_next_path("/portal/ic3"))

    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key, user = find_auth_user(username)
        if user and check_password_hash(str(user.get("password_hash", "")), password):
            users = load_auth_users()
            if key and key in users:
                users[key]["last_login"] = datetime.now().isoformat(timespec="seconds")
                save_auth_users(users)
            session[SESSION_USER_KEY] = {
                "username": key or username,
                "is_admin": bool(user.get("is_admin", False)),
                "email": user.get("email") or key or username,
            }
            session.permanent = True
            MANAGER.start_all()
            return redirect(get_next_path("/portal/ic3"))
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
def auth_register() -> Response:
    if session.get(SESSION_USER_KEY):
        return redirect(get_next_path("/portal/ic3"))

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
            users = load_auth_users()
            if any(
                username.lower() == existing.lower() or username.lower() == str(user.get("email", "")).strip().lower()
                for existing, user in users.items()
                if isinstance(user, dict)
            ):
                error = "Username already exists."
            else:
                users[username] = {
                    "password_hash": generate_password_hash(password),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "last_login": None,
                    "is_admin": False,
                    "email": username,
                }
                save_auth_users(users)
                session[SESSION_USER_KEY] = {"username": username, "is_admin": False, "email": username}
                session.permanent = True
                return redirect(get_next_path("/portal/ic3"))

    return Response(
        render_template_string(
            REGISTER_HTML,
            error=error,
            next_path=request.args.get("next", ""),
            action_url=url_for("auth_register"),
            login_url=url_for("auth_login"),
        )
    )


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
    return redirect("/")


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
    if name not in CONFIG["apps"]:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    MANAGER.start(name)
    app_cfg = CONFIG["apps"][name]
    return render_template_string(
        PORTAL_APP_HTML,
        app_key=name,
        app_title=app_cfg["display_name"],
        raw_url=f"/app/{name}/",
    )


@app.route("/productmix")
@login_required
def portal_productmix_alias() -> Response:
    return redirect("/portal/productmix")


@app.route("/inventory")
@login_required
def portal_ic3_alias() -> Response:
    return redirect("/portal/ic3")


@app.route("/api/health")
def api_health() -> Response:
    return jsonify({"ok": True})


@app.route("/api/status")
@login_required
def api_status() -> Response:
    return jsonify({"apps": MANAGER.status(), "preflight": MANAGER.preflight()})


@app.route("/api/start-all", methods=["POST"])
@login_required
def api_start_all() -> Response:
    result = MANAGER.start_all()
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/stop-all", methods=["POST"])
@login_required
def api_stop_all() -> Response:
    return jsonify(MANAGER.stop_all())


@app.route("/api/apps/<name>/start", methods=["POST"])
@login_required
def api_start(name: str) -> Response:
    result = MANAGER.start(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/apps/<name>/stop", methods=["POST"])
@login_required
def api_stop(name: str) -> Response:
    result = MANAGER.stop(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


@app.route("/api/apps/<name>/restart", methods=["POST"])
@login_required
def api_restart(name: str) -> Response:
    result = MANAGER.restart(name)
    code = 200 if result.get("ok") else 409
    return jsonify(result), code


def _proxy(name: str, path: str) -> Response:
    if name not in CONFIG["apps"]:
        return jsonify({"ok": False, "message": f"Unknown app: {name}"}), 404

    status = MANAGER.status()[name]
    if not status["running"]:
        MANAGER.start(name)
        time.sleep(0.6)

    upstream_base = CONFIG["apps"][name]["base_url"].rstrip("/") + "/"
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

    try:
        upstream = requests.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
        )
    except requests.RequestException as exc:
        return jsonify({"ok": False, "message": f"Upstream request failed: {exc}"}), 502

    excluded_resp_headers = {
        "content-encoding",
        "transfer-encoding",
        "connection",
    }
    response_headers = [
        (k, v)
        for (k, v) in upstream.headers.items()
        if k.lower() not in excluded_resp_headers
    ]

    if "Location" in upstream.headers:
        loc = upstream.headers["Location"]
        base = CONFIG["apps"][name]["base_url"]
        if loc.startswith(base):
            rewritten = "/app/{}/{}".format(name, loc[len(base):].lstrip("/"))
            response_headers = [
                (k, rewritten if k.lower() == "location" else v)
                for (k, v) in response_headers
            ]

    return Response(upstream.content, upstream.status_code, response_headers)


@app.route("/app/<name>/")
@login_required
def app_root(name: str) -> Response:
    return _proxy(name, "")


@app.route(
    "/app/<name>/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
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
    if "/app/ic3/" in referer or "/portal/ic3" in referer:
        return _proxy("ic3", f"static/{path}")
    return _proxy("productmix", f"static/{path}")


@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
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

    return jsonify({"ok": False, "message": "Not found"}), 404


if __name__ == "__main__":
    front = CONFIG.get("front_door", {})
    host = front.get("host", "127.0.0.1")
    port = int(front.get("port", 5080))
    auto_open_browser = bool(front.get("auto_open_browser", True))
    open_path = str(front.get("open_path", "/")).strip() or "/"
    if not open_path.startswith("/"):
        open_path = f"/{open_path}"

    startup_result = MANAGER.start_all()
    if not startup_result.get("ok"):
        print("Dexter Assistant preflight warning:", startup_result)

    if auto_open_browser:
        startup_url = f"http://{host}:{port}{open_path}"
        threading.Timer(1.0, lambda: open_url_in_chrome(startup_url)).start()

    app.run(host=host, port=port, debug=False)
