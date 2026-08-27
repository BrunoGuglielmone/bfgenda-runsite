$ProjectPath = Split-Path -Parent $PSScriptRoot
$LogsPath = Join-Path $ProjectPath "logs"

New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
Start-Process explorer.exe -ArgumentList "`"$LogsPath`""
