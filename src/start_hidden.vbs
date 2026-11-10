' start_hidden.vbs — launches run.bat with no console window at all.
Dim fso, dir
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("Wscript.Shell").Run "cmd /c """ & dir & "\run.bat""", 0, False
