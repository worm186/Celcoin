// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-present The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <pow.h>

#include <arith_uint256.h>
#include <chain.h>
#include <primitives/block.h>
#include <uint256.h>
#include <util/check.h>

unsigned int GetNextWorkRequired(const CBlockIndex* pindexLast, const CBlockHeader *pblock, const Consensus::Params& params)
{
    assert(pindexLast != nullptr);
    unsigned int nProofOfWorkLimit = UintToArith256(params.powLimit).GetCompact();

    // Only change once per difficulty adjustment interval
    if ((pindexLast->nHeight+1) % params.DifficultyAdjustmentInterval() != 0)
    {
        if (params.fPowAllowMinDifficultyBlocks)
        {
            // Special difficulty rule for testnet:
            // If the new block's timestamp is more than 2* 10 minutes
            // then it MUST be a min-difficulty block.
            if (pblock->GetBlockTime() > pindexLast->GetBlockTime() + params.nPowTargetSpacing*2)
                return nProofOfWorkLimit;
            else
            {
                // Return the last non-special-min-difficulty-rules-block
                const CBlockIndex* pindex = pindexLast;
                while (pindex->pprev && pindex->nHeight % params.DifficultyAdjustmentInterval() != 0 && pindex->nBits == nProofOfWorkLimit)
                    pindex = pindex->pprev;
                return pindex->nBits;
            }
        }
        return pindexLast->nBits;
    }

    // Go back by what we want to be 14 days worth of blocks
    int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
    assert(nHeightFirst >= 0);
    const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
    assert(pindexFirst);

    return CalculateNextWorkRequired(pindexLast, pindexFirst->GetBlockTime(), params);
}

unsigned int CalculateNextWorkRequired(const CBlockIndex* pindexLast, int64_t nFirstBlockTime, const Consensus::Params& params)
{
    if (params.fPowNoRetargeting)
        return pindexLast->nBits;

    // Limit adjustment step
    int64_t nActualTimespan = pindexLast->GetBlockTime() - nFirstBlockTime;
    if (nActualTimespan < params.nPowTargetTimespan/4)
        nActualTimespan = params.nPowTargetTimespan/4;
    if (nActualTimespan > params.nPowTargetTimespan*4)
        nActualTimespan = params.nPowTargetTimespan*4;

    // Retarget
    const arith_uint256 bnPowLimit = UintToArith256(params.powLimit);
    arith_uint256 bnNew;

    // Special difficulty rule for Testnet4
    if (params.enforce_BIP94) {
        // Here we use the first block of the difficulty period. This way
        // the real difficulty is always preserved in the first block as
        // it is not allowed to use the min-difficulty exception.
        int nHeightFirst = pindexLast->nHeight - (params.DifficultyAdjustmentInterval()-1);
        const CBlockIndex* pindexFirst = pindexLast->GetAncestor(nHeightFirst);
        bnNew.SetCompact(pindexFirst->nBits);
    } else {
        bnNew.SetCompact(pindexLast->nBits);
    }

    bnNew /= params.nPowTargetTimespan;
    bnNew *= nActualTimespan;

    if (bnNew > bnPowLimit)
        bnNew = bnPowLimit;

    return bnNew.GetCompact();
}

// Check that on difficulty adjustments, the new difficulty does not increase
// or decrease beyond the permitted limits.
bool PermittedDifficultyTransition(const Consensus::Params& params, int64_t height, uint32_t old_nbits, uint32_t new_nbits)
{
    if (params.fPowAllowMinDifficultyBlocks) return true;

    if (height % params.DifficultyAdjustmentInterval() == 0) {
        int64_t smallest_timespan = params.nPowTargetTimespan/4;
        int64_t largest_timespan = params.nPowTargetTimespan*4;

        const arith_uint256 pow_limit = UintToArith256(params.powLimit);
        arith_uint256 observed_new_target;
        observed_new_target.SetCompact(new_nbits);

        // Calculate the largest difficulty value possible:
        arith_uint256 largest_difficulty_target;
        largest_difficulty_target.SetCompact(old_nbits);
        largest_difficulty_target *= largest_timespan;
        largest_difficulty_target /= params.nPowTargetTimespan;

        if (largest_difficulty_target > pow_limit) {
            largest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 maximum_new_target;
        maximum_new_target.SetCompact(largest_difficulty_target.GetCompact());
        if (maximum_new_target < observed_new_target) return false;

        // Calculate the smallest difficulty value possible:
        arith_uint256 smallest_difficulty_target;
        smallest_difficulty_target.SetCompact(old_nbits);
        smallest_difficulty_target *= smallest_timespan;
        smallest_difficulty_target /= params.nPowTargetTimespan;

        if (smallest_difficulty_target > pow_limit) {
            smallest_difficulty_target = pow_limit;
        }

        // Round and then compare this new calculated value to what is
        // observed.
        arith_uint256 minimum_new_target;
        minimum_new_target.SetCompact(smallest_difficulty_target.GetCompact());
        if (minimum_new_target > observed_new_target) return false;
    } else if (old_nbits != new_nbits) {
        return false;
    }
    return true;
}

// Bypasses the actual proof of work check during fuzz testing with a simplified validation checking whether
// the most significant bit of the last byte of the hash is set.
bool CheckProofOfWork(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    if (EnableFuzzDeterminism()) return (hash.data()[31] & 0x80) == 0;
    return CheckProofOfWorkImpl(hash, nBits, params);
}

std::optional<arith_uint256> DeriveTarget(unsigned int nBits, const uint256 pow_limit)
{
    bool fNegative;
    bool fOverflow;
    arith_uint256 bnTarget;

    bnTarget.SetCompact(nBits, &fNegative, &fOverflow);

    // Check range
    if (fNegative || bnTarget == 0 || fOverflow || bnTarget > UintToArith256(pow_limit))
        return {};

    return bnTarget;
}

bool CheckProofOfWorkImpl(uint256 hash, unsigned int nBits, const Consensus::Params& params)
{
    auto bnTarget{DeriveTarget(nBits, params.powLimit)};
    if (!bnTarget) return false;

    // Check proof of work matches claimed amount
    if (UintToArith256(hash) > bnTarget)
        return false;

    return true;
}

// ===== RandomX: hash da prova de trabalho (chave muda a cada 2 dias) =====
#include <randomx.h>
#include <primitives/block.h>
#include <streams.h>
#include <uint256.h>

#include <cstdint>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

// A chave do RandomX depende da "epoca" do cabecalho: nTime / 2 dias.
constexpr uint32_t RANDOMX_EPOCH_SECONDS = 2 * 24 * 60 * 60;
constexpr size_t RANDOMX_MAX_CACHED_EPOCHS = 2;

std::mutex g_randomx_mutex;
bool g_randomx_flags_ready = false;
randomx_flags g_randomx_flags = RANDOMX_FLAG_DEFAULT;

struct RandomXCache {
    randomx_cache* cache{nullptr};

    // Chamado com g_randomx_mutex travado.
    explicit RandomXCache(uint32_t epoch)
    {
        if (!g_randomx_flags_ready) {
            g_randomx_flags = randomx_get_flags();
            cache = randomx_alloc_cache(g_randomx_flags);
            if (!cache) {
                g_randomx_flags = RANDOMX_FLAG_DEFAULT;
                cache = randomx_alloc_cache(g_randomx_flags);
            }
            g_randomx_flags_ready = true;
        } else {
            cache = randomx_alloc_cache(g_randomx_flags);
        }
        if (!cache) throw std::runtime_error("RandomX: falha ao alocar cache");
        const std::string key = "Rubiana-RandomX-v1-" + std::to_string(epoch);
        randomx_init_cache(cache, key.data(), key.size());
    }
    ~RandomXCache()
    {
        if (cache) randomx_release_cache(cache);
    }
    RandomXCache(const RandomXCache&) = delete;
    RandomXCache& operator=(const RandomXCache&) = delete;
};

// Caches das epocas recentes (a mais recente primeiro).
std::vector<std::pair<uint32_t, std::shared_ptr<RandomXCache>>> g_randomx_caches;

std::shared_ptr<RandomXCache> GetCacheForEpoch(uint32_t epoch)
{
    std::lock_guard<std::mutex> lock(g_randomx_mutex);
    for (size_t i = 0; i < g_randomx_caches.size(); ++i) {
        if (g_randomx_caches[i].first == epoch) {
            auto found = g_randomx_caches[i];
            g_randomx_caches.erase(g_randomx_caches.begin() + i);
            g_randomx_caches.insert(g_randomx_caches.begin(), found);
            return found.second;
        }
    }
    auto created = std::make_shared<RandomXCache>(epoch);
    g_randomx_caches.insert(g_randomx_caches.begin(), std::make_pair(epoch, created));
    if (g_randomx_caches.size() > RANDOMX_MAX_CACHED_EPOCHS) g_randomx_caches.pop_back();
    return created;
}

struct RandomXVmDeleter {
    void operator()(randomx_vm* vm) const
    {
        if (vm) randomx_destroy_vm(vm);
    }
};

} // namespace

uint256 GetPoWHash(const CBlockHeader& block)
{
    const uint32_t epoch = block.nTime / RANDOMX_EPOCH_SECONDS;
    thread_local std::shared_ptr<RandomXCache> current_cache;
    thread_local uint32_t current_epoch = 0;
    thread_local std::unique_ptr<randomx_vm, RandomXVmDeleter> vm;

    if (!current_cache || current_epoch != epoch) {
        std::shared_ptr<RandomXCache> cache = GetCacheForEpoch(epoch);
        if (!vm) {
            vm.reset(randomx_create_vm(g_randomx_flags, cache->cache, nullptr));
            if (!vm) throw std::runtime_error("RandomX: falha ao criar a VM");
        } else {
            randomx_vm_set_cache(vm.get(), cache->cache);
        }
        current_cache = cache;
        current_epoch = epoch;
    }

    DataStream ss{};
    ss << block;
    uint256 result;
    randomx_calculate_hash(vm.get(), reinterpret_cast<const unsigned char*>(ss.data()), ss.size(), result.begin());
    return result;
}
