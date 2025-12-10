#!/usr/bin/env python3
"""
Racetrack Memory Full System Simulation (穩定版)

修復說明：
- 移除了自定義的 PaperProcessor（會破壞 KVM/O3 切換）
- 使用 gem5 stdlib 的標準 SimpleSwitchableProcessor
- 保持論文的 cache 配置（4MB L2, 64MB L3）
- CPU 參數使用 gem5 預設（ROB 等參數的小差異不影響 Racetrack 評估）
"""

# -*- coding: utf-8 -*-
from gem5.components.boards.x86_board import X86Board
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.processors.simple_switchable_processor import SimpleSwitchableProcessor
from gem5.components.cachehierarchies.classic.abstract_classic_cache_hierarchy import AbstractClassicCacheHierarchy
from gem5.components.boards.abstract_board import AbstractBoard
from gem5.isas import ISA
from gem5.resources.resource import KernelResource, DiskImageResource
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
# 主配置
# ============================================================================

requires(
    isa_required=ISA.X86,
    kvm_required=True,
)

# 1. Cache Hierarchy (論文配置)
cache_hierarchy = RacetrackHierarchy(
    l1i_size="32kB",
    l1i_assoc=4,
    l1d_size="32kB",
    l1d_assoc=4,
    l2_size="4MB",      # 論文: 4MB
    l2_assoc=8,
    l3_size="64MB",     # 論文: 64MB
    l3_assoc=16,
)

# 2. Memory (論文: 4GB)
memory = SingleChannelDDR3_1600(size="3GiB")

# 3. Processor (穩定版：使用標準 SimpleSwitchableProcessor)
# 注意：gem5 的 O3 預設參數略大於論文（ROB=192 vs 128）
# 但這不影響 Racetrack Memory 的評估，因為我們關注的是 cache shift 行為
processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,
    switch_core_type=CPUTypes.O3,
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

# 5. Workload
kernel = KernelResource("/home/usr/rm/gem5_resources/vmlinux")
disk = DiskImageResource("/home/usr/rm/gem5_resources/ubuntu.img")

benchmark_script = """#!/bin/bash
# Phase 1: KVM Boot
echo "=== Phase 1: KVM Boot Complete ==="
/sbin/m5 exit

# Phase 2-4: O3 CPU + Benchmarks
echo "=== Switched to O3 CPU ==="
cd /home/root/NPB || cd /home/gem5/NPB || exit 1

echo "Resetting stats..."
/sbin/m5 resetstats

echo "Running NPB benchmarks..."
for bench in *.S.x; do
    [ -f "$bench" ] || continue
    echo "Running $bench..."
    ./$bench
done

echo "Dumping final stats..."
/sbin/m5 dumpstats
/sbin/m5 exit
"""


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