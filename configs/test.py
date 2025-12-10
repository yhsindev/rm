#!/usr/bin/env python3
"""
Racetrack Memory Full System Simulation with KVM

基於 gem5 標準庫的 Full System 模擬
- Phase 1: 使用 KVM 快速啟動到 ROI
- Phase 2: 切換到 O3 CPU 進行詳細測量
- 使用自定義的 RacetrackCache 替代標準 cache
"""

# -*- coding: utf-8 -*-
# configs/kvm_stdlib.py
# 使用 Gem5 Standard Library 實現 KVM Fast-forward -> Racetrack Memory Simulation

import m5
from m5.objects import *
from gem5.utils.requires import requires
from gem5.components.boards.x86_board import X86Board
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.simple_switchable_processor import SimpleSwitchableProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.coherence_protocol import CoherenceProtocol
from gem5.simulate.simulator import Simulator
from gem5.simulate.exit_event import ExitEvent
from gem5.components.cachehierarchies.classic.abstract_classic_cache_hierarchy import AbstractClassicCacheHierarchy
from gem5.resources.resource import (
    CustomResource,
    KernelResource,
    DiskImageResource,
)

import os
import argparse

# 檢查編譯選項
requires(
    isa_required=ISA.X86,
    coherence_protocol_required=CoherenceProtocol.MESI_TWO_LEVEL,
    kvm_required=True,
)

# ============================================================================
# 自定義 Cache Hierarchy with RacetrackCache
# ============================================================================
from gem5.components.cachehierarchies.classic.private_l1_private_l2_cache_hierarchy import (
    PrivateL1PrivateL2CacheHierarchy,
)
from gem5.components.cachehierarchies.classic.caches.l2cache import L2Cache

class RacetrackL2Cache(L2Cache):
    """
    自定義的 L2 Cache，使用 RacetrackCache 替代標準 Cache
    
    配置參數來自論文 Table I:
    - Size: 256KB
    - Associativity: 8-way
    - Tag Latency: 10 cycles
    - Num Domains: 64 (Racetrack 特有參數)
    - Shift Latency: 1 cycle (Racetrack 特有參數)
    """
    
    def __init__(self, size: str = "256KiB"):
        super().__init__(size=size)
        
        # 將標準 Cache 替換為 RacetrackCache
        self.cache = RacetrackCache(
            size=size,
            assoc=8,
            tag_latency=10,        # 論文 Table I: 10 cycles
            data_latency=10,
            response_latency=10,
            num_domains=64,        # Racetrack Memory 參數
            shift_latency=1,       # Racetrack Memory 參數
            mshrs=20,
            tgts_per_mshr=12,
        )


class RacetrackCacheHierarchy(PrivateL1PrivateL2CacheHierarchy):
    """
    自定義的 Cache Hierarchy，使用 RacetrackCache 作為 L2
    
    配置：
    - L1 I/D: 32KB, SRAM (標準 Cache)
    - L2: 256KB, RacetrackCache (Private, 來自論文 Table I)
    
    注意：gem5 stdlib 的 PrivateL1PrivateL2CacheHierarchy 不支援 L3，
    如需 L3 需要使用其他 hierarchy 或自行實作完整的 AbstractClassicCacheHierarchy
    """
    
    def __init__(self):
        super().__init__(
            l1d_size="32KiB",
            l1i_size="32KiB", 
            l2_size="256KiB",
        )
    
    def incorporate_cache(self, board):
        """
        Override incorporate_cache 來使用 RacetrackL2Cache
        
        這個方法會被 gem5 stdlib 自動呼叫來建立 cache hierarchy
        """
        # 呼叫父類方法建立基本結構
        super().incorporate_cache(board)
        
        # 將所有 L2 cache 替換為 RacetrackL2Cache
        for i, cpu in enumerate(board.get_processor().get_cores()):
            # 找到已經建立的 L2 cache node
            l2_node_name = f"l2-cache-{i}"
            if hasattr(self, l2_node_name):
                # 取得原本的 L2 cache node
                old_l2 = getattr(self, l2_node_name)
                
                # 建立新的 RacetrackL2Cache
                new_l2 = RacetrackL2Cache(size=self._l2_size)
                
                # 替換 cache object（保留 node 結構）
                old_l2.cache = new_l2.cache
                
                print(f"[INFO] Core {i}: L2 cache replaced with RacetrackCache")
                print(f"       Size: {self._l2_size}, Tag Latency: 10 cycles, Num Domains: 64")

# ============================================================================
# 系統配置
# ============================================================================

# Cache Hierarchy
cache_hierarchy = RacetrackCacheHierarchy()

# Memory
memory = SingleChannelDDR3_1600(size="3GiB")

# Processor: KVM -> O3 switchable
processor = SimpleSwitchableProcessor(
    starting_core_type=CPUTypes.KVM,      # Phase 1: KVM 快速啟動
    switch_core_type=CPUTypes.O3,         # Phase 2: O3 詳細測量
    isa=ISA.X86,
    num_cores=1,
)

# Board
board = X86Board(
    clk_freq="3GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=cache_hierarchy,
)

# ============================================================================
# 設定 Workload（使用您的 kernel 和 disk image）
# ============================================================================

# 使用本地的 kernel 和 disk image
kernel = KernelResource("/home/usr/rm/gem5_resources/vmlinux")
disk = DiskImageResource("/home/usr/rm/gem5_resources/parsec.img")

board.set_kernel_disk_workload(
    kernel=kernel,
    disk_image=disk,
    readfile_contents="",  # 可以放入要執行的腳本內容
    kernel_args=[
        "earlyprintk=ttyS0",
        "console=ttyS0",
        "lpj=7999923",
        "root=/dev/hda1",      # IDE disk detected as hda, not sda
        "idle=poll",
    ]
)

# ============================================================================
# Exit Event Handler（控制模擬流程）
# ============================================================================

def exit_event_handler():
    """
    處理模擬中的 exit 事件
    
    Exit 1: Linux kernel 啟動完成
    Exit 2: 用戶腳本開始執行（這裡切換到 O3 CPU）
    Exit 3: 模擬完成
    """
    print("=" * 60)
    print("Exit Event 1: Kernel booted successfully")
    print("=" * 60)
    yield False  # 繼續模擬
    
    print("=" * 60)
    print("Exit Event 2: Reached ROI - Switching to O3 CPU")
    print("=" * 60)
    
    # 切換到 O3 CPU 進行詳細測量
    processor.switch()
    
    # 重置統計（開始測量 ROI）
    from m5 import stats
    stats.reset()
    
    print("Now running detailed simulation with O3 CPU...")
    yield False  # 繼續模擬
    
    print("=" * 60)
    print("Exit Event 3: Simulation complete")
    print("=" * 60)
    yield True  # 結束模擬

# ============================================================================
# 執行模擬
# ============================================================================

simulator = Simulator(
    board=board,
    on_exit_event={
        ExitEvent.EXIT: exit_event_handler()
    },
)

print("\n" + "=" * 60)
print("Starting Racetrack Memory Full System Simulation")
print("=" * 60)
print(f"Phase 1: KVM fast-forward")
print(f"Phase 2: O3 detailed simulation")
print(f"Kernel: {kernel.get_local_path()}")
print(f"Disk: {disk.get_local_path()}")
print("=" * 60 + "\n")

simulator.run()

print("\n" + "=" * 60)
print("Simulation finished!")
print("Check m5out/stats.txt for results")
print("=" * 60)

class SwitchProcessor(AbstractProcessor):
    """
    客製化處理器：支援 KVM (開機) -> O3 (測量) 切換
    O3 CPU 參數完全依照論文 Table I 規格設定
    """
    
    def __init__(self, num_cores=4):
        self._num_cores = num_cores
        
        # 1. 建立 KVM Cores (用於快速開機)
        # 使用 BaseCPUCore 包裝 SimObject (為了符合 AbstractProcessor 規範)
        self._kvm_cores = [
            BaseCPUCore(X86KvmCPU(cpu_id=i), ISA.X86)
            for i in range(num_cores)
        ]
        
        # 2. 建立 O3 Cores (用於詳細模擬，符合論文規格)
        self._o3_cores = self._create_o3_cores(num_cores)
        
        # 3. 初始化父類別
        super().__init__(cores=self._kvm_cores)
        
        self._switched = False

    # ---------------------------------------------------------
    # [修正 1] 只需定義，不需手動初始化
    # ---------------------------------------------------------
    def incorporate_processor(self, board):
        """
        將處理器連接到主機板。
        Gem5 v25 會自動處理 createThreads，這裡我們不需要做額外動作。
        只要這個方法存在，就不會報 NotImplementedError。
        """
        pass

    # ---------------------------------------------------------
    # [修正 2] 關鍵！回傳底層物件，讓 Cache 腳本可以連線
    # ---------------------------------------------------------
    def get_cores(self):
        """
        覆寫父類別方法。
        回傳目前的 'SimObject' (X86KvmCPU 或 O3CPU)，而不是 'BaseCPUCore'。
        這樣 incorporate_cache 裡的 cpu.connect_icache() 才能正常運作。
        """
        if self._switched:
            return [core.get_simobject() for core in self._o3_cores]
        else:
            return [core.get_simobject() for core in self._kvm_cores]

    def _create_o3_cores(self, num_cores):
        """建立符合論文規格的 O3 Cores"""
        from m5.objects import TournamentBP, SimpleBTB 

        cores = []
        for i in range(num_cores):
            core = O3CPU(cpu_id=i)
            
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
            
            # Branch Predictor
            core.branchPred = TournamentBP()
            core.branchPred.btb = SimpleBTB(numEntries=4096)
            
            # 包裝
            cores.append(BaseCPUCore(core, ISA.X86))
            
        return cores

    def switch(self):
        """執行 CPU 切換邏輯 (KVM -> O3)"""
        if self._switched:
            print("Warning: Already switched to O3!")
            return
        
        print("Switching from KVM to O3 CPU (Paper Spec)...")
        
        # 取出底層 SimObject 進行切換
        kvm_simobjects = [c.get_simobject() for c in self._kvm_cores]
        o3_simobjects = [c.get_simobject() for c in self._o3_cores]
        
        # 執行切換
        m5.switchCpus(self, list(zip(kvm_simobjects, o3_simobjects)))
        
        self._switched = True
        print("✓ Switched to O3 CPU successfully!")


def o3_paper(processor):
    """
    將 SimpleSwitchableProcessor 內部的 O3 CPU 
    修改為符合論文 Table I 的規格
    """
    print("Injecting Paper Specifications into O3 CPUs...")
    
    # 遍歷處理器中所有的 O3 Cores
    # (SimpleSwitchableProcessor 把切換目標存在 _switch_cores 列表裡)
    for core_wrapper in processor._switch_cores:
        # 取出底層的 O3CPU SimObject
        core = core_wrapper.get_simobject()
        
        # --- 套用論文規格 (Table I) ---
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
        
        # Branch Predictor
        core.branchPred = TournamentBP()
        core.branchPred.btb = SimpleBTB(numEntries=4096)
        # core.branchPred.RASSize = 16 (Gem5 預設值即為 16)
        
    print("✓ O3 CPUs configured successfully!")