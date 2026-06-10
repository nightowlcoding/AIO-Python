import pathlib, requests

hex_file = pathlib.Path(r'c:\Users\arnol\AppData\Roaming\Code\User\workspaceStorage\f4239f815908adac15096141461bc91a\GitHub.copilot-chat\chat-session-resources\b0abe7e1-70aa-4be7-ac84-4841f3c6aee1\toolu_bdrk_019cUe1ESCWjNVz4RLZfZ4kC__vscode-1779839388983\content.txt')
txt = hex_file.read_text(encoding='utf-8').strip()
if txt.startswith('Result: '):
    txt = txt[8:]
# strip surrounding quotes if present
if txt.startswith('"') and txt.endswith('"'):
    txt = txt[1:-1]
txt = txt.strip()

cookie = bytes.fromhex(txt).decode('utf-8')
out = pathlib.Path(r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Tools\toast_cookies.txt')
out.write_text(cookie, encoding='utf-8')
print(f'Saved {len(cookie)} chars to toast_cookies.txt')
print('Preview:', cookie[:100])

# Quick test using Session with proper cookie jar (handles Set-Cookie updates)
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'text/csv,*/*',
                  'Referer': 'https://www.toasttab.com/restaurants/admin/reports/home'})
# Parse cookie string into the session's cookie jar (so Set-Cookie responses update it)
for part in cookie.split(';'):
    part = part.strip()
    if '=' in part:
        name, _, value = part.partition('=')
        s.cookies.set(name.strip(), value.strip(), domain='.toasttab.com', path='/')

# Prime step - plain navigation (NOT DataTables/AJAX) to update session
prime = s.get(
    'https://www.toasttab.com/restaurants/admin/reports/closedshifts',
    params={'reportDateStart': '01-02-2026', 'reportDateEnd': '01-02-2026'},
    timeout=20
)
print(f'Prime: HTTP {prime.status_code}')
new_session = s.cookies.get("TOAST_SESSION", domain=".toasttab.com") or ''
print(f'TOAST_SESSION after prime: ...{new_session[40:120]}...')
# Check if employee filter is cleared
has_emp = 'reportEmployeeId' in new_session and 'reportEmployeeId=&' not in new_session
print(f'Employee filter still present: {has_emp}')
# Now download CSV
r = s.get(
    'https://www.toasttab.com/restaurants/admin/reports/closedshifts',
    params={'excel': 'true', 'reportDateStart': '01-02-2026', 'reportDateEnd': '01-02-2026'},
    timeout=20
)
print(f'CSV: HTTP {r.status_code}, {len(r.content)} bytes')
print('First 100 bytes:', r.content[:100])
