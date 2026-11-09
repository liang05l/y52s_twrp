#!/sbin/sh
echo "=== recovery.service + all init.svc ==="
getprop recovery.service
getprop | grep -i init.svc
echo "=== HAL processes ==="
ps -A | grep -iE 'keymaster|gatekeeper|mobicore|mcDriver|keystore|guardian|wait_for|vts_app|vold' | head -30
echo "=== mounts (all dm / system / vendor / persist) ==="
mount | grep -iE 'dm-|system|vendor|persist|/data |/metadata'
echo "=== /vendor HAL binaries visible? ==="
ls -l /vendor/bin/hw/android.hardware.keymaster@4.0-service.trustonic 2>&1
ls -l /vendor/bin/hw/android.hardware.gatekeeper@1.0-service 2>&1
ls -l /vendor/bin/android.hardware.gatekeeper@1.0-service 2>&1
ls -l /vendor/bin/mcDriverDaemon 2>&1
echo "=== system partition build.prop for patchlevel ==="
ls -l /system_root/system/build.prop 2>&1
grep -E 'ro.build.version.security_patch|ro.build.version.sdk|ro.build.version.release' /system_root/system/build.prop 2>&1 | head -6
echo "=== version props now ==="
getprop ro.build.version.security_patch
getprop ro.build.version.sdk
getprop ro.vendor.build.security_patch
getprop ro.vndk.version
echo "=== recovery.log: init/patchlevel/DE keys/service ==="
grep -aiE 'recovery.service|wait_for_keymaster|auto_patchlevel|resetprop|DE keys|decrypt|patchlevel|keystore|gatekeeper|keymaster|FsCrypt|fscrypt|install.*key' /tmp/recovery.log 2>/dev/null | head -50
echo "=== logcat HAL errors ==="
logcat -d 2>/dev/null | grep -aiE 'CANNOT LINK|keymaster|gatekeeper|keystore|trustonic|mobicore|patchlevel|failed to|denied' | tail -30
echo "=== rc file present / service defs ==="
ls -l /init.recovery.mt6853.rc /sbin/y52s_prepare.sh 2>&1
grep -nE '^(service|on )' /init.recovery.mt6853.rc 2>&1 | head -40
echo "=== END ==="
