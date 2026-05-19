# Start Here: Main AIO Apps

This guide is non-destructive.
It does not delete, move, or rename anything.

## Critical Apps (Top Priority)

These are your most important apps:

1. ProductMixRestaurantDB
- File: ProductMixRestaurantDB/app.py

2. Inventory Control 3
- File: Restaurant Management/Inventory Control 3/inventory_control3_launcher.py

## Main Apps To Use

1. Product Mix Database
- File: ProductMixRestaurantDB/app.py
- Run:
```powershell
./venv/Scripts/python.exe "ProductMixRestaurantDB/app.py"
```

2. Inventory Control 3 (Primary)
- File: Restaurant Management/Inventory Control 3/inventory_control3_launcher.py
- Run:
```powershell
./venv/Scripts/python.exe "Restaurant Management/Inventory Control 3/inventory_control3_launcher.py"
```

3. Manager App (Operations)
- File: Restaurant Management/Manager App/manager_app.py
- Run:
```powershell
./venv/Scripts/python.exe "Restaurant Management/Manager App/manager_app.py"
```

4. Payroll Web Version
- File: Restaurant Management/Payroll - WebVersion.py
- Run:
```powershell
./venv/Scripts/python.exe "Restaurant Management/Payroll - WebVersion.py"
```

## Quick Launcher (Optional)

Use this helper script to avoid typing paths:
- Tools/launch_main_apps.ps1

Run it from repo root:
```powershell
powershell -ExecutionPolicy Bypass -File "Tools/launch_main_apps.ps1"
```

## Notes

- All other app.py files are mostly mirrors, backups, or older variants.
- If you are unsure which app to run, use only the 4 above.
- This setup intentionally does not modify your existing files or folders.
