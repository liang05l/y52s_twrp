#!/sbin/sh
# read-only: FBE key material layout + lockscreen state
echo "=== /data/system (full, first 60) ==="
ls -1a /data/system/ 2>&1 | head -60
echo "=== /data/system_de (full, first 30) ==="
ls -1a /data/system_de/ 2>&1 | head -30
echo "=== /data/system_de/0 (full, first 40) ==="
ls -1a /data/system_de/0/ 2>&1 | head -40
echo "=== /data/misc (first 40) ==="
ls -1a /data/misc/ 2>&1 | head -40
echo "=== /data/misc/vold (recursive 2 levels) ==="
ls -1a /data/misc/vold/ 2>&1 | head -20
for d in /data/misc/vold/user_keys /data/misc/vold/user_keys/ce /data/misc/vold/user_keys/ce/0 \
         /data/misc/vold/user_keys/de /data/misc/vold/user_keys/de/0 \
         /data/misc/vold/user_keys/ce/0/current; do
    echo "--- $d"; ls -1a "$d" 2>&1 | head -20
done
echo "=== /data/misc/gatekeeper / keystore / keymaster ==="
for d in /data/misc/gatekeeper /data/misc/keystore /data/misc/keymaster /data/misc/credstore; do
    echo "--- $d"; ls -1a "$d" 2>&1 | head -15
done
echo "=== /data/system/locksettings anywhere ==="
find /data/system /data/system_de /data/system_ce -maxdepth 2 -iname '*locksettings*' -o -iname '*gatekeeper*' 2>/dev/null | head -30
echo "=== /metadata (vold metadata encryption) ==="
ls -1a /metadata/ 2>&1 | head -20
echo "=== mount / fstab ==="
mount | grep -E '/data |/metadata|/vendor |system_root'
grep -E '^/data|^/metadata|fileencryption|wrappedkey|metadata' /system/etc/recovery.fstab 2>&1 | head -12
echo "=== END ==="
