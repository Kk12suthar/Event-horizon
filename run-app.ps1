param(
  [switch]$Restart,
  [switch]$SkipHealthCheck
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root 'backend'
$AgentDir = Join-Path $Root 'agent-server'
$FrontendDir = Join-Path $Root 'new-frontend\app'
$LogDir = Join-Path $Root 'logs'

$BackendPort = 8001
$AgentPort = 8010
$FrontendPort = 5174
$HostName = '127.0.0.1'

$Global:ServicesToStart = @()

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step($Message) {
  Write-Host "[EventHorizon] $Message" -ForegroundColor Cyan
}

function Write-Warn($Message) {
  Write-Host "[EventHorizon] $Message" -ForegroundColor Yellow
}

function Find-Command($Preferred, $Fallback) {
  $cmd = Get-Command $Preferred -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $cmd = Get-Command $Fallback -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw "Could not find '$Preferred' or '$Fallback' on PATH."
}

function Get-PortProcessIds([int]$Port) {
  try {
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
  } catch {
    return @()
  }
}

function Stop-Port([int]$Port) {
  $pids = Get-PortProcessIds $Port
  foreach ($processId in $pids) {
    if ($processId -and $processId -ne $PID) {
      Write-Warn "Stopping process $processId on port $Port"
      Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
  }
}

function Start-ServiceProcess($Name, $FilePath, [string[]]$Arguments, $WorkingDirectory, [int]$Port) {
  $existing = Get-PortProcessIds $Port
  if ($existing.Count -gt 0) {
    if ($Restart) {
      Stop-Port $Port
      Start-Sleep -Milliseconds 800
    } else {
      Write-Warn "$Name already appears to be running on port $Port (PID: $($existing -join ', ')). Use -Restart to replace it."
      return $null
    }
  }

  $stdout = Join-Path $LogDir "$Name.out.log"
  $stderr = Join-Path $LogDir "$Name.err.log"
  if (Test-Path $stdout) { Remove-Item $stdout -Force }
  if (Test-Path $stderr) { Remove-Item $stderr -Force }

  Write-Step "Queueing $Name to start on http://$HostName`:$Port"
  
  $service = [PSCustomObject]@{
    Name = $Name
    FilePath = $FilePath
    Arguments = $Arguments
    WorkingDirectory = $WorkingDirectory
    Port = $Port
  }
  $Global:ServicesToStart += $service
  return $null
}

function Wait-Http($Name, $Url, [int]$TimeoutSeconds = 40) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        Write-Step "$Name responded with HTTP $($response.StatusCode): $Url"
        return $true
      }
    } catch {
      Start-Sleep -Milliseconds 700
    }
  } while ((Get-Date) -lt $deadline)

  Write-Warn "$Name did not respond before timeout: $Url"
  return $false
}

function Import-DotEnv($Path) {
  if (-not (Test-Path $Path)) { return }

  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { return }

    $name, $value = $line.Split('=', 2)
    $name = $name.Trim()
    $value = $value.Trim().Trim('"').Trim("'")
    if ($name) {
      [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
  }
}
if (-not (Test-Path (Join-Path $Root '.env'))) {
  Write-Warn "Root .env was not found. Copy .env.example to .env and fill required values for full functionality."
}

Import-DotEnv (Join-Path $Root '.env')

if (-not $env:VITE_BACKEND_URL) {
  $env:VITE_BACKEND_URL = "http://$HostName`:$BackendPort"
}
if (-not $env:VITE_AGENT_URL) {
  $env:VITE_AGENT_URL = "http://$HostName`:$AgentPort"
}
if (-not $env:VITE_ENABLE_DEV_GMAIL_SIGNIN -and $env:ENABLE_DEV_GMAIL_SIGNIN) {
  $env:VITE_ENABLE_DEV_GMAIL_SIGNIN = $env:ENABLE_DEV_GMAIL_SIGNIN
}

if (-not (Test-Path $BackendDir)) { throw "Missing backend directory: $BackendDir" }
if (-not (Test-Path $AgentDir)) { throw "Missing agent-server directory: $AgentDir" }
if (-not (Test-Path $FrontendDir)) { throw "Missing frontend app directory: $FrontendDir" }

$Python = if ($env:EVENTHORIZON_PYTHON) { $env:EVENTHORIZON_PYTHON } else { Find-Command 'python' 'py' }
$Npm = Find-Command 'npm.cmd' 'npm'

Write-Step "Using Python: $Python"
Write-Step "Using npm: $Npm"

$backend = Start-ServiceProcess `
  -Name 'backend' `
  -FilePath $Python `
  -Arguments @('-m','uvicorn','main:app','--host',$HostName,'--port',[string]$BackendPort,'--ws-ping-interval','10','--ws-ping-timeout','30') `
  -WorkingDirectory $BackendDir `
  -Port $BackendPort

$agent = Start-ServiceProcess `
  -Name 'agent-server' `
  -FilePath $Python `
  -Arguments @('-m','uvicorn','main:app','--host',$HostName,'--port',[string]$AgentPort) `
  -WorkingDirectory $AgentDir `
  -Port $AgentPort

$frontend = Start-ServiceProcess `
  -Name 'frontend' `
  -FilePath $Npm `
  -Arguments @('run','dev','--','--host',$HostName,'--port',[string]$FrontendPort,'--strictPort') `
  -WorkingDirectory $FrontendDir `
  -Port $FrontendPort

if ($Global:ServicesToStart.Count -gt 0) {
  $wt = Get-Command wt -ErrorAction SilentlyContinue
  if ($wt) {
    Write-Step "Launching $($Global:ServicesToStart.Count) services in a single Windows Terminal window with tabs..."
    $wtArgs = @()
    for ($i = 0; $i -lt $Global:ServicesToStart.Count; $i++) {
      $s = $Global:ServicesToStart[$i]
      $argStr = $s.Arguments -join ' '
      $cmd = "& '$($s.FilePath)' $argStr"
      $tabArgs = "--title `"$($s.Name)`" -d `"$($s.WorkingDirectory)`" powershell.exe -NoExit -Command `"$cmd`""
      if ($i -eq 0) {
        $wtArgs += $tabArgs
      } else {
        $wtArgs += "; new-tab $tabArgs"
      }
    }
    $finalWtArgs = $wtArgs -join ' '
    Start-Process wt.exe -ArgumentList $finalWtArgs
  } else {
    Write-Warn "Windows Terminal (wt.exe) not found. Falling back to separate PowerShell windows."
    foreach ($s in $Global:ServicesToStart) {
      $argStr = $s.Arguments -join ' '
      $cmd = "Set-Location '$($s.WorkingDirectory)'; `$Host.UI.RawUI.WindowTitle = 'EventHorizon - $($s.Name)'; & '$($s.FilePath)' $argStr"
      Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $cmd
    }
  }
}

if (-not $SkipHealthCheck) {
  Write-Step 'Waiting for services...'
  Wait-Http 'Backend' "http://$HostName`:$BackendPort/api/health/live" | Out-Null
  Wait-Http 'Agent' "http://$HostName`:$AgentPort/health" | Out-Null
  Wait-Http 'Frontend' "http://$HostName`:$FrontendPort" | Out-Null
}

Write-Host ''
Write-Step 'Application URLs'
Write-Host "  Frontend: http://$HostName`:$FrontendPort"
Write-Host "  Backend:  http://$HostName`:$BackendPort"
Write-Host "  Agent:    http://$HostName`:$AgentPort"
Write-Host ''
Write-Step 'Logs'
Write-Host "  $LogDir"
Write-Host ''
Write-Step 'Useful commands'
Write-Host '  Start normally:   powershell -ExecutionPolicy Bypass -File .\run-app.ps1'
Write-Host '  Restart all:      powershell -ExecutionPolicy Bypass -File .\run-app.ps1 -Restart'
Write-Host '  Skip health wait: powershell -ExecutionPolicy Bypass -File .\run-app.ps1 -SkipHealthCheck'
