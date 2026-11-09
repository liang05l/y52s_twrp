#!/sbin/sh
# Read-only post-boot probe. Only fixed markers are grepped, never command
# lines that may carry the lock-screen credential.
echo "=== DE / PASSWORD PAGE (sanitized) ==="
grep -aE 'Decrypt_FBE_DE|fscrypt_initialize_systemwide_keys|Set page:|Is_Encrypted|Is_Decrypted|Successfully generated disk decryption secret key|km_error|keystore_auth|Decrypt_User: ENTER|PageManager|decrypt' /tmp/recovery.log 2>/dev/null | tail -40
echo "=== crypto props ==="
getprop | grep -iE 'twrp\.user|tw_is_|tw_crypto|ro\.crypto|fbe\.|keymaster_ver' | head -20
echo "=== services ==="
getprop | grep -iE 'init\.svc\.(keystore|gatekeeper|mobicore|wait_for)' | head -12
echo "=== DE key dir ==="
ls -1 /data/misc/vold/user_keys/de/0/ 2>&1 | head -6
echo "=== keystore_auth binary ==="
ls -l /system/bin/keystore_auth 2>&1 | head -2
echo "=== last keystore-related log lines ==="
grep -aiE 'keystore|fscrypt' /tmp/recovery.log 2>/dev/null | tail -15
echo "=== END ==="
