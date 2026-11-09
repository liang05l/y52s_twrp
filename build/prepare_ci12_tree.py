#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Turn the upstream Y73s (PD2031) twrp-12.1 device tree into a Y52s (PD2057)
tree, using ONLY measured Y52s assets that are already checked into this repo.

Why this exists
---------------
The verified working image `a3855ed4...` is exactly:
    Y73s 12.1 ramdisk  +  Y52s stock kernel/dtb  +  official vivo vbmeta.
So the correct way to fix user 999 is to rebuild THAT 12.1 tree with patch
0007, not to start over on twrp-11 (its keystore SIGABRTs on this Android 10
device -- proven on run 42616212138).

Every substitution below is measured on this device; nothing is guessed.
"""
import argparse
import os
import shutil

V52 = "device/vivo/y52s"
DT_REL = "device/vivo/k6853v1_64_6360"


def read(p):
    return open(p, "r", encoding="utf-8", newline="").read()


def write(p, s):
    open(p, "w", encoding="utf-8", newline="").write(s)


def sub(text, old, new, label, required=True):
    n = text.count(old)
    if n == 0:
        if required:
            raise SystemExit("FATAL: pattern not found: " + label)
        print("  skip (absent): " + label)
        return text
    print("  %-52s x%d" % (label, n))
    return text.replace(old, new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="TWRP source root")
    ap.add_argument("--repo", required=True, help="this checked-out repository")
    a = ap.parse_args()
    dt = os.path.join(a.work, DT_REL)
    v52 = os.path.join(a.repo, V52)
    assert os.path.isdir(dt), "Y73s device tree not cloned at " + dt
    print("== Y52s-ising " + dt)

    # --- 1) kernel / dtb / dtbo: Y52s STOCK (touch + display drivers) -------
    for f in ("kernel", "dtb.img", "dtbo.img"):
        src = os.path.join(v52, "prebuilt", f)
        assert os.path.isfile(src), "missing measured asset " + src
        shutil.copyfile(src, os.path.join(dt, "prebuilt", f))
        print("  prebuilt/%s <- Y52s (%d B)" % (f, os.path.getsize(src)))

    # --- 2) touch firmware: drop PD2031, install the 14 verified PD2057 ----
    fwdir = os.path.join(dt, "recovery/root/vendor/firmware")
    os.makedirs(fwdir, exist_ok=True)
    for f in os.listdir(fwdir):
        os.remove(os.path.join(fwdir, f))
    srcfw = os.path.join(v52, "recovery/root/vendor/firmware")
    names = sorted(os.listdir(srcfw))
    assert len(names) == 14, "expected 14 measured touch blobs, got %d" % len(names)
    for f in names:
        shutil.copyfile(os.path.join(srcfw, f), os.path.join(fwdir, f))
    print("  vendor/firmware <- 14 Y52s blobs")

    # --- 3) product makefile must list the NEW firmware names ---------------
    dmk = os.path.join(dt, "device.mk")
    t = read(dmk)
    start = t.find("# 触摸固件")
    end = t.find("\n\n", start)
    assert start >= 0 and end > start, "device.mk firmware block not found"
    lines = ["# y52s: measured PD2057 touch firmware (14 blobs)"]
    lines.append("PRODUCT_COPY_FILES += \\")
    for i, f in enumerate(names):
        tail = " \\" if i != len(names) - 1 else ""
        lines.append("    $(LOCAL_PATH)/recovery/root/vendor/firmware/%s:$(TARGET_COPY_OUT_RECOVERY)/root/vendor/firmware/%s%s"
                     % (f, f, tail))
    t = t[:start] + "\n".join(lines) + t[end:]
    write(dmk, t)
    print("  device.mk firmware COPY_FILES rewritten (%d entries)" % len(names))

    # --- 4) vts_app_recovery is panel-specific ------------------------------
    shutil.copyfile(os.path.join(v52, "recovery/root/system/bin/vts_app_recovery"),
                    os.path.join(dt, "recovery/root/system/bin/vts_app_recovery"))
    print("  system/bin/vts_app_recovery <- Y52s")

    # --- 5) fstab: measured Y52s partition set ------------------------------
    shutil.copyfile(os.path.join(v52, "recovery.fstab"),
                    os.path.join(dt, "recovery.fstab"))
    print("  recovery.fstab <- Y52s")

    # --- 6) BoardConfig: product version + real patch level -----------------
    bc = os.path.join(dt, "BoardConfig.mk")
    t = read(bc)
    t = sub(t, "product.version=PD2031_A_5.12.1", "product.version=PD2057_A_1.16.4",
            "BOARD_KERNEL_CMDLINE product.version")
    t = sub(t, "PLATFORM_SECURITY_PATCH := 2022-11-01",
            "PLATFORM_SECURITY_PATCH := 2023-02-01", "PLATFORM_SECURITY_PATCH")
    write(bc, t)

    # --- 7) product makefile: identity --------------------------------------
    om = os.path.join(dt, "omni_k6853v1_64_6360.mk")
    t = read(om)
    t = sub(t, "PRODUCT_MODEL := PD2031", "PRODUCT_MODEL := V2057A", "PRODUCT_MODEL")
    t = sub(t, "FOX_DEVICE_MODEL := PD2031", "FOX_DEVICE_MODEL := V2057A", "FOX_DEVICE_MODEL")
    t = sub(t, "compiler10052108", "compiler04181705", "compiler tag")
    t = sub(t, "vivo/PD2031/PD2031", "vivo/PD2057/PD2057", "BUILD_FINGERPRINT device")
    write(om, t)

    # --- 8) rc: the panel firmware picker keys off ro.vivo.product.model ----
    for root, _dirs, files in os.walk(os.path.join(dt, "recovery/root")):
        for fn in files:
            if not fn.endswith(".rc"):
                continue
            p = os.path.join(root, fn)
            t = read(p)
            if "PD2031" in t:
                write(p, t.replace("PD2031", "PD2057"))
                print("  rc PD2031 -> PD2057: %s" % os.path.relpath(p, dt))

    # --- 9) sanity -----------------------------------------------------------
    assert read(bc).count("PD2057_A_1.16.4") == 1
    assert read(dmk).count("TP-CONFIG-FW-PD2031") == 0
    assert "PD2031" not in read(om)
    print("PREPARE_OK")


if __name__ == "__main__":
    main()
