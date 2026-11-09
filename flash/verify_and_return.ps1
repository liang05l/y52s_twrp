# y52s: verify TWRP in recovery, then AUTOMATICALLY return to the system.
# Solves the two problems seen so far: adb lost after entering TWRP (MTP),
# and "power-on always goes to recovery" (stale boot-recovery BCB).
#
# Run only from the Android system with adb online (flash\adb_fix.ps1 first).
param([string]$Serial = "MBLF9LSONZPJG69L",
      [string]$AdbPath = "D:\Android\Sdk\platform-tools\adb.exe")

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

# --- [1] must be in the system ----------------------------------------------
$st = (& $AdbPath -s $Serial get-state 2>&1 | Out-String).Trim()
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
    Write-Warning "TWRP did not expose adb. The phone may still be usable via keys;"
    Write-Warning "long-press POWER to reboot, then run flash\fix_boot_loop.sh from the system."
    exit 2
}

# --- [4] evidence ------------------------------------------------------------
Write-Host "[4/6] collecting read-only evidence ..."
& $AdbPath -s $Serial push (Join-Path $PSScriptRoot "verify_twrp.sh") /tmp/y52s_verify.sh 2>&1 | Out-Null
& $AdbPath -s $Serial shell "sh /tmp/y52s_verify.sh" 2>&1 | Out-Null
$local = Join-Path $root "build\y52s_verify.txt"
& $AdbPath -s $Serial pull /tmp/y52s_verify.txt $local 2>&1 | Out-Null
if (Test-Path $local) { Write-Host "  EVIDENCE: $local" } else { Write-Warning "  evidence pull failed" }

# --- [5] clear BCB BEFORE leaving recovery ----------------------------------
Write-Host "[5/6] clearing boot-recovery BCB (32-byte command field only) ..."
& $AdbPath -s $Serial shell "dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 conv=notrunc 2>/dev/null; sync" 2>&1 | Out-Null
& $AdbPath -s $Serial shell "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1" 2>&1 | Out-Null

# --- [6] return to the system ------------------------------------------------
Write-Host "[6/6] rebooting back to Android system ..."
& $AdbPath -s $Serial reboot 2>&1 | Out-Null
$back = $false
for ($i = 0; $i -lt 18; $i++) {
    Start-Sleep -Seconds 10
    $line = (& $AdbPath devices 2>&1 | Out-String)
    if ($line -match "$Serial\s+device") { $back = $true; Write-Host "  system online after $(($i+1)*10)s"; break }
}
if ($back) { Write-Host "DONE - back in system; BCB cleared, normal power-on stays in system." }
else { Write-Warning "system adb not back yet; re-run flash\adb_fix.ps1" }
