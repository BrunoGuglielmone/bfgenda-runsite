$ErrorActionPreference = "Stop"

$ProjectPath = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$ServerScript = Join-Path $PSScriptRoot "servidor_agende.py"
$PidFile = Join-Path $ProjectPath "runtime\agende.pid"
$StandbyPidFile = Join-Path $ProjectPath "runtime\bfgenda_espera.pid"
$EnvFile = Join-Path $ProjectPath ".env"
$ErrorLog = Join-Path $ProjectPath "logs\inicio_error.log"

function Show-BFGendaMessage {
    param(
        [string]$Text,
        [string]$Title = "BFGenda",
        [ValidateSet("Information", "Warning", "Error")]
        [string]$Icon = "Information"
    )

    Add-Type -AssemblyName PresentationFramework
    $iconValue = [System.Enum]::Parse(
        [System.Windows.MessageBoxImage],
        $Icon
    )

    [System.Windows.MessageBox]::Show(
        $Text,
        $Title,
        [System.Windows.MessageBoxButton]::OK,
        $iconValue
    ) | Out-Null
}

function Read-EnvValue {
    param(
        [string]$Name,
        [string]$DefaultValue
    )

    if (-not (Test-Path $EnvFile)) {
        return $DefaultValue
    }

    $line = Get-Content $EnvFile -Encoding UTF8 |
        Where-Object {
            $_ -match "^\s*$([regex]::Escape($Name))\s*="
        } |
        Select-Object -First 1

    if (-not $line) {
        return $DefaultValue
    }

    return (($line -split "=", 2)[1]).Trim().Trim('"').Trim("'")
}

function Get-BFGendaProcess {
    if (-not (Test-Path $PidFile)) {
        return $null
    }

    $storedPid = Get-Content $PidFile -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $storedPid) {
        return $null
    }

    return Get-Process -Id $storedPid -ErrorAction SilentlyContinue
}

function Stop-BFGendaStandby {
    if (-not (Test-Path $StandbyPidFile)) {
        return
    }

    $standbyPid = Get-Content $StandbyPidFile -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($standbyPid) {
        $standbyProcess = Get-Process `
            -Id $standbyPid `
            -ErrorAction SilentlyContinue

        if ($standbyProcess) {
            Stop-Process `
                -Id $standbyProcess.Id `
                -Force `
                -ErrorAction SilentlyContinue

            try {
                $standbyProcess.WaitForExit(5000) | Out-Null
            }
            catch {
                # El proceso ya pudo haber finalizado.
            }
        }
    }

    Remove-Item `
        $StandbyPidFile `
        -Force `
        -ErrorAction SilentlyContinue

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $listener = Get-NetTCPConnection `
            -LocalPort 8000 `
            -State Listen `
            -ErrorAction SilentlyContinue

        if (-not $listener) {
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw "El servidor de espera no liberó el puerto 8000."
}


function Find-GoogleChrome {
    $chromeCommand = Get-Command "chrome.exe" -ErrorAction SilentlyContinue

    if ($chromeCommand -and (Test-Path $chromeCommand.Source)) {
        return $chromeCommand.Source
    }

    $candidatePaths = @()

    if ($env:LOCALAPPDATA) {
        $candidatePaths += Join-Path `
            $env:LOCALAPPDATA `
            "Google\Chrome\Application\chrome.exe"
    }

    if ($env:ProgramFiles) {
        $candidatePaths += Join-Path `
            $env:ProgramFiles `
            "Google\Chrome\Application\chrome.exe"
    }

    if (${env:ProgramFiles(x86)}) {
        $candidatePaths += Join-Path `
            ${env:ProgramFiles(x86)} `
            "Google\Chrome\Application\chrome.exe"
    }

    foreach ($candidatePath in $candidatePaths) {
        if ($candidatePath -and (Test-Path $candidatePath)) {
            return $candidatePath
        }
    }

    $registryPaths = @(
        "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        "Registry::HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    )

    foreach ($registryPath in $registryPaths) {
        if (-not (Test-Path $registryPath)) {
            continue
        }

        try {
            $registeredPath = (Get-Item $registryPath).GetValue("")

            if ($registeredPath -and (Test-Path $registeredPath)) {
                return $registeredPath
            }
        }
        catch {
            # Continúa con la siguiente ubicación disponible.
        }
    }

    return $null
}

function Open-BFGendaBrowser {
    param([string]$Url)

    $preferredBrowser = Read-EnvValue `
        -Name "AGENDE_BROWSER" `
        -DefaultValue "chrome"

    if ($preferredBrowser.Trim().ToLowerInvariant() -eq "chrome") {
        $chromePath = Find-GoogleChrome

        if ($chromePath) {
            Start-Process `
                -FilePath $chromePath `
                -ArgumentList @("--new-tab", $Url)
            return
        }
    }

    # Respaldo: utiliza el navegador predeterminado de Windows.
    Start-Process $Url
}

try {
    if (-not (Test-Path $PythonPath)) {
        throw "No se encontró el entorno virtual de BFGenda."
    }

    if (-not (Test-Path $ServerScript)) {
        throw "No se encontró el iniciador del servidor."
    }

    New-Item -ItemType Directory -Path (Join-Path $ProjectPath "logs") -Force |
        Out-Null
    New-Item -ItemType Directory -Path (Join-Path $ProjectPath "runtime") -Force |
        Out-Null

    $browserUrl = Read-EnvValue `
        -Name "AGENDE_BROWSER_URL" `
        -DefaultValue "http://127.0.0.1:8000/"

    $runningProcess = Get-BFGendaProcess

    if ($runningProcess) {
        Stop-BFGendaStandby
        Open-BFGendaBrowser -Url $browserUrl
        exit 0
    }

    Stop-BFGendaStandby

    if (Test-Path $PidFile) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }

    $process = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @("`"$ServerScript`"") `
        -WorkingDirectory $ProjectPath `
        -WindowStyle Hidden `
        -PassThru

    $ready = $false

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500

        if ($process.HasExited) {
            break
        }

        try {
            $response = Invoke-WebRequest `
                -Uri $browserUrl `
                -UseBasicParsing `
                -TimeoutSec 2

            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                $ready = $true
                break
            }
        }
        catch {
            # El servidor todavía está iniciando.
        }
    }

    if (-not $ready) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }

        throw (
            "BFGenda no pudo iniciar. Revisa el archivo " +
            "logs\servidor.log para conocer el motivo."
        )
    }

    Open-BFGendaBrowser -Url $browserUrl
}
catch {
    New-Item -ItemType Directory -Path (Split-Path -Parent $ErrorLog) -Force |
        Out-Null

    $message = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | $($_.Exception.Message)"
    Add-Content -Path $ErrorLog -Value $message -Encoding UTF8

    Show-BFGendaMessage `
        -Text $_.Exception.Message `
        -Title "No se pudo iniciar BFGenda" `
        -Icon "Error"

    exit 1
}
