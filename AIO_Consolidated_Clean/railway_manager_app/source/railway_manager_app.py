import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MANAGER_APP_DIR = os.path.join(BASE_DIR, "Restaurant Management", "Manager App")

os.chdir(BASE_DIR)
os.makedirs(os.path.join(BASE_DIR, "company_data"), exist_ok=True)

if MANAGER_APP_DIR not in sys.path:
    sys.path.insert(0, MANAGER_APP_DIR)

from manager_app import app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
