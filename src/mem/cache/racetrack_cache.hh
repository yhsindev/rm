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

#ifndef __MEM_CACHE_RACETRACK_CACHE_HH__
#define __MEM_CACHE_RACETRACK_CACHE_HH__

#include <vector>

#include "mem/cache/cache.hh"
#include "params/RacetrackCache.hh"

namespace gem5
{

class RacetrackCache : public Cache
{
  protected:
    /**
     * Number of domains in a track.
     */
    const unsigned numDomains;

    /**
     * Latency for shifting one domain.
     */
    const Tick shiftLatency;

    /**
     * Number of read/write ports per track.
     */
    const unsigned numRWPorts;

    /**
     * Current position of the head for each track.
     * The index of this vector corresponds to the track ID.
     * The value represents the current domain index under the head.
     */
    std::vector<int> headPositions;

    /**
     * Calculate the shift penalty for accessing the given packet.
     *
     * @param pkt The packet being accessed.
     * @return The latency penalty in ticks due to shifting.
     */
    Tick calculateShiftPenalty(const PacketPtr pkt);

  public:
    /**
     * Convenience typedef.
     */
    typedef RacetrackCacheParams Params;

    /**
     * Construct and initialize this cache.
     */
    RacetrackCache(const Params &p);

    /**
     * Overridden to add shift penalty.
     */
    void recvTimingReq(PacketPtr pkt) override;
};

} // namespace gem5

#endif // __MEM_CACHE_RACETRACK_CACHE_HH__
