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
dd if="$IMG" of="$PART" bs=4096 2>/dev/null || { echo "E: dd failed"; exit 1; }
sync

GOT=$(sha256sum "$PART" 2>/dev/null | cut -d ' ' -f1)
[ "$GOT" = "$EXPECT" ] || { echo "E: verify failed ($GOT != $EXPECT)"; exit 1; }
echo "I: OK - partition sha256 matches. /data untouched."
exit 0
