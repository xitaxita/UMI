# Action 4 原生 H.264 驱动修复候选

已停止：用户改为 MJPEG 输入转码 H.264，不再执行本目录的驱动修补路线。
没有加载或安装任何候选模块。以下仅保留诊断记录。

状态：补丁已准备，未编译、未加载、未实机验证。不要将其视为已修复。

## 已确认的证据

2026-09-11：USB `2ca3:0023`，UVC 1.00，H.264 FORMAT_FRAME_BASED
描述符为 `bVariableSize=0`、`bBitsPerPixel=0`、`dwBytesPerLine=0`。
1080p/720p 的 V4L2 sizeimage 均为 0，REQBUFS 返回 EINVAL。
显式设置 sizeimage 无效。运行内核为 `7.0.0-31-generic`。

上游源码将 bVariableSize 非零的 frame-based 格式标记为 COMPRESSED；
否则根据 bpp 计算缓冲大小，uvc_fixup_video_ctrl 又覆盖协商缓冲大小。
本设备的描述符因此触发零大小路径。补丁仅对这个 VID/PID 的 H.264
补上 COMPRESSED 标记，不修改 MJPEG，也不修改其他相机。

源码依据：
- https://github.com/torvalds/linux/blob/master/drivers/media/usb/uvc/uvc_driver.c
- https://github.com/torvalds/linux/blob/master/drivers/media/usb/uvc/uvc_video.c

## 应用前提与验证顺序

1. 获取与运行内核完全匹配的 Ubuntu 驱动源码及构建配置。不能直接把
   master 驱动装入 Ubuntu 内核。先在该源码根目录运行
   `git apply --check /home/xing/Documents/UMI/tools/action4_uvc/action4-h264-compressed.patch`。
2. 应用补丁后构建匹配的 uvcvideo 模块，检查符号版本及 Secure Boot
   签名要求。保留发行版原始模块；初次测试只临时加载候选模块，不覆盖它。
3. 管理员在关闭所有相机消费者后卸载原 uvcvideo，临时加载候选模块。
   这会影响所有使用 uvcvideo 的设备，因此应确认没有其他相机正在工作。
4. 重新检查 H.264 sizeimage，再测试 150 帧。若仍为零，说明还需要检查
   相机 PROBE 响应中的 dwMaxVideoFrameSize；本补丁不凭空编造该值。
5. 若采集成功，保存原生 H.264 并检查 SPS/PPS、解码、时间间隔，再测试
   项目 MP4 加预览链路。REQBUFS 成功不等于视频可解码或无掉帧。
6. 恢复时卸载候选模块并用 modprobe 加载原发行版模块；未覆盖模块文件
   的前提下重启也恢复原驱动。

当前阻塞：`sudo -n true` 返回需要密码，代理无法自行完成管理员加载。
应用层 io-mode/缓冲参数不能修改内核内部的压缩格式标记。
