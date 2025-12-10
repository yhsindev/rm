#!/bin/bash
# 將 m5 工具安裝到 parsec.img 的腳本
# 需要 sudo 權限

set -e

M5_BINARY="/home/usr/rm/gem5/util/m5/build/x86/out/m5"
DISK_IMAGE="/home/usr/rm/gem5_resources/parsec.img"
MOUNT_POINT="/tmp/parsec_mount"
OFFSET=$((2048 * 512))  # 從 fdisk 輸出計算：2048 sectors * 512 bytes

echo "=========================================="
echo "安裝 m5 工具到 parsec.img"
echo "=========================================="
echo ""

# 檢查 m5 是否存在
if [ ! -f "$M5_BINARY" ]; then
    echo "✗ 錯誤: m5 工具不存在"
    echo "  請先執行: /home/usr/rm/gem5/configs/boot/build_m5.sh"
    exit 1
fi

echo "✓ 找到 m5 工具: $M5_BINARY"

# 檢查 disk image 是否存在
if [ ! -f "$DISK_IMAGE" ]; then
    echo "✗ 錯誤: disk image 不存在: $DISK_IMAGE"
    exit 1
fi

echo "✓ 找到 disk image: $DISK_IMAGE"
echo ""

# 創建掛載點
echo "步驟 1: 創建掛載點..."
sudo mkdir -p "$MOUNT_POINT"
echo "✓ 掛載點已創建: $MOUNT_POINT"

# 掛載 disk image
echo ""
echo "步驟 2: 掛載 disk image..."
echo "  使用偏移量: $OFFSET bytes"
sudo mount -o loop,offset=$OFFSET "$DISK_IMAGE" "$MOUNT_POINT"
echo "✓ Disk image 已掛載"

# 檢查是否成功掛載
if ! mountpoint -q "$MOUNT_POINT"; then
    echo "✗ 錯誤: 掛載失敗"
    exit 1
fi

# 檢查 /sbin 目錄是否存在
echo ""
echo "步驟 3: 檢查目標目錄..."
if [ ! -d "$MOUNT_POINT/sbin" ]; then
    echo "  /sbin 不存在，正在創建..."
    sudo mkdir -p "$MOUNT_POINT/sbin"
fi
echo "✓ 目標目錄: $MOUNT_POINT/sbin"

# 複製 m5
echo ""
echo "步驟 4: 複製 m5 工具..."
sudo cp "$M5_BINARY" "$MOUNT_POINT/sbin/m5"
sudo chmod 755 "$MOUNT_POINT/sbin/m5"
echo "✓ m5 已複製到 /sbin/m5"

# 驗證
echo ""
echo "步驟 5: 驗證安裝..."
if [ -f "$MOUNT_POINT/sbin/m5" ]; then
    ls -lh "$MOUNT_POINT/sbin/m5"
    file "$MOUNT_POINT/sbin/m5"
    echo "✓ 驗證成功"
else
    echo "✗ 驗證失敗"
fi

# 卸載
echo ""
echo "步驟 6: 卸載 disk image..."
sudo umount "$MOUNT_POINT"
echo "✓ 已卸載"

echo ""
echo "=========================================="
echo "✓ 安裝完成！"
echo "=========================================="
echo ""
echo "parsec.img 現在包含 /sbin/m5 工具"
echo "可以開始執行 gem5 模擬了"
