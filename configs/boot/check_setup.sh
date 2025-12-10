#!/bin/bash
# 檢查 gem5 Full System 環境設置

echo "=========================================="
echo "gem5 Full System 環境檢查"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# 檢查 1: Kernel
echo "[1/7] 檢查 Kernel..."
if [ -f "/home/usr/rm/gem5_resources/vmlinux" ]; then
    SIZE=$(du -h /home/usr/rm/gem5_resources/vmlinux | cut -f1)
    echo "  ✓ vmlinux 存在 (大小: $SIZE)"
else
    echo "  ✗ vmlinux 不存在！"
    ERRORS=$((ERRORS+1))
fi

# 檢查 2: Disk Image
echo "[2/7] 檢查 Disk Image..."
if [ -f "/home/usr/rm/gem5_resources/parsec.img" ]; then
    SIZE=$(du -h /home/usr/rm/gem5_resources/parsec.img | cut -f1)
    echo "  ✓ parsec.img 存在 (大小: $SIZE)"
    
    # 檢查分區
    echo "  檢查分區結構..."
    PARTITIONS=$(fdisk -l /home/usr/rm/gem5_resources/parsec.img 2>/dev/null | grep "^/home" | wc -l)
    echo "  發現 $PARTITIONS 個分區"
    fdisk -l /home/usr/rm/gem5_resources/parsec.img 2>/dev/null | grep "^/home" | sed 's/^/    /'
else
    echo "  ✗ parsec.img 不存在！"
    ERRORS=$((ERRORS+1))
fi

# 檢查 3: boot.rcS
echo "[3/7] 檢查 boot.rcS..."
if [ -f "/home/usr/rm/gem5/configs/boot/boot.rcS" ]; then
    echo "  ✓ boot.rcS 存在"
    if [ -x "/home/usr/rm/gem5/configs/boot/boot.rcS" ]; then
        echo "  ✓ boot.rcS 可執行"
    else
        echo "  ⚠ boot.rcS 不可執行 (建議: chmod +x)"
        WARNINGS=$((WARNINGS+1))
    fi
else
    echo "  ✗ boot.rcS 不存在！"
    ERRORS=$((ERRORS+1))
fi

# 檢查 4: kvm.py
echo "[4/7] 檢查 kvm.py..."
if [ -f "/home/usr/rm/gem5/configs/kvm.py" ]; then
    echo "  ✓ kvm.py 存在"
    
    # 檢查路徑配置
    if grep -q "/home/usr/rm/gem5_resources/vmlinux" /home/usr/rm/gem5/configs/kvm.py; then
        echo "  ✓ kernel 路徑配置正確"
    else
        echo "  ⚠ kernel 路徑可能需要調整"
        WARNINGS=$((WARNINGS+1))
    fi
    
    if grep -q "/home/usr/rm/gem5_resources/parsec.img" /home/usr/rm/gem5/configs/kvm.py; then
        echo "  ✓ disk-image 路徑配置正確"
    else
        echo "  ⚠ disk-image 路徑可能需要調整"
        WARNINGS=$((WARNINGS+1))
    fi
    
    # 檢查 root 分區設定
    ROOT_DEV=$(grep "root=/dev/sda" /home/usr/rm/gem5/configs/kvm.py | grep -o "root=/dev/sda[0-9]" | head -1)
    echo "  Kernel 參數設定: $ROOT_DEV"
else
    echo "  ✗ kvm.py 不存在！"
    ERRORS=$((ERRORS+1))
fi

# 檢查 5: m5 工具
echo "[5/7] 檢查 m5 工具..."
if [ -f "/home/usr/rm/gem5/util/m5/build/x86/out/m5" ]; then
    echo "  ✓ m5 工具已編譯"
    ls -lh /home/usr/rm/gem5/util/m5/build/x86/out/m5 | sed 's/^/    /'
else
    echo "  ✗ m5 工具未編譯"
    echo "    請執行: /home/usr/rm/gem5/configs/boot/build_m5.sh"
    ERRORS=$((ERRORS+1))
fi

# 檢查 6: gem5 binary
echo "[6/7] 檢查 gem5 執行檔..."
if [ -f "/home/usr/rm/gem5/build/X86/gem5.opt" ]; then
    echo "  ✓ gem5.opt 已編譯"
else
    echo "  ✗ gem5.opt 不存在"
    echo "    請先編譯 gem5: scons build/X86/gem5.opt -j$(nproc)"
    ERRORS=$((ERRORS+1))
fi

# 檢查 7: KVM 支援
echo "[7/7] 檢查 KVM 支援..."
if [ -e /dev/kvm ]; then
    echo "  ✓ /dev/kvm 存在"
    if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
        echo "  ✓ KVM 可讀寫"
    else
        echo "  ⚠ KVM 權限不足 (需要: sudo usermod -aG kvm $USER)"
        WARNINGS=$((WARNINGS+1))
    fi
else
    echo "  ⚠ /dev/kvm 不存在 (將使用 atomic CPU)"
    WARNINGS=$((WARNINGS+1))
fi

echo ""
echo "=========================================="
echo "檢查完成"
echo "=========================================="
echo "錯誤: $ERRORS"
echo "警告: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo "✓ 所有必要元件已就緒"
    echo ""
    echo "下一步: 執行 gem5"
    echo "  cd /home/usr/rm/gem5"
    echo "  ./build/X86/gem5.opt configs/kvm.py"
    exit 0
else
    echo "✗ 請先解決上述錯誤"
    exit 1
fi
