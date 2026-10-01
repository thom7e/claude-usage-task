Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
folder = fso.GetParentFolderName(WScript.ScriptFullName)
py = q & "C:\Program Files\Python313\pythonw.exe" & q
script = q & folder & "\usage_tray.py" & q
shell.Run py & " " & script, 0, False
