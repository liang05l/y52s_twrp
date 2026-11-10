#!/sbin/sh
echo "=== STATE ==="
getprop | grep -iE 'twrp\.user|tw_is_decrypted|tw_crypto' | head -10
echo "=== USER 0 BEGIN / ERROR TRACE ==="
grep -aE 'Decrypt_User: ENTER user_id=0|\[SECDIS\] Auth token written|\[SECDIS\] Gatekeeper verification succeeded|\[Keymaster\] begin \(authToken\)|begin callback: error=|Keymaster begin returned error|Successfully generated disk decryption|User 0 Decrypted|Failed to decrypt user|\[SPBLOB\] Parsed auth token|corrected hw_auth_token' /tmp/recovery.log 2>/dev/null | tail -45
echo "=== PARTITION ==="
sha256sum /dev/block/by-name/recovery
echo "=== END ==="
