#!/sbin/sh
# read-only-ish: exercises the rc gate and RESTORES every property it changes.
echo "decrypt prop before = $(getprop twrp.user.0.decrypt)"
echo "config before       = $(getprop sys.usb.config)"

# simulate: user 0 decrypted, then user enables MTP in Mount
setprop twrp.user.0.decrypt 1
setprop sys.usb.ffs.mtp.ready 1
sleep 2
echo "config with decrypt=1 + mtp ready=1 = $(getprop sys.usb.config)"
echo "  f1 = $(readlink /config/usb_gadget/g1/configs/b.1/f1 2>/dev/null)"
echo "  f2 = $(readlink /config/usb_gadget/g1/configs/b.1/f2 2>/dev/null)"

# simulate: user disables MTP
setprop sys.usb.ffs.mtp.ready 0
sleep 1
echo "config after MTP off = $(getprop sys.usb.config)"

# restore the real (not-yet-decrypted) state
setprop twrp.user.0.decrypt 0
echo "decrypt prop after   = $(getprop twrp.user.0.decrypt)"
echo "=== GATE_TEST_DONE ==="
