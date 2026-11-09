#!/sbin/sh
echo "=== PARTITION ==="
sha256sum /dev/block/by-name/recovery
echo "=== TWRP / USB / TOUCH ==="
getprop ro.twrp.version
getprop ro.vivo.product.model
getprop sys.usb.config
getprop sys.usb.configfs
ls -l /dev/input/event3 2>&1 | head -2
echo "=== /data/media/0 (first 24) ==="
ls -1 /data/media/0 2>&1 | head -24
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
echo "=== DE/CE visibility ==="
ls -1 /data/system/ 2>&1 | grep -iE 'gatekeeper|locksettings|users' | head -8
ls -1 /data/misc/vold/user_keys/ 2>&1 | head -5
echo "=== crypto props ==="
getprop | grep -iE 'tw_is_|tw_crypto|twrp.user|ro.crypto|fbe\.|keymaster_ver' | head -20
echo "=== HAL ==="
getprop | grep -iE 'init.svc.(keymaster|gatekeeper|mobicore|wait_for)' | head -10
echo "=== recovery.log: decrypt result ==="
grep -aiE 'km_error|Decrypt_FBE_DE|Decrypt_User|decrypt.*success|Successfully|password|Is_Encrypted|Is_Decrypted|CE key|user 0' /tmp/recovery.log 2>/dev/null | tail -35
echo "=== mount /data ==="
mount | grep '/data '
echo "=== END ==="
