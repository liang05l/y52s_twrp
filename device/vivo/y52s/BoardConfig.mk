# ===========================================================================
# device/vivo/y52s/BoardConfig.mk  -- CORRECTED for this device
# Base: github.com/AceEdg/vivo-Y52s-devicetree @ twrp-10.0 (commit 3103f97)
# Proof: the RUNNING recovery.img contains kernel_size=16817288 and
#        dtb_size=158641, byte-for-byte equal to that repo's prebuilt/kernel
#        and prebuilt/dtb.img -> the installed TWRP is built from this tree.
# Evidence: device_dump/y52s_dump_20261108_122327/ (root dump, 2026-11-08)
# Lines marked FIX differ from the upstream tree and are backed by device data.
# ===========================================================================

DEVICE_PATH := device/vivo/y52s
ALLOW_MISSING_DEPENDENCIES := true

# ---- architecture  [uname.txt, getprop.all.txt] ----------------------------
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := cortex-a55
TARGET_2ND_ARCH := arm
TARGET_2ND_ARCH_VARIANT := armv7-a-neon
TARGET_2ND_CPU_ABI := armeabi-v7a
TARGET_2ND_CPU_ABI2 := armeabi
TARGET_2ND_CPU_VARIANT := generic
TARGET_2ND_CPU_VARIANT_RUNTIME := cortex-a55
OVERRIDE_TARGET_FLATTEN_APEX := true

TARGET_BOOTLOADER_BOARD_NAME := k6853v1_64_6360
TARGET_NO_BOOTLOADER := true
TARGET_BOARD_PLATFORM := mt6853
TARGET_SCREEN_DENSITY := 480

# ---- boot image format: VERIFIED by parsing the running recovery.img -------
# header_size 1660 | header_version 2 | page_size 2048
# kernel_addr 0x40080000 | ramdisk_addr 0x47c80000 | tags_addr 0x4bc80000
# dtb_addr 0x41f78000 | dtb_size 158641 | os_version 0x1800063c
BOARD_BOOTIMG_HEADER_VERSION := 2
BOARD_KERNEL_BASE := 0x40078000
BOARD_KERNEL_PAGESIZE := 2048
BOARD_RAMDISK_OFFSET := 0x07c08000
BOARD_KERNEL_TAGS_OFFSET := 0x0bc08000
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOTIMG_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --ramdisk_offset $(BOARD_RAMDISK_OFFSET)
BOARD_MKBOOTIMG_ARGS += --tags_offset $(BOARD_KERNEL_TAGS_OFFSET)
BOARD_KERNEL_IMAGE_NAME := Image

# FIX: upstream cmdline says product.version=PD2057_A_1.7.6 (and the installed
# recovery.img carries 1.7.6). Device /proc/cmdline says PD2057_A_1.16.4.
BOARD_KERNEL_CMDLINE := bootopt=64S3,32N2,64N2 product.version=PD2057_A_1.16.4 fingerprint.abbr=10/QP1A.190711.020 buildvariant=user

# ---- prebuilt kernel / dtb / dtbo -----------------------------------------
TARGET_FORCE_PREBUILT_KERNEL := true
ifeq ($(TARGET_FORCE_PREBUILT_KERNEL),true)
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/kernel
TARGET_PREBUILT_DTB := $(DEVICE_PATH)/prebuilt/dtb.img
BOARD_MKBOOTIMG_ARGS += --dtb $(TARGET_PREBUILT_DTB)
BOARD_INCLUDE_DTB_IN_BOOTIMG :=
BOARD_PREBUILT_DTBOIMAGE := $(DEVICE_PATH)/prebuilt/dtbo.img
BOARD_KERNEL_SEPARATED_DTBO :=
endif
BOARD_INCLUDE_RECOVERY_DTBO := true

# ---- partitions  [sysfs sizes 196608*512 = 100663296 for boot & recovery] --
BOARD_FLASH_BLOCK_SIZE := 131072
BOARD_BOOTIMAGE_PARTITION_SIZE := 100663296
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 100663296
BOARD_HAS_LARGE_FILESYSTEM := true
BOARD_SYSTEMIMAGE_PARTITION_TYPE := ext4
BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE := ext4
# FIX: upstream said ext4; device fstab.mt6853 says userdata = f2fs
BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE := f2fs
TARGET_COPY_OUT_VENDOR := vendor
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_USERIMAGES_USE_F2FS := true

# ---- dynamic partitions  [lpdump.txt, mapper.txt] -------------------------
# FIX: upstream group "vivo_dynamic_partitions" / size 9122611200 do not exist
# on this device. lpdump reports group "main", max 8472494080, super 9126805504.
BOARD_SUPER_PARTITION_SIZE := 9126805504
BOARD_SUPER_PARTITION_GROUPS := main
BOARD_MAIN_PARTITION_SIZE := 8472494080
BOARD_MAIN_PARTITION_LIST := system vendor product

# ---- TWRP fstab + FBE decryption  [FIX: upstream had none of these] -------
# TWRP fstab is the corrected device/vivo/y52s/recovery.fstab.
# fstab.mt6853 in this folder is the VERBATIM original vendor fstab (evidence).
TWRP_FSTAB := $(DEVICE_PATH)/recovery.fstab

# COMPILE FLAGS (authoritative source: TeamWin/android_bootable_recovery
# @ android-12.1, openrecoveryscript.cpp + partitionmanager.cpp):
#   Decrypt_Device() real implementation is inside #ifdef TW_INCLUDE_CRYPTO;
#   its #else only prints "no_crypto_support=No crypto support was compiled
#   into this build." and returns -1.  The running 3.7.1_12-0 binary printed
#   exactly that message on `twrp decrypt`, so TW_INCLUDE_CRYPTO was NOT set.
#   Decrypt_Data() (which sets TW_IS_ENCRYPTED and opens the password page at
#   boot) is also entirely inside #ifdef TW_INCLUDE_CRYPTO -- that is why no
#   password screen ever appeared.
#   The FBE user-key path (android::keystore::Decrypt_User) is additionally
#   guarded by #ifdef TW_INCLUDE_FBE. Both are REQUIRED for this device.
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_FBE := true
# NOTE: "TW_INCLUDE_CRYPTO_FBE" is the older 10.0-branch spelling; it was
# present in the first draft of this tree but is NOT what android-12.1 checks.
# Metadata encryption is NOT needed: the measured vendor fstab has
#   /dev/block/by-name/metadata /metadata ext4 ... wait,formattable,first_stage_mount
# with no metadata_encryption= flag, so TW_INCLUDE_FBE_METADATA_DECRYPT is off.
# Do NOT set TW_EXCLUDE_ENCRYPTED_BACKUPS (the installed binary logs it as true);
# it is unrelated to decryption but should not be asserted in a crypto build.
# RAMDISK REALITY (verified 2026-11-08): the installed recovery.img contains
# exactly ONE fstab -- system/etc/recovery.fstab -- in the vendor
# first_stage_mount format. The upstream TWRP-format recovery.fstab was never
# included in the image. When patching the ramdisk, place the corrected fstab
# at the path TWRP actually reads and keep TWRP_FSTAB pointing at it.
# Card-flash (install zip) is a FEATURE of the TWRP being fixed: it needs
# correct mounts, a readable zip source (internal / SD / OTG) and the zip
# toolchain (twrp, unzip, zipinfo, libziparchive, otacerts -- all present).
# NOTE: enabling the flags is necessary but NOT sufficient. The running
# recovery ramdisk has ZERO keymaster / gatekeeper / vendor HAL modules
# (cpio scan: 3557 entries, 0 hits) while init.recovery.platform.rc declares
# those services. The vendor blobs listed in the PENDING block must be added.

# ---- AVB (kept from upstream; device cmdline = unlocked / orange / eio) ----
BOARD_AVB_ENABLE := true
BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS += --flags 3
BOARD_AVB_RECOVERY_KEY_PATH := external/avb/test/data/testkey_rsa4096.pem
BOARD_AVB_RECOVERY_ALGORITHM := SHA256_RSA4096
BOARD_AVB_RECOVERY_ROLLBACK_INDEX := 1
BOARD_AVB_RECOVERY_ROLLBACK_INDEX_LOCATION := 1
# FIX (v5 runtime proof): the upstream tree used 2099-12-31 / 16.1.0, which
# made keymaster read os_version=120000, os_patchlevel=209912 while the real
# system keys are bound to Android 10 / 2023-02-01 / vendor 2020-07-05.
# These values are baked into prop.default at SOURCE BUILD time, so a rebuild
# must use the measured values (see device_dump props + v5 verification).
PLATFORM_SECURITY_PATCH := 2023-02-01
VENDOR_SECURITY_PATCH := 2020-07-05
PLATFORM_VERSION := 10

# ---- TWRP UI (upstream, consistent with 1080x2408 @ 480dpi) ---------------
TW_THEME := portrait_hdpi
TW_EXTRA_LANGUAGES := true
TW_SCREEN_BLANK_ON_BOOT := true
TW_INPUT_BLACKLIST := "hbtp_vm"
TW_USE_TOOLBOX := true
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888

# ===========================================================================
# PENDING -- no guesswork. See y52s_twrp_final.html "待确认项".
#  P1  vendor crypto blobs -> recovery ramdisk. All paths VERIFIED on device
#      2026-11-08 (root list):
#      /vendor/bin/hw/android.hardware.keymaster@4.0-service.trustonic  (97712 B)
#      /vendor/bin/hw/android.hardware.gatekeeper@1.0-service           <-- FIX:
#          init.recovery.platform.rc points at /vendor/bin/android.hardware.
#          gatekeeper@1.0-service, which does NOT exist on this device
#      /vendor/bin/mcDriverDaemon                                       (881680 B)
#      /vendor/lib64/hw/libMcGatekeeper.so                              (23856 B)
#      /vendor/lib64/hw/gatekeeper.k6853v1_64_6360.so, gatekeeper.default.so,
#          android.hardware.gatekeeper@1.0-impl.so, libSoftGatekeeper.so
#      /vendor/app/mcRegistry/*.drbin  (39 files, used by mobicore)
#      + confirm TWRP sets "recovery.service=1" (the rc gate for those services)
#  P2  exact FBE keyword syntax in twrp-10.0 fstab (fileencryption vs equivalent)
#  P3  the "other bugs" you still need to describe (symptoms, not guesses here)
#  P4  target version list: one recovery.img cannot cover every OTA version;
#      each version needs its own kernel/dtb/cmdline bundle
# ===========================================================================
