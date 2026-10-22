// rubiana-miner: motor de mineracao RandomX da Rubiana (PROTOTIPO).
// Conversa por linhas (stdin/stdout):
//   entrada: JOB <id> <cabecalho_76_bytes_hex> <alvo_64_hex> | STATS | QUIT
//   saida:   READY | FOUND <id> <nonce> <hash_hex> | STATS <hashes_totais> <segundos>
// opcoes: --threads N   --full (modo completo, usa ~2 GB; sem isso, modo leve)
#include <randomx.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <random>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Job {
    uint64_t id{0};
    uint8_t header[76]{};
    uint8_t target_le[32]{};
};

std::mutex g_job_mutex;
Job g_job;
std::atomic<uint64_t> g_job_gen{0};
std::atomic<bool> g_job_ready{false};
std::atomic<bool> g_quit{false};
std::atomic<uint64_t> g_hashes{0};
std::atomic<uint32_t> g_next_nonce{0};
std::atomic<uint64_t> g_found_gen{0};
std::atomic<uint64_t> g_res_version{0};
std::mutex g_out_mutex;
std::shared_mutex g_res_mutex;

randomx_flags g_flags = RANDOMX_FLAG_DEFAULT;
bool g_full = false;
int g_threads = 1;
randomx_cache* g_cache = nullptr;
randomx_dataset* g_dataset = nullptr;
bool g_res_built = false;
uint32_t g_res_epoch = 0;

int HexVal(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

bool ParseHex(const std::string& s, std::vector<uint8_t>& out)
{
    if (s.size() % 2) return false;
    out.clear();
    for (size_t i = 0; i < s.size(); i += 2) {
        const int hi = HexVal(s[i]);
        const int lo = HexVal(s[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back(static_cast<uint8_t>(hi * 16 + lo));
    }
    return true;
}

void FreeResources()
{
    if (g_dataset) {
        randomx_release_dataset(g_dataset);
        g_dataset = nullptr;
    }
    if (g_cache) {
        randomx_release_cache(g_cache);
        g_cache = nullptr;
    }
    g_res_built = false;
}

// Chamado com g_res_mutex travado (exclusivo).
bool BuildResources(uint32_t epoch)
{
    FreeResources();
    // Mesma regra de chave do no (pow.cpp).
    const std::string key = "Rubiana-RandomX-v1-" + std::to_string(epoch);
    fprintf(stderr, "[motor] preparando a chave da epoca %u (%s)...\n", epoch, g_full ? "modo completo" : "modo leve");
    g_cache = randomx_alloc_cache(g_flags);
    if (!g_cache) {
        fprintf(stderr, "erro: sem memoria para o cache\n");
        return false;
    }
    randomx_init_cache(g_cache, key.data(), key.size());
    if (g_full) {
        g_dataset = randomx_alloc_dataset(g_flags);
        if (!g_dataset) {
            fprintf(stderr, "erro: sem memoria para o conjunto de dados (2 GB)\n");
            return false;
        }
        const unsigned long items = randomx_dataset_item_count();
        std::vector<std::thread> ts;
        for (int i = 0; i < g_threads; ++i) {
            const unsigned long a = items * i / g_threads;
            const unsigned long b = items * (i + 1) / g_threads;
            ts.emplace_back([a, b] { randomx_init_dataset(g_dataset, g_cache, a, b - a); });
        }
        for (auto& t : ts) t.join();
    }
    g_res_epoch = epoch;
    g_res_built = true;
    ++g_res_version;
    fprintf(stderr, "[motor] pronto.\n");
    return true;
}

void Worker()
{
    randomx_vm* vm = nullptr;
    uint64_t vm_version = 0;
    uint64_t my_gen = 0;
    while (!g_quit.load()) {
        const uint64_t gen = g_job_gen.load();
        if (!g_job_ready.load() || gen == my_gen) {
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            continue;
        }
        my_gen = gen;
        Job job;
        {
            std::lock_guard<std::mutex> lock(g_job_mutex);
            job = g_job;
        }
        std::shared_lock<std::shared_mutex> res_lock(g_res_mutex);
        if (!g_res_built) continue;
        const uint64_t version = g_res_version.load();
        if (vm == nullptr || vm_version != version) {
            if (vm) {
                randomx_destroy_vm(vm);
                vm = nullptr;
            }
            if (g_full) {
                vm = randomx_create_vm(static_cast<randomx_flags>(g_flags | RANDOMX_FLAG_FULL_MEM), nullptr, g_dataset);
            } else {
                vm = randomx_create_vm(g_flags, g_cache, nullptr);
            }
            if (!vm) {
                fprintf(stderr, "erro: falha ao criar a VM\n");
                g_quit = true;
                break;
            }
            vm_version = version;
        }
        uint8_t buf[80];
        memcpy(buf, job.header, 76);
        while (!g_quit.load() && g_job_gen.load() == gen) {
            const uint32_t nonce = g_next_nonce.fetch_add(1);
            buf[76] = nonce & 0xff;
            buf[77] = (nonce >> 8) & 0xff;
            buf[78] = (nonce >> 16) & 0xff;
            buf[79] = (nonce >> 24) & 0xff;
            uint8_t hash[32];
            randomx_calculate_hash(vm, buf, sizeof(buf), hash);
            g_hashes.fetch_add(1, std::memory_order_relaxed);
            bool ok = true;
            for (int b = 31; b >= 0; --b) {
                if (hash[b] < job.target_le[b]) break;
                if (hash[b] > job.target_le[b]) {
                    ok = false;
                    break;
                }
            }
            if (ok && g_found_gen.exchange(gen) != gen) {
                std::lock_guard<std::mutex> out_lock(g_out_mutex);
                printf("FOUND %llu %u ", static_cast<unsigned long long>(job.id), nonce);
                for (int b = 0; b < 32; ++b) printf("%02x", hash[b]);
                printf("\n");
                fflush(stdout);
            }
        }
    }
    if (vm) randomx_destroy_vm(vm);
}

} // namespace

int main(int argc, char** argv)
{
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--full") {
            g_full = true;
        } else if (a == "--threads" && i + 1 < argc) {
            g_threads = std::max(1, atoi(argv[++i]));
        } else {
            fprintf(stderr, "uso: rubiana-miner [--threads N] [--full]\n");
            return 2;
        }
    }
    g_flags = randomx_get_flags();
    {
        // Se o JIT nao funcionar nesta maquina, cai para o modo sem JIT.
        randomx_cache* c = randomx_alloc_cache(g_flags);
        if (!c) {
            g_flags = RANDOMX_FLAG_DEFAULT;
        } else {
            randomx_release_cache(c);
        }
    }

    std::vector<std::thread> workers;
    for (int i = 0; i < g_threads; ++i) workers.emplace_back(Worker);
    const auto t0 = std::chrono::steady_clock::now();
    {
        std::lock_guard<std::mutex> out_lock(g_out_mutex);
        printf("READY\n");
        fflush(stdout);
    }

    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string cmd;
        in >> cmd;
        if (cmd == "JOB") {
            unsigned long long id = 0;
            std::string hh, tt;
            in >> id >> hh >> tt;
            std::vector<uint8_t> h, t;
            if (!ParseHex(hh, h) || h.size() != 76 || !ParseHex(tt, t) || t.size() != 32) {
                fprintf(stderr, "erro: JOB invalido\n");
                continue;
            }
            const uint32_t ntime = static_cast<uint32_t>(h[68]) | (static_cast<uint32_t>(h[69]) << 8) |
                                   (static_cast<uint32_t>(h[70]) << 16) | (static_cast<uint32_t>(h[71]) << 24);
            const uint32_t epoch = ntime / (2 * 24 * 60 * 60);
            g_job_ready = false;
            ++g_job_gen;
            {
                std::unique_lock<std::shared_mutex> res_lock(g_res_mutex);
                if (!g_res_built || epoch != g_res_epoch) {
                    if (!BuildResources(epoch)) {
                        g_quit = true;
                        break;
                    }
                }
            }
            Job j;
            j.id = id;
            memcpy(j.header, h.data(), 76);
            for (int i = 0; i < 32; ++i) j.target_le[i] = t[31 - i];
            {
                std::lock_guard<std::mutex> lock(g_job_mutex);
                g_job = j;
            }
            std::random_device rd;
            g_next_nonce = rd();
            g_job_ready = true;
            ++g_job_gen;
        } else if (cmd == "STATS") {
            const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            std::lock_guard<std::mutex> out_lock(g_out_mutex);
            printf("STATS %llu %.1f\n", static_cast<unsigned long long>(g_hashes.load()), secs);
            fflush(stdout);
        } else if (cmd == "QUIT") {
            break;
        }
    }
    g_quit = true;
    for (auto& w : workers) w.join();
    FreeResources();
    return 0;
}
