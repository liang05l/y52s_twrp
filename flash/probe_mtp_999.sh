#!/sbin/sh
# read-only probe; any decrypt command line is REDACTED before printing
echo "=== USB / MTP PROPS ==="
for p in sys.usb.config sys.usb.state sys.usb.configfs sys.usb.ffs.mtp.ready sys.usb.ffs.ready persist.sys.usb.config; do
  echo "$p = $(getprop $p)"
done
echo "=== USER / DECRYPT PROPS ==="
getprop | grep -iE 'twrp\.user|tw_all_users|tw_mtp|tw_is_decrypted|ro.crypto' | head -20
echo "=== DATA VIEW (is it decrypted?) ==="
ls -1 /data/media/0 2>/dev/null | head -10
echo "COUNT=$(ls -1 /data/media/0 2>/dev/null | wc -l)"
echo "=== GADGET ==="
for f in /config/usb_gadget/g1/configs/b.1/f1 /config/usb_gadget/g1/configs/b.1/f2; do
  echo "$f -> $(readlink $f 2>/dev/null)"
done
echo "idProduct=$(cat /config/usb_gadget/g1/idProduct 2>/dev/null)"
echo "=== MTP PROCESSES / FFS ENDPOINT ==="
ps -A | grep -iE 'mtp|mtpd|twrp' | head -10
ls -l /dev/usb-ffs/mtp/ 2>&1 | head -8
echo "=== TWRP SETTINGS (mtp switch) ==="
cat /cache/recovery/.twrps 2>/dev/null | head -20
echo "=== DECRYPT LOG (password REDACTED) ==="
grep -aiE 'decrypt|user_id=999|User 999|km_error|SPBLOB|unwrap|synthetic|Failed to decrypt' /tmp/recovery.log 2>/dev/null \
  | sed -E "s/(decrypt )[^ ]+/\1<REDACTED>/g; s/(Command 'decrypt )[^']*/\1<REDACTED>/g" \
  | tail -45
echo "=== END ==="
