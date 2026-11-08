#!/system/bin/sh
# ===========================================================================
# y52s - DEVICE-SIDE recovery writer (runs on the phone, driven by
#        flash/flash_recovery.ps1). All quoting stays inside this file so no
#        nested quotes ever pass through "adb shell su -c".
# Writes ONLY /dev/block/by-name/recovery. No format / wipe / userdata /
# metadata / super anywhere in this script.
# ===========================================================================
set -u
have() { command -v "$1" >/dev/null 2>&1; }
DIR=${1:-/data/local/tmp}

if [ "$(id -u 2>/dev/null)" != "0" ] && [ -z "${Y52S_FLASH:-}" ] && have su; then
    su -c "Y52S_FLASH=1 sh $0 $DIR" && exit 0
fi

IMG="$DIR/y52s_recovery.img"
SUM="$DIR/y52s_recovery.sha256"
PART=/dev/block/by-name/recovery

[ "$(id -u 2>/dev/null)" = "0" ] || { echo "E: root required (grant Magisk Shell/ADB)"; exit 1; }
[ -f "$IMG" ]  || { echo "E: image missing on device"; exit 1; }
[ -f "$SUM" ]  || { echo "E: expected sha256 file missing"; exit 1; }
[ -e "$PART" ] || { echo "E: recovery partition not found"; exit 1; }

EXPECT=$(cut -d ' ' -f1 < "$SUM" 2>/dev/null)
[ -n "$EXPECT" ] || { echo "E: empty sha256"; exit 1; }

echo "I: target = $PART ($(readlink -f "$PART" 2>/dev/null))"
echo "I: writing ONLY the recovery partition; /data is not touched"

# Timing: the old bs=4096 meant 24576 tiny writes for 96 MB, then sync, then
# a full 96 MB read-back for sha256 -- that is the visible "stall" on flash.
# 1 MiB blocks cut the write syscalls ~256x; keep sync + full verification.
T0=$(date +%s 2>/dev/null || echo 0)
dd if="$IMG" of="$PART" bs=1048576 2>/dev/null || { echo "E: dd failed"; exit 1; }
T1=$(date +%s 2>/dev/null || echo 0)
sync
T2=$(date +%s 2>/dev/null || echo 0)

GOT=$(sha256sum "$PART" 2>/dev/null | cut -d ' ' -f1)
T3=$(date +%s 2>/dev/null || echo 0)
echo "I: timing: dd=$((T1-T0))s sync=$((T2-T1))s verify=$((T3-T2))s"
[ "$GOT" = "$EXPECT" ] || { echo "E: verify failed ($GOT != $EXPECT)"; exit 1; }
echo "I: OK - partition sha256 matches. /data untouched."
exit 0
