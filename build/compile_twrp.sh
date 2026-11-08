#!/usr/bin/env bash
# ===========================================================================
# y52s (V2057A / PD2057) -- TWRP twrp-11 源码编译，启用 FBE 解密
#
# 为什么必须重编译（源码级证据，非推测）：
#   设备现有 /system/bin/recovery 在 `twrp decrypt` 时打印
#     "no_crypto_support=No crypto support was compiled into this build."
#   TeamWin/android_bootable_recovery (android-11 / android-12.1 同构):
#     - partitionmanager.cpp: Decrypt_Device() 的真正实现整段在
#       #ifdef TW_INCLUDE_CRYPTO 内；#else 只输出上面这句话并返回 -1。
#     - 同一文件: 启动时设置 TW_IS_ENCRYPTED 并打开密码页的
#       Decrypt_Data() 也整段在 #ifdef TW_INCLUDE_CRYPTO 内。
#       => 未定义该宏时，永远不会弹密码框（用户实测现象）。
#     - FBE 用户密钥路径 android::keystore::Decrypt_User 额外由
#       #ifdef TW_INCLUDE_FBE 保护。
#   两个宏已在 device/vivo/y52s/BoardConfig.mk 中设为 true。
#
# 运行条件（本机 Windows 当前不满足；见 y52s_twrp_final.html）：
#   Linux x86_64；>=150 GB 空闲磁盘；>=16 GB RAM；
#   git / python3 / JDK 11 / ccache / make / gcc；
#   网络可访问 github.com 与 android.googlesource.com（首次 sync 约 40-60 GB）。
#
# 用法（把本工程整个目录复制到 Linux 后执行）：
#   bash build/compile_twrp.sh
#   TWRP_WORK=/mnt/twrp TWRP_JOBS=8 bash build/compile_twrp.sh
#
# 产物：$WORK/out/target/product/y52s/recovery.img
#       并复制为 $ROOT/build/recovery_src.img + sha256
# 编译产物需再经 build/build_recovery.py 的实测 ramdisk 后处理
# （逻辑分区挂载、HAL 服务、os_version 对齐、默认关 MTP），
# 这些修复的证据都在 device_dump/y52s_dump_20261108_122327/。
# ===========================================================================
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DT="$ROOT/device/vivo/y52s"
WORK="${TWRP_WORK:-$HOME/twrp-y52s}"
JOBS="${TWRP_JOBS:-$(nproc)}"
BRANCH="twrp-12.1"
MANIFEST="https://github.com/minimal-manifest-twrp/platform_manifest_twrp_aosp.git"
# BRANCH CHOICE IS DEVICE-EVIDENCE DRIVEN, NOT A DEFAULT:
#   This device is Android 10 (QP1A.190711.020). Its FBE stack is the OLD
#   android.security.keystore + HIDL keymaster@4.0 / gatekeeper@1.0 -- all
#   measured on the device. TeamWin/android_bootable_recovery @ android-11
#   crypto/fscrypt/Decrypt.cpp uses exactly that API
#   (String16("android.security.keystore"), V4_0::KeyPurpose::DECRYPT,
#    V1_0::IGatekeeper::getService()) and has NO keystore2 reference.
#   The android-12.1 build instead requires
#   android.system.keystore2.IKeystoreService/default. We transplanted an
#   official 12.1 TWRP binary (v10) and it hung forever at
#   "Attempting to initialize DE keys" because this device has no keystore2
#   service and no lazy AIDL declaration for it. So DO NOT use twrp-12.1.
#   minimal-manifest-twrp has twrp-11 / twrp-12.1 / twrp-14 / twrp-14.1
#   (no 10.0); twrp-11 is the closest compatible baseline.
BRANCH="twrp-11"

log() { printf '\n[y52s-build] %s\n' "$*"; }
die() { printf '\n[FATAL] %s\n' "$*" >&2; exit 1; }

# ---- 0. 前置检查 ----------------------------------------------------------
[ "$(uname -s)" = "Linux" ] || die "必须在 Linux 上编译（Android 构建系统不支持 Windows 原生）"
[ -f "$DT/BoardConfig.mk" ] || die "device tree 缺失: $DT/BoardConfig.mk"
for f in kernel dtb.img dtbo.img; do
  [ -s "$DT/prebuilt/$f" ] || die "prebuilt 缺失: $DT/prebuilt/$f（先跑 python3 build/extract_prebuilt.py）"
done
grep -q '^TW_INCLUDE_CRYPTO := true' "$DT/BoardConfig.mk" || die "BoardConfig 未启用 TW_INCLUDE_CRYPTO"
grep -q '^TW_INCLUDE_FBE := true' "$DT/BoardConfig.mk" || die "BoardConfig 未启用 TW_INCLUDE_FBE"
for c in git python3 java make gcc curl; do
  command -v "$c" >/dev/null 2>&1 || die "缺少工具: $c"
done
FREE_GB=$(df -BG --output=avail "$WORK" 2>/dev/null | tail -1 | tr -dc '0-9' || df -BG "$HOME" | tail -1 | awk '{print $4}' | tr -dc '0-9')
[ "${FREE_GB:-0}" -ge 150 ] || log "WARN: 可用空间 ${FREE_GB}GB < 150GB，repo sync 可能失败"
log "工作目录: $WORK | 并发: $JOBS | 分支: $BRANCH"

# ---- 1. repo 工具 ---------------------------------------------------------
mkdir -p "$HOME/bin" "$WORK"
if ! command -v repo >/dev/null 2>&1; then
  log "安装 repo 引导程序"
  curl -fsSL https://storage.googleapis.com/git-repo-downloads/repo -o "$HOME/bin/repo"
  chmod +x "$HOME/bin/repo"
fi
export PATH="$HOME/bin:$PATH"

# ---- 2. 初始化并同步 android-12.1 minimal manifest ------------------------
if [ ! -d "$WORK/.repo" ]; then
  log "repo init ($BRANCH)"
  ( cd "$WORK" && repo init --depth=1 -u "$MANIFEST" -b "$BRANCH" )
else
  log "复用已有 .repo"
fi
log "repo sync（首次约 40-60 GB，耗时较长）"
( cd "$WORK" && repo sync -c -j"$JOBS" --force-sync --no-clone-bundle --no-tags )

# ---- 3. 放入本机型 device tree（唯一机型，不引入 common tree）-------------
log "安装 device/vivo/y52s"
mkdir -p "$WORK/device/vivo"
rm -rf "$WORK/device/vivo/y52s"
cp -a "$DT" "$WORK/device/vivo/y52s"
# BoardConfig 中的 FIX 值来自本机实测 dump，禁止构建系统回写
log "device tree 已就位；加密宏校验通过"

# ---- 4. 编译 --------------------------------------------------------------
log "lunch omni_y52s-eng && mka recoveryimage"
(
  cd "$WORK"
  # shellcheck disable=SC1091
  . build/envsetup.sh
  lunch omni_y52s-eng
  mka recoveryimage -j"$JOBS"
)

IMG="$WORK/out/target/product/y52s/recovery.img"
[ -s "$IMG" ] || die "未生成 $IMG"
cp -f "$IMG" "$ROOT/build/recovery_src.img"
( cd "$ROOT/build" && sha256sum recovery_src.img > recovery_src.img.sha256 )
log "完成: build/recovery_src.img ($(stat -c%s "$IMG") bytes)"

# ---- 5. 编译产物自检 ------------------------------------------------------
python3 - "$ROOT/build/recovery_src.img" <<'PY'
import sys, struct, re
p = sys.argv[1]
b = open(p, 'rb').read(4096)
assert b[:8] == b'ANDROID!', 'not an Android boot image'
v = struct.unpack_from('<10I', b, 8)
print('header_version=%d page_size=%d kernel_size=%d ramdisk_size=%d' %
      (v[8], v[7], v[0], v[2]))
PY
log "下一步：把 build/recovery_src.img 交给 build/build_recovery.py 做实测 ramdisk 后处理，再用 flash/flash_recovery.ps1 刷入。"
