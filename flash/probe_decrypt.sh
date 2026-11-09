#!/sbin/sh
# y52s: read-only probe of the FBE decryption decision inputs.
# Never writes /data. Everything goes to stdout so PowerShell can capture it.
echo "=== /data/system gatekeeper / locksettings files ==="
ls -1 /data/system/ 2>&1 | grep -iE 'gatekeeper|locksettings|password|device_policies|spblob' | head -40
echo "=== exact gatekeeper key paths ==="
for f in /data/system/gatekeeper.password.key /data/system/gatekeeper.pin.key \
         /data/system/gatekeeper.pattern.key /data/system/locksettings.db \
         /data/system/locksettings.db-wal /data/system/locksettings.db-shm; do
    if [ -e "$f" ]; then ls -l "$f"; else echo "MISSING $f"; fi
done
echo "=== /data top level ==="
ls -1 /data/ 2>&1 | head -30
echo "=== /data/system_de / system_ce ==="
ls -1 /data/system_de/0/ 2>&1 | head -20
echo "--- ce ---"
ls -1 /data/system_ce/0/ 2>&1 | head -20
echo "=== FBE key material ==="
ls -1 /data/misc/vold/user_keys/ 2>&1 | head -12
echo "--- ce/0 ---"
ls -1 /data/misc/vold/user_keys/ce/0/current/ 2>&1 | head -12
echo "--- de/0 ---"
ls -1 /data/misc/vold/user_keys/de/0/ 2>&1 | head -12
echo "--- gatekeeper misc ---"
ls -1 /data/misc/gatekeeper/ 2>&1 | head -12
echo "=== /data/media/0 view (first 12) ==="
ls -1 /data/media/0 2>&1 | head -12
echo "=== fstab data row ==="
grep -E '^/data|fileencryption|wrappedkey|metadata' /system/etc/recovery.fstab 2>&1 | head -10
echo "=== vivo crypto libs in ramdisk ==="
ls -1 /system/lib64/ 2>&1 | grep -iE 'vivofscrypt|vivogatekeeper|twrpfscrypt|keystore' | head -20
echo "=== twrp decrypt-related props ==="
getprop | grep -iE 'twrp\.user|twrp\.mount_to_decrypt|tw_is_|tw_crypto|ro.crypto|fbe\.|keymaster_ver|sys.usb.config' | head -30
echo "=== recovery.log decrypt section (last 90 lines) ==="
tail -90 /tmp/recovery.log 2>/dev/null
echo "=== END ==="
