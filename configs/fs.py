#!/usr/bin/env python3
"""
Racetrack Memory Full System Simulation with KVM

基於 gem5 標準庫的 Full System 模擬
- Phase 1: 使用 KVM 快速啟動到 ROI
- Phase 2: 切換到 O3 CPU 進行詳細測量
- 使用自定義的 RacetrackCache 替代標準 cache
"""

#!/usr/bin/env python3
"""
Racetrack Memory Full System Simulation with KVM
修正版本 - 解決 KVM -> O3 CPU -> ROI 測量流程問題

主要修正：
1. CPU 類型改為 O3 (原本是 TIMING)
2. Cache Hierarchy 的 SimObject 創建方式修正
3. Exit Event Handler 的 generator 語法修正
4. Workload 路徑和執行流程優化
5. 統計數據重置和輸出的時機調整
"""

# -*- coding: utf-8 -*-
from gem5.components.boards.x86_board import X86Board
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_switchable_processor import SimpleSwitchableProcessor
from gem5.components.cachehierarchies.classic.abstract_classic_cache_hierarchy import AbstractClassicCacheHierarchy
from gem5.components.boards.abstract_board import AbstractBoard
from gem5.isas import ISA
from gem5.resources.resource import (
    obtain_resource,
    KernelResource,
    DiskImageResource,
)
from gem5.simulate.exit_event import ExitEvent
from gem5.simulate.simulator import Simulator
from gem5.utils.requires import requires

# 導入 gem5 原生物件
from m5.objects import Cache, L2XBar, SystemXBar, BadAddr, RacetrackCache
import m5

print("="*80)
print("RACETRACK MEMORY FULL SYSTEM SIMULATION (STABLE)")
print("="*80)


class RacetrackHierarchy(AbstractClassicCacheHierarchy):
    """
    三層 Cache Hierarchy 使用 Racetrack Memory
    
    根據論文 TABLE I：
    - L1I/L1D: 32KB SRAM (4-way, 2 cycle, Private)
    - L2: 4MB Racetrack (8-way, 10 cycles, Private, Exclusive)
    - L3: 64MB Racetrack (16-way, 24 cycles, Shared, Mostly Inclusive)
    - RM: 64 domains, 1 rw port, 1 cycle per shift
    """
    
    def __init__(
        self,
        l1i_size: str = "32kB",
        l1i_assoc: int = 4,
        l1d_size: str = "32kB",
        l1d_assoc: int = 4,
        l2_size: str = "4MB",       # 論文配置
        l2_assoc: int = 8,
        l3_size: str = "64MB",      # 論文配置
        l3_assoc: int = 16,
    ):
        super().__init__()
        
        self._l1i_size = l1i_size
        self._l1i_assoc = l1i_assoc
        self._l1d_size = l1d_size
        self._l1d_assoc = l1d_assoc
        self._l2_size = l2_size
        self._l2_assoc = l2_assoc
        self._l3_size = l3_size
        self._l3_assoc = l3_assoc
        
        # 預先創建 membus
        self.membus = SystemXBar(width=64)
        self.membus.badaddr_responder = BadAddr()
        self.membus.default = self.membus.badaddr_responder.pio

    def incorporate_cache(self, board: AbstractBoard) -> None:
        """
        設定 Racetrack Cache Hierarchy
        """
        
        print("\n[INFO] Setting up Racetrack Cache Hierarchy (Paper Config)...")
        
        # 1. 設定 cache line size
        board.cache_line_size = 64
        
        # 2. 創建 L3 bus
        self.l3bus = L2XBar(width=64)
        
        # 3. 創建 Shared L3 Cache (Racetrack)
        self.l3_cache = RacetrackCache(
            size=self._l3_size,
            assoc=self._l3_assoc,
            tag_latency=24,
            data_latency=24,
            response_latency=24,
            num_domains=64,
            shift_latency=1,
            mshrs=20,
            tgts_per_mshr=12,
            writeback_clean=False,
        )
        print(f"  ✓ L3: RacetrackCache {self._l3_size}, {self._l3_assoc}-way, 24 cyc")

        # 4. 連接 L3
        self.l3_cache.cpu_side = self.l3bus.mem_side_ports
        self.l3_cache.mem_side = self.membus.cpu_side_ports
        
        # 5. 連接 system port 和 memory
        board.connect_system_port(self.membus.cpu_side_ports)
        for _, port in board.get_mem_ports():
            self.membus.mem_side_ports = port
        
        # 6. 為每個 core 創建 L1 和 L2
        cores = board.get_processor().get_cores()
        print(f"  Creating caches for {len(cores)} cores...")
        
        for i, cpu in enumerate(cores):
            
            # 創建 L2 Cache (Racetrack)
            l2_cache = RacetrackCache(
                size=self._l2_size,
                assoc=self._l2_assoc,
                tag_latency=10,
                data_latency=10,
                response_latency=10,
                num_domains=64,
                shift_latency=1,
                mshrs=20,
                tgts_per_mshr=12,
                writeback_clean=False,
            )
            setattr(self, f"l2_cache_{i}", l2_cache)
            
            # 創建 L1 Caches (SRAM)
            l1i_cache = Cache(
                size=self._l1i_size,
                assoc=self._l1i_assoc,
                tag_latency=2,
                data_latency=2,
                response_latency=2,
                mshrs=4,
                tgts_per_mshr=20,
                writeback_clean=False,
            )
            
            l1d_cache = Cache(
                size=self._l1d_size,
                assoc=self._l1d_assoc,
                tag_latency=2,
                data_latency=2,
                response_latency=2,
                mshrs=4,
                tgts_per_mshr=20,
                writeback_clean=False,
            )
            
            setattr(self, f"l1i_cache_{i}", l1i_cache)
            setattr(self, f"l1d_cache_{i}", l1d_cache)
            
            # 創建 L2 bus
            l2bus = L2XBar()
            setattr(self, f"l2bus_{i}", l2bus)
            
            # 連接 caches
            l2bus.mem_side_ports = l2_cache.cpu_side
            l2_cache.mem_side = self.l3bus.cpu_side_ports
            l1i_cache.mem_side = l2bus.cpu_side_ports
            l1d_cache.mem_side = l2bus.cpu_side_ports
            
            # 連接 CPU
            cpu.connect_icache(l1i_cache.cpu_side)
            cpu.connect_dcache(l1d_cache.cpu_side)
            cpu.connect_walker_ports(
                self.membus.cpu_side_ports, 
                self.membus.cpu_side_ports
            )
            
            # X86 interrupt 連接
            if board.get_processor().get_isa() == ISA.X86:
                cpu.connect_interrupt(
                    self.membus.mem_side_ports,
                    self.membus.cpu_side_ports,
                )
            else:
                cpu.connect_interrupt()
            
            print(f"  ✓ Core {i}: L1 (SRAM 32kB) + L2 (RM {self._l2_size})")
        
        # 7. I/O cache
        if board.has_coherent_io():
            self.iocache = Cache(
                assoc=8,
                tag_latency=50,
                data_latency=50,
                response_latency=50,
                mshrs=20,
                size="1KiB",
                tgts_per_mshr=12,
                addr_ranges=board.mem_ranges,
                writeback_clean=False,
            )
            self.iocache.mem_side = self.membus.cpu_side_ports
            self.iocache.cpu_side = board.get_mem_side_coherent_io_port()
        
        print(f"\n✅ Cache Hierarchy Complete:")
        print(f"   L1: 32kB SRAM (Private, 2 cyc)")
        print(f"   L2: {self._l2_size} Racetrack (Private, 10 cyc)")
        print(f"   L3: {self._l3_size} Racetrack (Shared, 24 cyc)")
        print(f"   RM: 64 domains, 1 port, 1 cyc/shift\n")

    def get_mem_side_port(self):
        return self.membus.mem_side_ports

    def get_cpu_side_port(self):
        return self.membus.cpu_side_ports

# ============================================================================
# 主要模擬腳本
# ============================================================================

# 檢查環境需求
requires(
    isa_required=ISA.X86,
    kvm_required=True,  
)

# 1. 創建 Cache Hierarchy
cache_hierarchy = RacetrackHierarchy(
    l1i_size="32kB",
    l1i_assoc=4,
    l1d_size="32kB",
    l1d_assoc=4,
    l2_size="4MB",
    l2_assoc=8,
    l3_size="64MB",
    l3_assoc=16,
)

# 2. Memory
memory = SingleChannelDDR3_1600(size="3GiB")

# 3. Processor
processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,  
    switch_core_type=CPUTypes.O3,     # 切換：使用 O3 CPU
    isa=ISA.X86,
    num_cores=4,
)

# 4. Board
board = X86Board(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# 5. Workload - 使用本地的 kernel 和 disk image
kernel = KernelResource("/home/usr/rm/gem5_resources/vmlinux")
disk = DiskImageResource("/home/usr/rm/gem5_resources/ubuntu.img")

# 定義要送進虛擬機執行的腳本
# 根據 FS 規格書的要求，實現 4 個階段的流程
benchmark_script = """#!/bin/bash

# ============================================================================
# Phase 1: KVM 快速啟動完成
# ============================================================================
echo "=== Phase 1: KVM Boot Complete ==="
echo "Triggering first m5 exit to switch to O3 CPU..."
/sbin/m5 exit

# ============================================================================
# Phase 2 & 3: 切換到 O3 CPU 並進行預熱
# ============================================================================
# 注意：當從 KVM 切換到 O3 後，程式會從這裡繼續執行

echo ""
echo "=== Phase 2: Switched to O3 CPU ==="
echo "=== Phase 3: Warming up Racetrack Cache ==="

# 進入 NPB 目錄
if [ -d /home/gem5/NPB ]; then
    cd /home/gem5/NPB
elif [ -d /home/root/NPB ]; then
    cd /home/root/NPB
else
    echo "ERROR: NPB directory not found!"
    ls /home
    /sbin/m5 exit
fi

echo "Current directory: $(pwd)"
echo "Available benchmarks:"
ls -lh *.S.x 2>/dev/null || echo "No .S.x files found"

# 預熱階段：執行一個短暫的測試來填充 Pattern Table
# 這裡我們可以選擇跳過預熱，或執行一個簡短的 benchmark
echo "Skipping explicit warm-up phase (Pattern Table will warm up during ROI)"

# ============================================================================
# Phase 4: ROI 測量
# ============================================================================
echo ""
echo "=== Phase 4: Starting ROI Measurement ==="
echo "Running all NPB benchmarks with statistics collection..."
echo ""

# 重置統計數據：清除 KVM 階段和切換過程的數據
echo "Resetting statistics before ROI..."
/sbin/m5 resetstats

# 計數器
benchmark_count=0
total_benchmarks=$(ls -1 *.S.x 2>/dev/null | wc -l)

# 逐一執行所有 NPB benchmarks
for bench in *.S.x; do
    if [ -f "$bench" ]; then
        benchmark_count=$((benchmark_count + 1))
        
        echo "========================================================================"
        echo "Benchmark [$benchmark_count/$total_benchmarks]: $bench"
        echo "========================================================================"
        
        # 執行 benchmark
        echo "Executing ./$bench ..."
        ./$bench
        
        # 輸出這個 benchmark 的統計數據
        echo "Dumping statistics for $bench..."
        /sbin/m5 dumpstats
        
        # 為下一個 benchmark 重置統計（可選）
        # 如果你想要每個 benchmark 的統計是獨立的，就取消註解下面這行
        # /sbin/m5 resetstats
        
        echo ""
    fi
done

echo "========================================================================"
echo "=== All Benchmarks Completed ==="
echo "Total benchmarks executed: $benchmark_count"
echo "========================================================================"

# 最後一次輸出統計數據（如果需要累積統計）
echo "Final statistics dump..."
/sbin/m5 dumpstats

# 結束模擬
echo "Simulation complete. Exiting..."
/sbin/m5 exit
"""

# 設定 workload
board.set_kernel_disk_workload(
    kernel=kernel,
    disk_image=disk,
    readfile_contents=benchmark_script,
    kernel_args=[
        "earlyprintk=ttyS0",
        "console=ttyS0",
        "lpj=7999923",
        "root=/dev/hda1",
        "rw",  # 讓磁碟可寫
        "init=/init.sh",
    ]
)

# 6. Exit Event Handler - 修正版本
def handle_exit_events():
    """
    處理模擬過程中的 exit events
    修正版本：改進 generator 的實作方式
    """
    
    exit_count = 0
    
    while True:
        exit_count += 1
        
        if exit_count == 1:
            # 第一次 exit: KVM 啟動完成，切換到 O3 CPU
            print("\n" + "=" * 80)
            print("EXIT EVENT 1: KVM Boot Complete")
            print("=" * 80)
            print("Action: Switching from KVM to O3 CPU...")
            
            # 切換 CPU
            processor.switch()
            
            print("✅ CPU switched to O3 (detailed Out-of-Order simulation)")
            print("✅ Starting Phase 3 (Warm-up) & Phase 4 (ROI Measurement)")
            print("✅ Racetrack Cache Pattern Table will be populated during execution")
            print("=" * 80 + "\n")
            
            # 繼續模擬
            yield False
            
        elif exit_count == 2:
            # 第二次 exit: 所有 benchmarks 執行完成
            print("\n" + "=" * 80)
            print("EXIT EVENT 2: All Benchmarks Complete")
            print("=" * 80)
            print("✅ ROI Measurement finished")
            print("✅ Statistics saved to m5out/stats.txt")
            print("=" * 80 + "\n")
            
            # 結束模擬
            yield True
            
        else:
            # 意外的額外 exit events
            print(f"\n⚠ Warning: Unexpected exit event #{exit_count}")
            print("Terminating simulation...")
            yield True

# 7. 創建 Simulator
simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: handle_exit_events(),
    },
)

# 8. 執行模擬
print("\n" + "=" * 80)
print("RACETRACK MEMORY FULL SYSTEM SIMULATION")
print("=" * 80)
print(f"Configuration:")
print(f"  - CPUs: {processor.get_num_cores()} cores (KVM → O3)")
print(f"  - Memory: {memory.get_size()}")
print(f"  - Cache: 3-level hierarchy with Racetrack L2/L3")
print(f"  - Workload: NPB Benchmarks")
print(f"  - Kernel: {kernel}")
print(f"  - Disk: {disk}")
print("=" * 80)
print("\nStarting simulation...")
print("Phase 1: KVM fast-forwarding to boot Linux...")
print("=" * 80 + "\n")

try:
    simulator.run()
    
    print("\n" + "=" * 80)
    print("SIMULATION COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print("Results location:")
    print("  - Statistics: m5out/stats.txt")
    print("  - Console output: m5out/system.pc.com_1.device")
    print("  - Terminal output: m5out/simerr, m5out/simout")
    print("\nKey metrics to analyze:")
    print("  1. totalShiftLatency (Racetrack shift operations)")
    print("  2. Average memory access time")
    print("  3. Cache hit rates (L1/L2/L3)")
    print("  4. IPC (Instructions Per Cycle)")
    print("=" * 80 + "\n")
    
except Exception as e:
    print("\n" + "=" * 80)
    print("SIMULATION ERROR")
    print("=" * 80)
    print(f"Error: {e}")
    print("\nTroubleshooting tips:")
    print("  1. Check if KVM is available: lsmod | grep kvm")
    print("  2. Verify disk image exists: ls -lh /home/usr/rm/gem5_resources/parsec.img")
    print("  3. Check NPB benchmarks in disk: mount and verify /home/root/NPB/")
    print("  4. Review gem5 output: cat m5out/simerr")
    print("=" * 80 + "\n")
    raise