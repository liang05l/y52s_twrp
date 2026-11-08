#!/usr/bin/env python3
# ===========================================================================
# y52s - extract the prebuilt kernel / dtb / dtbo needed for a source build.
#
# Source: the ROOT-DUMPED, ORIGINAL recovery.img of THIS device. Every byte is
# measured, nothing is guessed. Earlier verification showed kernel_size and
# dtb_size in that image equal the byte sizes of the upstream tree's
# prebuilt/kernel and prebuilt/dtb.img, so this is the same bundle that the
# installed TWRP was built with.
#
# Android boot image header v2 layout used here:
#   0x0008 kernel_size, ramdisk_size, ..., page_size, header_version, os_version
#   0x0660 (1632) recovery_dtbo_size   (u32)
#   0x0664 (1636) recovery_dtbo_offset (u64)
#   0x066C (1644) header_size          (u32)
#   0x0670 (1648) dtb_size             (u32)
# ===========================================================================
import os, struct, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "device_dump", "y52s_dump_20261108_122327", "images", "recovery.img")
OUT = os.path.join(ROOT, "device", "vivo", "y52s", "prebuilt")

raw = open(SRC, "rb").read()
assert raw[:8] == b"ANDROID!", "not an Android boot image"
v = struct.unpack_from("<10I", raw, 8)
ksz, rsz, page, hv = v[0], v[2], v[7], v[8]
assert hv >= 2, "expected header v2"
hsz = struct.unpack_from("<I", raw, 1644)[0]
dtb_size = struct.unpack_from("<I", raw, 1648)[0]
dtbo_size = struct.unpack_from("<I", raw, 1632)[0]
dtbo_off = struct.unpack_from("<Q", raw, 1636)[0]
pg = lambda n: ((n + page - 1) // page) * page
koff = pg(hsz)
roff = koff + pg(ksz)
doff = roff + pg(rsz)

kernel = raw[koff:koff + ksz]
dtb = raw[doff:doff + dtb_size]
dtbo = raw[dtbo_off:dtbo_off + dtbo_size] if dtbo_size else b""
# header v2 of this device has recovery_dtbo_size = 0; the dtbo lives in its
# own dumped partition instead.
if not dtbo:
    standalone = os.path.join(os.path.dirname(SRC), "dtbo.img")
    if os.path.isfile(standalone):
        dtbo = open(standalone, "rb").read()
        print("dtbo taken from dumped partition:", standalone)

print("header_version=%d page=%d header_size=%d" % (hv, page, hsz))
print("kernel  off=0x%x size=%d" % (koff, ksz))
print("ramdisk off=0x%x size=%d" % (roff, rsz))
print("dtb     off=0x%x size=%d" % (doff, dtb_size))
print("dtbo    off=0x%x size=%d" % (dtbo_off, dtbo_size))

os.makedirs(OUT, exist_ok=True)
for name, data in (("kernel", kernel), ("dtb.img", dtb), ("dtbo.img", dtbo)):
    if not data:
        print("SKIP (empty):", name)
        continue
    p = os.path.join(OUT, name)
    open(p, "wb").write(data)
    print("%-10s %9d bytes  sha256=%s" %
          (name, len(data), hashlib.sha256(data).hexdigest()))

# sanity: kernel is a real large image; this MediaTek platform wraps dtb/dtbo
# in its own container (magic d7 b7 ab 1e) instead of a bare FDT.
assert len(kernel) > 1000000, "kernel too small"
assert dtb[:4] == b"\xd7\xb7\xab\x1e", "unexpected dtb container magic"
if dtbo:
    assert dtbo[:4] == b"\xd7\xb7\xab\x1e", "unexpected dtbo container magic"
print("PREBUILT READY:", OUT)
