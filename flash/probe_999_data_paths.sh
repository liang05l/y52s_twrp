#!/sbin/sh
echo "=== /data/media/999 (profile external storage) ==="
ls -1 /data/media/999/ 2>&1 | head -10
echo "COUNT=$(ls -1 /data/media/999/ 2>/dev/null | wc -l)"
echo "=== /data/media/virtual_system* ==="
for d in /data/media/virtual_system /data/media/virtual_system_files; do
  echo "--- $d ---"; ls -1 "$d" 2>&1 | head -6
done
echo "=== /data/media/0 count (owner, decrypted) ==="
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
echo
echo "=== why is keystore restarting? ==="
grep -aiE 'keystore|service .*keystore|signal 6|SIGABRT|crash' /tmp/recovery.log 2>/dev/null | tail -18
echo "=== dmesg keystore ==="
dmesg 2>/dev/null | grep -i keystore | tail -8
echo
echo "=== can the 999 CE key blob be parsed? (sizes only, no content) ==="
for f in /data/misc/vold/user_keys/ce/999/current/*; do echo "  $(wc -c < "$f") B  $f"; done
echo "=== /auth_token freshness ==="
ls -l /auth_token 2>&1 | head -2
echo "=== END ==="
