import requests
import time
import json

endpoints = [
    "http://127.0.0.1:5080/api/products",
    "http://127.0.0.1:5080/api/inventory/list",
    "http://127.0.0.1:5080/api/invoices/import-log",
    "http://127.0.0.1:5003/api/invoices/import-log"
]

def smoke_test():
    for url in endpoints:
        print(f"Testing {url}...")
        for i in range(15):
            try:
                resp = requests.get(url, timeout=5)
                print(f"Status: PASS (Code: {resp.status_code})")
                try:
                    data = resp.json()
                    snippet = data[0] if isinstance(data, list) and len(data) > 0 else data
                    print("Snippet:", json.dumps(snippet, indent=2)[:500])
                except:
                    print("Response is not JSON or empty")
                break
            except Exception as e:
                if i == 14:
                    print(f"Status: FAIL - {str(e)}")
                time.sleep(2)
        print("-" * 20)

if __name__ == "__main__":
    smoke_test()
