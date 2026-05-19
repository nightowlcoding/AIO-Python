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
AUTH_USERS_PATH = ROOT / "dexter_assistant_users.json"
SESSION_USER_KEY = "dexter_user"


DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Dexter Assistant</title>
  <style>
    :root {
      --bg:#f4f7f0;
      --panel:#ffffff;
      --ink:#1f2a1f;
      --muted:#5e6a5e;
      --ok:#2e7d32;
      --warn:#ef6c00;
      --bad:#c62828;
      --accent:#005f73;
      --edge:#d7dfd3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 0%, #d9ead3 0%, rgba(217,234,211,0) 40%),
        radial-gradient(circle at 90% 10%, #dceefb 0%, rgba(220,238,251,0) 35%),
        var(--bg);
    }
    .wrap {
      max-width: 1080px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }
    h1 { margin: 0 0 10px; font-size: 32px; }
    .subtitle { margin: 0 0 24px; color: var(--muted); }
    .banner {
      border: 1px solid #b7d4bf;
      background: #edf8ef;
      border-radius: 12px;
      padding: 12px 14px;
      margin-bottom: 16px;
      color: #215b2b;
    }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr)); gap: 14px; }
    .card {
      background: var(--panel);
      border: 1px solid var(--edge);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 8px 24px rgba(33, 48, 33, 0.06);
    }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .name { font-size: 20px; font-weight: 600; }
    .pill {
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid transparent;
    }
    .running { color: #1b5e20; background: #e8f5e9; border-color: #b7dfbb; }
    .stopped { color: #5d4037; background: #fbe9e7; border-color: #f5c9c1; }
    .error { color: #7f1d1d; background: #fee2e2; border-color: #fecaca; }
    .meta { color: var(--muted); font-size: 13px; margin: 8px 0 10px; }
    .btns { display: flex; gap: 8px; flex-wrap: wrap; }
    button, a.btn {
      appearance: none;
      border: 1px solid #c4d1bd;
      background: #fff;
      color: #213021;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 82px;
    }
    button.primary { background: var(--accent); color: #fff; border-color: #004553; }
    button.warning { background: #9a3412; color: #fff; border-color: #7c2d12; }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    .footer { margin-top: 18px; color: var(--muted); font-size: 12px; }
    pre {
      margin-top: 10px;
      border-radius: 10px;
      border: 1px solid var(--edge);
      background: #f8faf7;
      padding: 8px;
      max-height: 160px;
      overflow: auto;
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Dexter Assistant</h1>
    <p class="subtitle">Single front door for exact copied apps with start, stop, health, and proxy routing.</p>
    <div class="banner">Original source folders stay untouched. This dashboard controls only copied apps in this Dexter Assistant directory.</div>
    <div class="actions">
      <button class="primary" onclick="act('/api/start-all')">Start All</button>
      <button class="warning" onclick="act('/api/stop-all')">Stop All</button>
      <button onclick="refreshState()">Refresh</button>
            <a class="btn" href="/auth/logout">Logout</a>
    </div>
    <div id="grid" class="grid"></div>
    <div class="footer">Front door: {{ host }}:{{ port }}</div>
  </div>
  <script>
    async function act(url, body) {
      const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: body ? JSON.stringify(body) : '{}'});
      if (!res.ok) {
        const txt = await res.text();
        alert('Action failed: ' + txt);
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

    function card(name, state) {
      const c = document.createElement('div');
      c.className = 'card';
      const safeLog = (state.log_tail || '').replace(/[<>&]/g, (m) => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[m]));
      c.innerHTML = `
        <div class="row">
          <div class="name">${state.display_name}</div>
          <div class="${badgeClass(state)}">${badgeText(state)}</div>
        </div>
        <div class="meta">key: ${name} | url: ${state.base_url} | pid: ${state.pid || 'n/a'}</div>
        <div class="btns">
          <button class="primary" onclick="act('/api/apps/${name}/start')" ${state.running ? 'disabled' : ''}>Start</button>
          <button onclick="act('/api/apps/${name}/restart')">Restart</button>
          <button class="warning" onclick="act('/api/apps/${name}/stop')" ${state.running ? '' : 'disabled'}>Stop</button>
          <a class="btn" href="/app/${name}/" target="_blank" rel="noopener">Open</a>
        </div>
        <pre>${safeLog || 'No runtime log yet.'}</pre>
      `;
      return c;
    }

    async function refreshState() {
      const res = await fetch('/api/status');
      const data = await res.json();
      const grid = document.getElementById('grid');
      grid.innerHTML = '';
      Object.entries(data.apps).forEach(([name, state]) => grid.appendChild(card(name, state)));
    }

    refreshState();
    setInterval(refreshState, 2500);
  </script>
</body>
</html>
"""


PORTAL_HOME_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Dexter Assistant Portal</title>
    <style>
        :root {
            --ink:#1d2a28;
            --muted:#51615c;
            --bg:#eef3ea;
            --panel:#ffffff;
            --edge:#d5ddd2;
            --brand:#0f766e;
            --brand-2:#166534;
            --danger:#8b1d1d;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Segoe UI", "Trebuchet MS", sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 0% 0%, #d9efe4 0%, rgba(217,239,228,0) 45%),
                radial-gradient(circle at 100% 10%, #e8f0d8 0%, rgba(232,240,216,0) 35%),
                var(--bg);
            min-height: 100vh;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 18px;
            border-bottom: 1px solid var(--edge);
            background: #f8fbf6;
            position: sticky;
            top: 0;
            z-index: 5;
        }
        .brand { font-size: 20px; font-weight: 700; letter-spacing: 0.2px; }
        .nav { display: flex; gap: 8px; flex-wrap: wrap; }
        .nav a, .nav button {
            border: 1px solid #c6d2c7;
            background: #fff;
            color: #1f2d2b;
            border-radius: 10px;
            padding: 8px 12px;
            text-decoration: none;
            font-size: 13px;
            cursor: pointer;
        }
        .nav .primary { background: var(--brand); color: #fff; border-color: #0c5b55; }
        .nav .danger { background: var(--danger); color: #fff; border-color: #6f1717; }
        .wrap { max-width: 1120px; margin: 0 auto; padding: 28px 18px 36px; }
        h1 { margin: 0 0 6px; font-size: 34px; }
        .subtitle { color: var(--muted); margin: 0 0 18px; }
        .banner {
            border: 1px solid #b9d7c3;
            background: #eaf8ef;
            border-radius: 12px;
            padding: 10px 12px;
            color: #245538;
            margin-bottom: 18px;
        }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
        .card {
            background: var(--panel);
            border: 1px solid var(--edge);
            border-radius: 14px;
            padding: 16px;
            box-shadow: 0 10px 22px rgba(33, 48, 33, 0.06);
        }
        .card h2 { margin: 0 0 6px; font-size: 21px; }
        .card p { margin: 0 0 12px; color: var(--muted); }
        .actions { display: flex; gap: 8px; flex-wrap: wrap; }
        .actions a {
            border: 1px solid #c6d2c7;
            background: #fff;
            color: #1f2d2b;
            border-radius: 10px;
            padding: 8px 12px;
            text-decoration: none;
            font-size: 13px;
        }
        .actions a.primary { background: var(--brand-2); color: #fff; border-color: #0f4d26; }
        .footer { margin-top: 18px; color: var(--muted); font-size: 12px; }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand">Dexter Assistant Portal</div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/portal/productmix">ProductMix</a>
            <a href="/portal/ic3">Inventory Control 3</a>
            <a href="/admin">Admin</a>
            <button class="primary" onclick="act('/api/start-all')">Start All</button>
            <button class="danger" onclick="act('/api/stop-all')">Stop All</button>
            <a href="/auth/logout">Logout</a>
        </div>
    </div>
    <div class="wrap">
        <h1>Restaurant Management</h1>
        <p class="subtitle">Run both systems under one website and switch between them from shared navigation.</p>
        <div class="banner">Both copied apps are hosted behind this portal. Original source folders remain untouched.</div>
        <div class="cards">
            <div class="card">
                <h2>ProductMixRestaurantDB</h2>
                <p>Upload and analyze product mixes, production lists, and report views.</p>
                <div class="actions">
                    <a class="primary" href="/portal/productmix">Open ProductMix</a>
                    <a href="/app/productmix/" target="_blank" rel="noopener">Open Raw App</a>
                </div>
            </div>
            <div class="card">
                <h2>Inventory Control 3</h2>
                <p>Inventory tracking, invoice imports, and usage analytics for locations.</p>
                <div class="actions">
                    <a class="primary" href="/portal/ic3">Open Inventory Control 3</a>
                    <a href="/app/ic3/" target="_blank" rel="noopener">Open Raw App</a>
                </div>
            </div>
        </div>
        <div class="footer">Front door: {{ host }}:{{ port }}</div>
    </div>
    <script>
        async function act(url) {
            const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
            if (!res.ok) {
                const txt = await res.text();
                alert('Action failed: ' + txt);
            }
        }
    </script>
</body>
</html>
"""


PORTAL_APP_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>{{ app_title }} - Dexter Assistant</title>
    <style>
        :root {
            --ink:#1d2a28;
            --bg:#eef3ea;
            --panel:#ffffff;
            --edge:#d5ddd2;
            --brand:#0f766e;
            --muted:#55655f;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Segoe UI", "Trebuchet MS", sans-serif;
            color: var(--ink);
            background: var(--bg);
            min-height: 100vh;
            display: grid;
            grid-template-rows: auto auto 1fr;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 14px;
            border-bottom: 1px solid var(--edge);
            background: #f8fbf6;
        }
        .brand { font-size: 18px; font-weight: 700; }
        .nav { display: flex; gap: 8px; flex-wrap: wrap; }
        .nav a, .nav button {
            border: 1px solid #c6d2c7;
            background: #fff;
            color: #1f2d2b;
            border-radius: 10px;
            padding: 7px 10px;
            text-decoration: none;
            font-size: 12px;
            cursor: pointer;
        }
        .nav .primary { background: var(--brand); color: #fff; border-color: #0c5b55; }
        .subbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--edge);
            background: #fff;
            padding: 8px 14px;
            color: var(--muted);
            font-size: 13px;
        }
        iframe {
            width: 100%;
            height: calc(100vh - 104px);
            border: 0;
            background: #fff;
        }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand">{{ app_title }}</div>
        <div class="nav">
            <a href="/">Home</a>
            <a href="/portal/productmix">ProductMix</a>
            <a href="/portal/ic3">Inventory Control 3</a>
            <a href="/admin">Admin</a>
            <button class="primary" onclick="restart()">Restart This App</button>
            <a href="/auth/logout">Logout</a>
        </div>
    </div>
    <div class="subbar">
        <span>Embedded via Dexter Assistant portal routing.</span>
        <a href="{{ raw_url }}" target="_blank" rel="noopener">Open Raw App</a>
    </div>
    <iframe src="{{ raw_url }}"></iframe>
    <script>
        async function restart() {
            const res = await fetch('/api/apps/{{ app_key }}/restart', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
            if (!res.ok) {
                const txt = await res.text();
                alert('Restart failed: ' + txt);
                return;
            }
            window.location.reload();
        }
    </script>
</body>
</html>
"""


LOGIN_HTML = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Dexter Assistant Login</title>
    <style>
        :root { --bg:#eef3ea; --panel:#fff; --ink:#1f2a1f; --muted:#5f6a60; --edge:#d7dfd3; --brand:#0f766e; --danger:#991b1b; }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: "Segoe UI", "Trebuchet MS", sans-serif; color: var(--ink); background: var(--bg); }
        .wrap { min-height: 100vh; display: grid; place-items: center; padding: 20px; }
        .card { width: 100%; max-width: 460px; background: var(--panel); border: 1px solid var(--edge); border-radius: 14px; padding: 20px; box-shadow: 0 10px 26px rgba(33, 48, 33, 0.08); }
        h1 { margin: 0 0 8px; font-size: 28px; }
        p { margin: 0 0 18px; color: var(--muted); }
        label { display: block; margin: 10px 0 6px; font-size: 14px; }
        input { width: 100%; padding: 10px 12px; border: 1px solid #c7d2c4; border-radius: 10px; font-size: 14px; }
        .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
        .check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
        .check input { width: auto; margin: 0; }
        button { margin-top: 14px; width: 100%; border: 1px solid #0b645e; background: var(--brand); color: #fff; border-radius: 10px; padding: 10px 12px; font-size: 14px; cursor: pointer; }
        .error { margin: 10px 0 0; color: var(--danger); font-size: 13px; }
        .links { margin-top: 12px; font-size: 13px; color: var(--muted); }
        .links a { color: #0b5a56; text-decoration: none; }
    </style>
</head>
<body>
    <div class="wrap">
        <form class="card" method="post" action="{{ action_url }}">
            <h1>Dexter Assistant</h1>
            <p>Sign in to access app controls and protected routes.</p>
            <label>Username</label>
            <input id="login-username" type="text" name="username" required autofocus autocomplete="username" />
            <label>Password</label>
            <input id="login-password" type="password" name="password" required autocomplete="current-password" />
            <div class="row">
                <label class="check"><input id="show-password" type="checkbox" /> Show password</label>
                <label class="check"><input id="save-password" type="checkbox" /> Save password</label>
            </div>
            <button type="submit">Sign In</button>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <div class="links">No account yet? <a href="{{ register_url }}{% if next_path %}?next={{ next_path }}{% endif %}">Create one</a></div>
        </form>
    </div>
    <script>
        (function () {
            const usernameInput = document.getElementById('login-username');
            const passwordInput = document.getElementById('login-password');
            const showPassword = document.getElementById('show-password');
            const savePassword = document.getElementById('save-password');
            const storageKey = 'dexterAssistantLogin';

            try {
                const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
                if (saved && typeof saved === 'object') {
                    if (typeof saved.username === 'string') usernameInput.value = saved.username;
                    if (typeof saved.password === 'string') passwordInput.value = saved.password;
                    showPassword.checked = !!saved.showPassword;
                    savePassword.checked = !!saved.savePassword;
                    if (showPassword.checked) passwordInput.type = 'text';
                }
            } catch (e) {
                // Ignore malformed stored data.
            }

            showPassword.addEventListener('change', () => {
                passwordInput.type = showPassword.checked ? 'text' : 'password';
            });

            document.querySelector('form.card').addEventListener('submit', () => {
                if (savePassword.checked) {
                    localStorage.setItem(storageKey, JSON.stringify({
                        username: usernameInput.value,
                        password: passwordInput.value,
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
    <title>Dexter Assistant Register</title>
    <style>
        :root { --bg:#eef3ea; --panel:#fff; --ink:#1f2a1f; --muted:#5f6a60; --edge:#d7dfd3; --brand:#166534; --danger:#991b1b; }
        * { box-sizing: border-box; }
        body { margin: 0; font-family: "Segoe UI", "Trebuchet MS", sans-serif; color: var(--ink); background: var(--bg); }
        .wrap { min-height: 100vh; display: grid; place-items: center; padding: 20px; }
        .card { width: 100%; max-width: 460px; background: var(--panel); border: 1px solid var(--edge); border-radius: 14px; padding: 20px; box-shadow: 0 10px 26px rgba(33, 48, 33, 0.08); }
        h1 { margin: 0 0 8px; font-size: 28px; }
        p { margin: 0 0 18px; color: var(--muted); }
        label { display: block; margin: 10px 0 6px; font-size: 14px; }
        input { width: 100%; padding: 10px 12px; border: 1px solid #c7d2c4; border-radius: 10px; font-size: 14px; }
        button { margin-top: 14px; width: 100%; border: 1px solid #14532d; background: var(--brand); color: #fff; border-radius: 10px; padding: 10px 12px; font-size: 14px; cursor: pointer; }
        .error { margin: 10px 0 0; color: var(--danger); font-size: 13px; }
        .links { margin-top: 12px; font-size: 13px; color: var(--muted); }
        .links a { color: #0b5a56; text-decoration: none; }
    </style>
</head>
<body>
    <div class="wrap">
        <form class="card" method="post" action="{{ action_url }}">
            <h1>Create Account</h1>
            <p>Basic local auth for Dexter Assistant.</p>
            <label>Username</label>
            <input type="text" name="username" required minlength="3" autofocus />
            <label>Password</label>
            <input type="password" name="password" required minlength="8" />
            <label>Confirm Password</label>
            <input type="password" name="confirm_password" required minlength="8" />
            <button type="submit">Register</button>
            {% if error %}<div class="error">{{ error }}</div>{% endif %}
            <div class="links">Already have an account? <a href="{{ login_url }}{% if next_path %}?next={{ next_path }}{% endif %}">Sign in</a></div>
        </form>
    </div>
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
    users = load_auth_users()
    admin_username = "arnoldrjr@gmail.com"
    admin_password_hash = generate_password_hash("Passramirez4!")
    current = users.get(admin_username)
    if not current or not current.get("is_admin"):
        users[admin_username] = {
            "password_hash": admin_password_hash,
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

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        with self._lock:
            for name, app in self.config["apps"].items():
                proc = self._procs.get(name)
                running = proc is not None and proc.poll() is None
                health_url = urljoin(app["base_url"], app.get("health_path", "/"))
                healthy = check_health(health_url)
                out[name] = {
                    "display_name": app["display_name"],
                    "base_url": app["base_url"],
                    "running": running,
                    "healthy": healthy,
                    "pid": proc.pid if running else None,
                    "log_tail": self._tail_log(name),
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
app.secret_key = os.environ.get("DEXTER_SECRET_KEY") or os.environ.get("SECRET_KEY") or "dexter-assistant-local-secret"
ensure_default_admin_user()


@app.before_request
def require_auth_for_protected_routes() -> Response | None:
    public_prefixes = (
        "/auth/login",
        "/auth/register",
        "/favicon.ico",
        "/api/status",
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
        return redirect(get_next_path("/admin"))

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
            return redirect(get_next_path("/admin"))
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
        return redirect(get_next_path("/admin"))

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
                return redirect(get_next_path("/admin"))

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


@app.route("/")
@login_required
def index() -> str:
    fd = CONFIG.get("front_door", {})
    return render_template_string(
        PORTAL_HOME_HTML,
        host=fd.get("host", "127.0.0.1"),
        port=fd.get("port", 5080),
    )


@app.route("/admin")
@login_required
def admin() -> str:
    fd = CONFIG.get("front_door", {})
    return render_template_string(
        DASHBOARD_HTML,
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


@app.route("/api/status")
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
    if path.startswith("api/"):
        if "/app/productmix/" in referer or "/portal/productmix" in referer:
            return _proxy("productmix", path)
        if "/app/ic3/" in referer or "/portal/ic3" in referer:
            return _proxy("ic3", path)

        # Default IC3 API passthrough for direct calls from the inventory UI.
        if path.startswith(("api/products", "api/inventory", "api/invoices")):
            return _proxy("ic3", path)
        return jsonify({"ok": False, "message": "Not found"}), 404

    if "/app/productmix/" in referer or path.startswith("product-mix"):
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
