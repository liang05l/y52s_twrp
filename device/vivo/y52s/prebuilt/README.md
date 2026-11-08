# prebuilt/ — 二进制素材状态（2026-11-08 root 采集后）

2026-11-08 采集器已以 `uid=0` 跑通，证据在
`device_dump/y52s_dump_20261108_122327/images/`（48 文件 / 172674866 字节，逐文件 sha256 见 manifest.txt）：

| 已取到 | 大小 | 说明 |
| --- | --- | --- |
| `recovery.img` | 96 MB | **现有 TWRP 本体**，同时是回退镜像 |
| `dtbo.img` | 8 MB | dtbo |
| `vbmeta.img` / `vbmeta_system.img` / `vbmeta_vendor.img` | 各 8 MB | AVB |
| `metadata.img` | 32 MB | 元数据分区 |
| `misc.img` | 512 KB | misc |
| `super_head_4M.bin` | 4 MB | 动态分区 metadata 头部 |
| `gpt_header.bin` | 17 KB | GPT 头 |

**`boot.img` 未取到**：即使 root，`/dev/block/by-name/boot` 与裸节点 `/dev/block/sdc48`
都返回 `Permission denied`（设备对 boot 分区读取做了保护）。
**这不构成阻塞**——`recovery.img` 的头已给出全部打包参数
（header v2 / page 2048 / kernel 0x40080000 / ramdisk 0x47c80000 / tags 0x4bc80000 /
dtb 0x41f78000，dtb_size 158641），kernel 与 dtb 也可直接从 recovery.img 提取；
其字节数与上游仓库 `prebuilt/kernel`(16817288)、`prebuilt/dtb.img`(158641) 完全一致。

## 需要放入本目录的文件

- `kernel`、`dtb.img`、`dtbo.img`：从本机 `recovery.img` 解包，或使用同源的上游 prebuilt（二者一致）。
- 从本机 `/vendor` 提取的解密模块（见 BoardConfig.mk 的 P1）：keymaster 4.0 trustonic 服务、
  gatekeeper 1.0 服务、`libMcGatekeeper.so`、`mcDriverDaemon`、`/vendor/app/mcRegistry/*.drbin`。

## 规则

- 全部素材来自同一台设备、同一 fingerprint：
  `vivo/PD2057/PD2057:10/QP1A.190711.020/compiler04181705:user/release-keys`。
- 每个文件在 `SOURCES.txt` 记录原路径、字节数、sha256、解包工具与版本。
- 采集与解包全程只读；**禁止格式化 /data**，用户数据已实测仍在。
- 不从其他机型拷贝 kernel 或 dtb；目标版本变化时重新提取对应镜像。
