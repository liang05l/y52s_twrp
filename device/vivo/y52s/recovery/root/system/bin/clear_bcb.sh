#!/system/bin/sh
# 删了你手机就只能进rec了
# 但是要保留 boot-fastboot 命令，让 twrp 能够检测并进入 fastbootd 模式

MISC_DEV="/dev/block/by-name/misc"

# 读取 BCB command 字段 (前 32 字节)
BCB_CMD=$(dd if=$MISC_DEV bs=32 count=1 2>/dev/null | tr -d '\0')

# 如果是 boot-fastboot 命令，不清除 BCB
if [ "$BCB_CMD" = "boot-fastboot" ]; then
    echo "clear_bcb: boot-fastboot detected, keeping BCB"
    exit 0
fi

# 其他命令，清除 BCB 防止重启循环
dd if=/dev/zero of=$MISC_DEV bs=2048 count=1 2>/dev/null
sync
