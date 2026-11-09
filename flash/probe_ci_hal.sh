#!/sbin/sh
echo "=== SERVICES ==="
getprop | grep -iE 'init.svc.' | grep -iE 'keymaster|gatekeeper|mobicore|keystore|guardian|wait_for|health|boot-hal' | head -20
echo "=== PROCESSES ==="
ps -A 2>/dev/null | grep -iE 'keymaster|gatekeeper|mobicore|keystore|guardian|vts' | head -20
echo "=== RECOVERY.LOG TAIL (errors) ==="
grep -aiE 'error|fail|crash|CANNOT LINK|cannot locate|km_error|Decrypt|Initialize|keymaster|gatekeeper|touch|vts' /tmp/recovery.log 2>/dev/null | tail -60
echo "=== DMESG LINKER / SEGV ==="
dmesg 2>/dev/null | grep -iE 'linker|segfault|cannot|keymaster|gatekeeper|mobicore|trustonic|init:' | tail -40
echo "=== FILES PRESENT ==="
for f in /vendor/bin/hw/android.hardware.keymaster@4.0-service.trustonic /vendor/bin/android.hardware.gatekeeper@1.0-service /vendor/bin/mcDriverDaemon /vendor/lib64/hw/libMcGatekeeper.so /vendor/lib64/hw/gatekeeper.k6853v1_64_6360.so /system/bin/keystore /system/bin/keystore_auth /system/bin/guardianangle /system/bin/wait_for_keymaster; do
  if [ -e "$f" ]; then echo "OK   $f"; else echo "MISS $f"; fi
done
echo "=== UDC / gadget ==="
cat /config/usb_gadget/g1/UDC 2>/dev/null
cat /config/usb_gadget/g1/idProduct 2>/dev/null
echo "=== END ==="
