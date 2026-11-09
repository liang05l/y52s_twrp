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
  * boot header os_version <- Y52s stock 0x1800063c
  * prop.default   <- PD2031 -> PD2057, compiler10052108 -> compiler04181705,
                      compiler10052108 in description -> compiler09042257,
                      security_patch 2020-09-01 -> 2023-02-01,
                      all *.version.sdk 32 -> 29, build.id -> QP1A.190711.020
  * fstab          <- device/vivo/y52s/recovery.fstab (measured partition set)
  * touch firmware <- Y52s v7 vendor/firmware/* (14 blobs, PD2057 panel)
  * gatekeeper rc  <- /vendor/bin/hw/... (path measured on this device)
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

# --- 4) gatekeeper service path (measured: /vendor/bin/hw/...) --------------
gk = 0
for e in y_ents:
    if e["name"].endswith(".rc"):
        txt = e["data"].decode("utf-8", "replace")
        old = "service gatekeeper-1-0 /vendor/bin/android.hardware.gatekeeper@1.0-service"
        if old in txt:
            e["data"] = txt.replace(
                old,
                "service gatekeeper-1-0 /vendor/bin/hw/android.hardware.gatekeeper@1.0-service",
                1).encode()
            gk += 1
print("gatekeeper rc paths fixed:", gk)

# --- 5) rebuild boot image with Y52s kernel/dtb -----------------------------
cpio = cpio_build(y_ents)
gz = gzip.compress(cpio, mtime=0)
hdr = bytearray(y_raw[:y["hsz"]])
struct.pack_into("<I", hdr, 8, len(s["kernel"]))       # kernel_size
struct.pack_into("<I", hdr, 16, len(gz))                # ramdisk_size
struct.pack_into("<I", hdr, 44, struct.unpack_from("<I", s_raw, 44)[0])  # os_version
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
vbmeta = s_raw[svbo:svbo + svbs]
assert vbmeta[:4] == b"AVB0"
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
assert struct.unpack_from("<I", out, 44)[0] == struct.unpack_from("<I", s_raw, 44)[0]
print("VERIFY OK: Y52s kernel/dtb + Y73s ramdisk + STOCK vivo AVB footer")

open(DST, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
open(DST + ".sha256", "w", newline="\n").write(
    sha + "  recovery_y73s_port.img\n")
print("WROTE", DST, len(out), "bytes")
print("SHA256", sha)
print("NOTE: UNVERIFIED FALLBACK -- flash only if the primary image fails.")
