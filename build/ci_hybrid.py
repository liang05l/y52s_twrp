#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI post-build step: graft the GENUINE vivo-signed AVB footer/vbmeta onto a
freshly compiled recovery.img.

Why this is mandatory (measured, not guessed)
--------------------------------------------
* The device's bootloader passes the vbmeta boot props into the TEE as
  boot_patchlevel / boot_os_version. Keys created by the stock system are
  bound to the ORIGINAL vivo values:
      boot.security_patch = 2019-06-06
      system = 2023-02-01, vendor = 2020-07-05
      boot header os_version = 0x14000172 (Android 10.0.0 / 2023-02)
* A source build signs with the AOSP test key and (in this tree) hack values
  2099-12-31 / 16.1.0. That makes keymaster return
  KM_ERROR_KEY_REQUIRES_UPGRADE (-62) for every FBE DE key and decryption
  cannot start at all.
* The vivo LK verifies only the public key, not the vbmeta hash (Y73s
  DEVELOPMENT_LOG stage 6, confirmed on this device 2026-11-09:
  `km_error=0`, `User 0 Decrypted Successfully!`).

Rules (same as build/make_official_hybrid.py, but for a variable-length
CI artifact instead of a padded 96 MB image):
  * keep the compiled TWRP content byte-for-byte
  * take the OFFICIAL 1728 B vbmeta + 64 B footer unmodified
  * rewrite ONLY footer.vbmeta_offset; keep original_image_size
  * force the measured boot-header os_version (same-length field)

Input  : out/target/product/y52s/recovery.img
Output : the same path, padded to the measured 100663296 B partition,
         plus recovery.img.sha256. The unmodified compiler output is kept
         as recovery_ci_built.img for inspection.
"""
import hashlib
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VBMETA = os.path.join(ROOT, "device", "vivo", "y52s", "avb", "vbmeta_official.bin")
FOOTER = os.path.join(ROOT, "device", "vivo", "y52s", "avb", "footer_official.bin")
PART_SIZE = 100663296
REAL_OS_VERSION = 0x14000172


def pg(n, page):
    return ((n + page - 1) // page) * page


def main():
    img = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "build", "recovery.img")
    raw = open(img, "rb").read()
    assert raw[:8] == b"ANDROID!", "not an Android boot image"
    v = struct.unpack_from("<10I", raw, 8)
    page, ksz, rsz, ssz = v[7], v[0], v[2], v[4]
    hdr_ver = v[8]
    hsz = struct.unpack_from("<I", raw, 1644)[0] if hdr_ver >= 2 else page
    dtbo_sz = struct.unpack_from("<I", raw, 1632)[0] if hdr_ver >= 1 else 0
    dtbo_off = struct.unpack_from("<Q", raw, 1636)[0] if hdr_ver >= 1 else 0
    dtb_sz = struct.unpack_from("<I", raw, 1648)[0] if hdr_ver >= 2 else 0
    koff = pg(hsz, page)
    roff = koff + pg(ksz, page)
    second_off = roff + pg(rsz, page)
    tail = second_off + pg(ssz, page) + pg(dtbo_sz, page) + pg(dtb_sz, page)
    if dtbo_off:
        tail = max(tail, dtbo_off + pg(dtbo_sz, page))
    content_end = pg(tail, page)
    assert content_end <= len(raw), "truncated boot image"
    print("compiled image: %d B, header_version=%d page=%d content_end=0x%x" %
          (len(raw), hdr_ver, page, content_end))

    vbmeta = open(VBMETA, "rb").read()
    foot = bytearray(open(FOOTER, "rb").read())
    assert vbmeta[:4] == b"AVB0" and len(vbmeta) == 1728
    assert foot[:4] == b"AVBf" and len(foot) == 64
    auth, aux = struct.unpack_from(">QQ", vbmeta, 12)
    pk_off, pk_size = struct.unpack_from(">QQ", vbmeta, 64)
    pk = vbmeta[256 + auth + pk_off:256 + auth + pk_off + pk_size]
    assert hashlib.sha256(pk).hexdigest().startswith("4bdf3ccd"), \
        "not the vivo public key"
    assert b"2019-06-06" in vbmeta, "official boot_patchlevel missing"
    orig_size = struct.unpack_from(">Q", foot, 12)[0]

    # ---- build -------------------------------------------------------------
    out = bytearray(b"\0" * PART_SIZE)
    out[:content_end] = raw[:content_end]
    # Header os_version is a 4-byte field at offset 44. A source build may
    # bake a different value (12.0 / 2099-12). Force the MEASURED value.
    struct.pack_into("<I", out, 44, REAL_OS_VERSION)
    new_vbo = content_end + page
    assert new_vbo + len(vbmeta) + 64 < PART_SIZE, "no room for official vbmeta"
    out[new_vbo:new_vbo + len(vbmeta)] = vbmeta
    struct.pack_into(">Q", foot, 20, new_vbo)   # ONLY vbmeta_offset
    out[PART_SIZE - 64:PART_SIZE] = foot

    res = bytes(out)
    assert res[new_vbo:new_vbo + len(vbmeta)] == vbmeta
    assert struct.unpack_from(">Q", res[-64:], 12)[0] == orig_size
    assert struct.unpack_from("<I", res, 44)[0] == REAL_OS_VERSION
    # Everything except the 4-byte os_version field must be byte-identical.
    a, b = bytearray(raw[:content_end]), bytearray(res[:content_end])
    struct.pack_into("<I", a, 44, REAL_OS_VERSION)
    assert a == b, "compiled content changed unexpectedly"

    # Keep the compiler's untouched output for forensics.
    open(os.path.join(os.path.dirname(img), "recovery_ci_built.img"), "wb").write(raw)
    open(img, "wb").write(res)
    sha = hashlib.sha256(res).hexdigest()
    open(img + ".sha256", "w", newline="\n").write(sha + "  recovery.img\n")
    print("official vbmeta=%d B public key sha=%s original_image_size=%d" %
          (len(vbmeta), hashlib.sha256(pk).hexdigest()[:16], orig_size))
    print("boot_patchlevel: boot=2019-06-06 system=2023-02-01 vendor=2020-07-05")
    print("verify: content identical (except os_version), official vbmeta byte-identical, "
          "only vbmeta_offset=0x%x rewritten" % new_vbo)
    print("WROTE %s (%d B)  SHA256 %s" % (img, len(res), sha))


if __name__ == "__main__":
    main()
