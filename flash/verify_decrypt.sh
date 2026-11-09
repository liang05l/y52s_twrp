#!/sbin/sh
# read-only final verification of FBE decryption after the patchlevel fix
echo "=== partition ==="
sha256sum /dev/block/by-name/recovery
echo "=== version / usb / touch ==="
getprop ro.twrp.version
getprop ro.vivo.product.model
getprop sys.usb.config
getprop sys.usb.configfs
ls -l /dev/input/event3 2>&1 | head -2
echo "=== /data/media/0 (first 14) ==="
ls -1 /data/media/0 2>&1 | head -14
echo "=== /data/system gatekeeper files ==="
ls -1 /data/system/ 2>&1 | grep -iE 'gatekeeper|locksettings' | head -12
echo "=== /data/misc/vold/user_keys ==="
ls -1 /data/misc/vold/user_keys/ 2>&1 | head -8
echo "=== HAL services ==="
getprop | grep -iE 'init.svc.(keymaster|gatekeeper|mobicore|keystore|wait_for)' | head -15
echo "=== DE key / km_error result ==="
grep -aE 'Decrypt_FBE_DE|Decrypt_DE:|fscrypt_initialize|km_error|upgradeKey|DE keys|KEY_REQUIRES|Successfully|Decrypt_User|Unknown password|Is_Encrypted|Is_Decrypted|decrypt.*success|decrypt.*fail' /tmp/recovery.log 2>/dev/null | tail -45
echo "=== decrypt page state ==="
grep -aE "Set page: '(decrypt|decrypt_users|trydecrypt|main)'" /tmp/recovery.log 2>/dev/null | tail -12
echo "=== END ==="
