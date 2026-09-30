param([Parameter(Mandatory = $true)][string]$InstallDir)

$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd([char]'\')
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
