#!/sbin/sh
# Final on-device acceptance for the TWRP 12.1 (Y73s tree) build with the
# user-999 owner-auth-token fix. No credential is printed: only fixed log
# markers are grepped, never the command line that carried the PIN.
echo "=== PARTITION ==="
sha256sum /dev/block/by-name/recovery
echo "=== DECRYPT STATE ==="
for p in twrp.user.0.decrypt twrp.user.999.decrypt tw_is_encrypted tw_is_decrypted; do
  echo "$p=$(getprop $p)"
done
echo "=== USER999 LOG MARKERS (sanitized) ==="
grep -aE 'y52s: reusing owner auth token|y52s: no owner auth token|User 999 Decrypted|Decrypt_User: ENTER|km_error=|Successfully generated disk decryption|Failed to decrypt user|\[SPBLOB\] Parsed auth token|gatekeeper verification failed' /tmp/recovery.log 2>/dev/null | tail -35
echo "=== /data/user/999 ==="
ls -1 /data/user/999 2>&1 | head -12
echo "=== /data/media/0 ==="
ls -1 /data/media/0 2>/dev/null | head -6
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
echo "=== HAL SERVICES ==="
getprop | grep -iE 'init\.svc\.(keymaster|gatekeeper|mobicore|keystore)' | head -10
echo "=== MTP / TOUCH / USB ==="
timeout 5 /system/bin/twrp get tw_mtp_enabled 2>&1 | head -2
getprop sys.usb.config
grep -A2 'vivo_ts' /proc/bus/input/devices 2>/dev/null | head -4
echo "=== PATCH BINARY MARKER ==="
grep -ac 'y52s: reusing owner auth token' /system/lib64/libtwrpfscrypt.so /sbin/recovery /system/bin/recovery 2>/dev/null | head -5
echo "=== END ==="
