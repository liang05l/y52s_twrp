#!/sbin/sh
# Read-only diagnosis of the user-999 decrypt attempt. Only fixed markers are
# printed; command lines that could contain the lock-screen credential are
# never included.
echo "=== DECRYPT STATE ==="
for p in twrp.user.0.decrypt twrp.user.999.decrypt ro.crypto.state keymaster_ver; do
  echo "$p=$(getprop $p)"
done
echo "=== 0007 HELPER MARKERS ==="
grep -aE 'y52s: reusing owner auth token|y52s: no owner auth token|owner token unavailable|Write_Owner_Auth_Token' /tmp/recovery.log 2>/dev/null | tail -20
echo "=== DECRYPT FLOW (sanitized) ==="
grep -aE 'Decrypt_User: ENTER|Decrypt_User_Synth_Pass|Decrypted Successfully|Failed to decrypt user|km_error=|failed to unwrapSyntheticPasswordBlob|Successfully generated disk decryption secret key|\[SECDIS\]|\[SPBLOB\] Parsed auth token|\[SPBLOB\] Read auth_token|\[SPBLOB\] Found key file|\[Keymaster\] begin|Copying|copySqliteDb' /tmp/recovery.log 2>/dev/null | tail -70
echo "=== USER 999 SPECIFIC (sanitized) ==="
grep -aE 'user_id=999|User 999|user 999|999/spblob|c977db9a6356c1ad' /tmp/recovery.log 2>/dev/null | tail -35
echo "=== /data/user/999 ==="
ls -1 /data/user/999 2>&1 | head -8
echo "=== /data/media/0 ==="
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
ls -1 /data/media/0 2>/dev/null | head -4
echo "=== /auth_token ==="
ls -l /auth_token 2>&1 | head -2
od -An -tx1 /auth_token 2>/dev/null | head -5
echo "=== END ==="
