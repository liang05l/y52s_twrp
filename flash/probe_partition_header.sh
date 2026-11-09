#!/system/bin/sh
echo "=== first 64 bytes ==="
dd if=/dev/block/by-name/recovery bs=64 count=1 2>/dev/null | od -An -tx1
echo "=== footer (last 64 bytes) ==="
dd if=/dev/block/by-name/recovery bs=1048576 skip=95 2>/dev/null | tail -c 64 | od -An -tx1
echo "=== sha of first 1MB / last 1MB ==="
dd if=/dev/block/by-name/recovery bs=1048576 count=1 2>/dev/null | sha256sum
dd if=/dev/block/by-name/recovery bs=1048576 skip=95 count=1 2>/dev/null | sha256sum
