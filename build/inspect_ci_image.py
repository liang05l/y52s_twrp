#!/usr/bin/env python3
# ===========================================================================
# y52s - READ-ONLY inspection of the recovery.img produced by GitHub Actions.
#
# The CI image is a fresh source build, NOT the ramdisk-patched 96 MB image.
# Its header version, compression, ramdisk layout and AVB footer may differ,
# so NOTHING here assumes the measured local values. This script only reports
# what is actually in the file; post-processing is decided from its output.
#
# Usage: python3 build/inspect_ci_image.py <path-to-recovery.img>
# ===========================================================================
import os, sys, struct, gzip, hashlib, re

p = sys.argv[1] if len(sys.argv) > 1 else "build/recovery_ci.img"
assert os.path.isfile(p), "image not found: " + p
raw = open(p, "rb").read()
print("FILE", p, "size", len(raw), "sha256", hashlib.sha256(raw).hexdigest())
assert raw[:8] == b"ANDROID!", "not an Android boot image"

v = struct.unpack_from("<10I", raw, 8)
ksz, rsz, page, hv = v[0], v[2], v[7], v[8]
pg = lambda n: ((n + page - 1) // page) * page
print("header_version=%d page_size=%d kernel_size=%d ramdisk_size=%d os_version=0x%x" %
      (hv, page, ksz, rsz, v[9]))
print("kernel_addr=0x%x ramdisk_addr=0x%x tags_addr=0x%x" % (v[1], v[3], v[6]))
print("cmdline:", raw[64:576].split(b"\0")[0].decode(errors="replace")[:200])
print("name   :", raw[48:64].rstrip(b"\0").decode(errors="replace"))

hsz = page
dtb_size = 0
if hv >= 1:
    dtbo_size = struct.unpack_from("<I", raw, 1632)[0]
    dtbo_off = struct.unpack_from("<Q", raw, 1636)[0]
    print("recovery_dtbo_size=%d offset=0x%x" % (dtbo_size, dtbo_off))
if hv >= 2:
    hsz = struct.unpack_from("<I", raw, 1644)[0]
    dtb_size = struct.unpack_from("<I", raw, 1648)[0]
    print("header_size=%d dtb_size=%d dtb_addr=0x%x" %
          (hsz, dtb_size, struct.unpack_from("<Q", raw, 1652)[0]))
print("kernel_off=0x%x ramdisk_off=0x%x" % (pg(hsz), pg(hsz) + pg(ksz)))

koff = pg(hsz)
roff = koff + pg(ksz)
comp = raw[roff:roff + rsz]
print("ramdisk magic:", comp[:8].hex())

data = None
if comp[:2] == b"\x1f\x8b":
    data = gzip.decompress(comp)
    print("compression: gzip -> %d bytes" % len(data))
elif comp[:4] in (b"\x02\x21\x4c\x18", b"\x04\x22\x4d\x18"):
    print("compression: LZ4 (legacy) - install lz4 / use magiskboot to unpack")
elif comp[:6] in (b"070701", b"070702"):
    data = comp
    print("compression: none (raw cpio)")
else:
    print("compression: UNKNOWN - inspect manually")

if data:
    off, entries = 0, []
    while off + 110 <= len(data):
        if data[off:off+6] not in (b"070701", b"070702"):
            break
        fs = int(data[off+54:off+62], 16)
        ns = int(data[off+94:off+102], 16)
        mode = int(data[off+14:off+22], 16)
        name = data[off+110:off+110+ns].rstrip(b"\0").decode("utf-8", "replace")
        if name == "TRAILER!!!":
            break
        ds = (off + 110 + ns + 3) & ~3
        entries.append((name, data[ds:ds+fs], mode))
        off = (ds + fs + 3) & ~3
    print("cpio entries:", len(entries))
    d = {n: (b, m) for n, b, m in entries}
    for key in ("system/bin/recovery", "system/bin/twrp",
                "system/etc/recovery.fstab", "etc/recovery.fstab",
                "prop.default", "default.prop",
                "init.recovery.platform.rc", "init.recovery.svc.rc",
                "init.recovery.usb.rc", "init.recovery.service.rc"):
        if key in d:
            b, m = d[key]
            print("  %-38s %9d B mode=%s" % (key, len(b), oct(m)))
        else:
            print("  %-38s MISSING" % key)

    bin_, _ = d.get("system/bin/recovery", (b"", 0))
    if bin_[:4] == b"\x7fELF":
        strs = [m.group() for m in re.finditer(rb"[ -~]{6,}", bin_)]
        has_no = any(b"no_crypto_support" in s for s in strs)
        has_fbe = any(b"decrypting_user_fbe" in s for s in strs)
        has_ks2 = any(b"keystore2" in s for s in strs)
        print("  CRYPTO: no_crypto_support=%s decrypting_user_fbe=%s keystore2=%s" %
              (has_no, has_fbe, has_ks2))
        if has_no or has_ks2:
            print("  !! WRONG BASELINE: this binary would not decrypt this Android 10 device")

    rc, _ = d.get("init.recovery.platform.rc", (b"", 0))
    if rc:
        for line in rc.decode("utf-8", "replace").splitlines():
            if "gatekeeper" in line and line.strip().startswith("service"):
                print("  gatekeeper service:", line.strip()[:140])

    prop, _ = d.get("prop.default", (b"", 0))
    if prop:
        for line in prop.decode("utf-8", "replace").splitlines():
            if any(k in line for k in ("persist.sys.usb.config",
                                       "build.version.sdk=",
                                       "build.version.security_patch=")):
                print("  prop:", line.strip()[:140])

# AVB footer lives in the last 64 bytes of a padded partition image; a raw
# build output usually has none.
foot = raw[-64:]
print("AVB footer present:", foot[:4] == b"AVBf")
if foot[:4] == b"AVBf":
    print("  original_image_size=0x%x vbmeta_offset=0x%x vbmeta_size=0x%x" %
          (struct.unpack_from(">Q", foot, 12)[0],
           struct.unpack_from(">Q", foot, 20)[0],
           struct.unpack_from(">Q", foot, 28)[0]))
print("PARTITION_SIZE (measured local) = 100663296 B; flash script pads to it.")
print("NEXT: decide post-processing from this report; do NOT guess offsets.")
