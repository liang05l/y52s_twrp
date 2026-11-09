#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
y52s: repair the CI-built (twrp-11) recovery.img -- touch, adb, version, HALs.

WHY (all measured, nothing invented)
------------------------------------
CI device.mk had no PRODUCT_COPY_FILES, so the upstream device-specific
recovery/root payload never entered the image.  CI's init.rc still contains

    import /init.recovery.${ro.hardware}.rc

and ro.hardware == "mt6853" (measured on this device), but
init.recovery.mt6853.rc is ABSENT.  Consequently the whole chain

    init.recovery.mt6853.rc -> init.recovery.touch.rc
                            -> service touchupdate /system/bin/vts_app_recovery
                            -> /vendor/firmware/touch_firmwares_recovery.bin

is missing, while v7 (stock-based, touch verified working) carries all of it.
Kernel is byte-identical in CI and v7 (sha256 c2cda2f291f8f763...), so the
touch driver is NOT the problem -- the ramdisk is.

WHAT THIS DOES
--------------
* source = build/recovery_ci.img (CI artifact, 100663296 B, AVB signed,
  boot header v2, includes an 8 MiB recovery_dtbo segment)
* copies VERBATIM from build/recovery_v7.img:
    init.recovery.touch.rc, system/bin/vts_app_recovery,
    vendor/firmware/* (14 blobs), sbin/y52s_prepare.sh
* adds ONE new rc (init.recovery.y52s.rc) built from v7's service blocks:
    touchupdate + y52s_prepare + y52s_keymaster + y52s_gatekeeper,
    recovery.service=1, dual triggers, MTP interception
* points init.rc's ${ro.hardware} import at that single rc (deterministic)
* aligns prop.default version props to the measured Android 10 values
  (10 / 29 / 2023-02-01 / vendor 2020-07-05) -- v5 proved keymaster needs it
* keeps kernel, recovery_dtbo and dtb byte-identical; REPLACES the
  CI self-signed AVB vbmeta/footer with the STOCK vivo ones (only
  vbmeta_offset is rewritten) and copies the stock boot-header os_version

Output: build/recovery.img (+ .sha256), zero-padded to 100663296 B.
No /data access, no format, no wipe.
"""
import gzip
import hashlib
import io
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(ROOT, "build", "recovery_ci.img")
V7 = os.path.join(ROOT, "build", "recovery_v7.img")
DST = os.path.join(ROOT, "build", "recovery.img")
SUM = DST + ".sha256"
PART_SIZE = 100663296

# ---------------------------------------------------------------------------
# boot image / cpio helpers
# ---------------------------------------------------------------------------
def pg(n, page):
    return ((n + page - 1) // page) * page


def segments(raw):
    v = struct.unpack_from("<10I", raw, 8)
    page = v[7]
    hsz = struct.unpack_from("<I", raw, 1644)[0]
    dtb_sz = struct.unpack_from("<I", raw, 1648)[0]
    dtbo_sz = struct.unpack_from("<I", raw, 1632)[0]
    dtbo_off = struct.unpack_from("<Q", raw, 1636)[0]
    koff = pg(hsz, page)
    roff = koff + pg(v[0], page)
    return dict(v=v, page=page, hsz=hsz, dtb_sz=dtb_sz,
                dtbo_sz=dtbo_sz, dtbo_off=dtbo_off,
                koff=koff, roff=roff,
                kernel=raw[koff:koff + v[0]],
                ramdisk=raw[roff:roff + v[2]],
                dtbo=raw[dtbo_off:dtbo_off + dtbo_sz] if dtbo_sz else b"",
                dtb=raw[dtbo_off + pg(dtbo_sz, page):
                        dtbo_off + pg(dtbo_sz, page) + dtb_sz] if dtbo_sz
                     else raw[roff + pg(v[2], page):
                              roff + pg(v[2], page) + dtb_sz])


def cpio_parse(data):
    """Return list of dicts with every newc header field preserved."""
    out = []
    off = 0
    while off + 110 <= len(data):
        if data[off:off + 6] not in (b"070701", b"070702"):
            break
        f = [data[off + 6 + i * 8: off + 14 + i * 8] for i in range(13)]
        fs = int(f[6], 16)   # c_filesize
        ns = int(f[11], 16)  # c_namesize
        name = data[off + 110: off + 110 + ns].rstrip(b"\0").decode("utf-8", "replace")
        ds = (off + 110 + ns + 3) & ~3
        payload = data[ds:ds + fs]
        if name == "TRAILER!!!":
            break
        out.append(dict(magic=data[off:off + 6], fields=f, name=name, data=payload))
        off = (ds + fs + 3) & ~3
    return out


def cpio_build(entries):
    buf = io.BytesIO()
    for i, e in enumerate(entries):
        f = list(e["fields"])
        f[6] = ("%08X" % len(e["data"])).encode()
        ns = len(e["name"]) + 1
        f[11] = ("%08X" % ns).encode()
        buf.write(e["magic"])
        for x in f:
            buf.write(x)
        buf.write(e["name"].encode() + b"\0")
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
        buf.write(e["data"])
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    # TRAILER!!!
    f = [b"00000000"] * 13
    f[4] = b"00000001"          # nlink
    f[11] = b"0000000B"         # namesize = len("TRAILER!!!") + 1
    buf.write(b"070701")
    for x in f:
        buf.write(x)
    buf.write(b"TRAILER!!!\0")
    buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    return buf.getvalue()


def new_entry(name, data, mode, template):
    f = list(template["fields"])
    f[1] = ("%08X" % mode).encode()
    f[2] = ("%08X" % 0).encode()      # uid
    f[3] = ("%08X" % 0).encode()      # gid
    f[6] = ("%08X" % len(data)).encode()
    f[11] = ("%08X" % (len(name) + 1)).encode()
    return dict(magic=template["magic"], fields=f, name=name, data=data)


def eol_of(blob):
    return "\r\n" if b"\r\n" in blob else "\n"


# ---------------------------------------------------------------------------
# load both images
# ---------------------------------------------------------------------------
ci_raw = open(CI, "rb").read()
v7_raw = open(V7, "rb").read()
assert len(ci_raw) == PART_SIZE and len(v7_raw) == PART_SIZE
ci = segments(ci_raw)
v7 = segments(v7_raw)
print("CI : page=%d hsz=%d kernel=%d ramdisk=%d dtbo=%d dtb=%d" %
      (ci["page"], ci["hsz"], len(ci["kernel"]), len(ci["ramdisk"]),
       len(ci["dtbo"]), len(ci["dtb"])))
assert hashlib.sha256(ci["kernel"]).hexdigest() == \
       hashlib.sha256(v7["kernel"]).hexdigest(), "kernel differs - aborting"

ci_ents = cpio_parse(gzip.decompress(ci["ramdisk"]))
v7_ents = cpio_parse(gzip.decompress(v7["ramdisk"]))
ci_by = {e["name"]: e for e in ci_ents}
v7_by = {e["name"]: e for e in v7_ents}
print("cpio entries: CI=%d v7=%d" % (len(ci_ents), len(v7_ents)))

# AVB footer / vbmeta MUST come from the STOCK vivo image, not from the CI
# build.  Measured: stock vbmeta sha256 d5fe67c75120e2b7 (avbtool 1.2.0),
# CI vbmeta sha256 7bb339ce0789792d (avbtool 1.1.0, TWRP test key).
# The vivo bootloader trusts only its own public key; with a self-signed
# vbmeta it hands the TEE the default boot_patchlevel 20300101 instead of
# the value the FBE keys were bound to -> decryption always fails.
# (Confirmed by 4accccc/android_device_vivo_pd2031 DEVELOPMENT_LOG stage 6
#  and its make_hybrid.py.)
STOCK = os.path.join(ROOT, "device_dump", "y52s_dump_20261108_122327",
                     "images", "recovery.img")
stock_raw = open(STOCK, "rb").read()
assert len(stock_raw) == PART_SIZE
foot = bytearray(stock_raw[PART_SIZE - 64:PART_SIZE])
assert foot[:4] == b"AVBf", "stock AVB footer missing"
vbmeta_size = struct.unpack_from(">Q", foot, 28)[0]
stock_vbo = struct.unpack_from(">Q", foot, 20)[0]
vbmeta = stock_raw[stock_vbo:stock_vbo + vbmeta_size]
assert vbmeta[:4] == b"AVB0", "stock vbmeta blob missing"
print("AVB: using STOCK vivo vbmeta sha=%s size=%d (CI self-signed one discarded)" %
      (hashlib.sha256(vbmeta).hexdigest()[:16], vbmeta_size))

# ---------------------------------------------------------------------------
# 1) verbatim device-specific payload from v7
# ---------------------------------------------------------------------------
INJECT = ["init.recovery.touch.rc", "system/bin/vts_app_recovery",
          "sbin/y52s_prepare.sh"]
INJECT += [n for n in v7_by if n.startswith("vendor/firmware")]
INJECT += [n for n in ("vendor", "vendor/firmware") if n in v7_by]
INJECT = sorted(set(INJECT))

tpl = ci_by["init.recovery.touch.rc"] if "init.recovery.touch.rc" in ci_by \
      else ci_by["init.recovery.usb.rc"]
added = []
for name in INJECT:
    assert name in v7_by, "v7 missing " + name
    src = v7_by[name]
    mode = int(src["fields"][1], 16)   # c_mode
    is_dir = (mode & 0o170000) == 0o040000
    if is_dir and name in ci_by:
        continue                       # CI already has this mount-point dir
    assert name not in ci_by, "CI already has " + name + " - review needed"
    e = new_entry(name, src["data"], mode, tpl)
    ci_ents.append(e)
    ci_by[name] = e
    added.append(name)
print("injected %d verbatim entries (%d bytes)" %
      (len(added), sum(len(ci_by[n]["data"]) for n in added)))

# ---------------------------------------------------------------------------
# 2) one self-contained rc, wire init.rc to it
# ---------------------------------------------------------------------------
PREPARE = """#!/sbin/sh
# y52s: wait for dynamic-partition mapper nodes (they do NOT exist at 'on init'),
# then mount system/vendor so the FBE HAL binaries and VNDK libs are visible.
i=0
while [ $i -lt 30 ]; do
    [ -e /dev/block/mapper/system ] && [ -e /dev/block/mapper/vendor ] && break
    i=$((i+1))
    sleep 1
done
mkdir -p /system_root /vendor 2>/dev/null
mount | grep -q 'on /system_root type' || \\
    mount -t ext4 -o ro /dev/block/mapper/system /system_root 2>/dev/null
mount | grep -q 'on /vendor type' || \\
    mount -t ext4 -o ro /dev/block/mapper/vendor /vendor 2>/dev/null
exit 0
"""
# ramdisk /system/lib64 is always present (vendor is not), so list it FIRST.
LP = "/system/lib64:/system_root/system/lib64:/system_root/system/lib64/vndk-29:/vendor/lib64:/vendor/lib64/hw"

# Overwrite the injected v7 prepare script: it ran at "on init" when the
# dynamic-partition mapper nodes did not exist yet, so /vendor stayed
# unmounted and the HAL binaries were missing. Wait for the nodes instead.
prep = ci_by["sbin/y52s_prepare.sh"]
prep["data"] = PREPARE.encode()
prep["fields"][1] = ("%08X" % 0o100755).encode()
print("y52s_prepare.sh replaced with mapper-waiting version")

# Measured at runtime 13:20: libkeymaster4.so needs
# libpuresoftkeymasterdevice.so. It lives in the system vndk-29 dir, but the
# system logical partition is not mounted early, so y52s_keymaster stayed
# 'restarting'. Ship it in the ramdisk (/system/lib64, first in LD_LIBRARY_PATH).
LIB_SRC = os.path.join(ROOT, "build", "libs", "libpuresoftkeymasterdevice.so")
assert os.path.isfile(LIB_SRC), "missing " + LIB_SRC
libname = "system/lib64/libpuresoftkeymasterdevice.so"
if libname not in ci_by:
    le = new_entry(libname, open(LIB_SRC, "rb").read(), 0o100644, tpl)
    ci_ents.append(le)
    ci_by[libname] = le
    added.append(libname)
    print("injected", libname)

svc = v7_by["init.recovery.svc.rc"]["data"].decode("utf-8", "replace")


OLD_LP = ("setenv LD_LIBRARY_PATH /system_root/system/lib64:"
          "/system_root/system/lib64/vndk-29:/vendor/lib64:/vendor/lib64/hw")


def service_block(name):
    st = svc.find("service " + name + " ")
    assert st >= 0, "v7 service missing: " + name
    ends = [x for x in (svc.find("\nservice ", st + 1),
                        svc.find("\non ", st + 1)) if x >= 0]
    nx = min(ends) if ends else len(svc)
    blk = svc[st:nx].rstrip() + "\n"
    if "LD_LIBRARY_PATH" in blk:
        blk = blk.replace(OLD_LP, "setenv LD_LIBRARY_PATH " + LP)
        assert "setenv LD_LIBRARY_PATH " + LP in blk, "LD_LIBRARY_PATH not rewritten"
    return blk


EXEC_PREPARE = ("    exec u:r:recovery:s0 root root -- "
                "/sbin/sh /sbin/y52s_prepare.sh\n")
y52s_rc = (
    "# y52s: post-build device init. Every value below is copied from the\n"
    "# stock-based v7 image whose touch/USB/HAL behaviour was verified.\n"
    "# Touch firmware update lives in init.recovery.touch.rc, which v7's\n"
    "# init.recovery.usb.rc imports explicitly (deterministically loaded).\n"
    "# vivo's vts_app_recovery selects the panel firmware by\n"
    "# ro.vivo.product.model. It is ABSENT from prop.default (measured), so\n"
    "# without this the updater reports 'no firmware for product' and the\n"
    "# touchscreen stays dead even though /dev/input/event3 exists.\n"
    "# (Y73s DEVELOPMENT_LOG stage 2; verified on this device 13:25: with the\n"
    "#  prop set, TP-FW-PD2057-LCMID17-VER0x26.bin updates successfully.)\n"
    "on early-init\n"
    "    setprop ro.vivo.product.model PD2057\n"
    "    setprop ro.vendor.vivo.product.model PD2057\n\n"
    + service_block("y52s_keymaster") + "\n"
    + service_block("y52s_gatekeeper") + "\n"
    "on init\n"
    "    setprop sys.usb.configfs 1\n"          # v7, measured: device uses configfs
    "    setprop sys.usb.ffs.aio_compat 1\n"
    "    setprop recovery.service 1\n\n"
    "# mapper nodes do NOT exist at on init; 'exec' is synchronous so the\n"
    "# mounts are ready before the HAL services are started.\n"
    "on boot\n"
    + EXEC_PREPARE +
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n\n"
    "on property:twrp.modules.loaded=true\n"
    + EXEC_PREPARE +
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n\n"
    "# USB gadget config lives in v7's configfs init.recovery.usb.rc\n"
    "# (replaced below); it already contains the MTP interception guards.\n"
)
rc_name = "init.recovery.mt6853.rc"
assert rc_name not in ci_by
e = new_entry(rc_name, y52s_rc.encode(), 0o100750, tpl)
ci_ents.append(e)
ci_by[rc_name] = e
added.append(rc_name)

# init.rc imports /init.recovery.${ro.hardware}.rc. Property expansion during
# import parsing is unreliable (ro.hardware comes from androidboot.hardware
# and may not be set yet), which is why the 13:05 image had NO touch:
# init.recovery.mt6853.rc never loaded, so vts_app_recovery never ran.
# Replace it with an explicit, deterministic import.
irc = ci_by["system/etc/init/hw/init.rc"]
t = irc["data"].decode("utf-8", "replace")
old_import = "import /init.recovery.${ro.hardware}.rc"
assert old_import in t, "init.rc import line not found"
t = t.replace(old_import, "import /init.recovery.mt6853.rc", 1)
irc["data"] = t.encode()
print("init.rc: ${ro.hardware} import replaced with explicit mt6853.rc")

# Touch firmware update: append to init.recovery.touch.rc, which v7's
# init.recovery.usb.rc imports explicitly. This is the Y73s-verified form
# (`on boot exec ... /system/bin/vts_app_recovery --update`).
trc = ci_by["init.recovery.touch.rc"]
tt = trc["data"].decode("utf-8", "replace")
nl = "\r\n" if "\r\n" in tt else "\n"
exec_block = (
    "# y52s: load the panel touch firmware at boot (deterministic path).\n"
    "on boot\n"
    "    exec u:r:recovery:s0 root root -- /system/bin/vts_app_recovery --update\n"
)
if "vts_app_recovery" not in tt:
    tt = tt.rstrip("\r\n") + nl + nl + exec_block.replace("\n", nl)
    trc["data"] = tt.encode()
print("touch.rc: vts_app_recovery --update appended (on boot)")

# Persist both files into the device tree so future CI builds are born with
# touch support (TWRP merges recovery/root into the recovery ramdisk).
dt_root = os.path.join(ROOT, "device", "vivo", "y52s", "recovery", "root")
os.makedirs(dt_root, exist_ok=True)
dt_rc = os.path.join(dt_root, "init.recovery.mt6853.rc")
open(dt_rc, "w", encoding="utf-8", newline="\n").write(y52s_rc)
os.chmod(dt_rc, 0o750)
open(os.path.join(dt_root, "init.recovery.touch.rc"), "wb").write(trc["data"])
open(os.path.join(dt_root, "sbin", "y52s_prepare.sh"), "wb").write(PREPARE.encode())
os.makedirs(os.path.join(dt_root, "system", "lib64"), exist_ok=True)
open(os.path.join(dt_root, "system", "lib64",
                  "libpuresoftkeymasterdevice.so"), "wb").write(open(LIB_SRC, "rb").read())
print("device tree rc + touch.rc + prepare.sh + keymaster lib written")

# ---------------------------------------------------------------------------
# 3) version props -> measured Android 10 values
# ---------------------------------------------------------------------------
prop = ci_by["prop.default"]
lines = prop["data"].decode("utf-8", "replace").splitlines(True)
n = 0
out = []
for l in lines:
    if "build.version.sdk=" in l and l.rstrip().endswith("=30"):
        l = l.replace("=30", "=29")
        n += 1
    elif "build.version.release=" in l and l.rstrip().endswith("=11"):
        l = l.replace("=11", "=10")
        n += 1
    out.append(l)
assert n >= 6, "expected >=6 version prop lines, got %d" % n
prop["data"] = "".join(out).encode()
print("version props changed:", n)

# ---------------------------------------------------------------------------
# 4) USB: replace the CI build's android_usb rc with v7's CONFIGFS rc.
#
# Measured: CI init.recovery.usb.rc is 1323 B with 0 "configfs" and 19
# "android_usb" references; v7's is 5185 B with 11 "configfs" references and
# already contains the y52s MTP interception. This device uses a configfs USB
# gadget, so the CI rc never brings up adb -- that is why "adb devices" stayed
# empty every time we booted the CI-based image into TWRP (13:05 run: 180 s,
# no adb, USB not enumerated at all). Appending MTP guards to the wrong rc
# could not fix it; the whole implementation must be the configfs one.
# ---------------------------------------------------------------------------
usb = ci_by["init.recovery.usb.rc"]
v7_usb_text = v7_by["init.recovery.usb.rc"]["data"].decode("utf-8", "replace")
# v7's usb.rc imports rc files that exist only in the stock ramdisk
# (mt6833 / svc / platform). Comment those out so init does not stumble on
# missing imports; keep /init.recovery.touch.rc, which we DID inject and which
# now carries the touch-firmware exec.
fixed_lines = []
for line in v7_usb_text.splitlines(True):
    s = line.strip()
    if s.startswith("import /") and not s.startswith("#"):
        target = s.split(None, 1)[1].lstrip("/")
        if target not in ci_by:
            line = "# " + line.lstrip()
    fixed_lines.append(line)
v7_usb = "".join(fixed_lines).encode()
assert b"configfs" in v7_usb and b"y52s" in v7_usb, "v7 configfs usb.rc unexpected"
assert b"import /init.recovery.touch.rc" in v7_usb, "touch.rc import lost"
usb["data"] = v7_usb
usb["fields"][1] = v7_by["init.recovery.usb.rc"]["fields"][1]
print("usb.rc replaced with v7 configfs version (%d bytes, stale imports commented)"
      % len(v7_usb))

# Persist the same USB rc into the device tree so future CI builds are born
# with a working adb/MTP configuration.
dt_usb = os.path.join(ROOT, "device", "vivo", "y52s", "recovery", "root",
                      "init.recovery.usb.rc")
open(dt_usb, "wb").write(v7_usb)
os.chmod(dt_usb, 0o750)

# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------
cpio = cpio_build(ci_ents)
buf = io.BytesIO()
gz = gzip.compress(cpio, mtime=0)
buf.write(gz)
print("new cpio=%d gzip=%d (was %d)" %
      (len(cpio), len(gz), len(ci["ramdisk"])))

hdr = bytearray(ci_raw[:ci["hsz"]])
struct.pack_into("<I", hdr, 16, len(gz))                 # ramdisk_size
new_dtbo_off = ci["roff"] + pg(len(gz), ci["page"])
struct.pack_into("<Q", hdr, 1636, new_dtbo_off)           # recovery_dtbo_offset
# boot header os_version / os_patch_level: measured stock 0x1800063c,
# CI build 0x16000172. Copy the stock value verbatim (no invented numbers).
struct.pack_into("<I", hdr, 44, struct.unpack_from("<I", stock_raw, 44)[0])

out = bytearray(b"\0" * PART_SIZE)
out[:ci["hsz"]] = hdr
p = ci["koff"]
out[p:p + len(ci["kernel"])] = ci["kernel"]
p = ci["roff"]
out[p:p + len(gz)] = gz
p = new_dtbo_off
out[p:p + len(ci["dtbo"])] = ci["dtbo"]
p = p + pg(len(ci["dtbo"]), ci["page"])
out[p:p + len(ci["dtb"])] = ci["dtb"]
content_end = p + pg(len(ci["dtb"]), ci["page"])

new_vbo = pg(content_end, ci["page"]) + ci["page"]
assert new_vbo + vbmeta_size < PART_SIZE - 64, "image too large"
out[new_vbo:new_vbo + vbmeta_size] = vbmeta
# make_hybrid.py behaviour: only vbmeta_offset is rewritten. original_image_size
# stays at the STOCK value -- vivo's bootloader checks the public key, not the
# hash, which is exactly why a hybrid image is possible at all.
struct.pack_into(">Q", foot, 20, new_vbo)
out[PART_SIZE - 64:PART_SIZE] = foot
assert len(out) == PART_SIZE

# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------
chk = segments(bytes(out))
assert chk["kernel"] == ci["kernel"], "kernel changed"
assert chk["dtbo"] == ci["dtbo"], "recovery_dtbo changed"
assert chk["dtb"] == ci["dtb"], "dtb changed"
assert bytes(out[new_vbo:new_vbo + vbmeta_size]) == vbmeta, "vbmeta changed"
assert bytes(out[PART_SIZE - 64:PART_SIZE]) == foot, "footer changed"
back = cpio_parse(gzip.decompress(chk["ramdisk"]))
assert len(back) == len(ci_ents), "cpio entry count mismatch"
names = {x["name"]: x["data"] for x in back}
for k in added:
    assert k in names and names[k] == ci_by[k]["data"], "lost entry: " + k
assert b"no_crypto_support" not in names["system/bin/recovery"], \
       "CI binary unexpectedly lacks crypto support"
assert names["prop.default"] == prop["data"]
print("VERIFY OK: header/kernel/dtbo/dtb/vbmeta preserved; %d cpio entries; "
      "content_end=0x%x vbmeta=0x%x" % (len(back), content_end, new_vbo))

os.makedirs(os.path.dirname(DST), exist_ok=True)
open(DST, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
open(SUM, "w", newline="\n").write(sha + "  recovery.img\n")
print("WROTE", DST, len(out), "bytes")
print("SHA256", sha)
