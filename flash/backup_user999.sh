#!/system/bin/sh
# y52s: back up vivo DOUBLE_APP (user 999) data from the BOOTED ANDROID SYSTEM.
#
# TWRP cannot decrypt user 999 (its synthetic password code takes the
# "secdis" branch for non-zero users and fails). In the booted system all
# users are already decrypted, so Magisk root can read them directly.
#
# Run from the PC:
#   adb push flash/backup_user999.sh /data/local/tmp/y52s_backup999.sh
#   adb shell "su -c 'sh /data/local/tmp/y52s_backup999.sh'"
#   adb pull /sdcard/user999_backup_<stamp>.tar
#
# NOTE: the archive contains private app data (e.g. a cloned WeChat). Keep it
# on your own machine; do NOT include the FBE key material under
# /data/misc/vold/user_keys (deliberately excluded here).
set -u
STAMP=$(date +%Y%m%d_%H%M%S)
OUT="/sdcard/user999_backup_${STAMP}.tar"

echo "ID: $(id -u)"
if [ "$(id -u)" != "0" ]; then echo "E: root required"; exit 1; fi

echo "I: collecting user 999 data ..."
for d in /data/user/999 /data/system_ce/999 /data/system_de/999 /data/media/999; do
    if [ -d "$d" ]; then echo "  FOUND $d"; else echo "  skip   $d"; fi
done

tar -cf "$OUT" \
    -C /data \
    user/999 \
    system_ce/999 \
    system_de/999 \
    2>/dev/null || { echo "E: tar failed"; exit 1; }

sync
echo "I: archive = $OUT"
ls -lh "$OUT"
echo "I: sha256 = $(sha256sum "$OUT" | cut -d' ' -f1)"
echo "I: pull it with: adb pull $OUT"
echo "BACKUP999_DONE"
