#!/sbin/sh
# Read-only: does this vivo device store the AOSP "tied profile" random
# credential the same way LockSettingsService does? No secret values printed,
# only file names, sizes and a short hex prefix.
echo "=== /data/system/users/999 ==="
ls -la /data/system/users/999/ 2>&1 | head -25
echo "=== all gatekeeper.profile.key ==="
find /data/system -name 'gatekeeper.profile.key' 2>/dev/null | head -10
echo "=== profile_key keystore blobs ==="
ls -1 /data/misc/keystore/user_0/ 2>/dev/null | grep -iE 'profile_key|profile.*decrypt|profile.*encrypt' | head -20
echo "=== any USRSKEY entries ==="
ls -1 /data/misc/keystore/user_0/ 2>/dev/null | grep -c 'USRSKEY' 2>/dev/null
echo "=== parent SID / unified challenge hints in locksettings db ==="
strings /data/system/locksettings.db 2>/dev/null | grep -iE 'profilechallenge|unified|separate' | head -10
echo "=== users/999 spblob handle file ==="
ls -l /data/system_de/999/spblob/0000000000000000.handle 2>&1 | head -2
echo "=== END ==="
