#!/system/bin/sh
# y52s: read-only evidence collector for TWRP verification.
# Pushed to the device and run as a FILE (no inline adb shell quoting).
# Writes everything to /tmp/y52s_verify.txt; never writes to /data.
OUT=/tmp/y52s_verify.txt
: > "$OUT"
say() { echo "" >> "$OUT"; echo "===== $* =====" >> "$OUT"; }

say "IDENTITY"
getprop ro.product.model ro.product.device ro.build.fingerprint \
        ro.build.version.bbk ro.twrp.version >> "$OUT" 2>&1
echo "uptime: $(cat /proc/uptime 2>/dev/null)" >> "$OUT"
echo "mode: $(getprop ro.bootmode 2>/dev/null) / $(getprop sys.boot.reason 2>/dev/null)" >> "$OUT"

say "RECOVERY MAIN PROCESS"
ps -A 2>/dev/null | grep -iE 'recovery|twrp' >> "$OUT"
echo "binary: $(ls -l /system/bin/recovery 2>&1)" >> "$OUT"
echo "sha256: $(sha256sum /system/bin/recovery 2>/dev/null | cut -d' ' -f1)" >> "$OUT"

say "PARTITION HASH (must match the flashed image)"
sha256sum /dev/block/by-name/recovery >> "$OUT" 2>&1

say "CRYPTO / FBE PROPS"
getprop | grep -iE 'crypto|fbe|decrypt|tw_is_|keymaster_ver|twrp.version' >> "$OUT"

say "USB / MTP"
getprop | grep -iE 'sys.usb.config|sys.usb.state|ffs.mtp.ready|persist.sys.usb' >> "$OUT"

say "HAL SERVICES"
getprop | grep -iE 'init.svc.(y52s|keymaster|gatekeeper|mobicore|keystore)' >> "$OUT"
ps -A 2>/dev/null | grep -iE 'keymaster|gatekeeper|mobicore|trustonic|keystore|vold' >> "$OUT"

say "MOUNTS"
mount 2>/dev/null | grep -E '/data|/vendor|system_root|/metadata|/cache' >> "$OUT"

say "TOUCH INPUT DEVICES"
cat /proc/bus/input/devices 2>/dev/null | grep -E '^(I:|N:|P:|S:|H:|B:)' | head -120 >> "$OUT"
echo "--- /dev/input nodes ---" >> "$OUT"
ls -l /dev/input/ 2>&1 >> "$OUT"
echo "--- getevent -il (2s sample) ---" >> "$OUT"
timeout 2 getevent -il 2>&1 | head -60 >> "$OUT"

say "DATA VIEW (normal names = decrypted; base64-like = CE key missing)"
ls -1 /data/media/0 2>&1 | head -20 >> "$OUT"
echo "count: $(ls -1 /data/media/0 2>/dev/null | wc -l)" >> "$OUT"

say "BOOT PATCHLEVEL / TEE"
dmesg 2>/dev/null | grep -iE 'boot_patchlevel|patchlevel|tee|keymaster|trustonic|avb' | tail -30 >> "$OUT"
logcat -d 2>/dev/null | grep -aiE 'CANNOT LINK|keystore2|boot_patchlevel|os_version|os_patchlevel|TrustonicKeymaster|TlcTeeGatekeeper' | tail -30 >> "$OUT"

say "RECOVERY.LOG DECRYPTION LINES"
grep -aiE 'TW_INCLUDE_CRYPTO|File Based|DE keys|decrypt|password|Keymaster_Ver|FBE contents|Is_Encrypted|no_crypto|patchlevel' \
     /tmp/recovery.log 2>/dev/null | tail -40 >> "$OUT"

say "LINKER / HAL ERRORS"
logcat -d 2>/dev/null | grep -aiE 'CANNOT LINK|library .* not found|Unable to start service|init.*parse' | tail -20 >> "$OUT"

echo "" >> "$OUT"
echo "===== END =====" >> "$OUT"
echo "COLLECTED"
