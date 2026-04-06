Set WshShell = CreateObject("WScript.Shell")
' 0 parametresi pencereyi gizli (hidden) olarak çalıştırır
WshShell.Run "py """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptPosition) & "\hotkey_launcher.py""", 0, False
