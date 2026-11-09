#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
y52s: hybrid recovery image = TWRP content + GENUINE vivo-signed AVB footer.

This is the fix for KM_ERROR_KEY_REQUIRES_UPGRADE (-62) on the FBE DE key.

Evidence (all measured, nothing guessed):
  * Official PD2057_A_1.16.4 recovery (user supplied, recovery.bin):
      - AVB public key sha 4bdf3ccd... == the system vbmeta partition key
      - boot header os_version 0x14000172 = Android 10.0.0 / 2023-02
      - vbmeta descriptors: boot.security_patch = 2019-06-06,
        system.security_patch = 2023-02-01, vendor = 2020-07-05
      - signed with avbtool 1.1.0 (vivo), vbmeta 1728 B, AVB footer 64 B,
        original_image_size 47024128
  * Every image we built before carried the AOSP test key (7728e30f...) and
    hack values 2099-12-31 / 16.1.0. The vivo LK then passes the DEFAULT
    boot_patchlevel to the TEE, so the FBE key blob looks outdated.
  * Y73s (PD2031) DEVELOPMENT_LOG.md stage 6 used exactly this hybrid approach
    ("vivo bootloader checks only the public key, not the hash") and decryption
    then worked.

Rules (make_hybrid.py):
  * keep the TWRP content byte-for-byte (kernel / ramdisk / dtb / header)
  * take the OFFICIAL vbmeta blob and footer unmodified
  * rewrite ONLY footer.vbmeta_offset; keep official original_image_size
  * do NOT edit any vbmeta byte (that would invalidate the vivo signature)

Input : build/recovery_y73s_port.img  (1d890f45... -- touch, gatekeeper path,
        explicit init.rc import, measured os_version all fixed)
Output: build/recovery.img (+ .sha256)
"""
import hashlib
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build", "recovery_y73s_port.img")
# Prefer the in-project archive (created from the user-supplied file) so a
# rebuild does not depend on a path on the Desktop; fall back to the original.
OFFICIAL = os.path.join(ROOT, "reference", "y52s_official_recovery.img")
if not os.path.isfile(OFFICIAL):
    OFFICIAL = r"C:\Users\30345\Desktop\新建文件夹 (2)\recovery.bin"
DST = os.path.join(ROOT, "build", "recovery.img")
PART_SIZE = 100663296


def pg(n, page):
    return ((n + page - 1) // page) * page


t = bytearray(open(SRC, "rb").read())
o = bytearray(open(OFFICIAL, "rb").read())
assert len(t) == len(o) == PART_SIZE
assert t[:8] == b"ANDROID!" and o[:8] == b"ANDROID!"

# --- TWRP content extent ----------------------------------------------------
v = struct.unpack_from("<10I", t, 8)
page, ksz, rsz = v[7], v[0], v[2]
hsz = struct.unpack_from("<I", t, 1644)[0]
dtbo_sz = struct.unpack_from("<I", t, 1632)[0]
dtbo_off = struct.unpack_from("<Q", t, 1636)[0]
dtb_sz = struct.unpack_from("<I", t, 1648)[0]
koff = pg(hsz, page)
roff = koff + pg(ksz, page)
second_off = roff + pg(rsz, page)
content_end = pg(max(second_off + pg(dtbo_sz, page) + pg(dtb_sz, page),
                     dtbo_off + pg(dtbo_sz, page)), page)
print("TWRP content_end=0x%x (page=%d)" % (content_end, page))

# --- official vbmeta + footer -----------------------------------------------
foot = bytearray(o[PART_SIZE - 64:PART_SIZE])
assert foot[:4] == b"AVBf", "official AVB footer missing"
official_vbo = struct.unpack_from(">Q", foot, 20)[0]
official_vbs = struct.unpack_from(">Q", foot, 28)[0]
orig_size = struct.unpack_from(">Q", foot, 12)[0]
vbmeta = bytes(o[official_vbo:official_vbo + official_vbs])
assert vbmeta[:4] == b"AVB0" and len(vbmeta) == official_vbs
auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
pk_off, pk_size = struct.unpack_from(">QQ", vbmeta, 64)
pk = vbmeta[256 + auth + pk_off: 256 + auth + pk_off + pk_size]
print("official vbmeta=%d B, public key sha=%s, original_image_size=%d"
      % (official_vbs, hashlib.sha256(pk).hexdigest()[:16], orig_size))
assert hashlib.sha256(pk).hexdigest().startswith("4bdf3ccd"), \
    "not the vivo public key - wrong input file"
assert struct.unpack_from("<I", o, 44)[0] == 0x14000172
assert struct.unpack_from("<I", t, 44)[0] == 0x14000172, \
    "TWRP header os_version must already match the official one"

# --- build -------------------------------------------------------------------
out = bytearray(b"\0" * PART_SIZE)
out[:content_end] = t[:content_end]           # content, byte-identical
new_vbo = content_end + page
assert new_vbo + official_vbs + 64 < PART_SIZE, "no room for official vbmeta"
out[new_vbo:new_vbo + official_vbs] = vbmeta   # unmodified, signature valid
struct.pack_into(">Q", foot, 20, new_vbo)      # ONLY vbmeta_offset
out[PART_SIZE - 64:PART_SIZE] = foot

# --- verify ------------------------------------------------------------------
res = bytes(out)
assert res[:content_end] == t[:content_end], "TWRP content changed"
assert res[new_vbo:new_vbo + official_vbs] == vbmeta, "vbmeta changed"
assert struct.unpack_from(">Q", res[-64:], 12)[0] == orig_size
assert struct.unpack_from(">Q", res[-64:], 20)[0] == new_vbo
assert struct.unpack_from(">Q", res[-64:], 28)[0] == official_vbs
assert struct.unpack_from("<I", res, 44)[0] == struct.unpack_from("<I", o, 44)[0]
assert b"2019-06-06" in vbmeta, "official boot_patchlevel missing"
print("verify: content identical, official vbmeta byte-identical, "
      "only vbmeta_offset=0x%x rewritten" % new_vbo)
print("boot_patchlevel descriptors: boot=2019-06-06  system=2023-02-01  vendor=2020-07-05")

open(DST, "wb").write(res)
sha = hashlib.sha256(res).hexdigest()
open(DST + ".sha256", "w", newline="\n").write(sha + "  recovery.img\n")
print("WROTE", DST, len(res), "bytes")
print("SHA256", sha)
