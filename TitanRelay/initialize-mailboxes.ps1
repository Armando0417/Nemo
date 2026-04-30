$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $projectRoot "start-titanrelay.ps1") -InitMailboxes
