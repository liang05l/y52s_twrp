# y52s: fix "adb devices is empty / device not found" caused by mixed adb
# versions on this PC. An old adb server (v32, e.g. D:\搞机助手\adb.exe) can
# own port 5037 while the newer client (v41) is used, so `adb devices` reports
# nothing even though the phone enumerates ADB Interface correctly.
#
# This script uses ONLY the verified platform-tools adb (37.0.0 / server v41),
# stops every other adb.exe, then rescans.
param([string]$Serial = "MBLF9LSONZPJG69L")

$Adb = "D:\Android\Sdk\platform-tools\adb.exe"
if (-not (Test-Path $Adb)) { throw "verified adb not found: $Adb" }

Write-Host "[1/4] stopping every adb.exe (all versions) ..."
Get-Process -Name adb -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("  pid={0} path={1}" -f $_.Id, $_.Path)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

Write-Host "[2/4] killing stale server with the verified adb ..."
& $Adb kill-server 2>&1 | Out-Null
Start-Sleep -Seconds 1

Write-Host "[3/4] starting one server ..."
& $Adb start-server 2>&1 | Out-Null
Start-Sleep -Seconds 2

Write-Host "[4/4] devices:"
$list = (& $Adb devices -l 2>&1 | Out-String).Trim()
$list
if ($list -match "$Serial\s+(device|recovery|unauthorized|offline)") {
    $st = $Matches[1]
    Write-Host "STATE = $st"
    switch ($st) {
        "unauthorized" { Write-Host "ACTION: on the phone, tap 'Allow USB debugging' (tick Always allow)." }
        "offline"      { Write-Host "ACTION: re-plug the USB cable, then re-run this script." }
        "device"       { Write-Host "OK: in Android system, adb root via 'su -c' is available." }
        "recovery"     { Write-Host "OK: in TWRP, adb shell is already root." }
    }
} else {
    Write-Host "STATE = NONE"
    Write-Host "Check: cable, USB mode (charge/transfer files), and Windows PnP 'ADB Interface'."
}
Write-Host ""
Write-Host "NOTE: do NOT run the older 33.0.0 adb.exe (from the phone-assistant folder)"
Write-Host "      in parallel -- it restarts the 5037 server and breaks this connection."
