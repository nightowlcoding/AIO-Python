# AIO App Purpose Guide

This is a plain-English map of your main app files.

## Core Apps

| File | Purpose | Role |
|---|---|---|
| app.py | Web app for daily inventory tracking and order consolidation. | Active |
| ProductMixRestaurantDB/app.py | Multi-restaurant Product Mix system with auth, uploads, and database-backed reporting. | Active |
| Restaurant Management/Inventory Control 3/app.py | Advanced inventory control with bulk invoice processing and forecasting workflows. | Active |
| Restaurant Management/Inventory Control 2/app.py | Older inventory system focused on chicken/product case logic and weighted items. | Legacy/Backup |
| Restaurant Management/Manager App/manager_app.py | Operations hub for employee, payroll, discipline, and daily log workflows. | Active |
| railway_manager_app.py | Deployment launcher/wrapper for the Manager App on Railway. | Active (deploy entry) |

## Payroll Apps

| File | Purpose | Role |
|---|---|---|
| Restaurant Management/Payroll - WebVersion.py | Payroll CSV processor with overtime calculations and Excel export. | Likely production payroll web app |
| Restaurant Management/app_web.py | Similar payroll processing flow and export behavior. | Likely alternate/backup version |

## Desktop Tools (Non-Web)

| File | Purpose | Role |
|---|---|---|
| Automate_Report_gui.py | Tkinter GUI to automate quarterly Excel report generation. | Active tool |
| Tools/application.py | Desktop PDF application/form generator utility. | Utility tool |

## Quick Notes

- You have many mirrored copies of these apps in AIO_Consolidated_* and AIO_Enclosed_Apps.
- Those copies are usually packaging/snapshot mirrors, not your main working source.
- If you want to reduce confusion, treat these as your main entrypoints:
  - ProductMixRestaurantDB/app.py
  - Restaurant Management/Inventory Control 3/app.py
  - Restaurant Management/Manager App/manager_app.py
  - Restaurant Management/Payroll - WebVersion.py

## Next Cleanup Step

Create a small launch index (one file) listing only your approved app entrypoints so you always run the right one.
