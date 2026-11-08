# device/vivo/y52s/device.mk
# Mirrors upstream device.mk (which only declares LOCAL_PATH), aligned to this
# workspace's device path so omni_y52s.mk's inherit-product resolves.

LOCAL_PATH := device/vivo/y52s

# recovery/root/ is merged into the recovery ramdisk automatically by the
# TWRP/Omni build system -- no PRODUCT_COPY_FILES needed. It MUST contain
# init.recovery.mt6853.rc, init.recovery.touch.rc, system/bin/vts_app_recovery
# and vendor/firmware/*.bin, otherwise the built TWRP has NO touch:
# init.rc imports /init.recovery.${ro.hardware}.rc (= mt6853 on this device)
# and that chain starts the touchupdate service that loads the panel firmware.

# Vendor crypto / gatekeeper modules are added with PRODUCT_COPY_FILES only
# after being pulled from THIS device's /vendor; none are guessed.
