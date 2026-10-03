param(
    [switch]$SkipInstaller,
    [ValidatePattern('^[a-z0-9-]+$')][string]$BuildSlot = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$distName = if ($BuildSlot) { ".dist-$BuildSlot" } else { '.dist' }
$distRoot = Join-Path $PSScriptRoot $distName
$stageRoot = Join-Path $distRoot 'runner'
$desktopDistRoot = Join-Path $distRoot 'desktop'
$buildName = if ($BuildSlot) { ".build-$BuildSlot" } else { '.build' }
$buildRoot = Join-Path $PSScriptRoot $buildName
$originalPath = $env:PATH

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Create .venv and install .[desktop] plus PyInstaller before building.'
}

Push-Location -LiteralPath $projectRoot
try {
    # PyInstaller searches PATH for native DLLs. Keep unrelated apps (for
    # example Poppler's incompatible ICU) out of the Qt bundle.
    $env:PATH = @((Split-Path -Parent $pythonExe), "$env:WINDIR\System32", $env:WINDIR) -join ';'
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --console `
        --name runner --paths $projectRoot --exclude-module PySide6 --icon "$projectRoot\agentrunner\assets\agentrunner.ico" `
        --add-data "$projectRoot\agentrunner\ui.html;agentrunner" `
        --distpath $distRoot --workpath (Join-Path $buildRoot 'runner') `
        --specpath $buildRoot (Join-Path $PSScriptRoot 'runner_exe.py')
    if ($LASTEXITCODE -ne 0) { throw "Console build failed: $LASTEXITCODE" }

    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name AgentRunner --paths $projectRoot --icon "$projectRoot\agentrunner\assets\agentrunner.ico" `
        --add-data "$projectRoot\agentrunner\ui.html;agentrunner" `
        --add-data "$projectRoot\agentrunner\assets;agentrunner/assets" `
        --distpath $desktopDistRoot --workpath (Join-Path $buildRoot 'desktop') `
        --specpath $buildRoot (Join-Path $PSScriptRoot 'desktop_exe.py')
    if ($LASTEXITCODE -ne 0) { throw "Desktop build failed: $LASTEXITCODE" }
    $desktopBundle = Join-Path $desktopDistRoot 'AgentRunner'
    $icu = Join-Path $desktopBundle '_internal\icuuc.dll'
    if ((Test-Path -LiteralPath $icu) -and (Get-Item -LiteralPath $icu).Length -gt 500000) {
        throw "Unexpected non-Windows ICU DLL in desktop bundle: $icu"
    }
    Copy-Item -LiteralPath (Join-Path $desktopBundle 'AgentRunner.exe') -Destination $stageRoot -Force
    Copy-Item -Path (Join-Path $desktopBundle '_internal\*') -Destination (Join-Path $stageRoot '_internal') -Recurse -Force
} finally {
    $env:PATH = $originalPath
    Pop-Location
}

if (-not $SkipInstaller) {
    $compiler = 'C:\Program Files (x86)\NSIS\makensis.exe'
    if (-not (Test-Path -LiteralPath $compiler)) { throw "NSIS compiler missing: $compiler" }
    & $compiler '/INPUTCHARSET' 'UTF8' "/DROOT=$projectRoot" "/DSTAGE=$stageRoot" "/DOUT=$distRoot" `
        (Join-Path $PSScriptRoot 'installer.nsi')
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed: $LASTEXITCODE" }
}

Write-Output "Build ready: $stageRoot"
