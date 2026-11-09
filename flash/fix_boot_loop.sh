#!/system/bin/sh
# y52s: read-only checks + clear the boot-recovery BCB so normal power-on
# boots into the SYSTEM instead of recovery. Never touches /data.
echo "=== ID ==="
id
echo "=== ROOT ==="
su -c id 2>&1
echo "=== RECOVERY PARTITION SHA256 ==="
su -c "sha256sum /dev/block/by-name/recovery" 2>&1
echo "=== MISC BCB BEFORE (command field, 32 bytes) ==="
su -c "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -c" 2>&1
echo "=== CLEAR BCB ==="
su -c "dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 conv=notrunc 2>/dev/null; sync" 2>&1
echo "=== MISC BCB AFTER ==="
su -c "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -c" 2>&1
echo "=== SYSTEM IDENTITY ==="
getprop ro.product.model
getprop ro.build.version.bbk
getprop ro.build.fingerprint
getprop ro.crypto.type
getprop ro.crypto.state
echo "=== USB / ADB ==="
getprop sys.usb.config
getprop sys.usb.state
getprop persist.sys.usb.config
echo "=== DATA INTEGRITY (read-only) ==="
su -c "ls -1 /data/media/0 2>/dev/null | wc -l" 2>&1
echo "=== DONE ==="
