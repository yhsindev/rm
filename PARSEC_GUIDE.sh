#!/bin/bash
# 在 gem5 Linux 系統內執行 PARSEC benchmark 的指令

cat << 'EOF'
================================================================
在 gem5 Linux 內執行 PARSEC Benchmark
================================================================

請在 telnet 終端（連接到 gem5）執行以下指令：

1. 連接到 gem5：
   telnet localhost 3456

2. 搜尋 PARSEC 安裝位置：
   find / -name "parsec*" -type d 2>/dev/null | head -10
   
3. 常見的 PARSEC 安裝位置：
   /parsec
   /home/parsec
   /usr/local/parsec
   
4. 如果找到 PARSEC，切換到該目錄：
   cd /parsec  # 或實際的安裝路徑
   
5. 執行 PARSEC benchmark（推薦從小規模開始）：

   # 方法 1: 使用 parsecmgmt（如果可用）
   parsecmgmt -a run -p blackscholes -i simsmall -n 2
   
   # 方法 2: 直接執行編譯好的 binary
   cd /parsec/pkgs/apps/blackscholes/inst/amd64-linux.gcc/bin
   ./blackscholes 2 /parsec/pkgs/apps/blackscholes/inputs/input_simsmall.txt prices.txt
   
   # 方法 3: 使用 run 腳本（如果有）
   /parsec/bin/parsecmgmt -a run -p blackscholes -i simsmall
   
6. 推薦的 PARSEC benchmarks（按複雜度排序）：

   簡單（快速）：
   - blackscholes (金融計算)
   - swaptions (金融衍生品定價)
   
   中等：
   - fluidanimate (流體動畫)
   - streamcluster (數據聚類)
   
   複雜（慢）：
   - canneal (晶片佈局優化)
   - dedup (數據去重)

7. 執行完畢後，結束模擬：
   /sbin/m5 exit

================================================================
如果 PARSEC 沒有安裝，可以執行簡單測試：
================================================================

   # CPU 密集測試
   time dd if=/dev/zero of=/dev/null bs=1M count=1000
   
   # 記憶體測試
   time dd if=/dev/zero of=/tmp/test bs=1M count=100
   
   # 計算測試
   time python3 -c "sum(range(10000000))"

完成後執行：
   /sbin/m5 exit

================================================================
EOF
