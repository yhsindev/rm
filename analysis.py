import re
import sys

def analyze_racetrack_log(filename):
    # 用字典來儲存每個 Cache 的統計數據
    # 格式: 'cache_name': {'count': 0, 'dist': 0, 'penalty': 0}
    cache_stats = {}

    print(f"正在分析 {filename} ... (這可能需要幾秒鐘)")

    # 定義正規表達式 (Regex) 來抓取關鍵數字
    # Log 格式範例: 
    # ... board.cache_hierarchy.l2_cache_2: Racetrack Access: ... Dist=57, Penalty=57
    pattern = re.compile(r"board\.cache_hierarchy\.(\w+): Racetrack Access:.*Dist=(\d+), Penalty=(\d+)")

    line_count = 0
    
    try:
        with open(filename, 'r') as f:
            for line in f:
                line_count += 1
                if line_count % 500000 == 0:
                    print(f"已處理 {line_count} 行...")

                # 進行比對
                match = pattern.search(line)
                if match:
                    cache_name = match.group(1)  # 例如 l2_cache_2
                    dist = int(match.group(2))   # 例如 57
                    penalty = int(match.group(3)) # 例如 57

                    # 初始化該 Cache 的紀錄
                    if cache_name not in cache_stats:
                        cache_stats[cache_name] = {'count': 0, 'dist': 0, 'penalty': 0}

                    # 累加數據
                    cache_stats[cache_name]['count'] += 1
                    cache_stats[cache_name]['dist'] += dist
                    cache_stats[cache_name]['penalty'] += penalty

    except FileNotFoundError:
        print(f"錯誤: 找不到檔案 {filename}")
        return

    # --- 輸出漂亮的報表 ---
    print("\n" + "="*80)
    print(f"{'Cache Name':<15} | {'Accesses':<10} | {'Total Dist':<12} | {'Total Penalty':<15} | {'Avg Penalty':<10}")
    print("-" * 80)

    total_shifts_system = 0
    
    # 排序並印出結果
    for name in sorted(cache_stats.keys()):
        stats = cache_stats[name]
        avg_penalty = stats['penalty'] / stats['count'] if stats['count'] > 0 else 0
        
        print(f"{name:<15} | {stats['count']:<10} | {stats['dist']:<12} | {stats['penalty']:<15} | {avg_penalty:<10.2f}")
        
        total_shifts_system += stats['dist']

    print("="*80)
    print(f"系統總移動距離 (Total Shifts): {total_shifts_system}")
    print("="*80)

if __name__ == "__main__":
    # 預設讀取 filtered_stats.txt，你也可以透過參數傳入檔名
    target_file = "filtered_stats.txt"
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
        
    analyze_racetrack_log(target_file)