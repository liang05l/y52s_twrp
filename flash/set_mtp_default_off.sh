#!/sbin/sh
# y52s: make MTP OFF by default in TWRP, so the MTP server does not enumerate
# /data/media before the user enters the lockscreen password (which made the
# PC show encrypted/garbled filenames even after decryption).
# Enabling MTP later, after decrypt, is a one-tap action in Mount; the rc then
# switches to the adb+MTP composite so adb stays alive.
mkdir -p /cache/recovery
printf 'tw_mtp_enabled=0\n' > /cache/recovery/.twrps
chmod 0666 /cache/recovery/.twrps
sync
echo "=== /cache/recovery/.twrps ==="
cat /cache/recovery/.twrps
echo "=== apply to the running TWRP too ==="
timeout 8 /system/bin/twrp set tw_mtp_enabled 0 2>&1 | head -5
echo "=== current value ==="
timeout 8 /system/bin/twrp get tw_mtp_enabled 2>&1 | head -5
echo "=== SET_MTP_OFF_DONE ==="
