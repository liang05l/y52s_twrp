# y52s: flash/verify TWRP and STAY there by default. The goal is a usable
# TWRP (touch + FBE decrypt + adb), not bouncing back into Android.
# Only when -ReturnToSystem is given does it clear the BCB and reboot back.
param([string]$Serial = "MBLF9LSONZPJG69L",
      [string]$AdbPath = "D:\Android\Sdk\platform-tools\adb.exe",
      [switch]$ReturnToSystem)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

# --- [1] must be in the system ----------------------------------------------
# NOTE: on Windows PowerShell 5.1 a native command's stderr is merged by
# 2>&1, so "adb server is starting..." can pollute get-state. Start the
# server first, then extract ONLY the state token from the output.
& $AdbPath start-server 2>&1 | Out-Null
Start-Sleep -Seconds 1
$rawState = (& $AdbPath -s $Serial get-state 2>&1 | Out-String)
$st = ($rawState -split "`r?`n" |
       Where-Object { $_ -match '^(device|recovery|unauthorized|offline|sideload)$' } |
       Select-Object -Last 1)
if (-not $st) { $st = "unknown" }
if ($st -ne "device") { throw "expected system state 'device', got '$st'" }
Write-Host "[1/6] system online"

# --- [2] reboot into recovery ------------------------------------------------
Write-Host "[2/6] reboot recovery ..."
& $AdbPath -s $Serial reboot recovery 2>&1 | Out-Null

# --- [3] wait for TWRP -------------------------------------------------------
Write-Host "[3/6] waiting for TWRP (MTK may need 60-120s) ..."
$online = $false
for ($i = 0; $i -lt 18; $i++) {
    Start-Sleep -Seconds 10
    $line = (& $AdbPath devices 2>&1 | Out-String)
    if ($line -match "$Serial\s+recovery") { $online = $true; Write-Host "  TWRP online after $(($i+1)*10)s"; break }
    Write-Host "  ... $(($i+1)*10)s"
}
if (-not $online) {
    Write-Warning "TWRP did not expose adb (USB/MTP may have taken over)."
    Write-Warning "The BCB may still say boot-recovery. Try fastboot reboot, then once"
    Write-Warning "back in the system run: flash\fix_boot_loop.sh (clears the BCB)."
    $fb = "D:\Android\Sdk\platform-tools\fastboot.exe"
    if (Test-Path $fb) {
        $fl = (& $fb devices 2>&1 | Out-String)
        if ($fl -match "$Serial\s+fastboot") {
            Write-Warning "device is in fastboot; sending reboot ..."
            & $fb -s $Serial reboot 2>&1 | Out-Null
        }
    }
    exit 2
}

# --- [4] evidence ------------------------------------------------------------
Write-Host "[4/6] collecting read-only evidence ..."
& $AdbPath -s $Serial push (Join-Path $PSScriptRoot "verify_twrp.sh") /tmp/y52s_verify.sh 2>&1 | Out-Null
& $AdbPath -s $Serial shell "sh /tmp/y52s_verify.sh" 2>&1 | Out-Null
$local = Join-Path $root "build\y52s_verify.txt"
& $AdbPath -s $Serial pull /tmp/y52s_verify.txt $local 2>&1 | Out-Null
if (Test-Path $local) { Write-Host "  EVIDENCE: $local" } else { Write-Warning "  evidence pull failed" }

# --- [5] always clear BCB ----------------------------------------------------
# (so a later normal power-on goes to the system, not recovery)
Write-Host "[5/6] clearing boot-recovery BCB (32-byte command field only) ..."
& $AdbPath -s $Serial shell "dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 conv=notrunc 2>/dev/null; sync" 2>&1 | Out-Null
$bcb = (& $AdbPath -s $Serial shell "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n'" 2>&1 | Out-String).Trim()
if ($bcb -match '^0+$' -and $bcb.Length -gt 0) { Write-Host "  BCB cleared (all zero)" }
else { Write-Warning "  BCB readback unexpected: $bcb" }

# --- [6] STAY in TWRP by default --------------------------------------------
if (-not $ReturnToSystem) {
    Write-Host "[6/6] staying in TWRP (this is the deliverable). BCB cleared,"
    Write-Host "      so a later normal reboot will go to the system as usual."
    Write-Host "DONE - evidence in build\y52s_verify.txt"
    exit 0
}
# TWRP turns `adb reboot` into a GUI "confirm reboot" page that stalls the
# command. The measured working method is a device-side kernel sysrq hard
# reboot (bypasses the GUI). Fall back to adb reboot only if sysrq fails.
Write-Host "[6/6] rebooting back to Android system (sysrq hard reboot) ..."
$r = (& $AdbPath -s $Serial shell "echo b > /proc/sysrq-trigger" 2>&1 | Out-String)
Start-Sleep -Seconds 5
$line = (& $AdbPath devices 2>&1 | Out-String)
if ($line -match "$Serial\s+(recovery|device)") {
    Write-Host "  sysrq did not reboot, falling back to adb reboot ..."
    & $AdbPath -s $Serial reboot 2>&1 | Out-Null
}
$back = $false
for ($i = 0; $i -lt 18; $i++) {
    Start-Sleep -Seconds 10
    $line = (& $AdbPath devices 2>&1 | Out-String)
    if ($line -match "$Serial\s+device") { $back = $true; Write-Host "  system online after $(($i+1)*10)s"; break }
}
if ($back) { Write-Host "DONE - back in system; BCB cleared, normal power-on stays in system." }
else { Write-Warning "system adb not back yet; re-run flash\adb_fix.ps1" }
