#!/sbin/sh
# y52s v4: mount logical system/vendor so the FBE HAL binaries exist.
mkdir -p /system_root /vendor 2>/dev/null
mount | grep -q 'on /system_root type' || mount -t ext4 -o ro /dev/block/mapper/system /system_root
mount | grep -q 'on /vendor type' || mount -t ext4 -o ro /dev/block/mapper/vendor /vendor
exit 0
