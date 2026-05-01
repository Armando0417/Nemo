$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = $ScriptDir
$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($gitCommand) {
    try {
        $gitRoot = (& $gitCommand.Source -C $ScriptDir rev-parse --show-toplevel 2>$null | Select-Object -First 1).Trim()
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($gitRoot)) {
            $RootDir = $gitRoot
        }
    }
    catch {
    }
}
$RootDir = [System.IO.Path]::GetFullPath($RootDir)
$FrontendDir = Join-Path $RootDir 'CodexVault'
$BackendDir = Join-Path $RootDir 'CodexVaultIndexer'
$BackendVenvDir = Join-Path $BackendDir 'venv'
$BackendPython = Join-Path $BackendVenvDir 'Scripts\python.exe'
$DefaultLibraryPath = 'D:\Wandering_Sea\T7_Branch\Sarcophagus\CV_Tomb'

function Import-EnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }

        if ($trimmed -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            continue
        }

        $name = $matches[1]
        $value = $matches[2].Trim()

        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "Env:$name" -Value $value
    }
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Default
    )

    $item = Get-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
    if ($null -eq $item -or [string]::IsNullOrWhiteSpace($item.Value)) {
        Set-Item -Path "Env:$Name" -Value $Default
        return $Default
    }

    return $item.Value
}

function Get-RequiredCommandPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Missing required command: $Name"
    }

    return $command.Source
}

function Get-ListeningProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    $results = @()
    foreach ($processId in $processIds) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        $results += [pscustomobject]@{
            Id = $processId
            ProcessName = if ($process) { $process.ProcessName } else { 'Unknown' }
            Path = if ($process) { $process.Path } else { '' }
        }
    }

    return $results
}

function Assert-PortAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    $listeners = Get-ListeningProcesses -Port $Port
    if ($listeners.Count -eq 0) {
        return
    }

    $details = ($listeners | ForEach-Object {
        if ($_.Path) {
            "PID $($_.Id) ($($_.ProcessName)) $($_.Path)"
        }
        else {
            "PID $($_.Id) ($($_.ProcessName))"
        }
    }) -join '; '

    throw "$Label port $Port is already in use. $details"
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Resolve-SystemPython {
    $configuredPython = Get-Item -Path 'Env:CODEX_VAULT_PYTHON_BIN' -ErrorAction SilentlyContinue
    if ($configuredPython -and -not [string]::IsNullOrWhiteSpace($configuredPython.Value)) {
        return @{
            FilePath = $configuredPython.Value
            Prefix = @()
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            FilePath = $py.Source
            Prefix = @('-3')
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            FilePath = $python.Source
            Prefix = @()
        }
    }

    throw 'Python was not found. Install Python 3 and ensure `py` or `python` is on PATH.'
}

function Join-ProcessArguments {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    return ($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + $_.Replace('"', '\"') + '"'
        }
        else {
            $_
        }
    }) -join ' '
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = Join-ProcessArguments -Arguments $Arguments
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $process.EnableRaisingEvents = $true

    if (-not $process.Start()) {
        throw "Failed to start $Name"
    }

    $stdoutId = "$Name-stdout-$([guid]::NewGuid())"
    $stderrId = "$Name-stderr-$([guid]::NewGuid())"
    $exitId = "$Name-exit-$([guid]::NewGuid())"

    Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -SourceIdentifier $stdoutId -MessageData $Name -Action {
        if ($EventArgs.Data) {
            Write-Host "[$($event.MessageData)] $($EventArgs.Data)"
        }
    } | Out-Null

    Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -SourceIdentifier $stderrId -MessageData $Name -Action {
        if ($EventArgs.Data) {
            Write-Host "[$($event.MessageData)] $($EventArgs.Data)"
        }
    } | Out-Null

    Register-ObjectEvent -InputObject $process -EventName Exited -SourceIdentifier $exitId -MessageData $Name -Action {
        Write-Host "[$($event.MessageData)] exited with code $($sender.ExitCode)"
    } | Out-Null

    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()

    return @{
        Name = $Name
        Process = $process
        EventIds = @($stdoutId, $stderrId, $exitId)
    }
}

function Stop-ManagedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$ManagedProcess
    )

    foreach ($eventId in $ManagedProcess.EventIds) {
        Unregister-Event -SourceIdentifier $eventId -ErrorAction SilentlyContinue
        Remove-Job -Name $eventId -Force -ErrorAction SilentlyContinue
    }

    $process = $ManagedProcess.Process
    if ($process -and -not $process.HasExited) {
        try {
            $process.Kill($true)
        }
        catch {
            $process.Kill()
        }
        [void]$process.WaitForExit(5000)
    }

    $process.Dispose()
}

Import-EnvFile (Join-Path $BackendDir '.env')
Import-EnvFile (Join-Path $FrontendDir '.env')

$BackendHost = Get-EnvValue 'CODEX_VAULT_BACKEND_HOST' '0.0.0.0'
$BackendPort = Get-EnvValue 'CODEX_VAULT_BACKEND_PORT' '6220'
$FrontendHost = Get-EnvValue 'CODEX_VAULT_FRONTEND_HOST' '0.0.0.0'
$FrontendPort = Get-EnvValue 'CODEX_VAULT_FRONTEND_PORT' '6221'
$null = Get-EnvValue 'CODEX_VAULT_LIBRARY_PATH' $DefaultLibraryPath
$null = Get-EnvValue 'VITE_FLASK_URL' "http://127.0.0.1:$BackendPort"
$null = Get-EnvValue 'READ_URL' "http://127.0.0.1:$FrontendPort/read/"

if (-not (Test-Path -LiteralPath $env:CODEX_VAULT_LIBRARY_PATH)) {
    throw "Library path does not exist: $($env:CODEX_VAULT_LIBRARY_PATH)"
}

Assert-PortAvailable -Port ([int]$BackendPort) -Label 'Backend'
Assert-PortAvailable -Port ([int]$FrontendPort) -Label 'Frontend'

$npmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if ($npmCommand) {
    $npmPath = $npmCommand.Source
}
else {
    $npmPath = Get-RequiredCommandPath 'npm'
}

if (-not (Test-Path -LiteralPath $BackendPython)) {
    Write-Host 'Creating backend virtual environment...'
    $systemPython = Resolve-SystemPython
    Invoke-CheckedProcess -FilePath $systemPython.FilePath -Arguments ($systemPython.Prefix + @('-m', 'venv', $BackendVenvDir)) -WorkingDirectory $BackendDir
}

if (-not (Test-Path -LiteralPath $BackendPython)) {
    throw "Backend virtual environment Python was not created: $BackendPython"
}

try {
    Invoke-CheckedProcess -FilePath $BackendPython -Arguments @('-m', 'pip', '--version') -WorkingDirectory $BackendDir
}
catch {
    Write-Host 'Bootstrapping pip in backend virtual environment...'
    Invoke-CheckedProcess -FilePath $BackendPython -Arguments @('-m', 'ensurepip', '--upgrade') -WorkingDirectory $BackendDir
}

try {
    Invoke-CheckedProcess -FilePath $BackendPython -Arguments @('-m', 'uvicorn', '--version') -WorkingDirectory $BackendDir
}
catch {
    Write-Host 'Installing backend dependencies...'
    Invoke-CheckedProcess -FilePath $BackendPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') -WorkingDirectory $BackendDir
    Invoke-CheckedProcess -FilePath $BackendPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $BackendDir 'requirements.txt')) -WorkingDirectory $BackendDir
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'node_modules'))) {
    Write-Host 'Installing frontend dependencies...'
    Invoke-CheckedProcess -FilePath $npmPath -Arguments @('install') -WorkingDirectory $FrontendDir
}

Write-Host 'Building frontend...'
Invoke-CheckedProcess -FilePath $npmPath -Arguments @('run', 'build') -WorkingDirectory $FrontendDir

$backend = $null
$frontend = $null

try {
    $backend = Start-ManagedProcess -Name 'backend' -FilePath $BackendPython -Arguments @('-m', 'uvicorn', 'main:app', '--host', $BackendHost, '--port', $BackendPort) -WorkingDirectory $BackendDir
    $frontend = Start-ManagedProcess -Name 'frontend' -FilePath $npmPath -Arguments @('run', 'preview', '--', '--host', $FrontendHost, '--port', $FrontendPort) -WorkingDirectory $FrontendDir

    Write-Host ''
    Write-Host "Library root: $($env:CODEX_VAULT_LIBRARY_PATH)"
    Write-Host "Backend URL: http://127.0.0.1:$BackendPort"
    Write-Host "Frontend URL: http://127.0.0.1:$FrontendPort"
    Write-Host 'Press Ctrl+C to stop both services.'
    Write-Host ''

    while ($true) {
        if ($backend.Process.HasExited -or $frontend.Process.HasExited) {
            break
        }

        Start-Sleep -Seconds 1
    }

    if ($backend.Process.HasExited -and $backend.Process.ExitCode -ne 0) {
        throw "Backend exited unexpectedly with code $($backend.Process.ExitCode)"
    }

    if ($frontend.Process.HasExited -and $frontend.Process.ExitCode -ne 0) {
        throw "Frontend exited unexpectedly with code $($frontend.Process.ExitCode)"
    }
}
finally {
    if ($frontend) {
        Stop-ManagedProcess -ManagedProcess $frontend
    }

    if ($backend) {
        Stop-ManagedProcess -ManagedProcess $backend
    }
}
