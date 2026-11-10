#!/sbin/sh
echo "=== BEFORE ==="
for p in init.svc.keystore init.svc.keystore2 init.svc.keystore_auth init.svc.gatekeeper-1-0 init.svc.vendor.keymaster-4-0-trustonic; do
  echo "$p = $(getprop $p)"
done
ls -l /auth_token /auth_error 2>&1 | head -4
echo
echo "=== 1) ctl.start keystore_auth ==="
setprop ctl.start keystore_auth
sleep 2
echo "init.svc.keystore_auth = $(getprop init.svc.keystore_auth)"
echo
echo "=== 2) direct exec /system/bin/keystore_auth ==="
/system/bin/keystore_auth 2>&1
echo "RC=$?"
echo "init.svc.keystore_auth = $(getprop init.svc.keystore_auth)"
echo
echo "=== 3) /auth_error (if any) ==="
ls -l /auth_error 2>&1 | head -2
cat /auth_error 2>/dev/null | head -3
echo
echo "=== 4) why does keystore exit 1? (one manual run, capture stderr) ==="
/system/bin/keystore /data/misc/keystore 2>&1 | head -12 &
KP=$!
sleep 2
kill $KP 2>/dev/null
echo
echo "=== 5) recent keystore log lines ==="
logcat -d -b all 2>/dev/null | grep -iE 'keystore|keymaster|KeystoreAuth' | tail -12
echo "=== END ==="
