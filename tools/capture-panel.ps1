# Learn the arcade panel: it asks you to press each control (the sticks, the buttons, the pinball flippers, the spinner,
# the trackball, the flight stick), shows what it saw, and saves the result to runs\panel-capture-<time>.json.
#
#   .\tools\capture-panel.ps1                          # everything, in order
#   .\tools\capture-panel.ps1 -Section flippers        # only the flipper buttons (also: p1, p2, p2stick, spinner, trackball, flight)
#   .\tools\capture-panel.ps1 -Idle 10                 # touch nothing: which controls chatter on their own
#
# While it waits you can skip a control with S (this window, or the Logitech keyboard), go back with B, stop and save with Q.
param([string]$Section = "", [int]$Idle = 0, [double]$Timeout = 25)
$root = Split-Path $PSScriptRoot -Parent
$python = @("$root\.venv\Scripts\python.exe", "$root\..\ai-arcade\.venv\Scripts\python.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = "python" }
$arguments = @("$root\tools\guided_capture.py", "--timeout", $Timeout)
if ($Section) { $arguments += @("--section", $Section) }
if ($Idle -gt 0) { $arguments += @("--idle", $Idle) }
Push-Location "$root\tools"
try { & $python @arguments } finally { Pop-Location }
