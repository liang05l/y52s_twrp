#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Port the verified vivo Y73s (PD2031) TWRP image to this vivo Y52s (PD2057).

Why this exists
---------------
4accccc/android_device_vivo_pd2031 @ twrp-12.1 is a FULLY WORKING TWRP for a
device with the same MT6853 / k6853v1_64_6360 / Android 10 / dynamic-partition
/ FBE platform. Its README explicitly says y52s can use it "with small fixes,
mostly editing props". Its ramdisk contains the whole decryption stack that
our twrp-11 CI build lacks (resetprop, wait_for_keymaster, guardianangle,
vivotool/vivofbe, libvivofscrypt, mcRegistry trustlets, vintf manifest).

Porting rules -- every substituted value is MEASURED on this device, not guessed:
  * kernel / dtb   <- Y52s STOCK (display + touch drivers must match the panel;
                     v7 proved this combination boots and shows the GUI)
  * recovery_dtbo  <- 0 (Y52s stock layout; v7 uses this)
  * boot header os_version <- THIS DEVICE's real boot partition header
        (build/y52s_boot_hdr.bin, read via dd): 0x14000172 = Android 10.0.0 /
        2023-02. The "stock" recovery image we dumped is itself a TWRP build
        whose header is the hack value 0x1800063c = 12.0.0 / 2099-12; copying
        that value made the TEE demand KEY_REQUIRES_UPGRADE (-62) on every key.
  * embedded vbmeta properties <- replace the same hack values
        (boot.security_patch 2099-12-31 -> 2023-02-01,
         boot.os_version 16.1.0 -> 10.0.0). Same-length in-place edits; the
         vivo LK verifies only the public key, not the hash (Y73s dev log 6.5).
  * prop.default   <- PD2031 -> PD2057, compiler10052108 -> compiler04181705,
                      compiler10052108 in description -> compiler09042257,
                      security_patch 2020-09-01 -> 2023-02-01,
                      all *.version.sdk 32 -> 29, build.id -> QP1A.190711.020
  * fstab          <- device/vivo/y52s/recovery.fstab (measured partition set)
  * touch firmware <- Y52s v7 vendor/firmware/* (14 blobs, PD2057 panel)
  * gatekeeper rc  <- keep /vendor/bin/... : that is where the Y73s ramdisk
        actually ships the binary (verified on the running image). Rewriting
        it to /vendor/bin/hw/... (which exists on the Y52s VENDOR PARTITION,
        not in this ramdisk) leaves the service unregistered.
  * AVB footer/vbmeta <- Y52s STOCK (make_hybrid.py rule)

Output: build/recovery_y73s_port.img (+ .sha256). ALWAYS run make_hybrid.py
afterwards if the input layout changes.

STATUS: this is an UNVERIFIED FALLBACK. The primary deliverable remains
build/recovery.img (CI-based, with the stock AVB fix). Flash this only if the
primary image fails decryption on the device.
"""
import gzip
import hashlib
import io
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y73S = os.path.join(ROOT, "build", "reference", "y73s_twrp.img")
STOCK = os.path.join(ROOT, "device_dump", "y52s_dump_20261108_122327",
                     "images", "recovery.img")
V7 = os.path.join(ROOT, "build", "recovery_v7.img")
FSTAB = os.path.join(ROOT, "device", "vivo", "y52s", "recovery.fstab")
BOOT_HDR = os.path.join(ROOT, "build", "y52s_boot_hdr.bin")
DST = os.path.join(ROOT, "build", "recovery_y73s_port.img")
PART_SIZE = 100663296


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
    return dict(v=v, page=page, hsz=hsz, dtb_sz=dtb_sz, dtbo_sz=dtbo_sz,
                dtbo_off=dtbo_off, koff=koff, roff=roff,
                kernel=raw[koff:koff + v[0]],
                ramdisk=raw[roff:roff + v[2]],
                dtb=raw[(dtbo_off + pg(dtbo_sz, page)) if dtbo_sz
                        else roff + pg(v[2], page):
                        ((dtbo_off + pg(dtbo_sz, page)) if dtbo_sz
                         else roff + pg(v[2], page)) + dtb_sz])


def cpio_parse(data):
    out, off = [], 0
    while off + 110 <= len(data):
        if data[off:off + 6] not in (b"070701", b"070702"):
            break
        f = [data[off + 6 + i * 8: off + 14 + i * 8] for i in range(13)]
        fs, ns = int(f[6], 16), int(f[11], 16)
        name = data[off + 110:off + 110 + ns].rstrip(b"\0").decode("utf-8", "replace")
        ds = (off + 110 + ns + 3) & ~3
        if name == "TRAILER!!!":
            break
        out.append(dict(magic=data[off:off + 6], fields=f, name=name,
                        data=data[ds:ds + fs]))
        off = (ds + fs + 3) & ~3
    return out


def cpio_build(entries):
    buf = io.BytesIO()
    for e in entries:
        f = list(e["fields"])
        f[6] = ("%08X" % len(e["data"])).encode()
        f[11] = ("%08X" % (len(e["name"]) + 1)).encode()
        buf.write(e["magic"])
        for x in f:
            buf.write(x)
        buf.write(e["name"].encode() + b"\0")
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
        buf.write(e["data"])
        buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    f = [b"00000000"] * 13
    f[4], f[11] = b"00000001", b"0000000B"
    buf.write(b"070701")
    for x in f:
        buf.write(x)
    buf.write(b"TRAILER!!!\0")
    buf.write(b"\0" * ((4 - buf.tell() % 4) % 4))
    return buf.getvalue()


def new_entry(name, data, mode, template):
    f = list(template["fields"])
    f[1] = ("%08X" % mode).encode()
    f[6] = ("%08X" % len(data)).encode()
    f[11] = ("%08X" % (len(name) + 1)).encode()
    return dict(magic=template["magic"], fields=f, name=name, data=data)


# ---------------------------------------------------------------------------
y_raw, s_raw, v7_raw = (open(p, "rb").read() for p in (Y73S, STOCK, V7))
assert len(y_raw) == len(s_raw) == len(v7_raw) == PART_SIZE
y, s, v7 = segments(y_raw), segments(s_raw), segments(v7_raw)
print("Y73s : kernel=%d ramdisk=%d dtbo=%d dtb=%d" %
      (len(y["kernel"]), len(y["ramdisk"]), y["dtbo_sz"], y["dtb_sz"]))
print("Y52s : kernel=%d dtb=%d (stock layout)" % (len(s["kernel"]), s["dtb_sz"]))

y_ents = cpio_parse(gzip.decompress(y["ramdisk"]))
v7_ents = cpio_parse(gzip.decompress(v7["ramdisk"]))
by = {e["name"]: e for e in y_ents}
v7by = {e["name"]: e for e in v7_ents}
tpl = by["prop.default"]
print("Y73s cpio entries:", len(y_ents))

# --- 1) props: every value below is measured on this Y52s --------------------
PROP = by["prop.default"]
t = PROP["data"].decode("utf-8", "replace")
subs = [
    ("PD2031", "PD2057"),
    ("compiler10052108", "compiler04181705"),
    ("ro.build.version.security_patch=2020-09-01",
     "ro.build.version.security_patch=2023-02-01"),
    ("ro.product.build.id=SP2A.220405.004",
     "ro.product.build.id=QP1A.190711.020"),
    ("full_k6853v1_64_6360-user 10 QP1A.190711.020 compiler04181705 release-keys",
     "full_k6853v1_64_6360-user 10 QP1A.190711.020 compiler09042257 release-keys"),
]
n = 0
for old, new in subs:
    c = t.count(old)
    assert c > 0, "prop pattern not found: " + old
    t = t.replace(old, new)
    n += c
lines = t.splitlines(True)
out_lines = []
for l in lines:
    if "build.version.sdk=" in l and l.rstrip().endswith("=32"):
        l = l.replace("=32", "=29")
        n += 1
    out_lines.append(l)
PROP["data"] = "".join(out_lines).encode()
print("prop substitutions:", n)

# --- 1b) USB composite: adb + MTP simultaneously ----------------------------
# init.rc defaults sys.usb.config to "adb", and the old prop.default carries
# four "persist.sys.usb.config=none" lines that override the first value.
# The Y73s mt6853.rc already contains the complete configfs action for
# "mtp,adb" (ffs.mtp -> f1 AND ffs.adb -> f2, idProduct 0x4ee2), so both
# interfaces can be enabled at once; the system-mode PnP on this device shows
# VID_2D95&PID_6013 MI_00 (mass storage/MTP) + MI_01 (ADB) together.
usb = PROP["data"].decode("utf-8", "replace")
usb = usb.replace("persist.sys.usb.config=adb",
                  "persist.sys.usb.config=mtp,adb")
usb = usb.replace("persist.sys.usb.config=none",
                  "persist.sys.usb.config=mtp,adb")
PROP["data"] = usb.encode()
print("prop.default: persist.sys.usb.config -> mtp,adb (all occurrences)")

# --- 2) fstab: Y52s measured partition set ----------------------------------
F = by["system/etc/recovery.fstab"]
F["data"] = open(FSTAB, "rb").read()
print("fstab replaced with measured y52s fstab (%d bytes)" % len(F["data"]))

# --- 3) touch firmware: drop PD2031 blobs, add Y52s PD2057 blobs ------------
for name in [k for k in by if k.startswith("vendor/firmware/")]:
    del by[name]
    y_ents = [e for e in y_ents if e["name"] != name]
fw_added = []
for e in v7_ents:
    if e["name"].startswith("vendor/firmware/"):
        if e["name"] in by:
            continue
        ne = new_entry(e["name"], e["data"], int(e["fields"][1], 16), tpl)
        y_ents.append(ne)
        by[ne["name"]] = ne
        fw_added.append(ne["name"])
print("touch firmware replaced with %d Y52s blobs" % len(fw_added))

# --- 4b) Y73s puts configfs USB + the touch exec in
# init.recovery.mt6853.rc, loaded only by init.rc's ${ro.hardware} import.
# Property expansion there is unreliable (measured on this device), so make
# the import explicit. Otherwise neither adb nor the touch updater starts.
irc = by["system/etc/init/hw/init.rc"]
it = irc["data"].decode("utf-8", "replace")
old_import = "import /init.recovery.${ro.hardware}.rc"
assert old_import in it, "Y73s init.rc import line not found"
irc["data"] = it.replace(old_import, "import /init.recovery.mt6853.rc", 1).encode()
print("init.rc: ${ro.hardware} import replaced with explicit mt6853.rc")

# --- 4b2) select the adb+MTP composite once FunctionFS is ready -------------
# Triggering on sys.usb.ffs.mtp.ready guarantees the configfs action above
# sees all of its conditions satisfied (config=mtp,adb, configfs=1,
# ffs.mtp.ready=1, ffs.ready=1) and links BOTH f1 (mtp) and f2 (adb).
mrc = by["init.recovery.mt6853.rc"]
mt = mrc["data"].decode("utf-8", "replace")
assert "on property:sys.usb.config=mtp,adb" in mt, \
    "configfs mtp,adb action missing - would not be safe to enable"
if "y52s: adb + MTP composite" not in mt:
    nl = "\r\n" if "\r\n" in mt else "\n"
    block = (
        "# y52s: adb + MTP composite\n"
        "on property:sys.usb.ffs.mtp.ready=1\n"
        "    setprop sys.usb.config mtp,adb\n"
    ).replace("\n", nl)
    mrc["data"] = (mt.rstrip("\r\n") + nl + block).encode()
    print("mt6853.rc: added mtp,adb selection on ffs.mtp.ready=1")

# --- 4c) Y73s rc files still hard-code PD2031 for the touch-firmware picker.
# Measured on this device: ro.vivo.product.model / ro.vendor.vivo.product.model
# are PD2057. Without this, vts_app_recovery looks for PD2031 firmware while
# the ramdisk carries PD2057 blobs -> "no firmware for product" -> no touch.
rc_fixed = 0
for e in y_ents:
    if e["name"].endswith(".rc"):
        txt = e["data"].decode("utf-8", "replace")
        if "PD2031" in txt:
            e["data"] = txt.replace("PD2031", "PD2057").encode()
            rc_fixed += 1
print("rc files with PD2031 -> PD2057:", rc_fixed)

# --- 4c) gatekeeper service path -------------------------------------------
# The Y73s ramdisk ships the binary at /vendor/bin/. Keep that path. An
# earlier revision rewrote it to /vendor/bin/hw/... (measured on the Y52s
# VENDOR PARTITION), but that path does not exist in this ramdisk, so init
# refused to register gatekeeper-1-0 at all -- confirmed by an empty
# "getprop init.svc.gatekeeper-1-0" on the device.
gk = 0
for e in y_ents:
    if e["name"].endswith(".rc"):
        txt = e["data"].decode("utf-8", "replace")
        wrong = "service gatekeeper-1-0 /vendor/bin/hw/android.hardware.gatekeeper@1.0-service"
        right = "service gatekeeper-1-0 /vendor/bin/android.hardware.gatekeeper@1.0-service"
        if wrong in txt:
            e["data"] = txt.replace(wrong, right, 1).encode()
            gk += 1
found = any(b"service gatekeeper-1-0 /vendor/bin/android.hardware.gatekeeper@1.0-service"
            in e["data"] for e in y_ents if e["name"].endswith(".rc"))
assert found, "gatekeeper service definition lost"
print("gatekeeper rc paths corrected:", gk)

# --- 5) rebuild boot image with Y52s kernel/dtb -----------------------------
# The OS version / patch level is read from THIS DEVICE's real boot partition
# header (dumped with dd, see flash/probe_*). It is NOT taken from the "stock"
# recovery image, which is itself a TWRP build with a 2099-12 hack value.
boot_hdr = open(BOOT_HDR, "rb").read()
assert boot_hdr[:8] == b"ANDROID!", "boot header dump invalid"
real_os_version = struct.unpack_from("<I", boot_hdr, 44)[0]
assert real_os_version == 0x14000172, \
    "unexpected real os_version 0x%08x" % real_os_version
cpio = cpio_build(y_ents)
gz = gzip.compress(cpio, mtime=0)
hdr = bytearray(y_raw[:y["hsz"]])
struct.pack_into("<I", hdr, 8, len(s["kernel"]))       # kernel_size
struct.pack_into("<I", hdr, 16, len(gz))                # ramdisk_size
struct.pack_into("<I", hdr, 44, real_os_version)        # OS 10.0.0 / 2023-02
struct.pack_into("<I", hdr, 1632, 0)                    # recovery_dtbo_size = 0
struct.pack_into("<Q", hdr, 1636, 0)                    # recovery_dtbo_offset = 0
struct.pack_into("<I", hdr, 1648, s["dtb_sz"])          # dtb_size

out = bytearray(b"\0" * PART_SIZE)
out[:y["hsz"]] = hdr
p = y["koff"]
out[p:p + len(s["kernel"])] = s["kernel"]
p = p + pg(len(s["kernel"]), y["page"])
out[p:p + len(gz)] = gz
p = p + pg(len(gz), y["page"])
out[p:p + len(s["dtb"])] = s["dtb"]
content_end = p + pg(len(s["dtb"]), y["page"])
print("new content_end=0x%x ramdisk_gz=%d" % (content_end, len(gz)))

# --- 6) Y52s STOCK AVB footer/vbmeta (make_hybrid rule) ---------------------
foot = bytearray(s_raw[PART_SIZE - 64:PART_SIZE])
assert foot[:4] == b"AVBf"
svbo = struct.unpack_from(">Q", foot, 20)[0]
svbs = struct.unpack_from(">Q", foot, 28)[0]
vbmeta = bytearray(s_raw[svbo:svbo + svbs])
assert bytes(vbmeta[:4]) == b"AVB0"


def replace_prop_value(blob, key, old, new):
    """Same-length in-place edit of an AVB property descriptor value."""
    k = blob.find(key.encode())
    assert k >= 0, "vbmeta property missing: " + key
    v = blob.find(old, k, k + 160)
    assert v >= 0, "vbmeta hack value missing: " + repr(old)
    assert len(old) == len(new), "value length must not change"
    blob[v:v + len(old)] = new


# The dumped "stock" recovery is a TWRP build whose vbmeta carries hack values.
# Those values are what the bootloader passes to the TEE as boot_patchlevel;
# 2099-12-31 makes every FBE key look outdated => KM_ERROR_KEY_REQUIRES_UPGRADE.
# Replace them with the values measured from THIS device (system patch level
# 2023-02-01, Android 10). Y73s dev log 6.5: vivo LK checks the public key only,
# not the vbmeta hash, so a same-length descriptor edit stays bootable.
replace_prop_value(vbmeta, "com.android.build.boot.security_patch",
                   b"2099-12-31", b"2023-02-01")
replace_prop_value(vbmeta, "com.android.build.boot.os_version",
                   b"16.1.0", b"10.0.0")
vbmeta = bytes(vbmeta)
print("vbmeta patched: patchlevel 2099-12-31 -> 2023-02-01, os 16.1.0 -> 10.0.0")
new_vbo = pg(content_end, y["page"]) + y["page"]
assert new_vbo + svbs + 64 < PART_SIZE
out[new_vbo:new_vbo + svbs] = vbmeta
struct.pack_into(">Q", foot, 20, new_vbo)     # ONLY vbmeta_offset
out[PART_SIZE - 64:PART_SIZE] = foot

# --- 7) verify ---------------------------------------------------------------
chk = segments(bytes(out))
assert chk["kernel"] == s["kernel"]
assert chk["dtb"] == s["dtb"]
assert bytes(out[new_vbo:new_vbo + svbs]) == vbmeta
assert len(cpio_parse(gzip.decompress(chk["ramdisk"]))) == len(y_ents)
assert struct.unpack_from("<I", out, 44)[0] == real_os_version
assert b"2099-12-31" not in bytes(out[new_vbo:new_vbo + svbs])
assert b"2023-02-01" in bytes(out[new_vbo:new_vbo + svbs])
print("VERIFY OK: Y52s kernel/dtb + Y73s ramdisk + measured OS/patch level")

open(DST, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
open(DST + ".sha256", "w", newline="\n").write(
    sha + "  recovery_y73s_port.img\n")
print("WROTE", DST, len(out), "bytes")
print("SHA256", sha)
print("NOTE: UNVERIFIED FALLBACK -- flash only if the primary image fails.")
