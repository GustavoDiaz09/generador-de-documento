' Lanzador silencioso del Generador de Protocolos (sin cmd, sin parpadeo).
' Uso: doble clic sobre este archivo, o acceso directo a el.
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
base = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = base
WshShell.Run """" & base & "\run_generador.py""", 0, False