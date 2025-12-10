#!/usr/bin/env python3
"""
自動連接到 gem5 串口並執行 m5 exit
"""

import socket
import time
import sys

HOST = 'localhost'
PORT = 3456

print(f"連接到 {HOST}:{PORT}...")

try:
    # 連接到 gem5 串口
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print("✅ 已連接")
    
    # 等待一下
    time.sleep(1)
    
    # 發送指令
    commands = [
        b"\n",
        b"\n",
        b"root\n",
        b"echo 'Testing m5 tool...'\n",
        b"ls -la /sbin/m5\n",
        b"echo 'Executing m5 exit...'\n",
        b"/sbin/m5 exit\n",
        b"echo 'Exit sent'\n",
    ]
    
    for cmd in commands:
        print(f"發送: {cmd.decode().strip()}")
        sock.sendall(cmd)
        time.sleep(0.5)
        
        # 接收回應
        try:
            sock.settimeout(1)
            data = sock.recv(4096)
            if data:
                print(f"回應: {data.decode('utf-8', errors='ignore')}")
        except socket.timeout:
            pass
    
    print("\n等待 gem5 回應...")
    time.sleep(2)
    
    # 保持連接
    print("按 Ctrl+C 斷開連接")
    while True:
        try:
            sock.settimeout(1)
            data = sock.recv(4096)
            if data:
                print(data.decode('utf-8', errors='ignore'), end='')
        except socket.timeout:
            pass
        except KeyboardInterrupt:
            break
    
except Exception as e:
    print(f"❌ 錯誤: {e}")
finally:
    sock.close()
    print("\n連接已關閉")
