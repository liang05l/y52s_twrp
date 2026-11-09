#!/sbin/sh
echo "=== USERS ON DEVICE ==="
ls -1 /data/system/users/ 2>&1 | head -20
echo "--- userlist.xml ---"
cat /data/system/users/userlist.xml 2>&1 | head -30
echo "--- 0.xml ---"
cat /data/system/users/0.xml 2>&1 | head -20
echo "=== twrp user props ==="
getprop | grep -iE 'twrp\.user|tw_is_decrypted|tw_crypto' | head -20
echo "=== user 999 log context ==="
grep -an -B4 -A12 'user_id=999' /tmp/recovery.log 2>/dev/null | head -60
echo "=== USB GADGET FUNCTIONS AVAILABLE ==="
ls -1 /config/usb_gadget/g1/functions/ 2>&1 | head -20
echo "--- configs b.1 ---"
ls -1 /config/usb_gadget/g1/configs/b.1/ 2>&1 | head -20
echo "--- current UDC / idProduct ---"
cat /config/usb_gadget/g1/UDC 2>/dev/null
cat /config/usb_gadget/g1/idProduct 2>/dev/null
echo "=== USB PROPS ==="
for p in sys.usb.config sys.usb.state sys.usb.configfs sys.usb.ffs.mtp.ready sys.usb.ffs.ready sys.usb.controller persist.sys.usb.config; do echo "$p = $(getprop $p)"; done
echo "=== MTP INTERCEPTION IN RC ==="
grep -n -A2 -B1 'sys.usb.config=mtp\|y52s' /init.recovery.usb.rc 2>/dev/null | head -40
echo "=== prop.default usb lines ==="
grep -n 'usb' /prop.default 2>/dev/null | head -20
echo "=== END ==="
