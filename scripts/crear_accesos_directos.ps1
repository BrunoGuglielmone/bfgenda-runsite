param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = Split-Path -Parent $PSScriptRoot
}

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    throw "No se pudo determinar la carpeta principal de BFGenda."
}

$ProjectPath = [System.IO.Path]::GetFullPath($ProjectPath)
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$PowerShellPath = (Get-Command powershell.exe).Source
$Shell = New-Object -ComObject WScript.Shell

function New-PowerShellShortcut {
    param(
        [string]$Name,
        [string]$ScriptPath,
        [string]$Description,
        [string]$IconLocation
    )

    $shortcutPath = Join-Path $DesktopPath "$Name.lnk"
    $shortcut = $Shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $PowerShellPath
    $shortcut.Arguments = (
        "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass " +
        "-File `"$ScriptPath`""
    )
    $shortcut.WorkingDirectory = $ProjectPath
    $shortcut.Description = $Description
    $shortcut.IconLocation = $IconLocation
    $shortcut.Save()
}

$startScript = Join-Path $ProjectPath "scripts\iniciar_agende.ps1"
$stopScript = Join-Path $ProjectPath "scripts\detener_agende.ps1"
$logsScript = Join-Path $ProjectPath "scripts\abrir_registros.ps1"
$IconPath = Join-Path $ProjectPath "agenda\static\agenda\img\branding\bfgenda-simbolo-xl.ico"

$LegacyShortcutNames = @(
    "Agende",
    "Detener Agende",
    "Registros de Agende"
)

foreach ($legacyName in $LegacyShortcutNames) {
    $legacyPath = Join-Path $DesktopPath "$legacyName.lnk"

    if (Test-Path $legacyPath) {
        Remove-Item $legacyPath -Force
    }
}

New-PowerShellShortcut `
    -Name "BFGenda" `
    -ScriptPath $startScript `
    -Description "Iniciar y abrir BFGenda" `
    -IconLocation "$IconPath,0"

New-PowerShellShortcut `
    -Name "Detener BFGenda" `
    -ScriptPath $stopScript `
    -Description "Detener el servidor privado de BFGenda" `
    -IconLocation "$IconPath,0"

New-PowerShellShortcut `
    -Name "Registros de BFGenda" `
    -ScriptPath $logsScript `
    -Description "Abrir los registros de actividad y errores" `
    -IconLocation "$IconPath,0"

Write-Host "Accesos directos creados en: $DesktopPath" -ForegroundColor Green
