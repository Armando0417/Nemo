param(
	[switch]$InitMailboxes,
	[switch]$CheckConfig
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction Stop
$configPath = Join-Path $projectRoot "titanrelay.json"
$serverPath = Join-Path $projectRoot "titanrelay_server.py"

$args = @($serverPath, "--config", $configPath)
if ($InitMailboxes) {
	$args += "--init-mailboxes"
}
if ($CheckConfig) {
	$args += "--check-config"
}

& $python.Source @args
