#!/system/bin/sh
for n in 0 1 10 30 55 56 57 58 90 95; do
  printf '%s ' "$n"
  dd if=/dev/block/by-name/recovery bs=1048576 skip=$n count=1 2>/dev/null | sha256sum | cut -c1-16
done
