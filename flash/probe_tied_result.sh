#!/sbin/sh
echo "=== DECRYPT STATE ==="
getprop | grep -iE 'twrp\.user|tw_all_users|tw_is_|tw_crypto' | head -12
echo "=== /data/user/999 (plaintext?) ==="
ls -1 /data/user/999/ 2>&1 | head -10
echo "COUNT_999=$(ls -1 /data/user/999/ 2>/dev/null | wc -l)"
echo "COUNT_0=$(ls -1 /data/user/0/ 2>/dev/null | wc -l)"
echo "=== TIED-PROFILE FILES ==="
ls -l /data/system/users/999/gatekeeper.profile.key 2>&1 | head -2
ls -l /data/misc/keystore/user_0/1000_USRPKEY_profile_key_name_decrypt_999 2>&1 | head -2
ls -l /auth_token 2>&1 | head -2
echo "=== ALL y52s / TIED MARKERS (sanitized, no command lines) ==="
grep -aE 'y52s:|tied-profile|profile_key_name|gatekeeper.profile.key' /tmp/recovery.log 2>/dev/null | tail -60
echo "=== DECRYPT TRACE (fixed markers only) ==="
grep -aE 'Decrypt_User: ENTER|Gatekeeper verification|gatekeeper verification|User .* Decrypted|Failed to decrypt user|km_error|begin callback: error|\[SPBLOB\]|\[SECDIS\]|Successfully generated disk decryption|Failed to Get_Password|failed to unwrapSynthetic' /tmp/recovery.log 2>/dev/null | tail -90
echo "=== END ==="
