#!/usr/bin/env python3
"""
Racetrack Memory Full System Simulation with KVM

基於 gem5 標準庫的 Full System 模擬
- Phase 1: 使用 KVM 快速啟動到 ROI
- Phase 2: 切換到 O3 CPU 進行詳細測量
- 使用自定義的 RacetrackCache 替代標準 cache
- 使用自定義的 SwitchProcessor 處理器類別：O3 <-> KVM 切換
"""

# -*- coding: utf-8 -*-
from gem5.components.boards.x86_board import X86Board
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.base_cpu_core import BaseCPUCore # [新增 Import]
from gem5.components.processors.simple_switchable_processor import SimpleSwitchableProcessor
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.abstract_processor import AbstractProcessor
from m5.objects import O3CPU, X86KvmCPU
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

# 導入 gem5 原生物件 # 直接導入 RacetrackCache
from m5.objects import Cache, L2XBar, SystemXBar, BadAddr, RacetrackCache
import m5
from m5.objects import *

print("="*80)
print("RACETRACK MEMORY FULL SYSTEM SIMULATION")
print("="*80)


class PaperProcessor(SimpleSwitchableProcessor):
    """
    繼承官方穩定版處理器，但在內部注入論文規格。
    """
    def __init__(self, num_cores):
        # 1. 讓爸爸 (官方代碼) 幫我們搞定 KVM 和基本的 O3 結構
        # 這保證了 KVM 不會崩潰，因為是用官方邏輯建立的
        super().__init__(
            starting_core_type=CPUTypes.KVM,
            switch_core_type=CPUTypes.O3,
            isa=ISA.X86,
            num_cores=num_cores
        )
        
        # 2. 在這裡 (內部) 修改 O3 參數是絕對安全的
        print("Applying Paper Specifications to O3 CPUs...")
        
        # self._switch_cores 是父類別建立好的 O3 Cores 列表
        # 我們在這裡把規格注入進去
        for core_wrapper in self._switch_cores:
            # 取出底層 SimObject
            core = core_wrapper.get_simobject()
            
            # --- 論文規格 (Table I) ---
            core.numROBEntries = 128
            core.issueWidth = 4
            core.decodeWidth = 4
            core.renameWidth = 4
            core.dispatchWidth = 4
            core.commitWidth = 4
            core.squashWidth = 4
            core.fetchWidth = 4
            
            core.numIQEntries = 64
            core.numPhysIntRegs = 256
            core.numPhysFloatRegs = 256
            core.LQEntries = 32
            core.SQEntries = 32
            
            # 分支預測器
            core.branchPred = TournamentBP()
            core.branchPred.btb = SimpleBTB(numEntries=4096)
            # core.branchPred.RASSize = 16 (預設值)
            
        print("✓ Paper Specifications Applied Successfully!")
        
class RacetrackHierarchy(AbstractClassicCacheHierarchy):
    """
    三層 Cache Hierarchy 使用 Racetrack Memory
    - L1I/L1D: 標準 SRAM Cache (每個 core 私有)
    - L2: Racetrack Cache (每個 core 私有)
    - L3: Racetrack Cache (所有 cores 共享)
    """
    
    def __init__(
        self,
        l1i_size: str = "32kB",
        l1i_assoc: int = 4,
        l1d_size: str = "32kB",
        l1d_assoc: int = 4,
        l2_size: str = "4MB",
        l2_assoc: int = 8,
        l3_size: str = "16MB",
        l3_assoc: int = 16,
    ):
        super().__init__()
        
        # L1 參數 (SRAM)
        self._l1i_size = l1i_size
        self._l1i_assoc = l1i_assoc
        self._l1d_size = l1d_size
        self._l1d_assoc = l1d_assoc
        
        # L2 參數 (Private Racetrack)
        self._l2_size = l2_size
        self._l2_assoc = l2_assoc
        
        # L3 參數 (Shared Racetrack)
        self._l3_size = l3_size
        self._l3_assoc = l3_assoc
        
        # 預先創建 membus
        self.membus = SystemXBar(width=64)
        self.membus.badaddr_responder = BadAddr()
        self.membus.default = self.membus.badaddr_responder.pio

    def incorporate_cache(self, board: AbstractBoard) -> None:
        """
        實作 AbstractClassicCacheHierarchy 要求的方法
        修正版本：直接使用 RacetrackCache，不依賴 has_racetrack flag
        """
        
        print("\n[INFO] Setting up Racetrack Cache Hierarchy...")
        
        # 1. 設定 cache line size
        board.cache_line_size = 64
        
        # 2. 創建 L3 bus (連接所有 L2 到 L3)
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
        print(f"  ✓ L3 Cache: RacetrackCache {self._l3_size}, {self._l3_assoc}-way")

        # 4. 連接 L3 cache
        self.l3_cache.cpu_side = self.l3bus.mem_side_ports
        self.l3_cache.mem_side = self.membus.cpu_side_ports
        
        # 5. 連接 system port 和 memory
        board.connect_system_port(self.membus.cpu_side_ports)
        for _, port in board.get_mem_ports():
            self.membus.mem_side_ports = port
        
        # 6. 連接核心 (修改迴圈內部)
        cores = board.get_processor().get_cores()
        for i, cpu_wrapper in enumerate(cores):
            # [修正關鍵] 取出底層 SimObject
            # 如果傳進來的是 Wrapper，就拆包；如果是裸機，就直接用
            cpu = cpu_wrapper.get_simobject() if hasattr(cpu_wrapper, "get_simobject") else cpu_wrapper

            # ... (建立 L2, L1, Bus 的代碼不變) ...
            
            # 直接連接 CPU Ports (現在 cpu 變數保證是 SimObject 了)
            cpu.icache_port = l1i_cache.cpu_side
            cpu.dcache_port = l1d_cache.cpu_side
            
            if hasattr(cpu, 'mmu'):
                cpu.mmu.itb.walker.port = self.membus.cpu_side_ports
                cpu.mmu.dtb.walker.port = self.membus.cpu_side_ports
            
            if board.get_processor().get_isa() == ISA.X86:
                if not hasattr(cpu, 'interrupts') or not cpu.interrupts:
                    cpu.createInterruptController()
                cpu.interrupts[0].pio = self.membus.mem_side_ports
                cpu.interrupts[0].int_requestor = self.membus.cpu_side_ports
                cpu.interrupts[0].int_responder = self.membus.mem_side_ports
            
            print(f"✓ Core {i} connected")
        
        # 7. 設定 I/O cache
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
        
        print(f"✓ Cache Hierarchy setup complete.")

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

# 1. Cache Hierarchy
cache_hierarchy = RacetrackHierarchy()

# 2. Memory
memory = SingleChannelDDR3_1600(size="2GiB")

# 3. Processor
# 3. Processor (改回官方穩定版)
processor = PaperProcessor(
    num_cores=4  # 論文規格 4 核
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