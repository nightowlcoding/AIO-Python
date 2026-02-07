#!/bin/bash

# Inventory Control System Startup Script

echo "🏪 Starting Inventory Control System..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# Check if required packages are installed
echo "📦 Checking dependencies..."
python3 -c "import flask, pandas" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "📥 Installing required packages..."
    pip install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies. Please run: pip install flask pandas"
        exit 1
    fi
fi

# Check if CSV file exists
if [ ! -f "Update - Sept 13th.csv" ]; then
    echo "⚠️  Warning: Product CSV file not found!"
    echo "   Please add 'Update - Sept 13th.csv' to this folder"
    echo ""
fi

# Start the application
echo "✅ All dependencies ready"
echo "🚀 Starting server..."
echo ""
python3 app.py
