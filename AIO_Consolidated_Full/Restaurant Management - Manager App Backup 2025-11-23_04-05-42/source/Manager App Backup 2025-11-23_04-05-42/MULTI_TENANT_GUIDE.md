# Multi-Tenant Manager App - Complete Guide

## 🎯 Overview

The Manager App has been transformed into a **multi-tenant system** that supports:
- ✅ Multiple restaurants/companies
- ✅ Multiple users per company
- ✅ Role-based access control
- ✅ Business admin capabilities
- ✅ Company-specific data isolation
- ✅ Audit logging

---

## 🚀 Getting Started

### First-Time Setup

1. **Launch the App**
   ```bash
   python "Manager App/auth.py"
   ```

2. **Create Your Account**
   - Click "Register Here"
   - Fill in your details:
     - Full Name
     - Username (minimum 3 characters)
     - Email
     - Phone (optional)
     - Password (minimum 6 characters)
   - Click "Create Account"

3. **Set Up Your Company**
   - Enter company information:
     - Company Name (required)
     - Address, Phone, Email
     - Website, Tax ID
     - Upload logo (optional)
   - Click "Create Company"
   
4. **You're Now a Business Admin!**
   - Full control over your company
   - Can add users and locations
   - Access all features

---

## 👥 User Roles

### 🔵 Business Admin
**Full Control**
- Manage company settings
- Add/remove users
- Assign roles and permissions
- Create locations
- View audit logs
- Access all features

### 🟢 Manager
**Operations Control**
- Daily log management
- Employee management
- Reports access
- Cash management
- Limited administrative functions

### 🟡 Staff
**Basic Access**
- Daily log entry
- Personal reports
- Limited features

### 🔴 Custom Roles
- Assignable permissions
- Granular access control

---

## 🏢 Managing Companies

### As Business Admin

#### Company Settings
1. From Dashboard → "Company Settings"
2. Update:
   - Company name
   - Contact information
   - Logo
   - Tax ID
3. Click "Save Changes"

#### Adding Users
1. Dashboard → "User Management"
2. Click "➕ Add User"
3. Enter user details
4. Assign role:
   - Business Admin
   - Manager
   - Staff
5. Set permissions (optional)

#### Managing Locations
1. Dashboard → "Locations"
2. Add multiple restaurant locations
3. Assign managers to each location
4. Track location-specific data

---

## 🔐 Security Features

### Authentication
- ✅ Secure password hashing (SHA-256)
- ✅ Session management
- ✅ Auto-logout on close
- ✅ Login attempt tracking

### Data Isolation
- ✅ Company-specific data directories
- ✅ Role-based access control
- ✅ Permission system
- ✅ Audit trail

### Audit Logging
Every action is logged:
- User logins/logouts
- Company creation/updates
- User management
- Data modifications
- Timestamps and IP tracking

---

## 📊 Database Structure

### Tables

**companies**
- Company information
- Settings and preferences
- Logo and branding
- Created/updated timestamps

**users**
- User credentials (hashed)
- Profile information
- System admin flag
- Activity tracking

**user_companies**
- User-company relationships
- Role assignments
- Permissions
- Access control

**locations**
- Multi-location support
- Location-specific managers
- Address and contact info

**audit_log**
- Complete activity history
- User actions
- Timestamps
- Details and IP addresses

---

## 📁 Data Organization

### Company Data Structure
```
~/Documents/AIO Python/
├── Manager App/
│   ├── auth.py              # Login/Registration
│   ├── dashboard.py         # Main Dashboard
│   ├── database.py          # Database Manager
│   ├── session.py           # Session Handler
│   ├── manager_app.db       # SQLite Database
│   └── [feature apps]
│
└── company_data/
    ├── [company-uuid-1]/
    │   ├── daily_logs/
    │   ├── reports/
    │   ├── employees/
    │   └── backups/
    │
    └── [company-uuid-2]/
        ├── daily_logs/
        └── ...
```

Each company has isolated data storage!

---

## 🎨 User Interface

### Login Screen
- Username/Password
- "Remember Me" option
- Register link
- Clean, modern design

### Registration
- Full name, email, username
- Secure password (min 6 chars)
- Phone number (optional)
- Immediate company setup

### Company Setup
- Company details form
- Logo upload
- Skip option (setup later)
- Visual feedback

### Dashboard
**Top Bar:**
- Company name
- User name and role
- Switch Company (if multiple)
- Settings
- Logout

**Quick Actions:**
- 📝 Daily Log
- 💰 Cash Manager
- 📈 Reports
- 📥 Import Data

**Employee Management:**
- 📋 Employee List
- 🎯 Employee Grading

**Business Admin (if applicable):**
- 🏢 Company Settings
- 👤 User Management
- 📍 Locations
- 📊 Audit Log

---

## 🔄 Switching Companies

Users can belong to multiple companies!

1. Click "🔄 Switch Company" in dashboard
2. Select desired company
3. Dashboard refreshes with new company data
4. All features use selected company's data

---

## 💡 Use Cases

### Single Restaurant Owner
1. Create account
2. Set up one company
3. Add employees as users (optional)
4. Use all features for your restaurant

### Multi-Location Owner
1. Create account
2. Set up company
3. Add each location
4. Assign managers to locations
5. View consolidated or location-specific data

### Restaurant Group
1. Business admin creates company
2. Adds managers for each restaurant
3. Each manager has their own access
4. Centralized reporting and control

### Consultant/Accountant
1. Create account once
2. Get added to multiple client companies
3. Switch between clients easily
4. Access each company's data separately

---

## 🛠️ Technical Details

### Session Management
- Session stored in `session.json`
- Auto-loads on app start
- Persists across restarts
- Cleared on logout

### Database
- SQLite for simplicity
- ACID compliance
- Foreign key constraints
- Automatic indexing

### Security
- Password hashing with SHA-256
- No plain-text passwords stored
- Session tokens
- SQL injection protection

---

## 📈 Migration Guide

### Existing Data
Your existing data is safe! 

**First Login:**
1. Register with new system
2. Create company
3. Existing files remain in original location
4. New company gets separate directory

**Data Migration (Optional):**
1. Copy existing data to new company directory
2. Or continue using original directory
3. Update file paths in code if needed

---

## 🎯 Best Practices

### For Business Admins

1. **Set Up Properly**
   - Complete all company information
   - Upload professional logo
   - Add contact details

2. **User Management**
   - Use appropriate roles
   - Don't make everyone admin
   - Regular access reviews

3. **Security**
   - Use strong passwords
   - Don't share credentials
   - Monitor audit logs

4. **Data Organization**
   - Regular backups
   - Clean old data periodically
   - Document procedures

### For All Users

1. **Passwords**
   - Minimum 8 characters
   - Mix letters, numbers, symbols
   - Don't reuse passwords

2. **Logging Out**
   - Always logout when done
   - Especially on shared computers

3. **Data Entry**
   - Double-check entries
   - Use consistent formatting
   - Save regularly (auto-save enabled)

---

## 🚨 Troubleshooting

### Can't Login
- ✅ Check username spelling
- ✅ Caps Lock off for password
- ✅ Contact admin if account locked

### Missing Features
- ✅ Check your role/permissions
- ✅ Contact business admin
- ✅ Ensure company selected

### Data Not Showing
- ✅ Verify correct company selected
- ✅ Check date filters
- ✅ Refresh the view

### Error Messages
- ✅ Read error carefully
- ✅ Check input validation
- ✅ Contact support with error details

---

## 📞 Support

### Getting Help

1. **In-App Help**
   - Tooltips on buttons
   - Status messages
   - Error explanations

2. **Documentation**
   - This guide
   - IMPROVEMENTS.md
   - Code comments

3. **Contact**
   - Business admin (for users)
   - System administrator
   - Developer support

---

## 🔮 Roadmap

### Coming Soon

**Phase 1: User Features**
- ✅ Email verification
- ✅ Password reset
- ✅ Profile pictures
- ✅ Two-factor authentication

**Phase 2: Company Features**
- ✅ Multi-location support (full)
- ✅ Custom permissions builder
- ✅ Company branding customization
- ✅ Subscription management

**Phase 3: Analytics**
- ✅ Cross-location reports
- ✅ User activity analytics
- ✅ Performance dashboards
- ✅ Export to external systems

**Phase 4: Mobile**
- ✅ Mobile-optimized interface
- ✅ Native mobile apps
- ✅ Push notifications
- ✅ Offline mode

---

## 📝 Quick Reference

### Keyboard Shortcuts
- `Ctrl+L` - Focus login field
- `Ctrl+S` - Save (in forms)
- `Esc` - Close window
- `Enter` - Submit form

### File Locations
- Database: `Manager App/manager_app.db`
- Session: `Manager App/session.json`
- Company Data: `company_data/[company-id]/`
- Backups: `company_data/[company-id]/backups/`

### Default Paths
```python
from session import get_session
session = get_session()

# Get current company's data directory
data_dir = session.get_data_dir()

# Check permissions
if session.is_business_admin():
    # Admin-only code
    pass
```

---

## ✨ Features Summary

### ✅ Implemented
- Multi-tenant architecture
- User authentication & registration
- Company management
- Role-based access control
- Session persistence
- Audit logging
- Company settings
- User management UI
- Dashboard with quick actions
- Auto-save (5 minutes)
- Automatic backups
- Keyboard shortcuts
- Input validation
- Error handling

### 🔄 In Progress
- Location management (full implementation)
- Custom permissions editor
- Audit log viewer
- Advanced reporting

### ⏳ Planned
- Email notifications
- Password reset
- Two-factor auth
- Mobile app
- API integrations

---

**Version:** 2.0.0  
**Last Updated:** November 19, 2025  
**Status:** Production Ready 🚀
