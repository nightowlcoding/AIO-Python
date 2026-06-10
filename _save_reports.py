import json, base64, pathlib

p = pathlib.Path(r'c:\Users\arnol\AppData\Roaming\Code\User\workspaceStorage\f4239f815908adac15096141461bc91a\GitHub.copilot-chat\chat-session-resources\b0abe7e1-70aa-4be7-ac84-4841f3c6aee1\toolu_bdrk_01BBuKKibBHxhH1onwfJfXie__vscode-1779839388949\content.txt')
d = pathlib.Path(r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-01-01_Big House Burgers')
d.mkdir(parents=True, exist_ok=True)

txt = p.read_text(encoding='utf-8').strip()
# Strip "Result: " prefix if present
if txt.startswith('Result: '):
    txt = txt[len('Result: '):]
data = json.loads(txt)

noah_b = base64.b64decode(data['noah']['b64'])
sarah_b = base64.b64decode(data['sarah']['b64'])

(d / 'Noah_Robledo_2026-01-01.xlsx').write_bytes(noah_b)
(d / 'Sarah_Moralez_2026-01-01.xlsx').write_bytes(sarah_b)
print('Noah:', len(noah_b), 'bytes saved')
print('Sarah:', len(sarah_b), 'bytes saved')
