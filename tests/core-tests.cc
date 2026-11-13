#include "hedera-core.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <set>
using namespace hedera;
static int checks=0;
void Require(bool condition,const char* message) { ++checks; if (!condition) throw std::runtime_error(message); }
int main() {
    FatTree tree(4);
    Require(tree.hosts==16 && tree.nodes==36 && tree.links.size()==96,"fat-tree counts");
    for (uint32_t s=0;s<16;++s) for (uint32_t d=0;d<16;++d) if (s!=d) {
        auto paths=tree.Candidates(s,d);
        Require(paths.size()==(tree.Edge(s)==tree.Edge(d)?1:tree.Pod(s)==tree.Pod(d)?2:4),"candidate count");
        for (const auto& p:paths) {
            Require(p.front()==s && p.back()==d,"path endpoints");
            Require(tree.PathLinks(p).size()+1==p.size(),"path adjacency");
        }
    }
    std::vector<Endpoint> example={{0,1},{0,2},{0,3},{1,0},{1,0},{1,2},{2,0},{2,3},{3,1},{3,1}};
    auto estimated=EstimateDemands(example,4);
    for (size_t n=0;n<example.size();++n)
        Require(std::abs(estimated.demand[n]-(n==7?2.0/3:1.0/3))<1e-10,"Figure 4 demand");
    Require(EstimateDemands({},4).demand.empty(),"empty estimator");
    std::set<uint32_t> buckets;
    for(uint32_t h=0;h<16;++h) buckets.insert(AvalancheHash(HashWords({0x0a000001+4*h,1}))%4);
    Require(buckets.size()==4,"hash avalanche distributes aligned /30 host addresses");
    std::mt19937_64 rng(42);
    for (int trial=0;trial<100;++trial) {
        std::vector<Endpoint> pairs;
        for (int f=0;f<50;++f) { uint32_t s=rng()%16,d=rng()%15; if (d>=s) ++d; pairs.push_back({s,d}); }
        auto demands=EstimateDemands(pairs,16);
        for (uint32_t h=0;h<16;++h) {
            double tx=0,rx=0;
            for (size_t i=0;i<pairs.size();++i) {
                Require(demands.demand[i]>=0,"nonnegative demand");
                if(pairs[i].src==h) tx+=demands.demand[i];
                if(pairs[i].dst==h) rx+=demands.demand[i];
            }
            Require(tx<=1+1e-9 && rx<=1+1e-9,"endpoint capacity");
        }
    }
    std::vector<Flow> flows;
    for (uint32_t n=0;n<8;++n) flows.push_back({n,n,n+8,0.8,tree.ViaCore(n,n+8,0)});
    GlobalFirstFit gff(tree);
    auto placed=gff.Place(flows);
    Require(Energy(tree,ComputeLoads(tree,flows,placed))<1e-8,"GFF avoids avoidable overload");
    Require(gff.Place(flows)==placed,"GFF keeps assignments");
    gff.Place({}); Require(gff.Reservations().empty(),"GFF expires reservations");
    auto exact=gff.Place({{98,0,8,1.0,tree.ViaCore(0,8,3)}});
    Require(gff.Reservations().count(98)==1,"GFF inclusive capacity boundary");
    auto fallback=gff.Place({{99,0,8,1.1,tree.ViaCore(0,8,3)}});
    Require(fallback.at(99)==tree.ViaCore(0,8,3),"GFF fallback when infeasible");
    Require(gff.Reservations().empty(),"fallback not a reservation");
    auto sa=Anneal(tree,flows,{},2000,rng,true);
    Require(ValidMapping(tree,sa.mapping),"SA bijection");
    Require(sa.bestEnergy<=sa.initialEnergy+1e-9,"SA returns best");
    auto warm=Anneal(tree,flows,sa.mapping,0,rng,true);
    Require(warm.mapping==sa.mapping,"warm start with zero steps");
    Require(std::abs(warm.bestEnergy-sa.bestEnergy)<1e-9,"warm start refresh");
    FatTree bigger(8); Require(bigger.hosts==128 && bigger.nodes==208,"k=8 counts");
    std::cout << "PASS: " << checks << " checks (topology, Figure 4, demand capacities, GFF, SA delta/warm start)\n";
}
