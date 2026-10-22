// Procura um nonce valido com RandomX (modo leve, 1 thread). PROTOTIPO.
// uso: rubiana-search <cabecalho_76_bytes_hex> <alvo_64_hex> <nonce_inicial> <quantidade>
// saida: "FOUND <nonce> <hash_hex>" ou "NONE"
#include <randomx.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static int HexVal(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static bool ParseHex(const std::string& s, std::vector<uint8_t>& out)
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

int main(int argc, char** argv)
{
    if (argc != 5) {
        fprintf(stderr, "uso: rubiana-search <cabecalho_76_bytes_hex> <alvo_64_hex> <nonce_inicial> <quantidade>\n");
        return 2;
    }
    std::vector<uint8_t> header, target_be;
    if (!ParseHex(argv[1], header) || header.size() != 76 || !ParseHex(argv[2], target_be) || target_be.size() != 32) {
        fprintf(stderr, "erro: cabecalho ou alvo invalido\n");
        return 2;
    }
    const uint32_t start = static_cast<uint32_t>(strtoul(argv[3], nullptr, 10));
    const uint64_t count = strtoull(argv[4], nullptr, 10);

    // nTime fica nos bytes 68 a 71 (versao 4 + anterior 32 + merkle 32).
    const uint32_t ntime = static_cast<uint32_t>(header[68]) | (static_cast<uint32_t>(header[69]) << 8) |
                           (static_cast<uint32_t>(header[70]) << 16) | (static_cast<uint32_t>(header[71]) << 24);
    // Mesma regra de chave do no (pow.cpp): epoca de 2 dias.
    const uint32_t epoch = ntime / (2 * 24 * 60 * 60);
    const std::string key = "Rubiana-RandomX-v1-" + std::to_string(epoch);

    randomx_flags flags = randomx_get_flags();
    randomx_cache* cache = randomx_alloc_cache(flags);
    if (!cache) {
        flags = RANDOMX_FLAG_DEFAULT;
        cache = randomx_alloc_cache(flags);
    }
    if (!cache) {
        fprintf(stderr, "erro: sem memoria para o cache\n");
        return 1;
    }
    randomx_init_cache(cache, key.data(), key.size());
    randomx_vm* vm = randomx_create_vm(flags, cache, nullptr);
    if (!vm) {
        fprintf(stderr, "erro: falha ao criar a VM\n");
        randomx_release_cache(cache);
        return 1;
    }

    uint8_t target_le[32];
    for (int i = 0; i < 32; ++i) target_le[i] = target_be[31 - i];
    uint8_t buf[80];
    memcpy(buf, header.data(), 76);

    for (uint64_t i = 0; i < count; ++i) {
        const uint32_t nonce = start + static_cast<uint32_t>(i);
        buf[76] = nonce & 0xff;
        buf[77] = (nonce >> 8) & 0xff;
        buf[78] = (nonce >> 16) & 0xff;
        buf[79] = (nonce >> 24) & 0xff;
        uint8_t hash[32];
        randomx_calculate_hash(vm, buf, sizeof(buf), hash);
        // O hash vale como numero de 256 bits "little-endian": compara do byte 31 ao 0.
        bool ok = true;
        for (int b = 31; b >= 0; --b) {
            if (hash[b] < target_le[b]) break;
            if (hash[b] > target_le[b]) {
                ok = false;
                break;
            }
        }
        if (ok) {
            printf("FOUND %u ", nonce);
            for (int b = 0; b < 32; ++b) printf("%02x", hash[b]);
            printf("\n");
            randomx_destroy_vm(vm);
            randomx_release_cache(cache);
            return 0;
        }
    }
    printf("NONE\n");
    randomx_destroy_vm(vm);
    randomx_release_cache(cache);
    return 0;
}
