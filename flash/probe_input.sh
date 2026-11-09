#!/system/bin/sh
# Read-only: find which input nodes the TWRP GUI process actually opened.
echo "=== recovery pid ==="
ps -A | grep -i recovery
echo "=== fds pointing at /dev/input ==="
for p in /proc/[0-9]*; do
    hit=$(ls -l "$p/fd" 2>/dev/null | grep '/dev/input')
    if [ -n "$hit" ]; then
        echo "--- $p (cmdline: $(cat "$p/cmdline" 2>/dev/null | tr '\0' ' '))"
        echo "$hit"
    fi
done
echo "=== recovery fd list (all) ==="
for p in /proc/[0-9]*; do
    c=$(cat "$p/cmdline" 2>/dev/null | tr '\0' ' ')
    case "$c" in *recovery*) echo "--- $p : $c"; ls -l "$p/fd" 2>/dev/null | head -40;; esac
done
echo "=== twrp input-related props / logs ==="
getprop | grep -iE 'tw_input|tw_.*touch|input|ro.minui|twrp.version'
grep -aiE 'Input|evdev|touch|event[0-9]|minui|ABS|keyboard' /tmp/recovery.log 2>/dev/null | head -40
echo "=== END ==="
