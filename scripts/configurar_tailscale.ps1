param(
    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
    $ProjectPath = Split-Path -Parent $PSScriptRoot
}

$ProjectPath = [System.IO.Path]::GetFullPath($ProjectPath)
$EnvFile = Join-Path $ProjectPath ".env"

function Show-BFGendaMessage {
    param(
        [string]$Text,
        [string]$Title = "BFGenda",
        [ValidateSet("Information", "Warning", "Error")]
        [string]$Icon = "Information"
    )

    try {
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
    catch {
        Write-Host $Text
    }
}

function Get-IPv4Addresses {
    $addresses = @()

    try {
        $addresses = Get-NetIPAddress `
            -AddressFamily IPv4 `
            -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*"
            } |
            Select-Object -ExpandProperty IPAddress
    }
    catch {
        # Si Get-NetIPAddress no est? disponible, se mantienen
        # ?nicamente localhost y la direcci?n de Tailscale.
    }

    return @($addresses)
}

try {
    if (-not (Test-Path $EnvFile)) {
        throw "No se encontr? el archivo privado .env de BFGenda."
    }

    $tailscaleCommand = Get-Command `
        "tailscale.exe" `
        -ErrorAction SilentlyContinue

    if (-not $tailscaleCommand) {
        throw "Tailscale no est? instalado o no est? disponible."
    }

    $tailscaleIp = (
        & $tailscaleCommand.Source ip -4 2>$null |
        Select-Object -First 1
    )

    if ([string]::IsNullOrWhiteSpace($tailscaleIp)) {
        throw (
            "Tailscale no tiene una direcci?n IPv4 activa. " +
            "Abre Tailscale y confirma que la PC est? conectada."
        )
    }

    $tailscaleIp = $tailscaleIp.Trim()

    if ($tailscaleIp -notmatch '^100\.\d{1,3}\.\d{1,3}\.\d{1,3}$') {
        throw (
            "La direcci?n obtenida no parece pertenecer a " +
            "la red privada de Tailscale."
        )
    }

    $tailscaleStatus = & $tailscaleCommand.Source status --json 2>$null |
        ConvertFrom-Json

    $tailscaleDnsName = [string]$tailscaleStatus.Self.DNSName
    $tailscaleDnsName = $tailscaleDnsName.Trim().TrimEnd(".")

    if ([string]::IsNullOrWhiteSpace($tailscaleDnsName)) {
        throw (
            "No se pudo obtener el nombre DNS privado de Tailscale."
        )
    }

    $tailscaleOrigin = "https://$tailscaleDnsName"

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupPath = "$EnvFile.backup-$timestamp"

    Copy-Item `
        -Path $EnvFile `
        -Destination $backupPath `
        -Force

    $lines = Get-Content $EnvFile -Encoding UTF8
    $key = "AGENDE_ALLOWED_HOSTS"
    $hosts = @(
        "127.0.0.1",
        "localhost"
    )

    foreach ($address in Get-IPv4Addresses) {
        if ($address -notin $hosts) {
            $hosts += $address
        }
    }

    if ($tailscaleIp -notin $hosts) {
        $hosts += $tailscaleIp
    }

    if ($tailscaleDnsName -notin $hosts) {
        $hosts += $tailscaleDnsName
    }

    $newLine = "$key=$($hosts -join ',')"
    $updated = @()
    $found = $false

    foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($key))\s*=") {
            if (-not $found) {
                $updated += $newLine
                $found = $true
            }

            continue
        }

        $updated += $line
    }

    if (-not $found) {
        $updated += $newLine
    }

    $csrfKey = "AGENDE_CSRF_TRUSTED_ORIGINS"
    $csrfLine = "$csrfKey=$tailscaleOrigin"
    $csrfUpdated = @()
    $csrfFound = $false

    foreach ($line in $updated) {
        if ($line -match "^\s*$([regex]::Escape($csrfKey))\s*=") {
            if (-not $csrfFound) {
                $csrfUpdated += $csrfLine
                $csrfFound = $true
            }

            continue
        }

        $csrfUpdated += $line
    }

    if (-not $csrfFound) {
        $csrfUpdated += $csrfLine
    }

    $csrfUpdated |
        Set-Content `
            -Path $EnvFile `
            -Encoding UTF8

    Write-Host (
        "[OK] Tailscale configurado para BFGenda: " +
        $tailscaleIp
    ) -ForegroundColor Green

    Write-Host (
        "[OK] Dominio HTTPS privado: " +
        $tailscaleDnsName
    ) -ForegroundColor Green

    Write-Host (
        "[OK] Copia preventiva creada: " +
        (Split-Path $backupPath -Leaf)
    ) -ForegroundColor Green

    Show-BFGendaMessage `
        -Text (
            "BFGenda qued? preparada para Tailscale.`n`n" +
            "Acceso HTTPS privado:`n$tailscaleOrigin/`n`n" +
            "Reinicia BFGenda para aplicar la configuraci?n."
        ) `
        -Title "Tailscale configurado" `
        -Icon "Information"
}
catch {
    Show-BFGendaMessage `
        -Text $_.Exception.Message `
        -Title "No se pudo configurar Tailscale" `
        -Icon "Error"

    exit 1
}
