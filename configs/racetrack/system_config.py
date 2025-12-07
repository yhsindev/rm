import m5
from m5.objects import *
import argparse

#設定參數
parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=str, required=True,
                    help='Path to the benchmark binary to run')
args, unknown = parser.parse_known_args()

# Create the system
system = System()

# Set the clock frequency
system.clk_domain = SrcClockDomain()
system.clk_domain.clock = "3GHz"
system.clk_domain.voltage_domain = VoltageDomain()

# Set up the system mode (SE mode)
system.mem_mode = "timing"
system.mem_ranges = [AddrRange("4GB")]

# --- 架構修改：建立 Shared L3 Bus ---
# 因為 L3 是 Shared 的，我們需要在 CPU 迴圈外面建立這條 Bus，
# 讓所有 CPU 的 Private L2 都能連接到這裡。
system.l3bus = L2XBar()

# Create 4 CPUs (DerivO3CPU)
system.cpu = [DerivO3CPU() for _ in range(4)]

for cpu in system.cpu:
    # --- CPU 參數 (Table 1) ---
    cpu.numROBEntries = 128
    cpu.fetchWidth = 4
    cpu.decodeWidth = 4
    cpu.issueWidth = 4
    cpu.commitWidth = 4
    
    cpu.createInterruptController()

    # --- L1 Caches (Private) ---
    cpu.icache = Cache(
        size="32kB",
        assoc=4,
        tag_latency=2,
        data_latency=2,
        response_latency=2,
        mshrs=4,
        tgts_per_mshr=20,
    )
    cpu.dcache = Cache(
        size="32kB",
        assoc=4,
        tag_latency=2,
        data_latency=2,
        response_latency=2,
        mshrs=4,
        tgts_per_mshr=20,
    )

    cpu.icache.cpu_side = cpu.icache_port
    cpu.dcache.cpu_side = cpu.dcache_port

    # --- L2 Cache (Private) ---
    # 這裡做了重大修改：
    # 1. 為每個 CPU 建立一個私有的 L2 Bus (連接 L1 I/D)
    # 2. 為每個 CPU 建立一個私有的 L2 Cache
    
    cpu.l2bus = L2XBar() # Private L2 Bus

    cpu.l2cache = RacetrackCache(
        size="256kB",
        assoc=8,
        tag_latency=10,
        data_latency=10,
        response_latency=10,
        clusivity="mostly_excl",
        num_domains=64,
        shift_latency=1,
        mshrs=20,
        tgts_per_mshr=12,
    )

    # 連接 L1 -> Private L2 Bus
    cpu.icache.mem_side = cpu.l2bus.cpu_side_ports
    cpu.dcache.mem_side = cpu.l2bus.cpu_side_ports

    # 連接 Private L2 Bus -> Private L2 Cache
    cpu.l2cache.cpu_side = cpu.l2bus.mem_side_ports

    # 連接 Private L2 Cache -> Shared L3 Bus
    # 每個核心的 L2 都連到全域的 system.l3bus
    cpu.l2cache.mem_side = system.l3bus.cpu_side_ports

# --- L3 Cache (Shared) ---
# L3 只建立一次 (在迴圈外)，作為所有核心共享
system.l3cache = RacetrackCache(
    size="16MB",
    assoc=16,
    tag_latency=24,
    data_latency=24,
    response_latency=24,
    clusivity="mostly_incl",
    num_domains=64,
    shift_latency=1,
    mshrs=20,
    tgts_per_mshr=12,
)

# Connect Shared L3 Bus -> Shared L3 Cache
system.l3cache.cpu_side = system.l3bus.mem_side_ports

# Create a memory bus
system.membus = SystemXBar()

# Connect the system up to the membus
system.system_port = system.membus.cpu_side_ports

# Connect Shared L3 Cache -> Memory Bus
system.l3cache.mem_side = system.membus.cpu_side_ports

# Connect interrupt controllers
for cpu in system.cpu:
    cpu.interrupts[0].pio = system.membus.mem_side_ports
    cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
    cpu.interrupts[0].int_responder = system.membus.mem_side_ports

# --- Memory Controller ---
system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

# Set up the process
process = Process()
process.cmd = [args.binary]

system.workload = SEWorkload.init_compatible(process.cmd[0])

# Assign workload to all CPUs
for cpu in system.cpu:
    cpu.workload = process
    cpu.createThreads()

# Instantiate the system and begin execution
root = Root(full_system=False, system=system)
m5.instantiate()

print("Beginning simulation!")
exit_event = m5.simulate()

print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")