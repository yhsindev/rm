#!/bin/bash
# 監控 gem5 O3 模擬狀態

echo "監控 gem5 詳細模擬狀態..."
echo "按 Ctrl+C 停止監控"
echo ""

while true; do
    clear
    echo "=================================="
    echo "gem5 O3 模擬狀態"
    echo "=================================="
    echo ""
    
    # 檢查進程
    if ps aux | grep "[g]em5.opt" > /dev/null; then
        CPU_USAGE=$(ps aux | grep "[g]em5.opt" | awk '{print $3}')
        MEM_USAGE=$(ps aux | grep "[g]em5.opt" | awk '{print $4}')
        echo "✅ gem5 運行中"
        echo "   CPU: ${CPU_USAGE}%"
        echo "   Memory: ${MEM_USAGE}%"
    else
        echo "❌ gem5 已停止"
        break
    fi
    
    echo ""
    echo "最近的統計資料更新："
    echo "----------------------------------"
    if [ -f m5out/stats.txt ]; then
        echo "stats.txt 大小: $(du -h m5out/stats.txt | cut -f1)"
        echo "最後修改: $(stat -c %y m5out/stats.txt | cut -d'.' -f1)"
    else
        echo "尚未生成 stats.txt"
    fi
    
    echo ""
    echo "提示："
    echo "  - O3 模式比 KVM 慢 1000+ 倍"
    echo "  - 在 Linux 內執行測試程式"
    echo "  - 完成後執行: /sbin/m5 exit"
    echo ""
    
    sleep 5
done

echo ""
echo "模擬已完成！查看結果："
echo "  cat m5out/stats.txt | grep racetrack"
