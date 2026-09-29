param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Folder,
    [int]$DelayMs = 0,
    [switch]$Fail
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Folder | Out-Null
Set-Content -LiteralPath (Join-Path $Folder "$Name.started") -Value ([DateTime]::UtcNow.ToString('o'))
if ($DelayMs -gt 0) { Start-Sleep -Milliseconds $DelayMs }
if ($Fail) {
    Write-Error "$Name failed by probe request"
    exit 7
}
Set-Content -LiteralPath (Join-Path $Folder "$Name.done") -Value ([DateTime]::UtcNow.ToString('o'))
Write-Output "$Name completed"
