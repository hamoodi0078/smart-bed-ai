Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\PC#####\Desktop\smart bed by me\scripts\start_backend.ps1""", 0, False
WScript.Sleep 3000
WshShell.Run "powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\PC#####\Desktop\smart bed by me\scripts\start_tunnel.ps1""", 0, False
