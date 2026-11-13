#include "hedera-core.h"
#include "hedera-oracle.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace hedera;
namespace {
using Clock=std::chrono::steady_clock;
double Milliseconds(Clock::time_point start) {
    return std::chrono::duration<double,std::milli>(Clock::now()-start).count();
}

std::vector<Endpoint> Traffic(uint32_t hosts,uint32_t count,std::mt19937_64& rng) {
    std::vector<Endpoint> result;
    result.reserve(count);
    for(uint32_t i=0;i<count;++i) {
        const uint32_t src=rng()%hosts;
        uint32_t dst=rng()%(hosts-1);
        if(dst>=src) ++dst;
        result.push_back({src,dst});
    }
    return result;
}

std::vector<Flow> Snapshot(const FatTree& tree,const std::vector<Endpoint>& endpoints,
                           const DemandResult& estimate) {
    std::vector<Flow> flows;
    flows.reserve(endpoints.size());
    for(size_t i=0;i<endpoints.size();++i) {
        const auto [src,dst]=endpoints[i];
        flows.push_back({static_cast<uint32_t>(i),src,dst,estimate.demand[i],tree.ViaCore(src,dst,0)});
    }
    return flows;
}

std::pair<double,uint64_t> ExactPerFlow(const FatTree& tree,const std::vector<Flow>& flows) {
    uint64_t states=1;
    std::vector<std::vector<std::vector<uint32_t>>> choices;
    for(const auto& f:flows) {
        const auto paths=tree.InterPod(f.src,f.dst)?tree.Candidates(f.src,f.dst):std::vector<Path>{f.baseline};
        if(states>1000000/paths.size()) throw std::length_error("exact per-flow state limit");
        states*=paths.size();
        choices.emplace_back();
        for(const auto& path:paths) choices.back().push_back(tree.PathLinks(path));
    }
    std::vector<double> load(tree.links.size());
    double best=std::numeric_limits<double>::infinity();
    uint64_t visited=0;
    std::function<void(size_t)> visit=[&](size_t i) {
        if(i==flows.size()) {
            best=std::min(best,Energy(tree,load));
            ++visited;
            return;
        }
        for(const auto& path:choices[i]) {
            for(auto l:path) load[l]+=flows[i].demand;
            visit(i+1);
            for(auto l:path) load[l]-=flows[i].demand;
        }
    };
    visit(0);
    if(visited!=states) throw std::logic_error("exact per-flow search incomplete");
    return {best,states};
}

double AnnealPerFlow(const FatTree& tree,const std::vector<Flow>& flows,
                     uint32_t steps,std::mt19937_64& rng) {
    std::vector<uint32_t> candidates;
    std::vector<double> load(tree.links.size());
    auto initial=InitialMapping(tree);
    std::vector<Path> paths;
    paths.reserve(flows.size());
    for(size_t i=0;i<flows.size();++i) {
        const auto& f=flows[i];
        bool inter=tree.InterPod(f.src,f.dst);
        if(inter) candidates.push_back(i);
        paths.push_back(inter?tree.ViaCore(f.src,f.dst,initial[f.dst]):f.baseline);
        for(auto l:tree.PathLinks(paths.back())) load[l]+=f.demand;
    }
    double energy=Energy(tree,load),best=energy;
    if(candidates.empty()) return best;
    const double scale=(tree.hosts==16?0.5:1000.0)*steps;
    std::uniform_real_distribution<double> uniform(0,1);
    for(uint32_t temp=steps;temp>0;--temp) {
        const auto i=candidates[std::uniform_int_distribution<size_t>(0,candidates.size()-1)(rng)];
        const auto& f=flows[i];
        auto proposed=tree.ViaCore(f.src,f.dst,std::uniform_int_distribution<uint32_t>(0,tree.cores-1)(rng));
        std::map<uint32_t,double> delta;
        for(auto l:tree.PathLinks(paths[i])) delta[l]-=f.demand;
        for(auto l:tree.PathLinks(proposed)) delta[l]+=f.demand;
        double next=energy;
        for(const auto& [l,d]:delta)
            next+=std::max(0.0,load[l]+d-tree.links[l].capacity)-std::max(0.0,load[l]-tree.links[l].capacity);
        if(next<=energy || uniform(rng)<std::exp(scale*(energy-next)/temp)) {
            paths[i]=std::move(proposed);
            for(const auto& [l,d]:delta) load[l]+=d;
            energy=std::max(0.0,next);
            best=std::min(best,energy);
        }
    }
    if(std::abs(Energy(tree,load)-energy)>1e-7) throw std::logic_error("per-flow delta inconsistent");
    return best;
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::invalid_argument("usage: paper-core-study output-prefix");
        const std::string prefix=argv[1];
        std::ofstream estimate(prefix+"-estimate.csv"),runtime(prefix+"-runtime.csv"),quality(prefix+"-quality.csv");
        if(!estimate || !runtime || !quality) throw std::runtime_error("cannot open benchmark outputs");
        estimate<<"hosts,flows,seed,rounds,runtime_ms\n"<<std::setprecision(10);
        runtime<<"hosts,flows,seed,iterations,variant,runtime_ms,energy\n"<<std::setprecision(10);
        quality<<"snapshot,flows,steps,seed,variant,oracle_energy,oracle_states,sa_energy,runtime_ms\n"<<std::setprecision(10);
        for(const auto& [hosts,count]:std::vector<std::pair<uint32_t,uint32_t>>{
            {1024,1024},{1024,5000},{8192,8192},{8192,25000},{8192,50000},
            {27648,27648},{27648,100000},{27648,250000}}) {
            for(uint32_t seed=1;seed<=5;++seed) {
                std::mt19937_64 rng(seed);
                auto endpoints=Traffic(hosts,count,rng);
                const auto start=Clock::now();
                auto result=EstimateDemands(endpoints,hosts);
                const double ms=Milliseconds(start);
                std::vector<double> incoming(hosts),outgoing(hosts);
                for(size_t i=0;i<endpoints.size();++i) {
                    outgoing[endpoints[i].src]+=result.demand[i];
                    incoming[endpoints[i].dst]+=result.demand[i];
                }
                if(*std::max_element(incoming.begin(),incoming.end())>1+1e-8 ||
                   *std::max_element(outgoing.begin(),outgoing.end())>1+1e-8)
                    throw std::logic_error("demand violates NIC bound");
                estimate<<hosts<<','<<count<<','<<seed<<','<<result.rounds<<','<<ms<<'\n';
            }
        }
        for(uint32_t k:{16u,32u}) {
            const FatTree tree(k);
            auto counts=k==16?std::vector<uint32_t>{3215,6250}:std::vector<uint32_t>{25000,50000};
            for(uint32_t count:counts) for(uint32_t seed=1;seed<=5;++seed) {
                std::mt19937_64 generator(seed);
                auto endpoints=Traffic(tree.hosts,count,generator);
                auto flows=Snapshot(tree,endpoints,EstimateDemands(endpoints,tree.hosts));
                for(uint32_t steps:{1000u,5000u,10000u}) for(bool perFlow:{false,true}) {
                    std::mt19937_64 rng(seed);
                    const auto start=Clock::now();
                    double h=perFlow?AnnealPerFlow(tree,flows,steps,rng):Anneal(tree,flows,{},steps,rng).bestEnergy;
                    runtime<<tree.hosts<<','<<count<<','<<seed<<','<<steps<<','
                           <<(perFlow?"flow":"destination")<<','<<Milliseconds(start)<<','<<h<<'\n';
                }
            }
        }
        const FatTree tree(4);
        for(uint32_t trial=0;trial<24;++trial) {
            std::mt19937_64 generator(913+trial);
            auto endpoints=Traffic(tree.hosts,4+trial%5,generator);
            // Alternate uniform endpoints and concentration on one destination pod.
            if(trial%2==0) for(auto& e:endpoints) {
                e.src=generator()%8;
                e.dst=8+generator()%4;
            }
            auto flows=Snapshot(tree,endpoints,EstimateDemands(endpoints,tree.hosts));
            if(trial==23) {
                // Two source-edge inequalities plus one destination-edge
                // inequality form a triangle of incompatible aggregation choices.
                flows={{0,0,9,.8,tree.ViaCore(0,9,0)},
                       {1,1,10,.3,tree.ViaCore(1,10,0)},
                       {2,2,8,.8,tree.ViaCore(2,8,0)},
                       {3,3,10,.3,tree.ViaCore(3,10,0)}};
            }
            auto restricted=ExactDestinationCore(tree,flows);
            const auto [unrestricted,states]=ExactPerFlow(tree,flows);
            if(unrestricted>restricted.energy+1e-8) throw std::logic_error("nested search spaces inconsistent");
            if(trial==23 && (unrestricted>1e-8 || restricted.energy<.099999))
                throw std::logic_error("expected a strict restriction gap for the triangle fixture");
            for(uint32_t steps:{10u,100u,1000u}) for(uint32_t seed=1;seed<=5;++seed) for(bool perFlow:{false,true}) {
                std::mt19937_64 rng(seed);
                const auto start=Clock::now();
                const double h=perFlow?AnnealPerFlow(tree,flows,steps,rng):Anneal(tree,flows,{},steps,rng).bestEnergy;
                const double ms=Milliseconds(start);
                const double exact=perFlow?unrestricted:restricted.energy;
                if(h+1e-8<exact) throw std::logic_error("SA below exact minimum");
                quality<<trial<<','<<flows.size()<<','<<steps<<','<<seed<<','<<(perFlow?"flow":"destination")<<','
                       <<exact<<','<<(perFlow?states:restricted.states)<<','<<h<<','<<ms<<'\n';
            }
        }
        return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
