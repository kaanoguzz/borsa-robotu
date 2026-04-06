$projectName = "Borsa Robotu"
$projectPath = "C:\Users\EmreOğuz\Desktop\Borsa Robotu"
$launcherPath = Join-Path $projectPath "baslat.bat"
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "$projectName.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $launcherPath
$Shortcut.WorkingDirectory = $projectPath
$Shortcut.Save()

Write-Host "✅ Masaüstü kısayolu başarıyla oluşturuldu: $shortcutPath"
