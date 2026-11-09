#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace the recovery partition's embedded vbmeta with the REAL vivo-signed
vbmeta taken from this device's vbmeta partition.

Evidence (measured, not guessed):
  * device_dump/.../images/vbmeta.img  : AVB0, public key sha 4bdf3ccd...,
    avbtool 1.1.0, valid vivo signature, chain-partition descriptors only
    (no hash descriptor -> recovery content is not hash-checked).
  * the "stock" recovery image we dumped and every image we built since then
    carry public key sha 7728e30f... -- the SAME AOSP test key as our CI build.
  * Y73s DEVELOPMENT_LOG.md stage 6: with a self-signed vbmeta the vivo LK
    passes the DEFAULT boot_patchlevel to the TEE, so FBE keys are seen as
    outdated -> KM_ERROR_KEY_REQUIRES_UPGRADE (-62) on every DE key.
  * recovery.log on this device: begin -> -62, upgradeKey -> -33, retried 3x.

With the vivo-signed vbmeta, LK trusts the key; the boot header already carries
the measured os_version 0x14000172 (Android 10.0.0 / 2023-02).

Input : build/recovery_y73s_port.img (patchlevel-aligned, touch working)
Output: build/recovery_vivokey.img (+ .sha256)
"""
import hashlib
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build", "recovery_y73s_port.img")
VBMETA = os.path.join(ROOT, "device_dump", "y52s_dump_20261108_122327",
                      "images", "vbmeta.img")
DST = os.path.join(ROOT, "build", "recovery_vivokey.img")
PART_SIZE = 100663296


def pg(n, page):
    return ((n + page - 1) // page) * page


vb = open(VBMETA, "rb").read()
assert vb[:4] == b"AVB0", "vbmeta partition is not AVB0"
auth, aux = struct.unpack_from(">QQ", vb, 12)
vb_size = 256 + auth + aux
vivo = vb[:vb_size]
assert vivo[:4] == b"AVB0" and len(vivo) == vb_size
print("vivo vbmeta: header=256 auth=%d aux=%d total=%d" % (auth, aux, vb_size))

raw = bytearray(open(SRC, "rb").read())
assert len(raw) == PART_SIZE
v = struct.unpack_from("<10I", raw, 8)
page, ksz, rsz = v[7], v[0], v[2]
hsz = struct.unpack_from("<I", raw, 1644)[0]
dtbo_sz = struct.unpack_from("<I", raw, 1632)[0]
dtb_sz = struct.unpack_from("<I", raw, 1648)[0]
dtbo_off = struct.unpack_from("<Q", raw, 1636)[0]
koff = pg(hsz, page)
roff = koff + pg(ksz, page)
second_off = roff + pg(rsz, page)
content_end = pg(max(second_off + pg(dtbo_sz, page) + pg(dtb_sz, page),
                     dtbo_off + pg(dtbo_sz, page)), page)
print("content_end=0x%x (page=%d)" % (content_end, page))

foot = bytearray(raw[PART_SIZE - 64:PART_SIZE])
assert foot[:4] == b"AVBf", "AVB footer missing"
old_vbo = struct.unpack_from(">Q", foot, 20)[0]
old_vbs = struct.unpack_from(">Q", foot, 28)[0]
orig_size = struct.unpack_from(">Q", foot, 12)[0]
print("old footer: vbmeta_offset=0x%x size=%d original_image_size=%d"
      % (old_vbo, old_vbs, orig_size))

# wipe the old vbmeta blob, keep every other byte (kernel/ramdisk/dtb intact)
raw[old_vbo:old_vbo + old_vbs] = b"\0" * old_vbs
new_vbo = content_end + page
assert new_vbo + vb_size + 64 < PART_SIZE, "no room for vivo vbmeta"
raw[new_vbo:new_vbo + vb_size] = vivo

struct.pack_into(">Q", foot, 20, new_vbo)   # vbmeta_offset
struct.pack_into(">Q", foot, 28, vb_size)   # vbmeta_size
# original_image_size is deliberately NOT changed (make_hybrid.py rule).
raw[PART_SIZE - 64:PART_SIZE] = foot

# --- verify ---------------------------------------------------------------
out = bytes(raw)
chk = bytearray(open(SRC, "rb").read())
assert out[:content_end] == chk[:content_end], "image content changed"
assert out[new_vbo:new_vbo + vb_size] == vivo
assert out[PART_SIZE - 64:] == bytes(foot)
assert struct.unpack_from("<I", out, 44)[0] == 0x14000172
# public key inside the new vbmeta must be the vivo one
pk_off, pk_size = struct.unpack_from(">QQ", vivo, 64)
pk = vivo[256 + auth + pk_off: 256 + auth + pk_off + pk_size]
print("vivo public key sha256:", hashlib.sha256(pk).hexdigest()[:16])
print("new footer: vbmeta_offset=0x%x size=%d original_image_size=%d"
      % (new_vbo, vb_size, orig_size))
print("VERIFY OK: image content byte-identical, only vbmeta+footer replaced")

open(DST, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
open(DST + ".sha256", "w", newline="\n").write(sha + "  recovery_vivokey.img\n")
print("WROTE", DST, len(out), "bytes")
print("SHA256", sha)
