/*
 * Copyright (c) 2023 The Regents of the University of California
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include "mem/cache/racetrack_cache.hh"

#include <cmath>

#include "base/trace.hh"
#include "debug/Cache.hh"
#include "mem/cache/tags/base.hh"

namespace gem5
{

RacetrackCache::RacetrackCache(const Params &p)
    : Cache(p),
      numDomains(p.num_domains),
      shiftLatency(p.shift_latency),
      numRWPorts(p.num_rw_ports)
{
    // Initialize head positions for each set (track)
    // We assume each set corresponds to a track.
    // The number of sets is available via tags->getNumSets() but tags might not be fully initialized here?
    // Actually, BaseTags is initialized in BaseCache constructor which runs before this body.
    // However, getNumSets() is not a standard method in BaseTags, we might need to rely on params or cast.
    // Let's check how to get numSets.
    // BaseTags has 'size', 'blkSize', 'assoc'. numSets = size / (blkSize * assoc).
    // But BaseTags doesn't expose numSets directly in base class usually.
    // Let's look at BaseSetAssoc.
    
    // For now, we will defer the resizing to the first access or use a safe way if possible.
    // Or better, we can calculate it from params:
    // numSets = size / (block_size * associativity)
    
    unsigned numSets = p.size / (p.system->cacheLineSize() * p.assoc);
    headPositions.resize(numSets, 0);
    
    DPRINTF(Cache, "RacetrackCache initialized with %d domains, %d sets\n", numDomains, numSets);
}

Tick
RacetrackCache::calculateShiftPenalty(const PacketPtr pkt)
{
    Addr addr = pkt->getAddr();
    
    // 1. Offset bits = log2(BlockSize)
    unsigned offset_bits = (unsigned)std::log2(pkt->getSize()); 
    // Note: pkt->getSize() might be request size, not block size. 
    // Better use system->cacheLineSize() or blkSize from BaseCache.
    offset_bits = (unsigned)std::log2(blkSize);

    // 2. Domain bits = log2(numDomains)
    unsigned domain_bits = (unsigned)std::log2(numDomains);

    // 3. Calculate Target Domain
    // Extract bits [offset_bits + domain_bits - 1 : offset_bits]
    int targetDomain = (addr >> offset_bits) & ((1 << domain_bits) - 1);

    // 4. Identify Wire ID (Set Index)
    // We can use the tags object to get the set index if available, 
    // or calculate it manually if we assume standard indexing.
    // Using tags->extractTag is for tags. We need set index.
    // Let's use the standard way gem5 does it: indexingPolicy.
    // But accessing indexingPolicy from here is hard without casting tags.
    // Let's use the manual calculation as per the plan, assuming simple addressing.
    // The plan says: int wireID = (addr >> (offset_bits + domain_bits)) % numSets;
    // This assumes the set index bits are immediately after domain bits.
    // This is a specific mapping (Vertical Scheme).
    
    unsigned numSets = headPositions.size();
    int wireID = (addr >> (offset_bits + domain_bits)) % numSets;

    // 5. Read Current Head Position
    int currentHead = headPositions[wireID];

    // 6. Calculate Distance and Penalty
    int distance = std::abs(targetDomain - currentHead);
    Tick penalty = distance * shiftLatency;

    // 7. LAZY Update: Move head to target domain
    headPositions[wireID] = targetDomain;

    DPRINTF(Cache, "Racetrack Access: Addr=%#x, Wire=%d, CurHead=%d, TgtHead=%d, Dist=%d, Penalty=%d\n",
            addr, wireID, currentHead, targetDomain, distance, penalty);

    return penalty;
}

void
RacetrackCache::recvTimingReq(PacketPtr pkt)
{
    // Calculate shift penalty
    Tick penalty = calculateShiftPenalty(pkt);

    // Add penalty to the packet's header delay
    // This simulates the time spent shifting the head before the access can begin.
    pkt->headerDelay += penalty;

    // Call the base class implementation to proceed with normal cache access
    Cache::recvTimingReq(pkt);
}

} // namespace gem5
