#!/sbin/sh
echo "=== keystore_auth / keystore link deps ==="
for b in /system/bin/keystore_auth /system/bin/keystore; do
  echo "--- $b ---"
  strings "$b" 2>/dev/null | grep -E '^lib.*\.so$|^\.so$|keystore@.*\.so$' | head -14
done
echo
echo "=== are those libs ANYWHERE in the ramdisk? ==="
for n in libkeystore_aidl.so libkeystore_binder.so vendor.vivo.hardware.wifi.keystore@1.0.so android.system.wifi.keystore@1.0.so; do
  printf '%-52s ' "$n"
  found=""
  for d in /system/lib64 /vendor/lib64 /system/lib /vendor/lib; do
    if [ -e "$d/$n" ]; then found="$found $d/$n"; fi
  done
  if [ -n "$found" ]; then echo "PRESENT:$found"; else echo "ABSENT"; fi
done
echo
echo "=== tied-profile key characteristics / key files ==="
ls -l /data/misc/keystore/user_0/1000_USRPKEY_profile_key_name_decrypt_999* 2>&1 | head -8
echo
echo "=== auth token freshness vs strategy ts ==="
ls -l /auth_token 2>&1 | head -2
echo "token_size=$(wc -c < /auth_token 2>/dev/null)"
echo
echo "=== keystore service state now ==="
getprop | grep -iE 'init\.svc\.(keystore|keystore_auth|keystore2)' | head -8
echo "=== END ==="
