#!/sbin/sh
echo "=== /auth_token raw structure bytes (first 37, HMAC excluded) ==="
od -An -tx1 -N37 /auth_token 2>&1 | head -4
echo "=== ALL 'Parsed auth token' lines ==="
grep -a 'Parsed auth token' /tmp/recovery.log 2>/dev/null | tail -12
echo "=== USER 0 SUCCESS SEGMENT (begin results) ==="
grep -aE 'Decrypt_User: ENTER user_id=0|SECDIS\] Auth token written|Gatekeeper verification succeeded|begin \(authToken\)|begin callback: error|Successfully generated disk decryption secret key|User 0 Decrypted Successfully|Keymaster begin returned error' /tmp/recovery.log 2>/dev/null | head -40
echo "=== TIED BEGIN lines (exact) ==="
grep -aE 'tied-profile|Keymaster\] begin \(authToken\): Purpose=1, keySize=208' /tmp/recovery.log 2>/dev/null | tail -16
echo "=== END ==="
