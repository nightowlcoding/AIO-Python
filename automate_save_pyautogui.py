import pyautogui
import time

# Give user time to see what's happening
time.sleep(0.5)

# Click on the filename field to ensure it's active
# The field appears to be at approximately x=700, y=502 based on the screenshot
pyautogui.click(700, 502)
time.sleep(0.3)

# Select all text in the field
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.2)

# Type the new filename
pyautogui.typewrite('Emileigh_Salinas_2026-05-19.xlsx', interval=0.01)
time.sleep(0.3)

# Now navigate to the folder - use Ctrl+L to open location bar
pyautogui.hotkey('ctrl', 'l')
time.sleep(0.3)

# Type the folder path
# Need to use direct path typing
path = r'C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers'
pyautogui.typewrite(path, interval=0.01)
time.sleep(0.3)

# Press Enter to navigate to that folder
pyautogui.press('enter')
time.sleep(0.5)

# Click the Save button - Alt+S is the keyboard shortcut
pyautogui.hotkey('alt', 's')
time.sleep(1)

print("Save operation completed")
