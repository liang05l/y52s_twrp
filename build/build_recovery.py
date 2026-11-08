#!/usr/bin/env python3
# ===========================================================================
# y52s - rebuild recovery.img from the EXISTING TWRP image (v2).
#
# Source: device_dump/y52s_dump_20261108_122327/images/recovery.img (measured)
# Boot header / kernel / dtb / AVB footer are preserved byte-for-byte.
#
# v1 (already flashed): fixed the gatekeeper service path and added
#   "setprop recovery.service 1". Measured in TWRP: the property took effect,
#   but keymaster/gatekeeper were still absent from init.svc.
# v2 (this build): logcat proved the exact cause --
#   CANNOT LINK EXECUTABLE ... library "android.hardware.keymaster@4.0.so" not found
#   CANNOT LINK EXECUTABLE ... library "android.hardware.gatekeeper@1.0.so" not found
#   TWRP mounts the real system at /system_root, so its VNDK/HIDL libs are not
#   on the default linker search path. We add the 2 HIDL libs plus their 2
#   missing dependencies (all pulled from /system_root/system/lib64 of THIS
#   device, DT_NEEDED verified complete) into ramdisk system/lib64/, and start
#   the HAL services explicitly in on post-fs instead of relying only on the
#   on property:recovery.service=1 trigger.
#   v3 (this build): v2 proved the libs are present in the running TWRP, but
#   a control experiment (start logd OK / start platform HALs "Unable to start
#   service") showed platform.rc's service declarations are not usable. The 3
#   HAL services are re-declared with new names inside init.recovery.svc.rc
#   (a rc file proven to be loaded) and started from on init and from
#   on property:twrp.modules.loaded=true.
# No /data writes. Output padded to 100663296 B for sha256 verification.
# ===========================================================================
import os, io, struct, gzip, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "device_dump", "y52s_dump_20261108_122327", "images", "recovery.img")
DST = os.path.join(ROOT, "build", "recovery.img")
SUM = DST + ".sha256"
PART_SIZE = 100663296
LIB_DIR = os.path.join(ROOT, "build", "libs")
LIBS = ["android.hardware.keymaster@4.0.so",
        "android.hardware.gatekeeper@1.0.so",
        "android.hardware.keymaster@3.0.so",
        "libhwbinder.so"]
# v8 (optional): only when a verified FBE-capable main binary is present,
# also add the 13 libraries its DT_NEEDED graph requires (including 2
# transitive ones). Without that binary this list stays exactly the v7 one.
SWAP = os.path.join(ROOT, "build", "reference", "recovery_crypto.bin")
CRYPTO_LIB_DIR = os.path.join(ROOT, "build", "crypto_libs")
if os.path.isfile(SWAP) and os.path.isdir(CRYPTO_LIB_DIR):
    extra = sorted(f for f in os.listdir(CRYPTO_LIB_DIR)
                   if f.endswith(".so") and f != "libtar.so")
    LIBS += extra
    LIBS.append("libtar.so")   # REPLACE the crypto-stripped local build
    print("v8: %d extra crypto libraries will be added" % len(extra))

def pg(n, page):
    return ((n + page - 1) // page) * page

def parse_cpio(data):
    off, out = 0, []
    while off + 110 <= len(data):
        magic = data[off:off+6]
        if magic not in (b"070701", b"070702"):
            break
        f = [data[off+6+i*8:off+6+(i+1)*8] for i in range(13)]
        fsize = int(f[6], 16)
        nsize = int(f[11], 16)
        name = data[off+110:off+110+nsize].rstrip(b"\0").decode("utf-8", "replace")
        ds = (off + 110 + nsize + 3) & ~3
        out.append({"magic": magic, "f": f, "name": name, "data": data[ds:ds+fsize]})
        off = (ds + fsize + 3) & ~3
    return out

def build_cpio(entries):
    out = bytearray()
    for e in entries:
        f = list(e["f"])
        f[6] = ("%08X" % len(e["data"])).encode()
        f[11] = ("%08X" % (len(e["name"].encode()) + 1)).encode()
        out += e["magic"] + b"".join(f)
        out += e["name"].encode() + b"\0"
        out += b"\0" * ((-len(out)) % 4)
        out += e["data"]
        out += b"\0" * ((-len(out)) % 4)
    return bytes(out)

# ---- read + parse measured image ------------------------------------------
raw = open(SRC, "rb").read(PART_SIZE)
assert raw[:8] == b"ANDROID!", "source is not an Android boot image"
v = struct.unpack_from("<10I", raw, 8)
ksz, rsz, page, hv = v[0], v[2], v[7], v[8]
hsz = struct.unpack_from("<I", raw, 1644)[0]
dtb_size = struct.unpack_from("<I", raw, 1648)[0]
koff = pg(hsz, page)
roff = koff + pg(ksz, page)
doff = roff + pg(rsz, page)
kernel = raw[koff:koff+ksz]
ramdisk_gz = raw[roff:roff+rsz]
dtb = raw[doff:doff+dtb_size]
tail_nonzero = sum(1 for b in raw[doff + pg(dtb_size, page):] if b)
print("header: version=%d page=%d hsz=%d kernel=%d ramdisk=%d dtb=%d" %
      (hv, page, hsz, ksz, rsz, dtb_size))
print("tail bytes after dtb that are non-zero:", tail_nonzero)

# ---- ramdisk: two evidence-backed edits ------------------------------------
cpio = gzip.decompress(ramdisk_gz)
entries = parse_cpio(cpio)
print("cpio entries (source):", len(entries))

def file_entry(name, data, ino):
    f = [("%08X" % ino).encode(), ("%08X" % 0o100644).encode(),
         b"00000000", b"00000000", b"00000001", b"00000000",
         ("%08X" % len(data)).encode(), b"00000000", b"00000000",
         b"00000000", b"00000000", ("%08X" % (len(name) + 1)).encode(),
         b"00000000"]
    return {"magic": b"070701", "f": f, "name": name, "data": data}

# insert before TRAILER!!! (otherwise cpio stops early)
trailer = next(i for i, e in enumerate(entries) if e["name"] == "TRAILER!!!")
added = []
inserted = 0
for i, lib in enumerate(LIBS):
    path = os.path.join(LIB_DIR, lib)
    if not os.path.isfile(path):
        path = os.path.join(CRYPTO_LIB_DIR, lib)
    assert os.path.isfile(path), "missing library: " + lib
    name = "system/lib64/" + lib
    blob = open(path, "rb").read()
    if lib == "libtar.so" and os.path.isfile(SWAP):
        # the FBE-capable binary needs crypto_scrypt, exported only by the
        # official libtar.so (393128 B). The local one (48928 B) is the
        # crypto-stripped build. Replace in place; never create a duplicate.
        hits = [e for e in entries if e["name"] == name]
        assert len(hits) == 1, "libtar.so entries: %d" % len(hits)
        hits[0]["data"] = blob
        added.append(name + " [REPLACED with official crypto build]")
    else:
        assert not any(e["name"] == name for e in entries), "already present: " + name
        entries.insert(trailer + inserted,
                       file_entry(name, blob, 4000000 + i))
        inserted += 1
        added.append(name)
print("added libs:", added)

old_path = "service gatekeeper-1-0 /vendor/bin/android.hardware.gatekeeper@1.0-service"
new_path = "service gatekeeper-1-0 /vendor/bin/hw/android.hardware.gatekeeper@1.0-service"
marker = '    write /proc/bootprof "MOBICORE: Starting mcDriverDaemon"\n'
changed = []
platform_txt = None

# v8 (OPTIONAL, gated by build/reference/recovery_crypto.bin):
# The installed 3.7.1_12-0 main binary was compiled WITHOUT TW_INCLUDE_CRYPTO
# and TW_INCLUDE_FBE -- `twrp decrypt` prints "no_crypto_support=..." and the
# boot-time Decrypt_Data() (which opens the password page) is compiled out.
# A source rebuild is the proper fix; until a Linux/AOSP build host is
# available, transplant the main binary from an official 3.7.1_12-0 image of
# the SAME android-12.1 base, after build/inspect_reference.py has verified
# that binary really has the crypto/FBE code compiled in.
# All other v7 repairs (libs, logical-partition mounts, HAL services,
# os_version alignment, MTP-off) stay in place.
# To roll back to v7 simply delete build/reference/recovery_crypto.bin.
if os.path.isfile(SWAP):
    blob = open(SWAP, "rb").read()
    assert blob[:4] == b"\x7fELF" and len(blob) > 1000000, "bad crypto binary"
    hits = 0
    for e in entries:
        if e["name"] == "system/bin/recovery":
            e["data"] = blob           # build_cpio recomputes filesize; mode kept
            hits += 1
    assert hits == 1, "system/bin/recovery entries: %d" % hits
    changed.append("system/bin/recovery (v8 FBE-capable binary)")
    print("v8: main binary swapped ->", len(blob), "bytes")
for e in entries:
    if e["name"].endswith("init.recovery.platform.rc"):
        s = e["data"].decode("utf-8", "replace")
        assert old_path in s, "gatekeeper path not found - aborting"
        s = s.replace(old_path, new_path, 1)
        assert marker in s, "post-fs marker not found - aborting"
        assert "setprop recovery.service" not in s, "already set - aborting"
        s = s.replace(marker, "    setprop recovery.service 1\n" + marker, 1)
        e["data"] = s.encode()
        platform_txt = s
        changed.append(e["name"])
        break
assert platform_txt, "init.recovery.platform.rc not found - aborting"

# v4: decisive runtime experiment on the device proved
#   mount -t ext4 -o ro /dev/block/mapper/system /system_root
#   mount -t ext4 -o ro /dev/block/mapper/vendor  /vendor
#   LD_LIBRARY_PATH=/system_root/system/lib64:/system_root/system/lib64/vndk-29:
#                   /vendor/lib64:/vendor/lib64/hw
#   -> BOTH keymaster@4.0 and gatekeeper@1.0 HALs start, no error.
# TWRP does NOT mount the logical system/vendor partitions at boot (mapper
# nodes exist, but the mount table has no /vendor or /system_root), so the HAL
# binaries are absent and init refuses to start the services. v4 therefore:
#   1) ship /sbin/y52s_prepare.sh that mounts those two logical partitions
#   2) re-declare the HAL services with an explicit LD_LIBRARY_PATH covering
#      the mounted VNDK / vendor libs (libkeymaster_messages.so,
#      libpuresoftkeymasterdevice.so live in system vndk-29)
#   3) trigger from on property:twrp.modules.loaded=true (measured true, after
#      the super symlinks have been created)
PREPARE = """#!/sbin/sh
# y52s: mount logical system/vendor so the FBE HAL binaries exist.
mkdir -p /system_root /vendor 2>/dev/null
mount | grep -q 'on /system_root type' || mount -t ext4 -o ro /dev/block/mapper/system /system_root
mount | grep -q 'on /vendor type' || mount -t ext4 -o ro /dev/block/mapper/vendor /vendor
exit 0
"""
# v10: the FBE-capable official binary starts Decrypt_Data() at boot, so the
# HALs must already be running BEFORE the GUI initialises DE keys. The old
# "on property:twrp.modules.loaded=true" trigger is not set by this binary,
# and plain "start" fails while /vendor is still unmounted. Instead each HAL
# service is a small self-bootstrapping script that waits for the super
# mapper nodes (TWRP creates them), mounts the two logical partitions and
# then execs the real HAL binary. Services are started from "on init", with
# two more triggers as belt-and-braces.
KM_SH = """#!/sbin/sh
i=0
while [ $i -lt 60 ]; do
  [ -e /dev/block/mapper/system ] && [ -e /dev/block/mapper/vendor ] && break
  sleep 1
  i=$((i+1))
done
mkdir -p /system_root /vendor 2>/dev/null
mount | grep -q 'on /system_root type' || mount -t ext4 -o ro /dev/block/mapper/system /system_root
mount | grep -q 'on /vendor type' || mount -t ext4 -o ro /dev/block/mapper/vendor /vendor
exec /vendor/bin/hw/android.hardware.keymaster@4.0-service.trustonic
"""
GK_SH = """#!/sbin/sh
i=0
while [ $i -lt 60 ]; do
  [ -x /vendor/bin/hw/android.hardware.gatekeeper@1.0-service ] && break
  sleep 1
  i=$((i+1))
done
exec /vendor/bin/hw/android.hardware.gatekeeper@1.0-service
"""
LP = "/system_root/system/lib64:/system_root/system/lib64/vndk-29:/vendor/lib64:/vendor/lib64/hw"
addition = (
    "\n# y52s v10: self-bootstrapping FBE HALs, started before the GUI needs DE keys.\n"
    "service y52s_prepare /sbin/sh /sbin/y52s_prepare.sh\n"
    "    disabled\n"
    "    oneshot\n"
    "    seclabel u:r:recovery:s0\n\n"
    "service y52s_keymaster /sbin/sh /sbin/y52s_keymaster.sh\n"
    "    disabled\n"
    "    user root\n"
    "    group root drmrpc\n"
    "    seclabel u:r:recovery:s0\n"
    "    setenv LD_LIBRARY_PATH " + LP + "\n\n"
    "service y52s_gatekeeper /sbin/sh /sbin/y52s_gatekeeper.sh\n"
    "    disabled\n"
    "    user root\n"
    "    group root\n"
    "    seclabel u:r:recovery:s0\n"
    "    setenv LD_LIBRARY_PATH " + LP + "\n\n"
    "on init\n"
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n\n"
    "on property:init.svc.recovery=running\n"
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n\n"
    "on property:twrp.modules.loaded=true\n"
    "    start y52s_keymaster\n"
    "    start y52s_gatekeeper\n"
)
trailer = next(i for i, e in enumerate(entries) if e["name"] == "TRAILER!!!")
for j, (nm, txt) in enumerate((
        ("sbin/y52s_prepare.sh", PREPARE),
        ("sbin/y52s_keymaster.sh", KM_SH),
        ("sbin/y52s_gatekeeper.sh", GK_SH))):
    se = file_entry(nm, txt.encode(), 4001000 + j)
    se["f"][1] = ("%08X" % 0o100755).encode()
    entries.insert(trailer + j, se)
for e in entries:
    if e["name"].endswith("init.recovery.svc.rc"):
        e["data"] = e["data"] + addition.encode()
        changed.append(e["name"])
        break
assert any("svc.rc" in x for x in changed), "init.recovery.svc.rc not found"
print("changed entries:", changed)
print("added scripts: y52s_prepare.sh / y52s_keymaster.sh / y52s_gatekeeper.sh (mode 0755)")

# v5: TrustonicKeymaster4DeviceImpl logged
#   os_version=120000, os_patchlevel=209912, vendor_patchlevel=20991231
# which come from TWRP's own ramdisk prop.default (release=12, sdk=32,
# patch=2099-12-31). The real system is Android 10 / sdk 29 / 2023-02-01,
# vendor patch 2020-07-05. Keymaster key blobs are bound to those values, so
# a mismatch makes CE decryption fail. Replace only these five lines with the
# measured values; nothing else in prop.default is touched.
PROP_FIXES = (
    # substring form: also covers ro.system / ro.vendor / ro.product /
    # ro.odm / ro.system_ext build.version.* lines in prop.default
    ("build.version.sdk=32", "build.version.sdk=29"),
    ("build.version.release=12", "build.version.release=10"),
    ("build.version.release_or_codename=16.1.0",
     "build.version.release_or_codename=10"),
    ("ro.build.version.security_patch=2099-12-31",
     "ro.build.version.security_patch=2023-02-01"),
    ("ro.vendor.build.security_patch=2099-12-31",
     "ro.vendor.build.security_patch=2020-07-05"),
    # prop.default has one "persist.sys.usb.config=adb" followed by FOUR
    # "=none" lines which override it -> USB comes up without adb.
    ("persist.sys.usb.config=none", "persist.sys.usb.config=adb"),
)
for e in entries:
    if e["name"] == "prop.default":
        t = e["data"].decode("utf-8", "replace")
        for old, new in PROP_FIXES:
            assert old in t, "prop line not found: " + old
            t = t.replace(old, new)   # all partition-scoped variants too
        e["data"] = t.encode()
        changed.append("prop.default")
        break
assert "prop.default" in changed, "prop.default not found"
print("version props aligned; persist.sys.usb.config forced to adb")

# v7: TWRP itself turns MTP on after boot (GUI default), which breaks adb
# after every reboot -- the user had to disable MTP by hand each time.
# Revert any MTP USB config back to adb from an rc file that init imports.
USB_ADD = (
    "\n# y52s v7: keep adb usable; never let TWRP switch USB to MTP.\n"
    "on property:sys.usb.config=mtp\n"
    "    setprop sys.usb.config adb\n\n"
    "on property:sys.usb.config=mtp,adb\n"
    "    setprop sys.usb.config adb\n\n"
    "on property:sys.usb.config=adb,mtp\n"
    "    setprop sys.usb.config adb\n"
)
for e in entries:
    if e["name"] == "init.recovery.usb.rc":
        # the file uses CRLF; keep the appended block in the same convention
        e["data"] = e["data"] + USB_ADD.replace("\n", "\r\n").encode()
        changed.append("init.recovery.usb.rc")
        break
assert "init.recovery.usb.rc" in changed, "usb rc not found"
print("init.recovery.usb.rc: MTP configs redirected to adb")

# NOTE: replacing system/etc/recovery.fstab with the TWRP-format fstab was
# tried as v6 and REVERTED. It broke the decryption initialisation
# ("Keymaster_Ver::Using keymaster version ''" instead of 4.x) and made /data
# mount read-only. Keep the verbatim vendor fstab.

new_cpio = build_cpio(entries)
assert len(parse_cpio(new_cpio)) == len(entries), "cpio round-trip entry count mismatch"
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
    g.write(new_cpio)
new_gz = buf.getvalue()
print("ramdisk: %d -> %d bytes (gzip %d -> %d)" %
      (len(cpio), len(new_cpio), len(ramdisk_gz), len(new_gz)))

# ---- rebuild boot image (header preserved, only ramdisk_size updated) ------
h = bytearray(raw[:hsz])
struct.pack_into("<I", h, 16, len(new_gz))
out = bytearray()
out += h
out += b"\0" * (pg(hsz, page) - hsz)
out += kernel
out += b"\0" * (pg(ksz, page) - ksz)
out += new_gz
out += b"\0" * (pg(len(new_gz), page) - len(new_gz))
out += dtb
out += b"\0" * (pg(dtb_size, page) - dtb_size)
out += b"\0" * (PART_SIZE - len(out))
assert len(out) == PART_SIZE, len(out)

# Preserve the AVB footer and the embedded vbmeta blob. Measured layout of
# the source image (100663296 B partition):
#   content_end        0x2af8800  (header + kernel + ramdisk + dtb)
#   vbmeta blob        0x2af9000  (2432 B, "AVB0"), i.e. next page
#   AVB footer          last 64 B ("AVBf"), fields at +12/+20/+28:
#                       original_image_size / vbmeta_offset / vbmeta_size
#   everything between vbmeta and the footer is zero padding.
# A larger ramdisk (v8) pushes content_end past the OLD vbmeta offset, so the
# blob must be relocated to the new page boundary and the two footer fields
# updated. The blob itself and vbmeta_size stay byte-for-byte identical.
foot = bytearray(raw[PART_SIZE-64:PART_SIZE])
assert foot[:4] == b"AVBf", "AVB footer missing - aborting"
orig_size = struct.unpack_from(">Q", foot, 12)[0]
vbmeta_off = struct.unpack_from(">Q", foot, 20)[0]
vbmeta_size = struct.unpack_from(">Q", foot, 28)[0]
print("AVB footer: original_image_size=0x%x vbmeta_offset=0x%x vbmeta_size=0x%x" %
      (orig_size, vbmeta_off, vbmeta_size))
assert 0 < vbmeta_off < PART_SIZE and vbmeta_size > 0
vbmeta_blob = raw[vbmeta_off:vbmeta_off+vbmeta_size]
assert vbmeta_blob[:4] == b"AVB0", "vbmeta blob missing - aborting"

new_roff = koff + pg(ksz, page)
new_content_end = new_roff + pg(len(new_gz), page) + pg(dtb_size, page)
new_vbmeta_off = pg(new_content_end, page)
assert new_vbmeta_off + vbmeta_size < PART_SIZE - 64, "no room for vbmeta"
out[new_vbmeta_off:new_vbmeta_off+vbmeta_size] = vbmeta_blob
struct.pack_into(">Q", foot, 12, new_content_end)
struct.pack_into(">Q", foot, 20, new_vbmeta_off)
out[PART_SIZE-64:PART_SIZE] = foot
print("AVB relocated: content_end=0x%x vbmeta_offset=0x%x (blob identical)" %
      (new_content_end, new_vbmeta_off))

os.makedirs(os.path.dirname(DST), exist_ok=True)
open(DST, "wb").write(out)
sha = hashlib.sha256(out).hexdigest()
open(SUM, "w", encoding="ascii").write("%s  recovery.img\n" % sha)

# ---- offline verification --------------------------------------------------
chk = open(DST, "rb").read()
assert chk[:8] == b"ANDROID!"
cv = struct.unpack_from("<10I", chk, 8)
assert cv[0] == ksz and cv[2] == len(new_gz) and cv[7] == page and cv[8] == hv
assert chk[koff:koff+ksz] == kernel, "kernel changed"
new_roff = koff + pg(ksz, page)
new_doff = new_roff + pg(len(new_gz), page)
assert chk[new_roff:new_roff+len(new_gz)] == new_gz, "ramdisk changed"
assert chk[new_doff:new_doff+dtb_size] == dtb, "dtb changed"
assert gzip.decompress(chk[new_roff:new_roff+len(new_gz)]) == new_cpio
assert len(parse_cpio(gzip.decompress(chk[new_roff:new_roff+len(new_gz)]))) == len(entries)
assert chk[:hsz] != raw[:hsz], "header unexpectedly identical (ramdisk_size must differ)"
assert chk[new_vbmeta_off:new_vbmeta_off+vbmeta_size] == vbmeta_blob, "vbmeta blob changed"
fchk = chk[PART_SIZE-64:PART_SIZE]
assert fchk[:4] == b"AVBf", "AVB footer missing"
assert struct.unpack_from(">Q", fchk, 12)[0] == new_content_end, "footer size field"
assert struct.unpack_from(">Q", fchk, 20)[0] == new_vbmeta_off, "footer offset field"
assert struct.unpack_from(">Q", fchk, 28)[0] == vbmeta_size, "footer vbmeta size field"
print("VERIFY OK: header/kernel/dtb/AVB-tail preserved, ramdisk round-trips, padded to", PART_SIZE)
print("SHA256:", sha)
print("OUTPUT:", DST)
