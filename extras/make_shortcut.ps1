# Creates "SmartKit Studio" shortcuts on the Desktop and in the Start menu (no console window, app icon).
$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $PSScriptRoot
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($py) { $pyw = Join-Path (Split-Path $py) 'pythonw.exe' }
}
if (-not $pyw -or -not (Test-Path $pyw)) {
    Write-Host 'Python was not found. Install Python 3 from python.org (tick "Add python.exe to PATH") and run this again.'
    exit 1
}
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($dir in $places) {
    $lnk = $shell.CreateShortcut((Join-Path $dir 'SmartKit Studio.lnk'))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + (Join-Path $app 'smartkit_app.py') + '"'
    $lnk.WorkingDirectory = $app
    $lnk.IconLocation = (Join-Path $app 'icon.ico') + ',0'
    $lnk.Description = 'SmartKit Studio - build Alesis Strike kits from drum plugins'
    $lnk.Save()
    Write-Host "Shortcut made: $dir\SmartKit Studio.lnk"
}
