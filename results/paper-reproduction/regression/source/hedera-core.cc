#include "hedera-core.h"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <set>
#include <stdexcept>

namespace hedera {
FatTree::FatTree(uint32_t radix)
    : k(radix), half(k / 2), perPod(half * half), hosts(k * perPod),
      edgeCount(k * half), cores(perPod), nodes(hosts + 2 * edgeCount + cores) {
    if (k < 4 || k > 32 || k % 2) throw std::invalid_argument("k must be even, 4..32");
    for (uint32_t h = 0; h < hosts; ++h) Connect(h, Edge(h));
    for (uint32_t pod = 0; pod < k; ++pod)
        for (uint32_t e = 0; e < half; ++e)
            for (uint32_t a = 0; a < half; ++a) Connect(hosts + pod * half + e, Agg(pod,a));
    for (uint32_t pod = 0; pod < k; ++pod)
        for (uint32_t a = 0; a < half; ++a)
            for (uint32_t c = 0; c < half; ++c) Connect(Agg(pod,a), Core(a * half + c));
}
void FatTree::Connect(uint32_t a, uint32_t b) {
    m_linkIds[{a,b}] = links.size(); links.push_back({a,b,1});
    m_linkIds[{b,a}] = links.size(); links.push_back({b,a,1});
}
uint32_t FatTree::Pod(uint32_t h) const { return h / perPod; }
uint32_t FatTree::Edge(uint32_t h) const { return hosts + Pod(h) * half + (h % perPod) / half; }
uint32_t FatTree::Agg(uint32_t p, uint32_t a) const { return hosts + edgeCount + p * half + a; }
uint32_t FatTree::Core(uint32_t c) const { return hosts + 2 * edgeCount + c; }
uint32_t FatTree::LinkId(uint32_t a, uint32_t b) const { return m_linkIds.at({a,b}); }
bool FatTree::InterPod(uint32_t s, uint32_t d) const { return Pod(s) != Pod(d); }
Path FatTree::ViaCore(uint32_t s, uint32_t d, uint32_t c) const {
    if (s >= hosts || d >= hosts || s == d || c >= cores)
        throw std::invalid_argument("invalid path endpoints/core");
    if (!InterPod(s,d)) return Candidates(s,d).at(c % (Edge(s)==Edge(d) ? 1 : half));
    return {s,Edge(s),Agg(Pod(s),c/half),Core(c),Agg(Pod(d),c/half),Edge(d),d};
}
std::vector<Path> FatTree::Candidates(uint32_t s, uint32_t d) const {
    if (s >= hosts || d >= hosts || s == d) throw std::invalid_argument("invalid endpoints");
    if (Edge(s) == Edge(d)) return {{s,Edge(s),d}};
    std::vector<Path> paths;
    if (Pod(s) == Pod(d)) {
        for (uint32_t a=0;a<half;++a) paths.push_back({s,Edge(s),Agg(Pod(s),a),Edge(d),d});
    } else {
        for (uint32_t c=0;c<cores;++c) paths.push_back(ViaCore(s,d,c));
    }
    return paths;
}
std::vector<uint32_t> FatTree::PathLinks(const Path& p) const {
    std::vector<uint32_t> ids;
    for (size_t i=1;i<p.size();++i) ids.push_back(LinkId(p[i-1],p[i]));
    return ids;
}
bool FatTree::Available(const Path& path) const {
    for (size_t i=1;i<path.size();++i)
        if (links[LinkId(path[i-1],path[i])].capacity<=0) return false;
    return true;
}
uint64_t HashWords(const std::vector<uint32_t>& words) {
    uint64_t value = 14695981039346656037ULL;
    for (auto w:words) for (unsigned shift=0;shift<32;shift+=8) {
        value ^= (w>>shift)&255; value *= 1099511628211ULL;
    }
    return value;
}
uint64_t AvalancheHash(uint64_t value) {
    value ^= value >> 30; value *= 0xbf58476d1ce4e5b9ULL;
    value ^= value >> 27; value *= 0x94d049bb133111ebULL;
    return value ^ (value >> 31);
}
DemandResult EstimateDemands(const std::vector<Endpoint>& f, uint32_t hosts) {
    DemandResult result; result.demand.assign(f.size(),0);
    std::vector<bool> frozen(f.size(),false);
    std::vector<std::vector<size_t>> outgoing(hosts),incoming(hosts);
    for (size_t n=0;n<f.size();++n) {
        if (f[n].src>=hosts || f[n].dst>=hosts) throw std::invalid_argument("unknown host");
        outgoing[f[n].src].push_back(n); incoming[f[n].dst].push_back(n);
    }
    if (f.empty()) return result;
    constexpr double eps=1e-12;
    for (size_t round=0;round<2*f.size()+10;++round) {
        auto old=result.demand;
        for (const auto& ids:outgoing) {
            double fixed=0; size_t remaining=0;
            for (auto id:ids) { if (frozen[id]) fixed+=result.demand[id]; else ++remaining; }
            if (remaining) for (auto id:ids) if (!frozen[id])
                result.demand[id]=std::max(0.0,1-fixed)/remaining;
        }
        for (auto remaining:incoming) {
            double total=0; for (auto id:remaining) total+=result.demand[id];
            if (total<=1+eps) continue;
            double fixed=0,share=0;
            while (!remaining.empty()) {
                share=(1-fixed)/remaining.size();
                std::vector<size_t> next;
                for (auto id:remaining) {
                    if (result.demand[id]<share-eps) fixed+=result.demand[id];
                    else next.push_back(id);
                }
                if (next.size()==remaining.size()) break;
                remaining=std::move(next);
            }
            for (auto id:remaining) { result.demand[id]=share; frozen[id]=true; }
        }
        ++result.rounds;
        double change=0;
        for (size_t n=0;n<f.size();++n) change=std::max(change,std::abs(old[n]-result.demand[n]));
        if (change<eps) return result;
    }
    throw std::runtime_error("demand estimator did not converge");
}
double Energy(const FatTree& tree,const std::vector<double>& load) {
    double energy=0;
    for (size_t l=0;l<load.size();++l) energy+=std::max(0.0,load[l]-tree.links[l].capacity);
    return energy;
}
std::vector<double> ComputeLoads(const FatTree& tree,const std::vector<Flow>& flows,
                               const std::map<uint32_t,Path>& paths) {
    std::vector<double> load(tree.links.size(),0);
    for (const auto& f:flows) for (auto l:tree.PathLinks(paths.at(f.id))) load[l]+=f.demand;
    return load;
}
GlobalFirstFit::GlobalFirstFit(const FatTree& tree):m_tree(tree) {}
std::map<uint32_t,Path> GlobalFirstFit::Place(const std::vector<Flow>& flows) {
    std::set<uint32_t> active; for (const auto& f:flows) active.insert(f.id);
    for (auto it=m_assigned.begin();it!=m_assigned.end();) {
        if (!active.count(it->first) || !m_tree.Available(it->second)) it=m_assigned.erase(it); else ++it;
    }
    std::vector<double> load(m_tree.links.size(),0);
    for (const auto& f:flows) if (m_assigned.count(f.id))
        for (auto l:m_tree.PathLinks(m_assigned.at(f.id))) load[l]+=f.demand;
    std::map<uint32_t,Path> result;
    for (const auto& f:flows) {
        if (m_assigned.count(f.id)) { result[f.id]=m_assigned.at(f.id); continue; }
        bool placed=false;
        for (const auto& p:m_tree.Candidates(f.src,f.dst)) {
            bool fits=true;
            // Inclusive capacity with numerical tolerance: permits a single
            // full-NIC demand on a free path (explicit boundary variant of Fig.5).
            for (auto l:m_tree.PathLinks(p)) {
                double capacity=m_tree.links[l].capacity;
                if (capacity<=0 || load[l]+f.demand>capacity+1e-12) { fits=false; break; }
            }
            if (!fits) continue;
            for (auto l:m_tree.PathLinks(p)) load[l]+=f.demand;
            result[f.id]=m_assigned[f.id]=p; placed=true; break;
        }
        if (!placed) result[f.id]=f.baseline;
    }
    return result;
}
std::vector<uint32_t> InitialMapping(const FatTree& t) {
    std::vector<uint32_t> mapping(t.hosts);
    for (uint32_t h=0;h<t.hosts;++h) mapping[h]=h%t.perPod;
    return mapping;
}
bool ValidMapping(const FatTree& t,const std::vector<uint32_t>& mapping) {
    if (mapping.size()!=t.hosts) return false;
    for (uint32_t pod=0;pod<t.k;++pod) {
        std::set<uint32_t> values;
        for (uint32_t n=0;n<t.perPod;++n) {
            auto core=mapping[pod*t.perPod+n]; if (core>=t.cores) return false;
            values.insert(core);
        }
        if (values.size()!=t.cores) return false;
    }
    return true;
}
AnnealResult Anneal(const FatTree& t,const std::vector<Flow>& flows,
                   const std::vector<uint32_t>& previous,uint32_t iterations,
                   std::mt19937_64& rng,bool checkEnergy) {
    auto mapping=previous.empty()?InitialMapping(t):previous;
    if (!ValidMapping(t,mapping)) throw std::invalid_argument("invalid SA mapping");
    auto pathFor=[&](const Flow& f) { return t.InterPod(f.src,f.dst)?t.ViaCore(f.src,f.dst,mapping[f.dst]):f.baseline; };
    auto pathsFor=[&]() { std::map<uint32_t,Path> paths; for (const auto& f:flows) paths[f.id]=pathFor(f); return paths; };
    auto load=ComputeLoads(t,flows,pathsFor());
    double energy=Energy(t,load);
    AnnealResult result; result.initialEnergy=result.bestEnergy=energy; result.mapping=mapping;
    if (flows.empty()) { result.paths=pathsFor(); return result; }
    std::vector<std::vector<size_t>> incoming(t.hosts);
    for (size_t i=0;i<flows.size();++i) if (t.InterPod(flows[i].src,flows[i].dst)) incoming[flows[i].dst].push_back(i);
    auto choose=[&](uint32_t bound) { return std::uniform_int_distribution<uint32_t>(0,bound-1)(rng); };
    const double c=(t.hosts==16?0.5:1000.0)*iterations;
    for (uint32_t temp=iterations;temp>0;--temp) {
        uint32_t type=choose(3),pod=choose(t.k);
        std::vector<uint32_t> eligible;
        if (type==0) {
            for (uint32_t n=0;n<t.perPod;++n) eligible.push_back(pod*t.perPod+n);
        } else if (type==1 || choose(2)==0) {
            uint32_t edge=choose(t.half);
            for (uint32_t n=0;n<t.half;++n) eligible.push_back(pod*t.perPod+edge*t.half+n);
        } else {
            uint32_t agg=choose(t.half);
            for (uint32_t n=0;n<t.perPod;++n) {
                uint32_t h=pod*t.perPod+n; if (mapping[h]/t.half==agg) eligible.push_back(h);
            }
        }
        if (eligible.size()<2) continue;
        uint32_t ai=choose(eligible.size()),bi=choose(eligible.size()-1); if (bi>=ai) ++bi;
        uint32_t a=eligible[ai],b=eligible[bi];
        std::vector<size_t> affected=incoming[a];
        affected.insert(affected.end(),incoming[b].begin(),incoming[b].end());
        std::map<uint32_t,double> delta;
        for (auto i:affected) for (auto l:t.PathLinks(pathFor(flows[i]))) delta[l]-=flows[i].demand;
        std::swap(mapping[a],mapping[b]);
        for (auto i:affected) for (auto l:t.PathLinks(pathFor(flows[i]))) delta[l]+=flows[i].demand;
        double next=energy;
        for (auto [l,d]:delta) {
            double capacity=t.links[l].capacity;
            next-=std::max(0.0,load[l]-capacity);
            next+=std::max(0.0,load[l]+d-capacity);
        }
        next=std::max(0.0,next);
        if (checkEnergy) {
            auto reference=ComputeLoads(t,flows,pathsFor());
            if (std::abs(Energy(t,reference)-next)>1e-8) throw std::runtime_error("SA delta energy mismatch");
        }
        if (next<result.bestEnergy-1e-12) { result.bestEnergy=next; result.mapping=mapping; }
        bool accept=next<=energy || std::uniform_real_distribution<double>(0,1)(rng)<std::exp(c*(energy-next)/temp);
        if (accept) { for (auto [l,d]:delta) load[l]+=d; energy=next; ++result.accepted; }
        else std::swap(mapping[a],mapping[b]);
    }
    mapping=result.mapping; result.paths=pathsFor();
    result.bestEnergy=Energy(t,ComputeLoads(t,flows,result.paths));
    return result;
}
}
