$wshell = New-Object -ComObject wscript.shell
Start-Sleep -Milliseconds 300

# Clear filename and type new one
$wshell.SendKeys('^a')
Start-Sleep -Milliseconds 100
$wshell.SendKeys('Emileigh_Salinas_2026-05-19.xlsx')
Start-Sleep -Milliseconds 200

# Navigate to folder via Ctrl+L (address bar)
$wshell.SendKeys('^l')
Start-Sleep -Milliseconds 100
$wshell.SendKeys('C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports\2026-05-19_Big House Burgers')
Start-Sleep -Milliseconds 100
$wshell.SendKeys('{ENTER}')
Start-Sleep -Milliseconds 500

# Click Save
$wshell.SendKeys('%s')
Start-Sleep -Milliseconds 500

Write-Host 'Save operation triggered'
