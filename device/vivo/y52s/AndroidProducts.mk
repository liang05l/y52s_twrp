# device/vivo/y52s/AndroidProducts.mk
# One lunch target for one device. Verify the registration style against the
# selected TWRP/Omni branch before building (P3 in BoardConfig.mk).

PRODUCT_MAKEFILES := \
    $(LOCAL_DIR)/omni_y52s.mk

COMMON_LUNCH_CHOICES := \
    omni_y52s-eng \
    omni_y52s-userdebug
