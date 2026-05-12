Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonExe = scriptDir & "\.venv\Scripts\pythonw.exe"
launcher = scriptDir & "\launcher.pyw"

If Not fileSystem.FileExists(pythonExe) Then
    MsgBox "Missing virtual environment. Run setup first: pip install -r requirements.txt", 16, "Anki Voice Field"
    WScript.Quit 1
End If

shell.Run """" & pythonExe & """ """ & launcher & """ --start-minimized", 0, False
