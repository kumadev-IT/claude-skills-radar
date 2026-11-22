# Skills Radar setup for Windows.
#   .\setup-radar.ps1            -> hourly background refresh + Desktop & Start Menu shortcut
#   .\setup-radar.ps1 -Uninstall -> remove both
param([switch]$Uninstall, [int]$EveryMinutes = 60)

$ErrorActionPreference = 'Stop'
$repo      = $PSScriptRoot
$taskName  = 'SkillsRadarRefresh'
$lnkName   = 'Skills Radar.lnk'
$lnkPaths  = @(
  (Join-Path ([Environment]::GetFolderPath('Desktop')) $lnkName),
  (Join-Path ([Environment]::GetFolderPath('Programs')) $lnkName)
)

if ($Uninstall) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  $lnkPaths | ForEach-Object { if (Test-Path $_) { Remove-Item $_ -Confirm:$false } }
  Write-Output 'Skills Radar removed.'
  return
}

# 1. Background refresh: pythonw runs without flashing a console window.
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) { throw 'pythonw.exe not found on PATH.' }
$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$repo\tracker.py`"" -WorkingDirectory $repo
$trigger  = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
              -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Description 'Refreshes the Skills Radar ranking (tracker.py).' -Force | Out-Null

# 2. App-style window: Edge --app gives a chromeless, resizable widget window.
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw 'Microsoft Edge not found.' }
$url  = 'file:///' + ((Join-Path $repo 'dashboard.html') -replace '\\', '/')
$wsh  = New-Object -ComObject WScript.Shell
foreach ($p in $lnkPaths) {
  $s = $wsh.CreateShortcut($p)
  $s.TargetPath   = $edge
  $s.Arguments    = "--app=`"$url`" --window-size=520,860"
  $s.IconLocation = "$edge,0"
  $s.Description  = 'Skills Radar: trending Claude skills'
  $s.Save()
}
Write-Output "Scheduled '$taskName' every $EveryMinutes min. Shortcut 'Skills Radar' added to Desktop and Start Menu."
