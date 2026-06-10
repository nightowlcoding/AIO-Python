#!/usr/bin/env python
"""Health check for Dexter Assistant after folder move"""

import json
import sys
from pathlib import Path

print("=" * 60)
print("DEXTER ASSISTANT HEALTH CHECK")
print("=" * 60)

base_path = Path('.')
checks_passed = 0
checks_failed = 0

# Check 1: Config file
try:
    config = json.loads((base_path / 'dexter_assistant_config.json').read_text())
    print("[PASS] Config file loads correctly")
    checks_passed += 1
except Exception as e:
    print(f"[FAIL] Config file error: {e}")
    checks_failed += 1

# Check 2: Database file exists
try:
    assert (base_path / 'dexter_assistant_rbac.db').exists()
    print("[PASS] RBAC database file exists")
    checks_passed += 1
except:
    print("[FAIL] RBAC database missing")
    checks_failed += 1

# Check 3: Users file exists
try:
    users = json.loads((base_path / 'dexter_assistant_users.json').read_text())
    print("[PASS] Users file exists and is valid JSON")
    checks_passed += 1
except Exception as e:
    print(f"[FAIL] Users file error: {e}")
    checks_failed += 1

# Check 4: Sub-app directories exist
for app_name in ['ProductMixRestaurantDB', 'Inventory Control 3', 'Manager App']:
    try:
        app_path = base_path / app_name
        assert app_path.is_dir(), f"{app_name} not found"
        app_py = app_path / 'app.py'
        if app_name == 'Manager App':
            app_py = app_path / 'manager_app.py'
        assert app_py.exists(), f"app.py not found in {app_name}"
        print(f"[PASS] {app_name} directory structure OK")
        checks_passed += 1
    except AssertionError as e:
        print(f"[FAIL] {app_name}: {e}")
        checks_failed += 1

# Check 5: Required runtime logs directory
try:
    logs_dir = base_path / 'runtime_logs'
    logs_dir.mkdir(exist_ok=True)
    print("[PASS] Runtime logs directory ready")
    checks_passed += 1
except Exception as e:
    print(f"[FAIL] Runtime logs error: {e}")
    checks_failed += 1

# Check 6: Parent directory references
try:
    parent = Path.cwd().parent
    assert (parent / 'company_data').is_dir(), "company_data not found"
    assert (parent / 'Restaurant Management').is_dir(), "Restaurant Management not found"
    print("[PASS] Parent directory references OK")
    checks_passed += 1
except AssertionError as e:
    print(f"[FAIL] Parent directory error: {e}")
    checks_failed += 1

print("=" * 60)
print(f"Results: {checks_passed} passed, {checks_failed} failed")
print("=" * 60)

if checks_failed == 0:
    print("All health checks passed! System is ready.")
    sys.exit(0)
else:
    print("Some checks failed. Please review above.")
    sys.exit(1)
