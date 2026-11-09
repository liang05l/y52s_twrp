#!/sbin/sh
# Read-only layout of the profile (user 999) synthetic-password material.
# DE storage is already decrypted in this session, so these files are visible.
echo "=== spblob dir 0 ==="
ls -la /data/system_de/0/spblob/ 2>&1 | head -20
echo "=== spblob dir 999 ==="
ls -la /data/system_de/999/spblob/ 2>&1 | head -25
echo "=== 999 handle ==="
cat /data/system_de/999/spblob/0000000000000000.handle 2>&1 | head -2
echo "=== .pwd bytes 0 vs 999 ==="
for f in /data/system_de/0/spblob/8b062251e4788049.pwd /data/system_de/999/spblob/c977db9a6356c1ad.pwd; do
  echo "--- $f ---"
  od -An -tx1 "$f" 2>&1 | head -6
done
echo "=== 999 escrow files (.e0 / .p1) ==="
for f in /data/system_de/999/spblob/0000000000000000.e0 /data/system_de/999/spblob/0000000000000000.p1; do
  echo "--- $f ---"
  ls -l "$f" 2>&1 | head -2
  od -An -tx1 "$f" 2>&1 | head -4
done
echo "=== CE key dirs 0 / 999 ==="
for u in 0 999; do
  echo "--- user $u ---"
  ls -la /data/misc/vold/user_keys/ce/$u/current/ 2>&1 | head -12
done
echo "=== spblob_bak / hash (999) ==="
ls -la /data/system_de/999/spblob_bak/ 2>&1 | head -12
od -An -tx1 /data/system_de/999/spblob_hash 2>&1 | head -4
echo "=== END ==="
