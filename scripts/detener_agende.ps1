param(
    [switch]$Silent,

    [ValidateRange(0, 30)]
    [int]$DelaySeconds = 0
)

$ErrorActionPreference = "Stop"

$ProjectPath = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectPath "runtime\agende.pid"
$StandbyPidFile = Join-Path $ProjectPath "runtime\bfgenda_espera.pid"
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$StandbyScript = Join-Path $PSScriptRoot "servidor_espera.py"

function Show-BFGendaMessage {
    param(
        [string]$Text,
        [string]$Title = "BFGenda",
        [ValidateSet("Information", "Warning", "Error")]
        [string]$Icon = "Information"
    )

    if ($Silent) {
        return
    }

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

function Get-BFGendaStandbyProcess {
    if (-not (Test-Path $StandbyPidFile)) {
        return $null
    }

    $standbyPid = Get-Content $StandbyPidFile -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $standbyPid) {
        return $null
    }

    return Get-Process -Id $standbyPid -ErrorAction SilentlyContinue
}

function Start-BFGendaStandby {
    $existingProcess = Get-BFGendaStandbyProcess

    if ($existingProcess) {
        return
    }

    Remove-Item `
        $StandbyPidFile `
        -Force `
        -ErrorAction SilentlyContinue

    if (-not (Test-Path $PythonPath)) {
        throw "No se encontró Python para iniciar el mensaje de espera."
    }

    if (-not (Test-Path $StandbyScript)) {
        throw "No se encontró scripts\\servidor_espera.py."
    }

    $process = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @("`"$StandbyScript`"") `
        -WorkingDirectory $ProjectPath `
        -WindowStyle Hidden `
        -PassThru

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 250

        if ($process.HasExited) {
            break
        }

        try {
            $response = Invoke-WebRequest `
                -Uri "http://127.0.0.1:8000/" `
                -UseBasicParsing `
                -TimeoutSec 2

            if (
                $response.StatusCode -eq 200 -and
                $response.Headers["Server"] -match "BFGenda-Espera"
            ) {
                return
            }
        }
        catch {
            # El servidor de espera todavía está iniciando.
        }
    }

    throw "No se pudo iniciar el mensaje de BFGenda cerrada."
}


if ($DelaySeconds -gt 0) {
    Start-Sleep -Seconds $DelaySeconds
}

if (-not (Test-Path $PidFile)) {
    Start-BFGendaStandby
    Show-BFGendaMessage -Text "BFGenda ya se encuentra detenido."
    exit 0
}

$storedPid = Get-Content $PidFile -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $storedPid) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Start-BFGendaStandby
    Show-BFGendaMessage -Text "BFGenda ya se encuentra detenido."
    exit 0
}

$process = Get-Process -Id $storedPid -ErrorAction SilentlyContinue

if (-not $process) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Start-BFGendaStandby
    Show-BFGendaMessage -Text "BFGenda ya se encuentra detenido."
    exit 0
}

try {
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit(5000) | Out-Null
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue

    Start-BFGendaStandby

    Show-BFGendaMessage -Text "BFGenda se detuvo correctamente."
}
catch {
    Show-BFGendaMessage `
        -Text "No se pudo detener BFGenda: $($_.Exception.Message)" `
        -Title "Error al detener BFGenda" `
        -Icon "Error"
    exit 1
}
