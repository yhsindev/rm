# -*- coding: utf-8 -*-
# /gem5/configs/kvm.py
# KVM Fast-forward -> Checkpoint -> Switch to Detailed O3 (with SE params) -> Warmup -> Measure

import m5
from m5.objects import *
from m5.objects import IdeDisk, CowDiskImage, RawDiskImage
from m5.util import addToPath
import os
import sys
import argparse
from gem5.resources.resource import Resource


# 加入 gem5 設定檔路徑
addToPath('../')

from common import ObjectList
from common import SimpleOpts
from common import FileSystemConfig
from common.Caches import *

# 載入 RacetrackCache (從 m5.objects 匯入)
try:
    from m5.objects import RacetrackCache
    has_rm = True
except ImportError:
    print("Error: RacetrackCache not found! Please check if gem5 is compiled with RacetrackCache.")
    has_rm = False

def build_system(options):
    """建立模擬的硬體系統 (對應 Phase 1 & Phase 2 的基礎架構)"""
    
    # 1. 系統基礎設定
    system = System()
    system.mmap_using_noreserve = True
    system.mem_mode = 'atomic_noncaching' # KVM 啟動初期必須使用此模式
    #system.addr_mask = 0xffffffffff # 40-bit 定址 #old
    
    system.clk_domain = SrcClockDomain(clock='3GHz', voltage_domain=VoltageDomain())
    #--- TO-DO：預設給 3GB，如果 Disk Image 比較大，可能要改 4GB 或 8GB ---#
    system.mem_ranges = [AddrRange('3GB')] # 若跑大型 Benchmark 建議改 4GB 或 8GB

    # 2. 設定 CPU: 初始階段使用 KVM CPU (快速)
    if options.cpu_type == "kvm":
        system.cpu = [X86KvmCPU(cpu_id=i) for i in range(options.num_cpus)]
    else:
        system.cpu = [AtomicSimpleCPU(cpu_id=i) for i in range(options.num_cpus)]

    # 3. 建立記憶體匯流排
    system.membus = SystemXBar()       # System Memory Bus
    system.l3bus = L2XBar()            # Shared L3 Bus (連接所有 Private L2 到 Shared L3)

    # 4. --- [整合 SE Script] 建立 Shared L3 Cache (Racetrack Memory) ---
    # 參數來源： SE Script (tag_latency=24, num_domains=64)
    if has_rm:
        system.l3cache = RacetrackCache(
            size=options.l3_size,
            assoc=16,
            tag_latency=24,      # 論文 Table I: 24 cycles
            data_latency=24,
            response_latency=24,
            mshrs=20,
            tgts_per_mshr=12,
            num_domains=64,      # RM 參數
            shift_latency=1,     # RM 參數
            # clusivity='mostly_incl' # Gem5 預設通常是 mostly inclusive
        )
    else:
        system.l3cache = Cache(size=options.l3_size, assoc=16)

    # 5. 連接 LLC (L3)
    system.l3cache.cpu_side = system.l3bus.mem_side_ports
    system.l3cache.mem_side = system.membus.cpu_side_ports

    # 6. 為每個 CPU 建立 Private Cache Hierarchy
    for cpu in system.cpu:
        cpu.createInterruptController()
        
        # --- [整合 SE Script] 定義 Private L1/L2 ---
        
        # L1 Instruction: SRAM (標準 Cache)
        cpu.icache = Cache(
            size="32kB", 
            assoc=4,
            tag_latency=2,
            data_latency=2,
            response_latency=2
        )
        
        # L1 Data: SRAM (標準 Cache)
        cpu.dcache = Cache(
            size="32kB", 
            assoc=4,
            tag_latency=2,
            data_latency=2,
            response_latency=2
        )

        # L2 Cache: Private RacetrackCache
        # 參數來源：SE Script (tag_latency=10, num_domains=64)
        cpu.l2cache = RacetrackCache(
            size="256kB", 
            assoc=8, 
            tag_latency=10,      # 論文 Table I: 10 cycles
            data_latency=10, 
            response_latency=10,
            num_domains=64,
            shift_latency=1,
            mshrs=20,
            tgts_per_mshr=12
        )

        # --- [整合 SE Script] 建立 Private L2 Bus ---
        # 因為 L2 只有 1 個 Port (論文所述)，需要 Bus 來仲裁 L1I 和 L1D 的請求
        cpu.l2bus = L2XBar()

        # 連接埠 (Ports)
        cpu.icache.cpu_side = cpu.icache_port
        cpu.dcache.cpu_side = cpu.dcache_port
        
        # L1 -> Private L2 Bus
        cpu.icache.mem_side = cpu.l2bus.cpu_side_ports
        cpu.dcache.mem_side = cpu.l2bus.cpu_side_ports
        
        # Private L2 Bus -> L2 Cache
        cpu.l2cache.cpu_side = cpu.l2bus.mem_side_ports

        # L2 Cache -> Shared L3 Bus
        cpu.l2cache.mem_side = system.l3bus.cpu_side_ports

        # 連接中斷 (x86 必須直接連到 MemBus)
        cpu.interrupts[0].pio = system.membus.mem_side_ports
        cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
        cpu.interrupts[0].int_responder = system.membus.mem_side_ports

    # 7. 連接 System Port 與 Memory Controller
    system.system_port = system.membus.cpu_side_ports
    system.mem_ctrl = MemCtrl()
    system.mem_ctrl.dram = DDR3_1600_8x8()
    system.mem_ctrl.dram.range = system.mem_ranges[0]
    system.mem_ctrl.port = system.membus.mem_side_ports

    # 8. 設定 Full System Workload
    system.workload = X86FsLinux()
    
    # --- [修改：使用 Resource 自動下載 Kernel 與 Disk] ---
    print("正在自動檢查/下載 Kernel 與 Disk Image...")
    
    # 8.1 設定 Kernel (核心)
    # 使用 Resource() 包住 ID，Gem5 就會自動去下載
    if options.kernel:
        print(f"Using local kernel: {options.kernel}")
        system.workload.object_file = options.kernel
    else:
        print("Downloading Kernel...")
        kernel_resource = Resource("x86-linux-kernel-5.4.49")
        system.workload.object_file = kernel_resource.get_local_path()

    if options.disk_image:
        print(f"Using local disk image: {options.disk_image}")
        image_list = [options.disk_image]
    else:
        print("Downloading Disk Image...")
        disk_resource = Resource("x86-parsec") 
        image_list = [disk_resource.get_local_path()]
    # ---

    # 設定硬碟物件 
    system.pc = Pc()
    system.pc.com_1.device = Terminal()
    # 使用 RawDiskImage 取代 Image，並改參數名為 image_file
    system.pc.south_bridge.ide.disks = [IdeDisk(driveID='device0', image=RawDiskImage(image_file=img)) 
                                        for img in image_list]
    # 設定開機參數 (這行一定要加，防止 mwait 崩潰！)
    system.workload.command_line = "earlyprintk=ttyS0 console=ttyS0 lpj=7999923 root=/dev/sda2 idle=poll"

    if options.script:
        system.readfile = options.script

    return system

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", type=str, 
                        default="/home/usr/gem5_resources/vmlinux", 
                        help="Path to vmlinux")
                        
    parser.add_argument("--disk-image", type=str, 
                        default=None, 
                        help="Path to disk image")
    parser.add_argument("--script", type=str, default="", help="Path to .rcS script")
    parser.add_argument("--num-cpus", type=int, default=1)
    parser.add_argument("--l3-size", type=str, default="16MB")
    parser.add_argument("--cpu-type", type=str, default="kvm", choices=["kvm", "atomic"])
    parser.add_argument("--warmup-insts", type=int, default=10000000, 
                        help="Instructions to run for warmup")
    parser.add_argument("--checkpoint-dir", type=str, default=None)
    parser.add_argument("--checkpoint-restore", type=int, default=None)

    args = parser.parse_args()

    system = build_system(args)
    root = Root(full_system=True, system=system)
    
    # 載入 Checkpoint (如果有)
    if args.checkpoint_dir:
        m5.instantiate(args.checkpoint_dir)
    else:
        m5.instantiate()

    # --- 邏輯 A: 建立 Checkpoint 階段 (KVM Fast-forward) ---
    if not args.checkpoint_restore:
        print("*** Phase 1: Fast-forwarding with KVM ***")
        exit_event = m5.simulate()
        
        if exit_event.getCause() == "checkpoint":
            print("*** ROI reached. Creating Checkpoint... ***")
            m5.checkpoint(os.path.join(os.getcwd(), "m5out"))
            print("*** Checkpoint created. Exiting. ***")
            return
        else:
            print(f"Exited unexpectedly: {exit_event.getCause()}")
            return

    # --- 邏輯 B: 從 Checkpoint 恢復並測量 (Detail CPU) ---
    else:
        print(f"*** Phase 2: Restoring from Checkpoint {args.checkpoint_restore} ***")
        
        print("*** Switching to Detailed CPU (DerivO3CPU) for ROI ***")
        
        # 1. 建立新的 O3 CPU
        # --- [整合 SE Script] 這裡帶入你的 O3 CPU 參數 ---
        detailed_cpus = []
        for i in range(args.num_cpus):
            cpu = DerivO3CPU(cpu_id=i, switched_out=False)
            # 移植你的 Table 1 參數
            cpu.numROBEntries = 128
            cpu.fetchWidth = 4
            cpu.decodeWidth = 4
            cpu.issueWidth = 4
            cpu.commitWidth = 4
            detailed_cpus.append(cpu)
        
        # 2. 將新 CPU 接上舊的 Cache
        for i, new_cpu in enumerate(detailed_cpus):
            old_cpu = system.cpu[i]
            
            # 複製時脈與工作負載
            new_cpu.clk_domain = old_cpu.clk_domain
            new_cpu.workload = old_cpu.workload
            
            # 連接 Cache (注意：要透過 Bus 連接)
            new_cpu.icache = old_cpu.icache
            new_cpu.dcache = old_cpu.dcache
            
            # 連接到 Private L2 Bus 的 Port
            # 注意：在 build_system 裡我們建立了 l2bus，這裡要接回去
            new_cpu.icache_port = old_cpu.icache.cpu_side
            new_cpu.dcache_port = old_cpu.dcache.cpu_side
            
            # 重建中斷控制器
            new_cpu.createInterruptController()
            new_cpu.interrupts[0].pio = system.membus.mem_side_ports
            new_cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
            new_cpu.interrupts[0].int_responder = system.membus.mem_side_ports
            
            new_cpu.system = system

        # 3. 執行 CPU 切換
        m5.drain(system)
        m5.switchCpus(system, list(zip(system.cpu, detailed_cpus)))
        system.cpu = detailed_cpus
        
        # 4. 切換到 Timing Mode
        system.mem_mode = 'timing'
        
        print("*** CPU Switched. Starting Warmup Phase... ***")
        
        # 5. 預熱 (Warmup)
        m5.stats.reset()
        m5.simulate(args.warmup_insts * 1000) 
        print("*** Warmup Complete. Resetting Stats. ***")

        # 6. 正式 ROI 測量
        m5.stats.reset()
        print("*** Starting ROI Detailed Measurement ***")
        exit_event = m5.simulate()
        
        print(f"*** Simulation Finished. Exit cause: {exit_event.getCause()} ***")

# 直接執行，不要 if 了
print(">>> SCRIPT STARTING... calling run() <<<") 
run()