import webbrowser
import subprocess
import time
import os
import sys

# Change to the script directory
script_dir = r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Restaurant Management"
os.chdir(script_dir)

# Start the Flask app in a subprocess
flask_process = subprocess.Popen(
    [r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\venv\Scripts\python.exe", "Payroll - WebVersion.py"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=0x08000000  # CREATE_NO_WINDOW flag
)

# Give Flask a moment to start
time.sleep(2)

# Open the browser to the Flask app
webbrowser.open('http://127.0.0.1:5000')

# Keep the process running
try:
    flask_process.wait()
except KeyboardInterrupt:
    flask_process.terminate()
