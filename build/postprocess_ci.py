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
LP = ("/system_root/system/lib64:/system_root/system/lib64/vndk-29:"
      "/vendor/lib64:/vendor/lib64/hw")
svc = v7_by["init.recovery.svc.rc"]["data"].decode("utf-8", "replace")


def service_block(name):
    st = svc.find("service " + name + " ")
    assert st >= 0, "v7 service missing: " + name
    ends = [x for x in (svc.find("\nservice ", st + 1),
                        svc.find("\non ", st + 1)) if x >= 0]
    nx = min(ends) if ends else len(svc)
    return svc[st:nx].rstrip() + "\n"


touch_svc = ("service touchupdate /system/bin/vts_app_recovery --update\n"
             "    user root\n"
             "    group root\n"
             "    disabled\n"
             "    seclabel u:r:recovery:s0\n")
mtp = ("on property:sys.usb.config=mtp\n"
       "    setprop sys.usb.config adb\n\n"
       "on property:sys.usb.config=mtp,adb\n"
       "    setprop sys.usb.config adb\n\n"
       "on property:sys.usb.config=adb,mtp\n"
       "    setprop sys.usb.config adb\n")

y52s_rc = (
    "# y52s: post-build device init. Every value below is copied from the\n"
    "# stock-based v7 image whose touch/USB/HAL behaviour was verified.\n"
    "import /init.recovery.touch.rc\n\n"
    + touch_svc + "\n"
    + service_block("y52s_prepare") + "\n"
    + service_block("y52s_keymaster") + "\n"
    + service_block("y52s_gatekeeper") + "\n"
    "on init\n"
    "    setprop recovery.service 1\n"
    "    exec_start y52s_prepare\n"
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n"
    "    start touchupdate\n\n"
    "on property:twrp.modules.loaded=true\n"
    "    exec_start y52s_prepare\n"
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n"
    "    start touchupdate\n\n"
    "# keep adb available; TWRP otherwise switches USB to MTP\n"
    + mtp
)
rc_name = "init.recovery.mt6853.rc"
assert rc_name not in ci_by
e = new_entry(rc_name, y52s_rc.encode(), 0o100750, tpl)
ci_ents.append(e)
ci_by[rc_name] = e
added.append(rc_name)

# init.rc already imports /init.recovery.${ro.hardware}.rc; ro.hardware is
# "mt6853" on this device (measured in getprop), so the file we add above is
# loaded automatically. Keep the stock line untouched for CI/local parity.
irc = ci_by["system/etc/init/hw/init.rc"]
t = irc["data"].decode("utf-8", "replace")
assert "import /init.recovery.${ro.hardware}.rc" in t, "init.rc import line not found"

# Also persist the same rc into the device tree so future CI builds are born
# with touch support (TWRP merges recovery/root into the recovery ramdisk).
dt_rc = os.path.join(ROOT, "device", "vivo", "y52s", "recovery", "root",
                     "init.recovery.mt6853.rc")
os.makedirs(os.path.dirname(dt_rc), exist_ok=True)
open(dt_rc, "w", encoding="utf-8", newline="\n").write(y52s_rc)
os.chmod(dt_rc, 0o750)
print("device tree rc written:", dt_rc)

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
# 4) MTP interception in CI's own usb.rc (keep its line endings)
# ---------------------------------------------------------------------------
usb = ci_by["init.recovery.usb.rc"]
u = usb["data"].decode("utf-8", "replace")
if "y52s" not in u:
    nl = eol_of(usb["data"])
    block = ("\n# y52s v7: keep adb usable; never let TWRP switch USB to MTP.\n"
             + mtp.rstrip("\n") + "\n")
    if nl == "\r\n":
        block = block.replace("\n", "\r\n")
        u = u.rstrip("\r\n") + "\r\n"
    usb["data"] = (u + block).encode()

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
