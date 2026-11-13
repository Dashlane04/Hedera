#include "hedera-oracle.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace hedera;
int main(int argc,char** argv) {
 try {
    if(argc<2) throw std::invalid_argument("oracle-study OUTPUT.csv [snapshot.csv: id,src,dst,demand]");
    FatTree tree(4);
    std::vector<std::pair<std::string,std::vector<Flow>>> cases;
    if(argc>2) {
        std::ifstream input(argv[2]); if(!input) throw std::runtime_error("cannot open snapshot");
        std::string line; std::getline(input,line); std::vector<Flow> flows;
        while(std::getline(input,line)) {
            std::replace(line.begin(),line.end(),',',' '); std::istringstream row(line);
            uint32_t id,src,dst; double demand;
            if(!(row>>id>>src>>dst>>demand)) throw std::invalid_argument("invalid snapshot CSV");
            std::string baselineText; Path baseline;
            if(row>>baselineText) {
                std::replace(baselineText.begin(),baselineText.end(),'-',' ');
                std::istringstream pathInput(baselineText); uint32_t node;
                while(pathInput>>node) baseline.push_back(node);
                if(baseline.size()<2 || baseline.front()!=src || baseline.back()!=dst) throw std::invalid_argument("invalid baseline endpoints");
                tree.PathLinks(baseline);
            } else {
                if(!tree.InterPod(src,dst)) throw std::invalid_argument("intra-pod snapshot requires baseline path column");
                baseline=tree.ViaCore(src,dst,0);
            }
            flows.push_back({id,src,dst,demand,baseline});
        }
        cases.push_back({"snapshot",flows});
    } else {
        std::mt19937_64 generator(20261029);
        for(uint32_t c=0;c<12;++c) {
            std::vector<Endpoint> endpoints;
            for(uint32_t n=0;n<4+c%5;++n) {
                uint32_t src=generator()%8,dst=8+generator()%8;
                endpoints.push_back({src,dst});
            }
            auto estimate=EstimateDemands(endpoints,tree.hosts);
            std::vector<Flow> flows;
            for(uint32_t i=0;i<endpoints.size();++i) {
                auto e=endpoints[i]; flows.push_back({i,e.src,e.dst,estimate.demand[i],tree.ViaCore(e.src,e.dst,0)});
            }
            cases.push_back({"nic-feasible-"+std::to_string(c),flows});
        }
        cases.push_back({"synthetic-over-demand",{{0,0,8,1.2,tree.ViaCore(0,8,0)}}});
    }
    std::ofstream out(argv[1]); if(!out) throw std::runtime_error("cannot write oracle output");
    out<<"case,flows,states,oracle_energy,oracle_ms,steps,seed,sa_energy,absolute_gap,optimal,sa_ms\n"<<std::setprecision(12);
    for(const auto& [name,flows]:cases) {
        auto begin=std::chrono::steady_clock::now(); auto exact=ExactDestinationCore(tree,flows);
        double exactMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
        for(uint32_t steps:{0u,10u,100u,1000u}) for(uint32_t seed=1;seed<=5;++seed) {
            std::mt19937_64 rng(seed); begin=std::chrono::steady_clock::now();
            auto sa=Anneal(tree,flows,{},steps,rng,true);
            double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
            double gap=sa.bestEnergy-exact.energy;
            if(gap < -1e-8 || !ValidMapping(tree,sa.mapping)) throw std::runtime_error("oracle regression failure");
            out<<name<<','<<flows.size()<<','<<exact.states<<','<<exact.energy<<','<<exactMs<<','<<steps<<','<<seed<<','<<sa.bestEnergy<<','<<std::max(0.0,gap)<<','<<(std::abs(gap)<1e-8)<<','<<ms<<'\n';
        }
    }
    std::cout<<"PASS: "<<cases.size()<<" exact cases, "<<cases.size()*20<<" SA comparisons; same objective/state space\n";
 } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
