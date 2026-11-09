#!/sbin/sh
# read-only probe of the MTP toggle path; decrypt command lines are redacted
echo "=== USB PROPS ==="
for p in sys.usb.config sys.usb.state sys.usb.configfs sys.usb.ffs.mtp.ready sys.usb.ffs.ready sys.usb.controller persist.sys.usb.config; do
  echo "$p = $(getprop $p)"
done
echo "=== DECRYPT / MTP DATA VARS ==="
getprop | grep -iE 'twrp\.user|tw_all_users|tw_mtp|tw_is_decrypted' | head -20
echo "=== GADGET ==="
for f in /config/usb_gadget/g1/configs/b.1/f1 /config/usb_gadget/g1/configs/b.1/f2; do
  echo "$f -> $(readlink $f 2>/dev/null)"
done
echo "functions dir: $(ls -1 /config/usb_gadget/g1/functions/ 2>/dev/null | tr '\n' ' ')"
echo "idProduct=$(cat /config/usb_gadget/g1/idProduct 2>/dev/null)"
echo "UDC=$(cat /config/usb_gadget/g1/UDC 2>/dev/null)"
echo "=== MTP FFS ENDPOINTS ==="
ls -l /dev/usb-ffs/mtp/ 2>&1 | head -8
echo "=== .twrps ==="
cat /cache/recovery/.twrps 2>/dev/null | head -10
echo "=== MTP-RELATED LOG (redacted) ==="
grep -aiE 'mtp|MTP|usb.config|Enable_MTP|Disable_MTP|toggle|decrypt' /tmp/recovery.log 2>/dev/null \
  | sed -E "s/(decrypt )[^ ]+/\1<REDACTED>/g; s/(Command 'decrypt )[^']*/\1<REDACTED>/g" \
  | tail -45
echo "=== END ==="
