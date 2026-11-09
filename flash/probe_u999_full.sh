#!/sbin/sh
# Full (sanitized) trace of every decrypt attempt. Only known log markers are
# printed, never the command line or the credential itself.
echo "=== ALL ATTEMPT MARKERS (no truncation) ==="
grep -anE 'Decrypt_User: ENTER|Unknown password type|Using synthetic password method|Attempting to decrypt user.s synthetic password|Attempting to decrypt user|Handle is|Failed to Get_Password_Data|Failed to Get_Password_Token|no password handle supplied|using secdis|using weaver|Failed to get secdis|gatekeeper verification failed|\[SECDIS\]|\[SPBLOB\] Found key file|\[SPBLOB\] Read auth_token|\[SPBLOB\] Parsed auth token|\[Keymaster\] begin: km_error|\[Keymaster\] begin \(authToken\)|Successfully generated disk decryption secret key|failed to unwrapSyntheticPasswordBlob|Decrypted Successfully|Failed to decrypt user|y52s:|copySqliteDb|Failed to decrypt|Decrypt_CE_storage' /tmp/recovery.log 2>/dev/null
echo "=== END ==="
