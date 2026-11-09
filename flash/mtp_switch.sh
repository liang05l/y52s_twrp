#!/sbin/sh
# y52s: switch the configfs USB gadget between adb-only and adb+MTP.
#
# Why this exists: TWRP 12.1 Enable_MTP() sets sys.usb.config=mtp,adb, but the
# Y73s configfs action for that value also requires sys.usb.ffs.mtp.ready=1,
# a property only ever CLEARED by Disable_MTP() on this device. So ffs.mtp is
# never linked into the gadget and the PC sees no MTP device (just a beep).
# This script performs the missing configfs switch itself.
#
# Usage: sh mtp_switch.sh on|off
# Run it in the background: UDC is briefly disconnected, which may drop adb.
G=/config/usb_gadget/g1
C=$G/configs/b.1
MODE=${1:-on}
UDC=$(getprop sys.usb.controller)
[ -z "$UDC" ] && UDC=musb-hdrc

log() { echo "[mtp_switch] $*"; }
log "mode=$MODE udc=$UDC"
log "before: $(getprop sys.usb.config) | f1=$(readlink $C/f1 2>/dev/null) f2=$(readlink $C/f2 2>/dev/null)"

# FunctionFS must be mounted and the function nodes must exist.
mkdir -p $G/functions/ffs.mtp 2>/dev/null
mkdir -p /dev/usb-ffs/mtp 2>/dev/null
if ! mount | grep -q '/dev/usb-ffs/mtp'; then
    mount -t functionfs mtp /dev/usb-ffs/mtp rmode=0770,fmode=0660,uid=2000,gid=2000 2>/dev/null
fi

# Disconnect the gadget before changing its configuration symlinks.
echo "" > $G/UDC 2>/dev/null
sleep 1
rm -f $C/f1 $C/f2 2>/dev/null

if [ "$MODE" = "on" ]; then
    write $C/strings/0x409/configuration "mtp_adb" 2>/dev/null || \
        echo "mtp_adb" > $C/strings/0x409/configuration 2>/dev/null
    echo "0x4ee2" > $G/idProduct 2>/dev/null
    ln -s $G/functions/ffs.mtp $C/f1 2>/dev/null
    ln -s $G/functions/ffs.adb $C/f2 2>/dev/null
    setprop sys.usb.config mtp,adb
    setprop sys.usb.state mtp,adb
else
    echo "0xd001" > $G/idProduct 2>/dev/null
    ln -s $G/functions/ffs.adb $C/f1 2>/dev/null
    setprop sys.usb.config adb
    setprop sys.usb.state adb
fi
sleep 1
echo "$UDC" > $G/UDC 2>/dev/null
log "after: $(getprop sys.usb.config) | f1=$(readlink $C/f1 2>/dev/null) f2=$(readlink $C/f2 2>/dev/null)"
log "idProduct=$(cat $G/idProduct 2>/dev/null) UDC=$(cat $G/UDC 2>/dev/null)"
log "MTP_SWITCH_DONE"
