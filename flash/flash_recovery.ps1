# ===========================================================================
# y52s - write recovery.img with an adb/root COMMAND (no card-flash zip).
# "卡刷" is a FEATURE of the TWRP being fixed; this script is only the channel
# used to put the fixed recovery.img onto the device.
#
# Verified environment 2026-11-08:
#   adb    D:\Android\Sdk\platform-tools\adb.exe (37.0.0)
#   serial MBLF9LSONZPJG69L   root: Magisk uid=0
#   target /dev/block/by-name/recovery -> /dev/block/sdc1, size 100663296 B
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\flash\flash_recovery.ps1 -Image .\build\recovery.img
# Optional: -AdbPath <path> -Serial <serial> -PartSize <bytes>
#
# Safety: pads the image to the exact partition size so the whole partition
# sha256 can be verified after writing; refuses unknown system versions;
# writes ONLY the recovery partition; no format/wipe of /data.
# ===========================================================================
param(
    [string]$Image   = "",
    [string]$AdbPath = "",
    [string]$Serial  = "MBLF9LSONZPJG69L",
    [int]$PartSize   = 100663296
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ($Image.Trim() -eq "") { $Image = Join-Path $ProjectRoot "build\recovery.img" }
if (-not (Test-Path $Image)) { throw "Image not found: $Image (build the fixed recovery.img first)" }

if ($AdbPath.Trim() -eq "") {
    foreach ($c in @("D:\Android\Sdk\platform-tools\adb.exe", "adb")) {
        if ($c -eq "adb") { if (Get-Command adb -ErrorAction SilentlyContinue) { $AdbPath = $c; break } }
        elseif (Test-Path $c) { $AdbPath = $c; break }
    }
}
if ($AdbPath -eq "") { throw "adb.exe not found; pass -AdbPath" }

function Invoke-Adb {
    param([string[]]$Arguments)
    $all = @("-s", $Serial) + $Arguments
    & $AdbPath @all
    return $LASTEXITCODE
}

Write-Host "adb    : $AdbPath"
Write-Host "serial : $Serial"
Write-Host "image  : $Image"

# --- [1] connection + root -------------------------------------------------
$list = (& $AdbPath devices 2>&1 | Out-String)
$line = ($list -split "`r?`n" | Where-Object { $_ -match "^\s*$([regex]::Escape($Serial))\s" } | Select-Object -First 1)
if (-not $line) { throw "Device $Serial not attached" }
$state = ($line.Trim() -split '\s+')[1]
switch ($state) {
    "unauthorized" { throw "USB debugging not authorised - tap Allow on the phone" }
    "authorizing"  { throw "Authorisation dialog still open - tap Allow" }
    "offline"      { throw "Device offline - re-plug USB" }
    "device"       { Write-Host "[1/5] adb: device (system)" }
    "recovery"     { Write-Host "[1/5] adb: recovery (TWRP)" }
    default        { throw "Unexpected adb state: $state" }
}
if ($state -eq "recovery") {
    # TWRP's adb shell is already uid=0 and has no "su" binary.
    $rootId = (& $AdbPath -s $Serial shell "id -u" 2>&1 | Out-String).Trim()
    if ($rootId -ne "0") { throw "TWRP shell is not root: $rootId" }
    Write-Host "[1/5] root: uid=0 (native TWRP shell)"
} else {
    $rootId = (& $AdbPath -s $Serial shell su -c id 2>&1 | Out-String)
    if ($rootId -notmatch "uid=0") { throw "root not available: $rootId" }
    Write-Host "[1/5] root: uid=0 (Magisk)"
}

# --- [2] version gate ------------------------------------------------------
if ($state -eq "recovery") {
    # TWRP's own props/cmdline carry the recovery build (1.7.6), NOT the
    # installed system. Read the real system identity from /vendor/build.prop.
    $vf = (& $AdbPath -s $Serial shell "grep '^ro.vendor.build.fingerprint=' /vendor/build.prop" 2>&1 | Out-String).Trim()
    if ($vf -match '^ro\.vendor\.build\.fingerprint=(.+)$') { $devVer = $Matches[1] }
    else { $devVer = "" }
} else {
    $devVer = (& $AdbPath -s $Serial shell getprop ro.build.version.bbk 2>&1 | Out-String).Trim()
}
$allowedFile = Join-Path $PSScriptRoot "allowed_versions.txt"
$allowed = Get-Content $allowedFile | Where-Object { $_ -and -not $_.TrimStart().StartsWith("#") } | ForEach-Object { $_.Trim() }
Write-Host "[2/5] device version: $devVer"
if ($devVer -and ($devVer -notin $allowed)) {
    throw "Version '$devVer' not in allowed_versions.txt - rebuild with that version's kernel/dtb first"
}

# --- [3] pad to exact partition size + hash --------------------------------
$raw = [System.IO.File]::ReadAllBytes($Image)
if ($raw.Length -gt $PartSize) { throw "Image ($($raw.Length) B) exceeds recovery partition ($PartSize B)" }
if ($raw.Length -lt $PartSize) {
    $buf = New-Object byte[] $PartSize
    [Array]::Copy($raw, $buf, $raw.Length)
} else { $buf = $raw }
$padded = Join-Path $env:TEMP "y52s_recovery_padded.img"
$sumFile = Join-Path $env:TEMP "y52s_recovery.sha256"
[System.IO.File]::WriteAllBytes($padded, $buf)
$sha = (Get-FileHash $padded -Algorithm SHA256).Hash.ToLower()
Set-Content -Path $sumFile -Value "$sha  recovery.img" -Encoding ascii
Write-Host "[3/5] padded to $PartSize B, sha256 $sha"

# --- [4] push as files, then run (no inline quoting) ----------------------
# TWRP: /data is not decrypted, so /data/local/tmp is unwritable -> use /tmp.
# System mode: keep /data/local/tmp (works with Magisk root).
$remoteDir = if ($state -eq "recovery") { "/tmp" } else { "/data/local/tmp" }
Write-Host "[4/5] remote dir: $remoteDir"
$devScript = Join-Path $PSScriptRoot "device_flash.sh"
$code = Invoke-Adb @("push", $devScript, "$remoteDir/y52s_flash.sh")
if ($code -ne 0) { throw "push device_flash.sh failed" }
$code = Invoke-Adb @("push", $padded, "$remoteDir/y52s_recovery.img")
if ($code -ne 0) { throw "push recovery.img failed" }
$code = Invoke-Adb @("push", $sumFile, "$remoteDir/y52s_recovery.sha256")
if ($code -ne 0) { throw "push sha256 failed" }
Write-Host "[4/5] payload pushed"

# --- [5] write + verify ----------------------------------------------------
$out = (& $AdbPath -s $Serial shell sh "$remoteDir/y52s_flash.sh" $remoteDir 2>&1 | Out-String)
Write-Host $out.Trim()
if ($out -notmatch "OK - partition sha256 matches") {
    throw "Write/verify failed. Restore with device_dump/.../images/recovery.img using the same script (-Image)."
}
Write-Host "[5/5] DONE - only the recovery partition was written; /data untouched."
Write-Host "Reboot into recovery when you are ready: adb reboot recovery"
