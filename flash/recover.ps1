# y52s: one-shot recovery after a bad vbmeta experiment.
# Waits for adb, clears the boot-recovery BCB, flashes back the last image
# whose touch + USB were verified on the device, and reports.
param(
  [string]$Serial = "MBLF9LSONZPJG69L",
  [string]$AdbPath = "D:\Android\Sdk\platform-tools\adb.exe",
  [string]$Image = "C:\Users\30345\WorkBuddy\y52s_rec\build\recovery_touch_ok.img",
  [int]$WaitSeconds = 240
)

$ErrorActionPreference = "Continue"
Write-Host "target image : $Image"
if (-not (Test-Path $Image)) { throw "image missing: $Image" }

# --- [1] wait for any usable adb state ---------------------------------------
$fastboot = "D:\Android\Sdk\platform-tools\fastboot.exe"
$deadline = (Get-Date).AddSeconds($WaitSeconds)
$state = ""
$bootSent = $false
while ((Get-Date) -lt $deadline) {
    $raw = (& $AdbPath devices 2>&1 | Out-String)
    if ($raw -match "$Serial\s+(device|recovery)") {
        $state = $Matches[1]
        break
    }
    # If the phone is stuck in fastboot, ask it to boot normally once.
    $fb = (& $fastboot devices 2>&1 | Out-String)
    if (-not $bootSent -and $fb -match $Serial) {
        Write-Host "  fastboot detected -> sending 'fastboot reboot' once"
        & $fastboot -s $Serial reboot 2>&1 | Out-Null
        $bootSent = $true
    }
    Write-Host "  waiting for adb ... ($($raw.Trim()))"
    Start-Sleep -Seconds 8
}
if ($state -eq "") {
    Write-Warning "device never came online in $WaitSeconds s"
    Write-Host "ACTION: long-press POWER 10+ s to force power-off, then power on normally;"
    Write-Host "        or hold VOL-UP + POWER to enter fastboot. Then re-run this script."
    exit 2
}
Write-Host "[1/3] online in state: $state"

# --- [2] clear BCB -----------------------------------------------------------
$devScript = Join-Path $PSScriptRoot "recover_clear_bcb.sh"
& $AdbPath -s $Serial push $devScript /tmp/y52s_recover_bcb.sh 2>&1 | Out-Null
$bcb = (& $AdbPath -s $Serial shell "sh /tmp/y52s_recover_bcb.sh" 2>&1 | Out-String)
$bcb.Trim()
if ($bcb -notmatch "BCB_CLEAR_DONE") { Write-Warning "BCB clear output unexpected" }
Write-Host "[2/3] BCB cleared (normal power-on will boot into the system)"

# --- [3] flash back the verified image ---------------------------------------
Write-Host "[3/3] flashing back the verified touch-working image ..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot "flash_recovery.ps1") -Image $Image
Write-Host "RECOVERY_IMAGE_SHA256:"
Get-Content ($Image + ".sha256") -ErrorAction SilentlyContinue
Write-Host "DONE. Do NOT reboot to recovery until you decide to; the system boots normally now."
