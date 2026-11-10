#!/sbin/sh
echo "=== STATE (no PIN entered this boot) ==="
getprop | grep -iE 'twrp\.user|tw_is_decrypted|tw_crypto' | head -8
echo "DE keys installed at boot:"
grep -aE 'installKeyLegacy: SUCCESS|fscrypt_initialize_systemwide_keys' /tmp/recovery.log 2>/dev/null | tail -3
echo
echo "=== A) DE area: material needed to decrypt user 999 ==="
for f in /data/system/users/999/gatekeeper.profile.key \
         /data/system/users/999/locksettings.db \
         /data/system_de/999/spblob/0000000000000000.handle \
         /data/misc/keystore/user_0/1000_USRPKEY_profile_key_name_decrypt_999 \
         /data/misc/vold/user_keys/ce/999/current/encrypted_key \
         /data/misc/vold/user_keys/ce/999/current/secdiscardable \
         /data/misc/vold/user_keys/de/999/encrypted_key ; do
  if [ -r "$f" ]; then echo "READABLE  $(wc -c < "$f") B  $f"; else echo "MISSING/NOACCESS  $f"; fi
done
echo
echo "=== B) CE area: user 999 DATA (ciphertext if CE key absent) ==="
echo "--- /data/user/999 ---"
ls -1 /data/user/999/ 2>&1 | head -8
echo "COUNT=$(ls -1 /data/user/999/ 2>/dev/null | wc -l)"
echo "--- /data/system_ce/999 ---"
ls -1 /data/system_ce/999/ 2>&1 | head -8
echo "--- /data/media (which user dirs exist) ---"
ls -1 /data/media/ 2>&1 | head -8
echo
echo "=== C) user 0 for comparison ==="
echo "COUNT_0=$(ls -1 /data/user/0/ 2>/dev/null | wc -l)"
echo "--- /data/media/0 sample ---"
ls -1 /data/media/0 2>&1 | head -6
echo
echo "=== D) /auth_token ==="
ls -l /auth_token 2>&1 | head -2
echo "=== E) keystore / HAL services ==="
getprop | grep -iE 'init.svc.(keystore|gatekeeper|keymaster|mobicore)' | head -8
echo "=== END ==="
