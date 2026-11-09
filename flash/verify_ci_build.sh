#!/sbin/sh
# Read-only verification of the freshly built TWRP 11 (2026-11-09 CI run).
echo "=== BUILD / PARTITION ==="
getprop ro.twrp.version
sha256sum /dev/block/by-name/recovery
echo "=== USB ==="
for p in sys.usb.config sys.usb.state sys.usb.configfs sys.usb.ffs.ready sys.usb.ffs.mtp.ready; do echo "$p = $(getprop $p)"; done
ls -l /config/usb_gadget/g1/configs/b.1/f1 2>&1 | head -2
echo "=== TOUCH ==="
grep -A2 -B1 'vivo_ts' /proc/bus/input/devices 2>/dev/null | head -6
ls -l /dev/input/event3 2>&1 | head -2
grep -aiE 'vts_app|touch|firmware' /tmp/recovery.log 2>/dev/null | tail -8
echo "=== HAL SERVICES ==="
getprop | grep -iE 'init.svc.(keymaster|gatekeeper|mobicore|keystore|guardian|wait_for)' | head -12
echo "=== DE KEY / DECRYPT STATE ==="
getprop | grep -iE 'twrp.user|tw_is_|ro.crypto|keymaster_ver|fbe\.' | head -20
grep -aiE 'km_error|Decrypt_FBE_DE|Decrypt_User|Successfully generated|Set page: .decrypt|User [0-9]+ Decrypted|failed to unwrap' /tmp/recovery.log 2>/dev/null | tail -25
echo "=== DATA VIEW ==="
ls -1 /data/media/0 2>/dev/null | head -8
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
ls -1 /data/system/ 2>&1 | grep -iE 'gatekeeper|locksettings|users' | head -6
echo "=== PATCH MARKER IN BINARY ==="
strings /system/lib64/libtwrpfscrypt.so 2>/dev/null | grep -iE 'y52s: owner|y52s: no owner|owner token unavailable' | head -6
echo "=== END ==="
