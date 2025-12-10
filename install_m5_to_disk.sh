#!/bin/bash
# 安裝 m5 工具到 parsec.img 磁碟映像

set -e

DISK_IMAGE="/home/usr/rm/gem5_resources/parsec.img"
M5_BINARY="/home/usr/rm/gem5/util/m5/build/x86/out/m5"
MOUNT_POINT="/tmp/parsec_mount_$$"

echo "============================================"
echo "安裝 m5 工具到 parsec.img"
echo "============================================"

# 檢查 m5 工具是否存在
if [ ! -f "$M5_BINARY" ]; then
    echo "錯誤: m5 工具不存在於 $M5_BINARY"
    echo "正在編譯 m5 工具..."
    cd /home/usr/rm/gem5/util/m5
    scons build/x86/out/m5
    M5_BINARY="/home/usr/rm/gem5/util/m5/build/x86/out/m5"
fi

# 檢查磁碟映像是否存在
if [ ! -f "$DISK_IMAGE" ]; then
    echo "錯誤: 磁碟映像不存在於 $DISK_IMAGE"
    exit 1
fi

# 創建掛載點
echo "創建掛載點: $MOUNT_POINT"
sudo mkdir -p "$MOUNT_POINT"

# 掛載磁碟映像
echo "掛載磁碟映像..."
sudo mount -o loop,offset=1048576 "$DISK_IMAGE" "$MOUNT_POINT"

# 複製 m5 工具
echo "複製 m5 工具到 /sbin/m5..."
sudo cp "$M5_BINARY" "$MOUNT_POINT/sbin/m5"
sudo chmod +x "$MOUNT_POINT/sbin/m5"

# 驗證
if [ -f "$MOUNT_POINT/sbin/m5" ]; then
    echo "✅ m5 工具已成功安裝到 /sbin/m5"
    ls -lh "$MOUNT_POINT/sbin/m5"
else
    echo "❌ m5 工具安裝失敗"
fi

# 卸載
echo "卸載磁碟映像..."
sudo umount "$MOUNT_POINT"
sudo rmdir "$MOUNT_POINT"

echo "============================================"
echo "完成！請重新啟動 gem5 模擬"
echo "============================================"
