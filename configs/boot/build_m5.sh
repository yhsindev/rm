#!/bin/bash
# 編譯 m5 工具的快速腳本

set -e

echo "=========================================="
echo "編譯 gem5 m5 工具 (x86 版本)"
echo "=========================================="

cd /home/usr/rm/gem5/util/m5

echo ""
echo "步驟 1: 檢查 scons 是否安裝..."
if ! command -v scons &> /dev/null; then
    echo "錯誤: scons 未安裝"
    echo "請執行: sudo apt-get install scons"
    exit 1
fi
echo "✓ scons 已安裝"

echo ""
echo "步驟 2: 開始編譯 m5 (x86 版本)..."
scons build/x86/out/m5

if [ -f "build/x86/out/m5" ]; then
    echo ""
    echo "=========================================="
    echo "✓ 編譯成功！"
    echo "=========================================="
    echo ""
    echo "m5 工具位置: $(pwd)/build/x86/out/m5"
    echo ""
    ls -lh build/x86/out/m5
    file build/x86/out/m5
    echo ""
    echo "下一步: 將此檔案複製到 parsec.img 的 /sbin/ 目錄"
    echo "請參考 SETUP_GUIDE.md 的說明"
else
    echo ""
    echo "✗ 編譯失敗"
    exit 1
fi
