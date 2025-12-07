from m5.params import *
from m5.objects.Cache import Cache

class RacetrackCache(Cache):
    type = 'RacetrackCache'
    cxx_header = "mem/cache/racetrack_cache.hh"
    cxx_class = 'gem5::RacetrackCache'

    num_domains = Param.Unsigned(64, "Number of domains in a track")
    shift_latency = Param.Cycles(1, "Latency for shifting one domain")
    num_rw_ports = Param.Unsigned(1, "Number of read/write ports per track")
