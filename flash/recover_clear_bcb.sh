#!/sbin/sh
# y52s: clear the boot-recovery BCB. Works from the Android system (via su)
# or from TWRP (native root shell). Read-only otherwise; never touches /data.
echo "ID: $(id -u)"
echo "--- BCB before (32-byte command field) ---"
if [ "$(id -u)" = "0" ]; then
    dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1
    dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 conv=notrunc 2>/dev/null
    sync
    echo "--- BCB after ---"
    dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1
else
    su -c "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1"
    su -c "dd if=/dev/zero of=/dev/block/by-name/misc bs=32 count=1 conv=notrunc 2>/dev/null; sync"
    echo "--- BCB after ---"
    su -c "dd if=/dev/block/by-name/misc bs=32 count=1 2>/dev/null | od -An -tx1"
fi
echo "--- /data read-only check ---"
if [ "$(id -u)" = "0" ]; then
    ls -1 /data/media/0 2>/dev/null | wc -l
else
    su -c "ls -1 /data/media/0 2>/dev/null | wc -l"
fi
echo "BCB_CLEAR_DONE"
