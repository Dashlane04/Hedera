#include "hedera-core.h"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <random>
using namespace hedera;
int main(int argc,char** argv) {
    if(argc!=2) { std::cerr<<"Usage: scheduler-benchmark output.csv\n"; return 1; }
    std::ofstream out(argv[1]);
    if(!out) return 1;
    out<<"k,hosts,flows,seed,algorithm,estimate_us,placement_us,energy\n";
    for(uint32_t k:{4,6,8}) for(uint32_t count:{16,64,256,1024}) for(uint32_t seed=1;seed<=5;++seed) {
        FatTree tree(k); std::mt19937_64 rng(seed);
        std::vector<Endpoint> endpoints;
        for(uint32_t i=0;i<count;++i) {
            uint32_t src=rng()%tree.hosts,dst;
            do { dst=rng()%tree.hosts; } while(src==dst);
            endpoints.push_back({src,dst});
        }
        auto start=std::chrono::steady_clock::now();
        auto demands=EstimateDemands(endpoints,tree.hosts);
        double estimate=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
        std::vector<Flow> flows;
        for(uint32_t i=0;i<count;++i) {
            auto paths=tree.Candidates(endpoints[i].src,endpoints[i].dst);
            flows.push_back({i,endpoints[i].src,endpoints[i].dst,demands.demand[i],paths[rng()%paths.size()]});
        }
        for(const std::string algorithm:{"gff","sa"}) {
            start=std::chrono::steady_clock::now();
            std::map<uint32_t,Path> paths;
            if(algorithm=="gff") { GlobalFirstFit gff(tree); paths=gff.Place(flows); }
            else { std::mt19937_64 search(seed); paths=Anneal(tree,flows,{},1000,search,false).paths; }
            double placement=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count();
            out<<k<<','<<tree.hosts<<','<<count<<','<<seed<<','<<algorithm<<','<<estimate<<','<<placement<<','
               <<Energy(tree,ComputeLoads(tree,flows,paths))<<'\n';
        }
    }
    std::cout<<"Wrote scheduler benchmark: "<<argv[1]<<" (SA 1000 iterations, no validation inside timing)\n";
}
