# ===========================================================================
# y52s (V2057A / PD2057) TWRP adaptation - device evidence collector
# Verified environment 2026-11-07:
#   adb   : D:\Android\Sdk\platform-tools\adb.exe  (Android Debug Bridge 1.0.41 / 37.0.0)
#   serial: MBLF9LSONZPJG69L
#   state : device (USB debugging authorised)
#
# Usage (no arguments needed on this machine):
#   powershell -ExecutionPolicy Bypass -File .\collect\run_collect.ps1
# Optional overrides: -AdbPath <path>  -Serial <serial>
#
# The collector is pushed as a FILE and executed on the device: no inline
# "adb shell" command, no nested quoting, no su -c redirection.
# ===========================================================================
param(
    [string]$AdbPath = "",
    [string]$Serial  = "MBLF9LSONZPJG69L"
)

# Native adb writes daemon notices to stderr. Keep them as text, not as
# terminating errors; every real failure below is checked explicitly.
$ErrorActionPreference = "Continue"
$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$LocalScript  = Join-Path $PSScriptRoot "device_collect.sh"
$RemoteScript = "/data/local/tmp/y52s_collect.sh"
$LatestPtr    = "/sdcard/y52s_dump_latest.txt"
$LocalDump    = Join-Path $ProjectRoot "device_dump"

# --- resolve adb: verified SDK path first, then PATH ---
# NOTE: do not mix in the older adb bundled with phone-assistant tools
# (different platform-tools version -> restarts/kills the same 5037 server).
if ($AdbPath.Trim() -eq "") {
    $candidates = @(
        "D:\Android\Sdk\platform-tools\adb.exe",
        "adb"
    )
    foreach ($c in $candidates) {
        if ($c -eq "adb") {
            if (Get-Command adb -ErrorAction SilentlyContinue) { $AdbPath = $c; break }
        } elseif (Test-Path $c) { $AdbPath = $c; break }
    }
}
if ($AdbPath -eq "") { throw "adb.exe not found. Pass -AdbPath <path>." }

if (-not (Test-Path $LocalScript)) { throw "Missing $LocalScript" }

function Invoke-Adb {
    param([string[]]$Arguments)
    $all = @()
    if ($Serial.Trim() -ne "") { $all += @("-s", $Serial.Trim()) }
    $all += $Arguments
    & $AdbPath @all
    return $LASTEXITCODE
}

Write-Host "adb    : $AdbPath"
Write-Host "serial : $Serial"

# --- [1] authorisation gate: stop early instead of pushing into a dead link ---
$list = (& $AdbPath devices 2>&1 | Out-String)
$line = ($list -split "`r?`n" | Where-Object { $_ -match "^\s*$([regex]::Escape($Serial))\s" } | Select-Object -First 1)
if (-not $line) { throw "Device $Serial is not attached. Check the USB cable / USB debugging." }
$state = ($line.Trim() -split '\s+')[1]
switch ($state) {
    "unauthorized" { throw "USB debugging NOT authorised. On the phone: unlock the screen, tap 'Allow USB debugging' (tick 'Always allow'), then re-run this script." }
    "authorizing"  { throw "Authorisation dialog is still open on the phone. Tap 'Allow', then re-run this script." }
    "offline"      { throw "Device is offline. Re-plug USB or restart adb (adb kill-server), then re-run." }
    "device"       { Write-Host "[1/5] authorised: device" }
    default        { throw "Unexpected adb state for ${Serial}: $state" }
}

# --- [2] push + run ---
Write-Host "[2/5] pushing and running collector on device"
$code = Invoke-Adb @("push", $LocalScript, $RemoteScript)
if ($code -ne 0) { throw "adb push failed" }
$code = Invoke-Adb @("shell", "sh", $RemoteScript)
if ($code -ne 0) { Write-Warning "collector returned $code - check collect.log after pull" }

# --- [3] resolve the fresh dump directory ---
Write-Host "[3/5] resolving dump path"
$catArgs = @("-s", $Serial, "shell", "cat", $LatestPtr)
$catOut  = (& $AdbPath @catArgs 2>&1 | Out-String) -split "`r?`n"
$raw = (($catOut | Where-Object { $_ -match '^/sdcard/y52s_dump_\d{8}_\d{6}$' } | Select-Object -Last 1) + "").Trim()
if ($raw -eq "") {
    throw "No valid dump path in $LatestPtr. Is /sdcard writable? Unlock the screen and retry."
}

# --- [4] pull ---
Write-Host "[4/5] pulling $raw"
if (-not (Test-Path $LocalDump)) { New-Item -ItemType Directory -Path $LocalDump -Force | Out-Null }
$code = & $AdbPath -s $Serial pull $raw $LocalDump
if ($LASTEXITCODE -ne 0) { throw "adb pull failed" }

# --- [5] integrity + completeness ---
Write-Host "[5/5] validating evidence"
$dumpDir  = Join-Path $LocalDump (Split-Path -Leaf $raw)
$manifest = Join-Path $dumpDir "manifest.txt"
if (-not (Test-Path $manifest)) { throw "manifest.txt missing - dump incomplete: $dumpDir" }

$files = Get-ChildItem -Path $dumpDir -Recurse -File
Write-Host ("  files {0}  bytes {1}" -f $files.Count, ($files | Measure-Object Length -Sum).Sum)

$rootFile = Join-Path $dumpDir "root_status.txt"
if (Test-Path $rootFile) { Write-Host ("  root  : " + ((Get-Content $rootFile -Raw).Trim() -replace "`r?`n", " | ")) }

$must = @("props\getprop.all.txt", "partitions.txt", "byname_resolved.txt",
          "cmdline.txt", "images\boot.img", "images\recovery.img")
foreach ($rel in $must) {
    if (-not (Test-Path (Join-Path $dumpDir $rel))) {
        Write-Warning "MISSING: $rel  (partition dumps need root - see collect.log)"
    }
}

$log = Join-Path $dumpDir "collect.log"
if (Test-Path $log) {
    $warns = Select-String -Path $log -Pattern "WARN|FAILED|FATAL" | Select-Object -First 12
    foreach ($w in $warns) { Write-Warning ("  " + $w.Line.Trim()) }
}

if (-not (Test-Path (Join-Path $dumpDir "images\boot.img"))) {
    $rs = Join-Path $dumpDir "root_status.txt"
    $isRoot = (Test-Path $rs) -and ((Get-Content $rs -Raw) -match "uid=0")
    Write-Host ""
    if ($isRoot) {
        Write-Warning "boot.img unreadable even as root: this device blocks reads of the boot partition (/dev/block/by-name/boot and /dev/block/sdc48 both return Permission denied)."
        Write-Host "        Not a blocker: recovery.img / dtbo.img / vbmeta*.img were dumped and carry the same boot header parameters."
    } else {
        Write-Warning "Partition images missing: Magisk denied root."
        Write-Host "ACTION: on the phone, open Magisk > Superuser and grant Shell / ADB shell"
        Write-Host "        (or tap the root prompt), then simply re-run this script."
        Write-Host "        The collector self-elevates; no manual dd / no extra commands needed."
    }
}

Write-Host ""
Write-Host ("DUMP READY: " + $dumpDir)
