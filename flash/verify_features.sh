#!/sbin/sh
echo "=== TOUCH INPUT DEVICE ==="
grep -A3 -B1 'vivo_ts' /proc/bus/input/devices 2>/dev/null | head -8
echo "=== FLASH-ENGINE FILES ==="
for f in /system/bin/unzip /system/bin/zipinfo /system/bin/twrp /system/lib64/libziparchive.so /system/etc/otacerts.zip /res/images; do
  if [ -e "$f" ]; then echo "OK  $f"; else echo "NO  $f"; fi
done
echo "=== INSTALL PAGE IN LOG ==="
grep -aE "Set page: 'install'|operation_start: 'Install'|Installing" /tmp/recovery.log 2>/dev/null | tail -8
echo "=== BRIGHTNESS ==="
ls -l /sys/class/leds/lcd-backlight/brightness 2>&1 | head -2
echo "=== USB ==="
getprop sys.usb.config
getprop sys.usb.state
getprop sys.usb.ffs.mtp.ready
echo "=== DATA COUNT ==="
ls -1 /data/media/0 2>/dev/null | wc -l
echo "=== END ==="
