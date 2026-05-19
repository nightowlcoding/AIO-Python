Set objShell = CreateObject("WScript.Shell")

' Define paths
payrollScript = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\payroll_launcher.py"
pythonwExe = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\venv\Scripts\pythonw.exe"
desktopPath = objShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\Payroll.lnk"
iconPath = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\payroll_icon.ico"

' Create the shortcut object
Set objShortcut = objShell.CreateShortCut(shortcutPath)

' Configure the shortcut - uses pythonw.exe for GUI apps (no console window)
objShortcut.TargetPath = pythonwExe
objShortcut.Arguments = """" & payrollScript & """"
objShortcut.WorkingDirectory = "C:\Users\arnol\OneDrive\Desktop\AIO-Python\"
objShortcut.Description = "Launch Payroll Application"
objShortcut.WindowStyle = 0

' Set the icon
objShortcut.IconLocation = iconPath & ",0"

' Save the shortcut
objShortcut.Save

WScript.Echo "Desktop shortcut created: " & shortcutPath
