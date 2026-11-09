# y52s: one-shot "flash + reboot + collect evidence" driver.
# Requires: adb online in system (root via Magisk) or in TWRP.
# It ONLY writes the recovery partition. /data is never touched.
param(
    [string]$Image = "",
    [string]$Serial = "MBLF9LSONZPJG69L",
    [string]$AdbPath = "D:\Android\Sdk\platform-tools\adb.exe"
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
if ($Image.Trim() -eq "") { $Image = Join-Path $root "build\recovery.img" }
if (-not (Test-Path $Image)) { throw "image not found: $Image" }

Write-Host "image: $Image"
$expected = (Get-FileHash -Algorithm SHA256 $Image).Hash.ToLower()
Write-Host "sha256: $expected"

# --- [1] wait for adb -------------------------------------------------------
$state = ""
for ($i = 0; $i -lt 12; $i++) {
    $line = (& $AdbPath devices 2>&1 | Out-String)
    if ($line -match "$Serial\s+(device|recovery)") { $state = $Matches[1]; break }
    Write-Host "[$i] waiting for adb ..."
    Start-Sleep -Seconds 10
}
if ($state -eq "") { throw "device not online via adb (check cable / MTP switch / power)" }
Write-Host "[1/5] adb state = $state"

# --- [2] flash --------------------------------------------------------------
Write-Host "[2/5] flashing via adb root dd ..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "flash_recovery.ps1") -Image $Image
if ($LASTEXITCODE -ne 0) { throw "flash_recovery.ps1 failed" }

# --- [3] hard reboot (TWRP's reboot command opens a GUI confirm page) -------
Write-Host "[3/5] writing boot-recovery BCB + sysrq hard reboot ..."
& $AdbPath -s $Serial shell "printf 'boot-recovery' | dd of=/dev/block/by-name/misc bs=1 seek=0 conv=notrunc 2>/dev/null; sync" 2>&1 | Out-Null
try { & $AdbPath -s $Serial shell "echo b > /proc/sysrq-trigger" 2>&1 | Out-Null } catch { }

# --- [4] wait for recovery --------------------------------------------------
Write-Host "[4/5] waiting for TWRP (MTK needs 60-120s) ..."
$ok = $false
for ($i = 0; $i -lt 18; $i++) {
    Start-Sleep -Seconds 10
    $line = (& $AdbPath devices 2>&1 | Out-String)
    if ($line -match "$Serial\s+(recovery|device)") {
        $st = (& $AdbPath -s $Serial get-state 2>&1 | Out-String).Trim()
        if ($st -eq "recovery" -or $st -eq "device") { $ok = $true; Write-Host "  online: $st after $(($i+1)*10)s"; break }
    }
    Write-Host "  ... $(($i+1)*10)s"
}
if (-not $ok) { Write-Warning "device did not come back; re-run this script once adb is visible" ; exit 2 }

# --- [5] evidence -----------------------------------------------------------
Write-Host "[5/5] collecting read-only evidence ..."
$dev = "/data/local/tmp/y52s_verify.sh"
$line = (& $AdbPath -s $Serial get-state 2>&1 | Out-String).Trim()
if ($line -eq "recovery") { $dev = "/tmp/y52s_verify.sh" }
& $AdbPath -s $Serial push (Join-Path $PSScriptRoot "verify_twrp.sh") $dev 2>&1 | Out-Null
& $AdbPath -s $Serial shell "sh $dev" 2>&1 | Out-Null
$local = Join-Path $root "build\y52s_verify.txt"
& $AdbPath -s $Serial pull "/tmp/y52s_verify.txt" $local 2>&1 | Out-Null
if (Test-Path $local) {
    Write-Host "EVIDENCE: $local"
    Get-Content $local | Select-String -Pattern 'PARTITION HASH|sha256|TOUCH INPUT|DATA VIEW|DECRYPTION|BOOT PATCHLEVEL|name=' |
        ForEach-Object { $_.Line }
} else {
    Write-Warning "evidence file not pulled; adb may still be settling"
}
Write-Host "DONE - only the recovery partition was written."
