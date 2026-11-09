#!/sbin/sh
# Zero-cost experiment: try the FBE standard default password for user 999.
# This is a public AOSP constant, NOT the user's lock-screen credential.
echo "=== twrp decrypt default_password 999 ==="
timeout 35 /system/bin/twrp decrypt default_password 999 > /tmp/y52s_try999.txt 2>&1
echo "RC=$?"
head -20 /tmp/y52s_try999.txt 2>/dev/null
echo "=== decrypt props ==="
echo "twrp.user.0.decrypt=$(getprop twrp.user.0.decrypt)"
echo "twrp.user.999.decrypt=$(getprop twrp.user.999.decrypt)"
echo "=== log markers (sanitized) ==="
grep -aE 'Decrypt_User: ENTER user_id=999|gatekeeper verification failed|Gatekeeper verification succeeded|\[SECDIS\] Auth token written|begin callback: error=|km_error=|User 999 Decrypted|Failed to decrypt user 999|y52s:|Successfully generated disk decryption' /tmp/recovery.log 2>/dev/null | tail -30
echo "=== END ==="
