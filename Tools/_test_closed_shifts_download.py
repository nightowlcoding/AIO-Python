"""
Test: two-step approach to download Closed Shifts CSV for May 22.
Step 1: DataTables AJAX request to update the session state
Step 2: Download CSV export
"""
import requests

COOKIE_STR = '_gcl_au=1.1.1571235137.1777130336; lastRestaurantGuid="7b6ea663-6c82-4a7d-b305-ea7d1512a8ff"; PLAY_LANG="en_US"; TOAST_SESSION="6efd300f505f603893f05395f369945ef1fc979a-reportName=orders&reportTimeEnd=&reportTenderSyncStatus=&uGuid=6a941995-bd32-474d-aee1-f4d8a7e84972&reportTimeRange=-2&reportEmployeeId=&reportVoided=&rUserId=100000008243765218&reportDateRange=custom&reportAutoClosed=&___AT=3a56198dc2dda0c21f319f7805de28349c9be5a4&reportShard=&reportScheduled=&___TS=2095110092404&reportState=&reportGroupIds=100000005969371643&reportSource=&reportRevenueCenter=&ele=45&reportDiningOption=&reportDateStart=05-21-2026&reportDiscount=&reportTimeStart=&reauthenticationTime=1779744339585&rId=61477000000000000&reportServiceArea=&reportDateEnd=05-21-2026&reportService=&rGuid=7b6ea663-6c82-4a7d-b305-ea7d1512a8ff&reportItemTags=&msGuid=70d84ae9-ab06-4f1a-83d2-f047d0c80e0a&___ID=f417eb0d-b0a3-4d1d-9f0e-2c05232b86fc&username=arnoldrjr%40gmail.com&reportTaxExempt="'

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.toasttab.com/restaurants/admin/reports/home',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest',
    'Cookie': COOKIE_STR,
})

# Step 1: DataTables AJAX request for May 22 to update session state
params_dt = {
    'reportDateStart': '05-22-2026',
    'reportDateEnd': '05-22-2026',
    'sEcho': '1',
    'iDisplayStart': '0',
    'iDisplayLength': '25',
    'iSortingCols': '0',
}
print("Step 1: DataTables AJAX request...")
r1 = session.get('https://www.toasttab.com/restaurants/admin/reports/closedshifts',
                 params=params_dt, timeout=30)
print(f"  Status: {r1.status_code}")
print(f"  Content-Type: {r1.headers.get('Content-Type')}")
print(f"  Content length: {len(r1.content)}")
print(f"  Set-Cookie: {r1.headers.get('Set-Cookie', '(none)')[:200]}")
print(f"  First 300 chars: {r1.text[:300]}")
print()

# Check if session cookie was updated
updated_session = None
for cookie in r1.cookies:
    if cookie.name == 'TOAST_SESSION':
        updated_session = cookie.value
        print(f"  NEW TOAST_SESSION found!")
        break

print()

# Step 2: Download CSV
print("Step 2: Download CSV export...")
r2 = session.get('https://www.toasttab.com/restaurants/admin/reports/closedshifts',
                 params={'excel': 'true'}, timeout=30)
print(f"  Status: {r2.status_code}")
print(f"  Content-Type: {r2.headers.get('Content-Type')}")
print(f"  Content length: {len(r2.content)}")
print(f"  First 300 chars: {r2.text[:300]}")
