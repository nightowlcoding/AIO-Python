# Manager App - Web Version

Professional Flask web application for restaurant management with mobile-responsive design.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd "Manager App"
pip install -r requirements-web.txt
```

### 2. Run Development Server

```bash
python manager_app.py
```

The app will be available at: **http://localhost:5000**

### 3. Access from Mobile/Tablet

On your phone or tablet, connect to the same WiFi network and visit:
```
http://YOUR_COMPUTER_IP:5000
```

To find your IP address:
- **Mac**: System Preferences → Network
- **Windows**: `ipconfig` in Command Prompt
- **Linux**: `ip addr` or `ifconfig`

## ✨ Features

### Authentication & Security
- ✅ User registration with email verification
- ✅ Secure login with PBKDF2 password hashing (100K iterations)
- ✅ Session timeout (30 minutes inactivity)
- ✅ Account lockout (5 failed attempts)
- ✅ Terms of Service acceptance
- ✅ GDPR-compliant data handling
- ✅ Role-based access control

### Multi-Tenant Support
- ✅ Multiple companies per user
- ✅ Company selection interface
- ✅ Data isolation between companies
- ✅ Role-based permissions (business_admin, manager, staff)

### Mobile-Responsive Design
- ✅ Works on desktop, tablet, and mobile
- ✅ Bootstrap 5 responsive layout
- ✅ Touch-optimized interface
- ✅ Mobile-friendly navigation

### Coming Soon (Integrated from Desktop App)
- ⏳ Daily Operations Log
- ⏳ Cash Manager
- ⏳ Employee Management
- ⏳ Reports & Analytics
- ⏳ Data Import/Export

## 🏗️ Project Structure

```
Manager App/
├── app.py                 # Flask application
├── database.py            # Database operations (reused from desktop)
├── security.py            # Security validation (reused from desktop)
├── requirements-web.txt   # Python dependencies
├── templates/             # HTML templates
│   ├── base.html         # Base layout
│   ├── index.html        # Landing page
│   ├── login.html        # Login page
│   ├── register.html     # Registration
│   ├── dashboard.html    # Main dashboard
│   ├── select_company.html
│   ├── create_company.html
│   ├── terms.html
│   ├── daily_log.html
│   ├── cash_manager.html
│   ├── employees.html
│   └── reports.html
└── static/                # Static assets
    ├── css/
    │   └── style.css     # Custom styles
    └── js/
        └── app.js        # Client-side JavaScript
```

## 🔐 Security Features

1. **Password Security**
   - PBKDF2-HMAC-SHA256 hashing
   - 100,000 iterations
   - Unique salt per user
   - Password strength validation

2. **Session Management**
   - 30-minute inactivity timeout
   - 8-hour maximum session duration
   - Secure HTTP-only cookies
   - CSRF protection

3. **Account Protection**
   - 5 failed login attempts = 15-minute lockout
   - Real-time attempt warnings
   - Account recovery options

4. **Data Protection**
   - HTTPS recommended for production
   - Encrypted data transmission
   - GDPR-compliant data export
   - Audit logging

## 📱 Mobile Access

### Option 1: Local Network (Development)

1. Run the app: `python app.py`
2. Find your computer's IP address
3. On mobile, visit: `http://YOUR_IP:5000`

**Limitations**: Only works on same WiFi network

### Option 2: Production Deployment (Recommended)

Deploy to a cloud platform for access from anywhere:

#### A. Railway (Easiest - $5/month)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Deploy
railway up
```

#### B. Heroku ($7/month)

```bash
# Create Procfile
echo "web: gunicorn app:app" > Procfile

# Install gunicorn
pip install gunicorn
pip freeze > requirements-web.txt

# Deploy
heroku login
heroku create my-manager-app
git push heroku main
```

#### C. AWS Elastic Beanstalk (Scalable)

```bash
# Install EB CLI
pip install awsebcli

# Initialize
eb init -p python-3.11 manager-app

# Create environment
eb create manager-app-prod

# Deploy
eb deploy
```

## 🌐 Environment Variables

Create a `.env` file for production:

```bash
SECRET_KEY=your-secret-key-here-use-secrets.token-hex-32
DATABASE_URL=postgresql://user:pass@host:5432/dbname  # For cloud PostgreSQL
FLASK_ENV=production
SESSION_COOKIE_SECURE=True  # Requires HTTPS
```

## 🔄 Migration from Desktop App

The web version uses the same database structure as the desktop app. To migrate:

1. Your existing `database.py` is already compatible
2. All users, companies, and data are preserved
3. Both desktop and web versions can run simultaneously
4. No data loss or conversion needed

## 🚀 Production Deployment Checklist

- [ ] Set strong `SECRET_KEY` in environment variables
- [ ] Enable HTTPS (SSL certificate)
- [ ] Set `FLASK_ENV=production`
- [ ] Use production WSGI server (gunicorn, uWSGI)
- [ ] Configure proper database (PostgreSQL recommended)
- [ ] Set up database backups
- [ ] Configure reverse proxy (nginx)
- [ ] Enable monitoring (Sentry, Datadog)
- [ ] Set up logging
- [ ] Configure CORS for your domain
- [ ] Test mobile responsiveness
- [ ] Security audit

## 📊 Tech Stack

- **Backend**: Flask 3.0 (Python)
- **Frontend**: Bootstrap 5 + Vanilla JavaScript
- **Database**: SQLite (dev) / PostgreSQL (production)
- **Authentication**: Flask-Login
- **Security**: PBKDF2, session management, CSRF protection
- **Icons**: Bootstrap Icons
- **Responsive**: Mobile-first design

## 🎨 Customization

### Change Colors

Edit `static/css/style.css`:

```css
:root {
    --primary-color: #0d6efd;  /* Change to your brand color */
    --secondary-color: #6c757d;
}
```

### Add Your Logo

Replace the icon in `templates/base.html`:

```html
<a class="navbar-brand" href="/">
    <img src="/static/images/logo.png" height="30"> Manager App
</a>
```

## 🐛 Troubleshooting

### "Address already in use"
Another app is using port 5000. Change the port in `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=8000)
```

### "Cannot connect from mobile"
1. Check firewall settings
2. Ensure same WiFi network
3. Use computer's actual IP (not 127.0.0.1)

### "Session expired"
Sessions timeout after 30 minutes. This is a security feature.

## 📚 Next Steps

1. **Complete Feature Integration**
   - Integrate Daily Log from desktop app
   - Add Cash Manager interface
   - Implement Employee Management
   - Add Reports & Analytics

2. **Progressive Web App (PWA)**
   - Add service worker for offline support
   - Create app manifest for "Add to Home Screen"
   - Implement push notifications

3. **Real-time Features**
   - WebSocket integration for live updates
   - Multi-user concurrent editing
   - Real-time notifications

4. **API Development**
   - RESTful API for mobile apps
   - API authentication (JWT)
   - API documentation (Swagger)

## 📄 License

© 2025 Manager App. All rights reserved.

## 🆘 Support

For issues or questions, contact support or check the documentation.

---

**Ready to deploy?** Follow the production deployment guide above! 🚀
