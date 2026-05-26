# Manager App - Complete Setup Guide

## 📁 Folder Location
All required files are in: `C:\Users\arnol\OneDrive\Desktop\AIO Programs\AIO Python\Restaurant Management\Manager App`

## ✅ Required Files (All Present)

### Core Application Files
- ✓ `app.py` - Main Flask application (2439 lines)
- ✓ `database.py` - Database operations layer
- ✓ `security.py` - Security utilities (validation, encryption)
- ✓ `manager_app.db` - SQLite database

### Supporting Modules
- ✓ `auth.py`, `auth_enhanced.py`, `auth_helpers.py` - Authentication utilities
- ✓ `data_export.py` - GDPR data export functionality
- ✓ `utils.py` - Helper functions
- ✓ `system_check.py` - System verification

### Configuration
- ✓ `requirements-web.txt` - Python dependencies
- ✓ `app_config.py` - Application configuration

### Templates (All HTML files in templates/ folder)
- ✓ Base: `base.html`, `index.html`
- ✓ Auth: `login.html`, `register.html`, `terms.html`
- ✓ Company: `create_company.html`, `select_company.html`, `dashboard.html`
- ✓ Operations: `daily_log.html`, `cash_manager.html`, `employees.html`
- ✓ Management: `locations.html`, `settings.html`, `users.html`, `reports.html`
- ✓ Utility: `audit_log.html`, `employee_profile.html`
- ✓ Error Pages: `403.html`, `404.html`, `500.html`

### Static Assets
- ✓ `static/css/` - Stylesheets
- ✓ `static/js/` - JavaScript files
- ✓ `static/img/` - Images
- ✓ `static/favicon.ico` - Site icon

## 🚀 Quick Start

### 1. Activate Virtual Environment
```powershell
# From: C:\Users\arnol\OneDrive\Desktop\AIO Programs
& ".venv\Scripts\Activate.ps1"
```

### 2. Navigate to Manager App Folder
```powershell
cd "AIO Python\Restaurant Management\Manager App"
```

### 3. Install Dependencies (if needed)
```powershell
pip install -r requirements-web.txt
```

### 4. Run the Application
```powershell
python app.py
```

### 5. Access the App
Open browser to: `http://127.0.0.1:8000`

## 📦 Dependencies (from requirements-web.txt)

- Flask 3.0.0 - Web framework
- Flask-Login 0.6.3 - User session management
- Flask-Limiter 3.5.1 - Rate limiting
- Werkzeug 3.0.1 - WSGI utilities
- python-dotenv 1.0.0 - Environment variables

## 🗂️ Data Storage Structure

All company data is stored in: `Manager App/company_data/`

```
company_data/
└── {company_id}/
    └── locations/
        └── {location_id}/
            ├── daily_logs/
            │   └── YYYYMMDD_Shift.csv
            └── employees/
                └── FirstName_LastName.json
```

## 🔧 Configuration

### Database Location
Default: `Manager App/manager_app.db`

### Secret Key
Generated automatically on first run

### Session Settings
- Duration: 30 days (if "Remember Me" checked)
- Secure cookies enabled
- HTTPOnly cookies enabled

## 📊 Multi-Location Support

The app supports multiple locations per company:
- Each location has isolated daily logs
- Separate employee records per location
- Location selector on all operational pages
- Reports can filter by location

## 🔐 User Roles

1. **Business Admin** - Full company access
   - Create/edit locations
   - Manage users
   - Access all reports
   - Modify settings

2. **Manager** - Location-specific access
   - View/edit daily logs
   - Manage employees
   - View reports

## 📝 First Time Setup

1. **Register Account**: Navigate to `/register`
2. **Accept Terms**: Review and accept Terms of Service
3. **Create Company**: Set up company with initial location(s)
4. **Add Locations**: Business admins can add more locations via Settings
5. **Add Employees**: Import or manually add employee records
6. **Start Logging**: Begin daily operations tracking

## 🛠️ Troubleshooting

### Database Issues
If database errors occur:
```powershell
# The database will auto-initialize on first run
# If needed, delete manager_app.db and restart app.py
```

### Import Errors
Ensure you're in the Manager App directory when running:
```powershell
pwd  # Should show: ...\Manager App
python app.py
```

### Port Already in Use
If port 8000 is busy:
- Edit `app.py` line ~2480
- Change port number: `app.run(port=8000)`

## 📖 Documentation Files

- `QUICK_START.md` - Quick setup instructions
- `MULTI_LOCATION_DEPLOYMENT.md` - Multi-location features guide
- `MULTI_TENANT_GUIDE.md` - Multi-tenant architecture
- `TESTING_GUIDE.md` - Testing procedures
- `WEB_VERSION_README.md` - Web version specifics

## 🎯 Everything You Need is Here!

This folder contains 100% of what's required to run the Manager App:
- ✅ All Python modules
- ✅ All HTML templates
- ✅ All static assets (CSS, JS, images)
- ✅ Database file
- ✅ Configuration files
- ✅ Documentation

**No external dependencies or files needed from other folders!**

## 🚦 Running the App

From the Manager App folder:
```powershell
# Make sure virtual environment is active (see prompt: (.venv))
python app.py

# Or use the start script:
./start_web.sh  # On Unix/Mac
```

Server will start at: **http://127.0.0.1:8000**

---

**Last Updated**: February 1, 2026  
**App Version**: Multi-Location Web v1.0
