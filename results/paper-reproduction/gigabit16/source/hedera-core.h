#ifndef HEDERA_CORE_H
#define HEDERA_CORE_H
#include <cstdint>
#include <map>
#include <random>
#include <utility>
#include <vector>

namespace hedera {
using Path = std::vector<uint32_t>;
struct Link { uint32_t from; uint32_t to; double capacity = 1.0; };
class FatTree {
public:
    explicit FatTree(uint32_t k);
    uint32_t k, half, perPod, hosts, edgeCount, cores, nodes;
    std::vector<Link> links;
    uint32_t Pod(uint32_t host) const;
    uint32_t Edge(uint32_t host) const;
    uint32_t Agg(uint32_t pod, uint32_t local) const;
    uint32_t Core(uint32_t local) const;
    uint32_t LinkId(uint32_t from, uint32_t to) const;
    bool InterPod(uint32_t src, uint32_t dst) const;
    std::vector<Path> Candidates(uint32_t src, uint32_t dst) const;
    Path ViaCore(uint32_t src, uint32_t dst, uint32_t core) const;
    std::vector<uint32_t> PathLinks(const Path& path) const;
private:
    std::map<std::pair<uint32_t, uint32_t>, uint32_t> m_linkIds;
    void Connect(uint32_t a, uint32_t b);
};
struct Endpoint { uint32_t src; uint32_t dst; };
struct DemandResult { std::vector<double> demand; uint32_t rounds = 0; };
DemandResult EstimateDemands(const std::vector<Endpoint>& flows, uint32_t hosts);
uint64_t HashWords(const std::vector<uint32_t>& words);
uint64_t AvalancheHash(uint64_t value);
struct Flow {
    uint32_t id, src, dst;
    double demand;
    Path baseline;
};
double Energy(const FatTree& tree, const std::vector<double>& loads);
std::vector<double> ComputeLoads(const FatTree& tree, const std::vector<Flow>& flows,
                                const std::map<uint32_t, Path>& paths);
class GlobalFirstFit {
public:
    explicit GlobalFirstFit(const FatTree& tree);
    std::map<uint32_t, Path> Place(const std::vector<Flow>& flows);
    const std::map<uint32_t, Path>& Reservations() const { return m_assigned; }
private:
    const FatTree& m_tree;
    std::map<uint32_t, Path> m_assigned;
};
struct AnnealResult {
    std::vector<uint32_t> mapping;
    std::map<uint32_t, Path> paths;
    double initialEnergy = 0, bestEnergy = 0;
    uint32_t accepted = 0;
};
std::vector<uint32_t> InitialMapping(const FatTree& tree);
bool ValidMapping(const FatTree& tree, const std::vector<uint32_t>& mapping);
AnnealResult Anneal(const FatTree& tree, const std::vector<Flow>& flows,
                   const std::vector<uint32_t>& previous, uint32_t iterations,
                   std::mt19937_64& rng, bool checkEnergy = false);
}
#endif
