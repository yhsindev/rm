# stats.py

import re
from collections import defaultdict

def parse_stats(stats_file='m5out/stats.txt'):
    """
    解析 gem5 stats.txt，提取 RacetrackCache 相關數據
    """
    
    stats = defaultdict(dict)
    current_cache = None
    
    with open(stats_file, 'r') as f:
        for line in f:
            line = line.strip()
            
            # 識別 cache 區塊
            if 'system.cpu' in line and 'l2cache' in line:
                current_cache = 'L2'
            elif 'system.l3cache' in line:
                current_cache = 'L3'
            
            # 提取統計數據
            if current_cache and line and not line.startswith('#'):
                match = re.match(r'(\S+)\s+(\S+)', line)
                if match:
                    stat_name, value = match.groups()
                    # 移除前綴，只保留統計名稱
                    clean_name = stat_name.split('.')[-1]
                    stats[current_cache][clean_name] = value
    
    return stats

def calculate_metrics(stats):
    """
    計算關鍵效能指標
    """
    metrics = {}
    
    for cache_level in ['L2', 'L3']:
        if cache_level not in stats:
            continue
            
        cache_stats = stats[cache_level]
        
        # 基本存取統計
        overall_accesses = float(cache_stats.get('overall_accesses::total', 0))
        overall_hits = float(cache_stats.get('overall_hits::total', 0))
        overall_misses = float(cache_stats.get('overall_misses::total', 0))
        
        # 計算 hit rate 和 miss rate
        if overall_accesses > 0:
            hit_rate = (overall_hits / overall_accesses) * 100
            miss_rate = (overall_misses / overall_accesses) * 100
        else:
            hit_rate = miss_rate = 0
        
        # MPKI (Misses Per Kilo Instructions)
        mpki = float(cache_stats.get('overall_mpki::total', 0))
        
        # 平均延遲
        avg_miss_latency = float(cache_stats.get('overall_avg_miss_latency::total', 0))
        
        metrics[cache_level] = {
            'Total Accesses': int(overall_accesses),
            'Hits': int(overall_hits),
            'Misses': int(overall_misses),
            'Hit Rate (%)': f'{hit_rate:.2f}',
            'Miss Rate (%)': f'{miss_rate:.2f}',
            'MPKI': f'{mpki:.2f}',
            'Avg Miss Latency (cycles)': f'{avg_miss_latency:.2f}',
        }
    
    return metrics

def print_report(metrics):
    """
    印出格式化的報告
    """
    print("=" * 80)
    print("RacetrackCache Performance Report")
    print("=" * 80)
    
    for cache_level, data in metrics.items():
        print(f"\n{cache_level} Cache:")
        print("-" * 80)
        for metric, value in data.items():
            print(f"  {metric:.<40} {value:>20}")
    
    print("\n" + "=" * 80)

def extract_racetrack_specific_stats(stats_file='m5out/stats.txt'):
    """
    提取 RacetrackCache 特定的統計（如果你在 C++ 中實作了自訂統計）
    """
    racetrack_stats = {}
    
    # 這些是你可能在 racetrack_cache.cc 中定義的統計
    # 例如：shift operations, domain accesses 等
    racetrack_patterns = [
        'shift_operations',
        'domain_accesses',
        'shift_latency_total',
        'racetrack_',  # 任何以 racetrack_ 開頭的統計
    ]
    
    with open(stats_file, 'r') as f:
        for line in f:
            for pattern in racetrack_patterns:
                if pattern in line:
                    print(f"RacetrackCache 特定統計: {line.strip()}")
                    # 可以進一步解析這些數據
    
    return racetrack_stats

# 主程式
if __name__ == '__main__':
    print("解析 gem5 統計資料...\n")
    
    # 解析標準 cache 統計
    stats = parse_stats()
    metrics = calculate_metrics(stats)
    print_report(metrics)
    
    # 提取 RacetrackCache 特定統計
    print("\n" + "=" * 80)
    print("RacetrackCache 特定統計:")
    print("=" * 80)
    extract_racetrack_specific_stats()