#!/system/bin/sh
# ===========================================================================
# y52s TWRP adaptation - DEVICE-SIDE EVIDENCE COLLECTOR
# Runs ON THE DEVICE:  adb shell sh /data/local/tmp/y52s_collect.sh
# Driven from PC by:   collect/run_collect.ps1  (do not inline this in adb shell)
#
# Rules:
#  - This script GUESSES NOTHING. Every value is read from this device.
#  - It never deletes anything. Each run writes a new timestamped directory.
#  - Some items need root (raw partition dd). Failures are logged, not fatal.
#  - Output path is written to /sdcard/y52s_dump_latest.txt for the PC script.
# ===========================================================================
set -u
have() { command -v "$1" >/dev/null 2>&1; }

# Self-elevate once. The su -c string lives INSIDE this file, so no nested
# quoting ever passes through "adb shell" (the usual cause of broken dumps).
# If su is absent or denied, the script continues unprivileged and records
# which dd operations failed in collect.log.
if [ "$(id -u 2>/dev/null)" != "0" ] && [ -z "${Y52S_ELEVATED:-}" ] && have su; then
  su -c "Y52S_ELEVATED=1 sh $0" && exit 0
fi

STAMP=$(date +%Y%m%d_%H%M%S)
OUT="/sdcard/y52s_dump_${STAMP}"
mkdir -p "$OUT/props" "$OUT/fstab" "$OUT/images" || {
  echo "FATAL: cannot create $OUT"; exit 1;
}
echo "$OUT" > /sdcard/y52s_dump_latest.txt || {
  echo "FATAL: cannot write latest-pointer"; exit 1;
}

log() { echo "[y52s] $*"; }
safe_name() { echo "$1" | tr '/' '_'; }

# ---------------------------------------------------------------------------
# [A] Identity / exact OS build  -> TWRP branch + product makefile
# ---------------------------------------------------------------------------
getprop > "$OUT/props/getprop.all.txt" 2>&1
getprop | grep -iE 'vbmeta|verified|verity|avb|dynamic_partition|slot|crypto|fbe|encrypt|keymaster|gatekeeper|secure|dtbo|bootloader|hardware|platform|fingerprint|security_patch|sdk|release' \
  > "$OUT/props/security_subset.txt" 2>&1

for f in /default.prop /system/build.prop /system/system/build.prop \
         /vendor/build.prop /vendor/default.prop /product/build.prop \
         /odm/build.prop /system/etc/prop.default; do
  if [ -f "$f" ]; then
    cp "$f" "$OUT/props/$(safe_name "$f")" 2>>"$OUT/collect.log"
  fi
done

cat /proc/version          > "$OUT/proc_version.txt"      2>&1
uname -a                   > "$OUT/uname.txt"             2>&1
cat /proc/cmdline          > "$OUT/cmdline.txt"           2>&1
cat /proc/bootconfig        > "$OUT/bootconfig.txt"        2>&1
cat /proc/cpuinfo          > "$OUT/cpuinfo.txt"           2>&1
getprop ro.boot.slot_suffix > "$OUT/slot_suffix.txt"      2>&1
getprop ro.build.fingerprint > "$OUT/fingerprint.txt"     2>&1
log "[A] identity done"

# Root capability decides whether the partition images in [D] can be dumped.
# Recorded explicitly so a missing boot.img is diagnosed, never guessed.
{
  echo "uid=$(id -u 2>/dev/null)"
  echo "id=$(id 2>/dev/null)"
  echo "su=$(command -v su 2>/dev/null || echo NONE)"
  echo "magisk=$(command -v magisk 2>/dev/null || echo NONE)"
} > "$OUT/root_status.txt" 2>&1

# ---------------------------------------------------------------------------
# [B] Partition topology  -> recovery.fstab / partition sizes / A-B / dynamic
# ---------------------------------------------------------------------------
cat /proc/partitions > "$OUT/partitions.txt" 2>&1
ls -l /dev/block/by-name/ > "$OUT/byname.txt" 2>&1

: > "$OUT/byname_resolved.txt"
for p in /dev/block/by-name/*; do
  [ -e "$p" ] || continue
  printf '%-32s -> %s\n' "$(basename "$p")" "$(readlink -f "$p" 2>/dev/null)" \
    >> "$OUT/byname_resolved.txt"
done

for d in /dev/block/by-name /dev/block/platform/bootdevice/by-name /dev/block/mapper; do
  if [ -d "$d" ]; then
    ls -l "$d" > "$OUT/$(safe_name "$d").ls.txt" 2>&1
  fi
done
ls -l /dev/block/mapper/ > "$OUT/mapper.txt" 2>&1

# MediaTek partition info, if this kernel exposes it
cat /proc/dumchar_info > "$OUT/dumchar_info.txt" 2>&1

# Block geometry + raw GPT header (parsed offline, no assumption about layout)
for b in /sys/block/mmcblk0 /sys/block/sda /sys/block/nvme0n1; do
  [ -d "$b" ] || continue
  n=$(basename "$b")
  [ -f "$b/size" ] && cat "$b/size" > "$OUT/block_${n}_size.txt" 2>&1
  [ -f "$b/queue/logical_block_size" ] && \
    cat "$b/queue/logical_block_size" > "$OUT/block_${n}_lbs.txt" 2>&1
  ls "$b" > "$OUT/block_${n}_sysfs.txt" 2>&1
done
for raw in /dev/block/mmcblk0 /dev/block/sda /dev/block/nvme0n1; do
  [ -e "$raw" ] || continue
  dd if="$raw" of="$OUT/images/gpt_header.bin" bs=512 count=34 \
     >>"$OUT/collect.log" 2>&1 || log "WARN: GPT header not readable from $raw (need root?)"
  echo "$raw" > "$OUT/gpt_source.txt"
  break
done

# All fstab variants present on this exact build
for f in /fstab.* /system/etc/fstab.* /vendor/etc/fstab.* /product/etc/fstab.* \
         /odm/etc/fstab.* /system_root/system/etc/fstab.*; do
  [ -f "$f" ] || continue
  cp "$f" "$OUT/fstab/$(safe_name "$f")" 2>>"$OUT/collect.log"
done
if have lpdump; then
  lpdump > "$OUT/lpdump.txt" 2>&1
else
  echo "lpdump not present on device" > "$OUT/lpdump.txt"
fi
log "[B] partitions done"

# ---------------------------------------------------------------------------
# [C] Crypto / display / input surface  -> TWRP decrypt + UI capability
# ---------------------------------------------------------------------------
ls -l /vendor/lib64/hw/ /system/lib64/hw/ /vendor/lib/hw/ /system/lib/hw/ \
  > "$OUT/hw_modules.txt" 2>&1
cat /proc/mounts > "$OUT/mounts.txt" 2>&1
ls -l /dev/input/ > "$OUT/input_devices.txt" 2>&1
cat /sys/class/graphics/fb0/modes > "$OUT/fb0_modes.txt" 2>&1
ls -l /sys/class/backlight/ > "$OUT/backlight.txt" 2>&1
ls -l /dev/block/ > "$OUT/dev_block_ls.txt" 2>&1
log "[C] surface done"

# ---------------------------------------------------------------------------
# [D] Binary evidence: partition images (NO parsing, NO assumptions here)
#     Unpacking / header analysis is done offline from these files.
# ---------------------------------------------------------------------------
for n in boot recovery dtbo vbmeta vendor_boot init_boot misc metadata \
         boot_a boot_b recovery_a recovery_b vendor_boot_a vendor_boot_b \
         dtbo_a dtbo_b vbmeta_a vbmeta_b vbmeta_system vbmeta_vendor; do
  src="/dev/block/by-name/$n"
  [ -e "$src" ] || continue
  dd if="$src" of="$OUT/images/${n}.img" bs=1048576 \
     >>"$OUT/collect.log" 2>&1 || log "WARN: dd FAILED for $n (uid=$(id -u 2>/dev/null); boot may be read-protected by Magisk)"
done

# super is huge: take only the head for metadata analysis, never the whole image
if [ -e /dev/block/by-name/super ]; then
  dd if=/dev/block/by-name/super of="$OUT/images/super_head_4M.bin" \
     bs=1048576 count=4 >>"$OUT/collect.log" 2>&1 \
     || log "WARN: super head not readable"
fi
log "[D] images done"

# ---------------------------------------------------------------------------
# [E] Integrity manifest (host verifies these hashes after pull)
# ---------------------------------------------------------------------------
{
  echo "# y52s evidence manifest"
  echo "# generated_on_device: $(date)"
  echo "# fingerprint: $(getprop ro.build.fingerprint 2>/dev/null)"
  echo "# slot_suffix: $(getprop ro.boot.slot_suffix 2>/dev/null)"
  echo "# format: relative_path | bytes | sha256"
  find "$OUT" -type f ! -name 'manifest.txt' | sort | while read -r f; do
    sz=$(wc -c < "$f" 2>/dev/null || echo 0)
    h="UNAVAILABLE"
    if have sha256sum; then
      h=$(sha256sum "$f" 2>/dev/null | cut -d ' ' -f1)
    elif have toybox; then
      h=$(toybox sha256sum "$f" 2>/dev/null | cut -d ' ' -f1)
    fi
    [ -n "$h" ] || h="UNAVAILABLE"
    printf '%s | %s | %s\n' "${f#$OUT/}" "$sz" "$h"
  done
} > "$OUT/manifest.txt"

log "DONE -> $OUT"
log "Pull it with: collect/run_collect.ps1"
