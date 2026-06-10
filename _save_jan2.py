import json, base64, pathlib

content_file = pathlib.Path(r'c:\Users\arnol\AppData\Roaming\Code\User\workspaceStorage\f4239f815908adac15096141461bc91a\GitHub.copilot-chat\chat-session-resources\b0abe7e1-70aa-4be7-ac84-4841f3c6aee1\toolu_bdrk_016nQP29WNJCsJE3q6zZHrox__vscode-1779839389004\content.txt')
txt = content_file.read_text(encoding='utf-8').strip()
if txt.startswith('Result: '): txt = txt[8:]
if txt.startswith('"') and txt.endswith('"'):
    txt = txt[1:-1]
    txt = txt.replace('\\"', '"').replace('\\\\', '\\')

data = json.loads(txt)
out_dir = pathlib.Path(r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-02_Big House Burgers')
out_dir.mkdir(parents=True, exist_ok=True)

# Save CSV
csv_text = data.get('csvText', '')
if csv_text:
    csv_path = out_dir / 'Closed_Shifts_2026-01-02_Big_House_Burgers.csv'
    csv_path.write_text(csv_text, encoding='utf-8')
    print(f'CSV: {len(csv_text)} chars saved')

# Save XLSX files (skip duplicates - keep largest for same employee)
seen = {}
for name, rpt in data.get('reports', {}).items():
    if 'b64' not in rpt:
        print(f'SKIP {name}: {rpt.get("skipped") or rpt.get("error")}')
        continue
    size = rpt['size']
    if name in seen and seen[name]['size'] >= size:
        print(f'SKIP {name} duplicate (smaller: {size} vs {seen[name]["size"]})')
        continue
    seen[name] = {'size': size, 'b64': rpt['b64']}

for name, info in seen.items():
    fname = name.title().replace(' ', '_') + '_2026-01-02.xlsx'
    fpath = out_dir / fname
    fpath.write_bytes(base64.b64decode(info['b64']))
    print(f'SAVED {fname}: {info["size"]:,} bytes')

print(f'\nDone — {len(seen)} files saved to {out_dir}')
