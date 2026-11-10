#!/sbin/sh
echo "=== STATE ==="
getprop | grep -iE 'twrp\.user|tw_all_users|tw_is_decrypted' | head -10
echo "COUNT_0=$(ls -1 /data/user/0/ 2>/dev/null | wc -l)"
echo "COUNT_999=$(ls -1 /data/user/999/ 2>/dev/null | wc -l)"
echo
echo "=== ALL STRATEGY LINES (sanitized, no credential) ==="
grep -aE 'y52s: (strategy|STRATEGY|raw token|all strategies|tied-profile|no tied|no owner|reusing|scrypt|profile verify)|\[Keymaster\] begin callback|begin failed' /tmp/recovery.log 2>/dev/null | tail -140
echo
echo "=== DECRYPT OUTCOME (fixed markers only) ==="
grep -aE 'User [0-9]+ Decrypted|Failed to decrypt user|Successfully generated disk decryption|failed to unwrapSynthetic|\[SECDIS\] Gatekeeper verification succeeded|gatekeeper verification failed|km_error|Decrypt_User: ENTER' /tmp/recovery.log 2>/dev/null | tail -40
echo
echo "=== STRATEGY OVERRIDE ==="
ls -l /tmp/y52s_km_only 2>&1 | head -2
echo "=== END ==="
