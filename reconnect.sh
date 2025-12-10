#!/bin/bash
# 重新連接到 gem5 串口並清理終端狀態

echo "等待 3 秒後連接..."
sleep 3

echo "按 Enter 鍵幾次來喚醒終端"
echo "如果看到登入提示，輸入: root"
echo "---"

telnet localhost 3456
