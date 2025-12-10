# gem5 Full System 模擬設置指南

## 📋 檢查清單

### ✅ 1. 編譯 m5 工具（必須）

m5 工具用於在虛擬機內部與 gem5 溝通（執行 checkpoint、exit 等操作）。

#### 編譯步驟：

```bash
cd /home/usr/rm/gem5/util/m5
scons build/x86/out/m5
```

編譯完成後，會產生：
- `/home/usr/rm/gem5/util/m5/build/x86/out/m5` - 靜態編譯的 binary

#### 驗證編譯結果：

```bash
ls -lh /home/usr/rm/gem5/util/m5/build/x86/out/m5
file /home/usr/rm/gem5/util/m5/build/x86/out/m5
```

應該看到類似：
```
-rwxr-xr-x ... m5
m5: ELF 64-bit LSB executable, x86-64, statically linked
```

---

### ✅ 2. 將 m5 工具放入 parsec.img

由於無法直接掛載需要 sudo，有兩種方法：

#### 方法 A：在 gem5 模擬啟動後再放入（推薦）

1. 先啟動一次 gem5（不使用 boot.rcS）
2. 在虛擬機內透過網路下載或掛載 host 目錄
3. 複製 m5 到 /sbin/m5

#### 方法 B：使用 guestfish 工具（如果有安裝）

```bash
# 安裝 libguestfs-tools
sudo apt-get install libguestfs-tools

# 將 m5 複製到 disk image
sudo guestfish -a /home/usr/rm/gem5_resources/parsec.img <<EOF
run
mount /dev/sda1 /
copy-in /home/usr/rm/gem5/util/m5/build/x86/out/m5 /sbin/
chmod 0755 /sbin/m5
umount /
EOF
```

#### 方法 C：使用 loop mount（需要 sudo）

```bash
# 創建掛載點
sudo mkdir -p /mnt/parsec

# 計算偏移量：2048 sectors * 512 bytes = 1048576
sudo mount -o loop,offset=1048576 /home/usr/rm/gem5_resources/parsec.img /mnt/parsec

# 複製 m5
sudo cp /home/usr/rm/gem5/util/m5/build/x86/out/m5 /mnt/parsec/sbin/
sudo chmod +x /mnt/parsec/sbin/m5

# 卸載
sudo umount /mnt/parsec
```

---

### ✅ 3. 確認 Linux kernel 的 root 分區參數

檢查 parsec.img 的分區結構：

```bash
fdisk -l /home/usr/rm/gem5_resources/parsec.img
```

根據輸出調整 kvm.py 第 173 行的 `root=` 參數：
- 如果只有一個分區 (sda1)：改為 `root=/dev/sda1`
- 如果是第二個分區 (sda2)：保持 `root=/dev/sda2`

當前設置：
```python
system.workload.command_line = "earlyprintk=ttyS0 console=ttyS0 lpj=7999923 root=/dev/sda2 idle=poll"
```

根據您的 fdisk 輸出，應該改為：
```python
system.workload.command_line = "earlyprintk=ttyS0 console=ttyS0 lpj=7999923 root=/dev/sda1 idle=poll"
```

---

### ✅ 4. 設定 boot.rcS 的預設路徑

為了方便使用，建議在 kvm.py 中設定預設的 script 路徑：

```python
parser.add_argument("--script", type=str, 
                    default="/home/usr/rm/gem5/configs/boot/boot.rcS", 
                    help="Path to .rcS script")
```

---

## 🚀 執行流程

### Phase 1: 建立 Checkpoint（使用 KVM 快速啟動）

```bash
cd /home/usr/rm/gem5

./build/X86/gem5.opt configs/kvm.py \
  --kernel=/home/usr/rm/gem5_resources/vmlinux \
  --disk-image=/home/usr/rm/gem5_resources/parsec.img \
  --script=/home/usr/rm/gem5/configs/boot/boot.rcS \
  --cpu-type=kvm \
  --num-cpus=1
```

預期輸出：
```
*** Phase 1: Fast-forwarding with KVM ***
Reading current kernel config...
Triggering checkpoint...
*** ROI reached. Creating Checkpoint... ***
*** Checkpoint created. Exiting. ***
```

Checkpoint 會儲存在：`/home/usr/rm/gem5/m5out/cpt.*`

### Phase 2: 從 Checkpoint 恢復並測量（使用 O3 CPU）

```bash
./build/X86/gem5.opt configs/kvm.py \
  --kernel=/home/usr/rm/gem5_resources/vmlinux \
  --disk-image=/home/usr/rm/gem5_resources/parsec.img \
  --checkpoint-dir=m5out \
  --checkpoint-restore=1 \
  --warmup-insts=10000000 \
  --cpu-type=kvm \
  --num-cpus=1
```

---

## 🔍 除錯技巧

### 查看 gem5 輸出

```bash
tail -f m5out/system.pc.com_1.device
```

### 如果 m5 命令找不到

在 boot.rcS 中加入診斷：
```bash
#!/bin/bash
echo "Checking m5 utility..."
which m5
ls -l /sbin/m5
file /sbin/m5
```

### 如果 root 分區掛載失敗

檢查 kernel panic 訊息，調整 `root=/dev/sdaX` 參數。

### 如果 KVM 不可用

使用 atomic CPU：
```bash
./build/X86/gem5.opt configs/kvm.py --cpu-type=atomic
```

---

## 📝 快速測試（不使用 boot.rcS）

測試 Linux 是否能正常啟動：

```bash
./build/X86/gem5.opt configs/kvm.py \
  --kernel=/home/usr/rm/gem5_resources/vmlinux \
  --disk-image=/home/usr/rm/gem5_resources/parsec.img
  # 不加 --script 參數
```

然後在另一個終端連接到虛擬機：
```bash
telnet localhost 3456
```
