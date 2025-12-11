Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "D:\pacs\telesoftweb\run_nginx.bat" & Chr(34), 0
Set WshShell = Nothing