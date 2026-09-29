param(
    [Parameter(Mandatory = $true)][string]$Folder
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Folder | Out-Null
$marker = Join-Path $Folder 'flaky.attempt'
$count = if (Test-Path -LiteralPath $marker) { [int](Get-Content -LiteralPath $marker) } else { 0 }
$count++
Set-Content -LiteralPath $marker -Value $count
if ($count -eq 1) { Write-Error 'intentional first failure'; exit 7 }
Set-Content -LiteralPath (Join-Path $Folder 'flaky.done') -Value 'ok'
