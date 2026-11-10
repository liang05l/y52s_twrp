#!/sbin/sh
# Is keymaster/gatekeeper stopped or restarted after user 0 decrypts?
# Only fixed markers are printed; credential command lines are excluded.
echo "=== DECRYPT STATE ==="
for p in twrp.user.0.decrypt twrp.user.999.decrypt; do echo "$p=$(getprop $p)"; done
echo "=== NEW PATCH MARKERS ==="
grep -aE 'y52s: scrypt password token|y52s: profile verify failed|y52s: reusing owner auth token|y52s: no owner auth token' /tmp/recovery.log 2>/dev/null | tail -20
echo "=== DECRYPT / KEYMASTER RESULT (sanitized) ==="
grep -aE 'Decrypt_User: ENTER|gatekeeper verification failed|Gatekeeper verification succeeded|\[SECDIS\] Auth token written|User 999 Decrypted|User 0 Decrypted|Failed to decrypt user|begin callback: error=|km_error=|failed to unwrapSyntheticPasswordBlob|Successfully generated disk decryption secret key' /tmp/recovery.log 2>/dev/null | tail -40
echo "=== SERVICE LIFECYCLE MARKERS IN LOG ==="
grep -aiE 'ctl\.stop|ctl\.start|stop keymaster|start keymaster|keymaster.*stop|stopping|service.*keymaster|Post_Decrypt|keystore_auth|wait_for_keymaster' /tmp/recovery.log 2>/dev/null | tail -35
echo "=== CURRENT SERVICE PROPS ==="
getprop | grep -iE 'init\.svc\.(keymaster|gatekeeper|mobicore|keystore|wait_for|guardian)|keymaster_ver' | head -20
echo "=== KEYMASTER PROCESSES ==="
ps -A 2>/dev/null | grep -iE 'keymaster|gatekeeper|mobicore|keystore' | head -12
echo "=== /auth_token ==="
ls -l /auth_token 2>&1 | head -2
echo "=== END ==="
