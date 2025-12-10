# 實作注意事項總結

## ✅ 已完成的設置

### 1. **路徑修正** ✓
- ✅ Kernel 路徑：`/home/usr/rm/gem5_resources/vmlinux`
- ✅ Disk Image 路徑：`/home/usr/rm/gem5_resources/parsec.img`
- ✅ Boot Script 預設路徑：`/home/usr/rm/gem5/configs/boot/boot.rcS`
- ✅ Root 分區參數：`root=/dev/sda1`（根據 fdisk 輸出）

### 2. **m5 工具編譯** ✓
- ✅ 已編譯 m5 工具
- 位置：`/home/usr/rm/gem5/util/m5/build/x86/out/m5`
- 大小：2.4M（靜態連結）

### 3. **輔助腳本建立** ✓
已建立以下腳本協助您：

| 腳本 | 用途 |
|------|------|
| `check_setup.sh` | 檢查所有環境設置 |
| `build_m5.sh` | 編譯 m5 工具 |
| `install_m5_to_disk.sh` | 將 m5 安裝到 parsec.img |
| `SETUP_GUIDE.md` | 完整設置指南 |

---

## 🚀 下一步：將 m5 工具安裝到 Disk Image

**這是唯一剩下需要做的步驟！**

### 執行安裝（需要 sudo 權限）：

```bash
cd /home/usr/rm/gem5/configs/boot
sudo ./install_m5_to_disk.sh
```

輸入您的密碼後，腳本會自動：
1. 掛載 parsec.img
2. 複製 m5 到 /sbin/m5
3. 設定正確權限
4. 卸載 disk image

### 如果沒有 sudo 權限

使用替代方案（在第一次啟動 gem5 後手動安裝）：

1. 先啟動一次 gem5（不使用 checkpoint）：
```bash
cd /home/usr/rm/gem5
./build/X86/gem5.opt configs/kvm.py --cpu-type=atomic
```

2. 在另一個終端連接虛擬機：
```bash
telnet localhost 3456
```

3. 在虛擬機內下載或掛載 host 目錄，然後複製 m5

---

## 📋 完整執行流程

### 安裝 m5 後，就可以開始模擬了：

#### Phase 1: 建立 Checkpoint

```bash
cd /home/usr/rm/gem5

./build/X86/gem5.opt configs/kvm.py
```

這會：
- 使用 KVM CPU 快速啟動 Linux
- 執行 boot.rcS 腳本
- 建立 checkpoint 到 `m5out/cpt.*`
- 自動退出

#### Phase 2: 從 Checkpoint 恢復並測量

```bash
./build/X86/gem5.opt configs/kvm.py \
  --checkpoint-dir=m5out \
  --checkpoint-restore=1 \
  --warmup-insts=10000000
```

這會：
- 從 checkpoint 恢復
- 切換到 O3 CPU
- 執行 warmup
- 進行詳細測量

---

## 📊 驗證所有設置

執行檢查腳本：

```bash
/home/usr/rm/gem5/configs/boot/check_setup.sh
```

應該顯示：
```
✓ 所有必要元件已就緒
錯誤: 0
警告: 0
```

---

## 🔍 除錯建議

### 如果 Linux 無法啟動

1. 查看輸出：
```bash
tail -f m5out/system.pc.com_1.device
```

2. 檢查是否是 root 分區問題：
   - 如果看到 "Kernel panic - not syncing: VFS: Unable to mount root fs"
   - 修改 `kvm.py` 第 173 行的 `root=/dev/sdaX` 參數

### 如果 m5 命令找不到

在 boot.rcS 中加入診斷：
```bash
echo "DEBUG: Checking for m5..."
which m5 || echo "m5 not in PATH"
ls -l /sbin/m5 || echo "/sbin/m5 not found"
```

### 如果 KVM 不可用

使用 atomic CPU（較慢但不需要 KVM）：
```bash
./build/X86/gem5.opt configs/kvm.py --cpu-type=atomic
```

---

## 📝 檔案位置總覽

```
/home/usr/rm/
├── gem5/
│   ├── configs/
│   │   ├── kvm.py                    # 主要配置檔
│   │   └── boot/
│   │       ├── boot.rcS               # Linux 開機腳本
│   │       ├── SETUP_GUIDE.md         # 完整指南
│   │       ├── check_setup.sh         # 環境檢查
│   │       ├── build_m5.sh            # 編譯 m5
│   │       └── install_m5_to_disk.sh  # 安裝 m5
│   ├── util/m5/build/x86/out/m5      # m5 工具 binary
│   └── build/X86/gem5.opt             # gem5 執行檔
└── gem5_resources/
    ├── vmlinux                        # Linux Kernel
    └── parsec.img                     # Disk Image (需要包含 /sbin/m5)
```
