#include "hedera-oracle.h"
#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <set>
#include <stdexcept>

namespace hedera {
OracleResult ExactDestinationCore(const FatTree& tree,const std::vector<Flow>& flows,uint64_t maxStates) {
    if(!maxStates) throw std::invalid_argument("oracle state limit must be positive");
    std::vector<std::set<uint32_t>> destinations(tree.k);
    std::set<uint32_t> ids;
    for(const auto& f:flows) {
        if(!ids.insert(f.id).second || f.src>=tree.hosts || f.dst>=tree.hosts || f.src==f.dst || !std::isfinite(f.demand) || f.demand<0)
            throw std::invalid_argument("invalid oracle flow");
        if(tree.InterPod(f.src,f.dst)) destinations[tree.Pod(f.dst)].insert(f.dst);
    }
    uint64_t bound=1;
    for(const auto& hosts:destinations) for(uint64_t i=0;i<hosts.size();++i) {
        uint64_t choices=tree.cores-i;
        if(bound>maxStates/choices) throw std::length_error("exact oracle exceeds maxStates; reduce active destinations");
        bound*=choices;
    }
    std::vector<uint32_t> active;
    for(const auto& hosts:destinations) active.insert(active.end(),hosts.begin(),hosts.end());
    auto mapping=InitialMapping(tree);
    std::vector<std::vector<bool>> used(tree.k,std::vector<bool>(tree.cores,false));
    OracleResult best; best.energy=std::numeric_limits<double>::infinity();
    std::function<void(size_t)> search=[&](size_t at) {
        if(at==active.size()) {
            // Complete every partial injection to a canonical full bijection.
            auto full=mapping;
            for(uint32_t pod=0;pod<tree.k;++pod) {
                uint32_t core=0;
                for(uint32_t n=0;n<tree.perPod;++n) {
                    uint32_t h=pod*tree.perPod+n;
                    if(destinations[pod].count(h)) continue;
                    while(used[pod][core]) ++core;
                    full[h]=core++;
                }
            }
            std::map<uint32_t,Path> paths;
            for(const auto& f:flows) paths[f.id]=tree.InterPod(f.src,f.dst)?tree.ViaCore(f.src,f.dst,full[f.dst]):f.baseline;
            double energy=Energy(tree,ComputeLoads(tree,flows,paths)); ++best.states;
            if(energy<best.energy) { best.energy=energy; best.mapping=std::move(full); best.paths=std::move(paths); }
            return;
        }
        uint32_t h=active[at],pod=tree.Pod(h);
        for(uint32_t core=0;core<tree.cores;++core) if(!used[pod][core]) {
            used[pod][core]=true; mapping[h]=core; search(at+1); used[pod][core]=false;
        }
    };
    search(0);
    if(best.states!=bound || !ValidMapping(tree,best.mapping)) throw std::logic_error("incomplete exact enumeration");
    return best;
}
}
