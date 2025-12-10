#!/bin/bash
# 連接到 gem5 串口並自動測試

echo "連接到 gem5 串口 (localhost:3456)..."
echo "----------------------------------------"
echo "提示:"
echo "  - 連接後按 2-3 次 Enter 喚醒終端"
echo "  - 如果看到 login: 提示，輸入 root"
echo "  - 斷開連接: Ctrl+] 然後輸入 quit"
echo "  - 測試 m5: /sbin/m5 --help"
echo "  - 切換到 O3: /sbin/m5 exit"
echo "----------------------------------------"
sleep 2

# 使用 expect 自動處理（如果可用）
if command -v expect &> /dev/null; then
    expect << 'EOF'
spawn telnet localhost 3456
expect {
    "login:" { 
        send "root\r"
        exp_continue
    }
    "#" {
        interact
    }
    timeout {
        interact
    }
}
EOF
else
    # 普通 telnet 連接
    telnet localhost 3456
fi
