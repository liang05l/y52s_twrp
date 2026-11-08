# device/vivo/y52s/omni_y52s.mk
# Values from device_dump/y52s_dump_20261108_122327/props/getprop.all.txt
# FIX vs upstream (omni_k6853v1_64_6360.mk): PRODUCT_MODEL was "vivo" and
# BUILD_FINGERPRINT pointed at compiler12021806 / 1.7.6-era build.
# Single product for this device only.

$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)
# DO NOT inherit vendor/omni/config/common.mk.
# 1) platform_manifest_twrp_aosp @ twrp-11 declares NO vendor/ project at
#    all (checked in default.xml), and platform_manifest_twrp_omni has only
#    5.1 / 8.1 / 10.0-deprecated branches -- there is no Omni 11 manifest.
# 2) Cloning android_vendor_omni/android-11 does not help: its common.mk only
#    adds Omni ROM *system* content (bootanimation, sounds, backuptool,
#    privapp permissions, and frameworks/native/data/etc files that the
#    minimal tree does not contain). None of it is needed for recoveryimage,
#    and PRODUCT_COPY_FILES pointing at absent files breaks the build.
# An unconditional inherit is what made the first CI run abort with
#   device/vivo/y52s/device.mk:5: error: _nic.PRODUCTS.[[.../omni_y52s.mk]]:
#   "vendor/omni/config/common.mk" does not exist
# -> dumpvars failed -> lunch "Device y52s not found".
# The AOSP product makefiles above are sufficient to register the product.
$(call inherit-product, device/vivo/y52s/device.mk)

PRODUCT_NAME        := omni_y52s
PRODUCT_DEVICE      := y52s
PRODUCT_BRAND       := vivo
PRODUCT_MODEL       := V2057A
PRODUCT_MANUFACTURER := vivo

BUILD_FINGERPRINT := vivo/PD2057/PD2057:10/QP1A.190711.020/compiler04181705:user/release-keys

# Vendor crypto / gatekeeper modules are added to PRODUCT_COPY_FILES only after
# they are pulled from THIS device's /vendor (P1 in BoardConfig.mk).
