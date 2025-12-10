#!/bin/bash
# 監控 gem5 Full System 模擬中的 Linux 啟動

echo "連接到 gem5 串口終端 (port 3456)..."
echo "提示: 使用 Ctrl+] 然後輸入 quit 來斷開連接"
echo "---"
sleep 2

# 嘗試連接到串口
telnet localhost 3456
