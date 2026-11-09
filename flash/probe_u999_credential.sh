#!/sbin/sh
# Read-only: does the profile (999) have its own lock-screen credential?
# DE storage is decrypted, so system_de/999 is visible. No credential value
# is printed, only password TYPE hints and file names.
echo "=== /data/system_de/999 ==="
ls -la /data/system_de/999/ 2>&1 | head -25
echo "=== locksettings db (type hints only) ==="
strings /data/system_de/999/locksettings.db 2>/dev/null | grep -iE 'lockscreen.password_type|passwordType|lockscreen|password_salt|pattern|pin' | head -20
echo "=== /data/system_de/0 for comparison (type hints only) ==="
strings /data/system_de/0/locksettings.db 2>/dev/null | grep -iE 'lockscreen.password_type|passwordType' | head -8
echo "=== profile escrow / gatekeeper files ==="
ls -la /data/system_de/999/ 2>/dev/null | grep -iE 'gatekeeper|spblob|locksettings|e0|p1' | head -15
echo "=== userlist / 999.xml ==="
cat /data/system/users/999.xml 2>/dev/null | head -12
echo "=== END ==="
