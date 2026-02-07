#!/bin/bash

# Dexter Restaurant Management Assistant - Web Version Launcher
# Quick script to start the Flask web server

echo "🚀 Starting Dexter Restaurant Management Assistant Web Server..."
echo ""

cd "$(dirname "$0")"

# Activate virtual environment
source ../.venv/bin/activate

# Set development environment
export FLASK_ENV=development
export FLASK_APP=manager_app.py

# Get local IP address for mobile access
if command -v ipconfig getifaddr en0 &> /dev/null; then
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")
else
    LOCAL_IP="localhost"
fi

echo "✅ Web server starting..."
echo ""
echo "📱 Access the app from:"
echo "   • Computer:  http://localhost:8000"
echo "   • Mobile:    http://$LOCAL_IP:8000"
echo ""
echo "⌨️  Press CTRL+C to stop the server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Start Flask development server
python manager_app.py
