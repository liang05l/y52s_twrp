# device/vivo/y52s/device.mk
# Mirrors upstream device.mk (which only declares LOCAL_PATH), aligned to this
# workspace's device path so omni_y52s.mk's inherit-product resolves.

LOCAL_PATH := device/vivo/y52s

# Vendor crypto / gatekeeper modules (P1 in BoardConfig.mk) are added here with
# PRODUCT_COPY_FILES once pulled from THIS device's /vendor. None are guessed.
