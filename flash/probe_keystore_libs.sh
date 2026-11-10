#!/sbin/sh
echo "=== missing lib resolution ==="
for n in libwifikeystorehal.so libkeystore_aidl.so libkeystore_binder.so libkeystore_parcelables.so \
         vendor.vivo.hardware.wifi.keystore@1.0.so android.system.wifi.keystore@1.0.so \
         libkeystore-wifi-hidl.so libkeystore-engine-wifi-hidl.so; do
  if [ -e "/system/lib64/$n" ]; then
    echo "RAMDISK_OK   $n"
  elif [ -e "/mnt/vendor_ro/lib64/$n" ]; then
    echo "VENDOR64     $n"
  elif [ -e "/mnt/vendor_ro/lib/$n" ]; then
    echo "VENDOR32     $n"
  else
    echo "MISSING      $n"
  fi
done
echo "=== /system/bin/keystore full needed list ==="
strings /system/bin/keystore 2>/dev/null | grep '\.so$' | sort -u | head -40
echo "=== END ==="
