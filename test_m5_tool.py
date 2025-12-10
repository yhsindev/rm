#!/usr/bin/env python3
"""
測試 m5 工具是否可用
"""

import socket
import time

HOST = 'localhost'
PORT = 3456

print("連接到 gem5 串口...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
print("✅ 已連接\n")

# 測試指令序列
test_commands = [
    ("喚醒終端", b"\n\n\n"),
    ("登入 (如需要)", b"root\n"),
    ("測試基本指令", b"pwd\n"),
    ("檢查 m5 檔案", b"ls -la /sbin/m5\n"),
    ("檢查 m5 權限", b"file /sbin/m5\n"),
    ("嘗試執行 m5 help", b"/sbin/m5 --help\n"),
]

for desc, cmd in test_commands:
    print(f"[{desc}]")
    sock.sendall(cmd)
    time.sleep(1.5)
    
    try:
        sock.settimeout(1)
        data = sock.recv(4096)
        output = data.decode('utf-8', errors='ignore')
        print(output)
        print("-" * 60)
    except socket.timeout:
        print("(無輸出)")
        print("-" * 60)

print("\n現在輸入互動模式，您可以手動輸入指令")
print("請手動輸入: /sbin/m5 exit")
print("然後檢查終端 3 (gem5) 的輸出\n")

# 互動模式
try:
    while True:
        try:
            sock.settimeout(0.5)
            data = sock.recv(4096)
            if data:
                print(data.decode('utf-8', errors='ignore'), end='', flush=True)
        except socket.timeout:
            pass
except KeyboardInterrupt:
    print("\n\n斷開連接")

sock.close()
