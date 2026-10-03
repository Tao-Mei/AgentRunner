param([Parameter(Mandatory = $true)][string]$InstallDir)

$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd([char]'\')
if ((Test-Path -LiteralPath $target) -and
    -not (Test-Path -LiteralPath (Join-Path $target 'runner.exe')) -and
    @(Get-ChildItem -LiteralPath $target -Force).Count) {
    Write-Output 'Choose an empty folder dedicated to AgentRunner.'
    exit 3
}
$running = @(
    Get-Process -Name runner, AgentRunner -ErrorAction SilentlyContinue | Where-Object {
        try {
            $image = $_.Path
            if (-not $image) { return $true }
            $path = [System.IO.Path]::GetFullPath($image)
            return $path.StartsWith($target + '\', [System.StringComparison]::OrdinalIgnoreCase)
        } catch {
            return $true
        }
    }
)
if ($running.Count) {
    $running | ForEach-Object { Write-Output ("Running process: {0} PID={1}" -f $_.ProcessName, $_.Id) }
    exit 2
}
exit 0
