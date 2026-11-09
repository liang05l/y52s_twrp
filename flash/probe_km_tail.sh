#!/sbin/sh
echo "=== recovery.log: everything from 'Key requires upgrade' onward ==="
awk '/Key requires upgrade/{f=1} f{print}' /tmp/recovery.log 2>/dev/null | head -120
echo "=== DE/CE key result lines (whole log) ==="
grep -aiE 'DE keys|DE key|upgrade|km_error|decrypt.*success|decrypt.*fail|FBE|Is_Encrypted|Is_Decrypted|Unknown password|gatekeeper|install.*key|fscrypt' /tmp/recovery.log 2>/dev/null | tail -70
echo "=== ramdisk vendor gatekeeper layout ==="
ls -l /vendor/bin/android.hardware.gatekeeper@1.0-service /vendor/bin/hw/ 2>&1 | head -20
echo "--- hw dir ---"
ls -1 /vendor/bin/hw/ 2>&1 | head -20
echo "--- gatekeeper HAL libs ---"
ls -1 /vendor/lib64/hw/ 2>&1 | grep -i gatekeeper
echo "=== init.svc gatekeeper explicit ==="
getprop init.svc.gatekeeper-1-0
echo "=== END ==="
