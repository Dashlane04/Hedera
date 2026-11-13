#include "hedera-core.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>

using namespace hedera;
namespace {
constexpr double nicBytes=125000000.0, tick=0.02, duration=60, meanBytes=125000000.0;
constexpr double offered=0.8, increase=15000000.0/nicBytes;

struct Transfer {
    Flow flow;
    double start, remaining, rate=0.01;
    bool slow=true;
    std::vector<uint32_t> links;
    bool large=false;
};

uint32_t Destination(const FatTree& tree,const std::string& pattern,uint32_t src,
                     const std::vector<uint32_t>& bijection,std::mt19937_64& rng) {
    if(pattern=="randbij") return bijection[src];
    if(pattern.rfind("stride",0)==0) {
        auto offset=std::stoul(pattern.substr(6))%tree.hosts;
        if(offset==0) throw std::invalid_argument("stride cannot be zero modulo the host count");
        return (src+offset)%tree.hosts;
    }
    uint32_t dst;
    if(pattern=="stag20" || pattern=="stag50" || pattern=="stag50pod0" || pattern=="stag100") {
        double edge=pattern=="stag20"?0.2:pattern=="stag100"?1.0:0.5;
        double pod=(pattern=="stag20" || pattern=="stag50")?0.3:0;
        double draw=std::generate_canonical<double,53>(rng);
        if(draw<edge) {
            do { dst=src/tree.half*tree.half+rng()%tree.half; } while(dst==src);
        } else if(draw<edge+pod) {
            do { dst=tree.Pod(src)*tree.perPod+rng()%tree.perPod; }
            while(tree.Edge(src)==tree.Edge(dst));
        } else {
            do { dst=rng()%tree.hosts; } while(tree.Pod(src)==tree.Pod(dst));
        }
    } else if(pattern=="rand") {
        do { dst=rng()%tree.hosts; } while(dst==src);
    } else throw std::invalid_argument("unknown communication pattern");
    return dst;
}

std::vector<Transfer> Workload(const FatTree& tree,const std::string& pattern,uint32_t seed) {
    std::mt19937_64 rng(seed);
    std::vector<uint32_t> bijection(tree.hosts);
    std::iota(bijection.begin(),bijection.end(),0);
    if(pattern=="randbij") {
        bool fixedPoint;
        do {
            std::shuffle(bijection.begin(),bijection.end(),rng);
            fixedPoint=false;
            for(uint32_t i=0;i<tree.hosts;++i) fixedPoint|=bijection[i]==i;
        } while(fixedPoint);
    }
    std::exponential_distribution<double> arrival(offered*tree.hosts*nicBytes/meanBytes);
    std::exponential_distribution<double> size(1/meanBytes);
    std::vector<Transfer> result;
    for(double t=arrival(rng);t<duration;t+=arrival(rng)) {
        const uint32_t src=rng()%tree.hosts;
        const uint32_t dst=Destination(tree,pattern,src,bijection,rng);
        const auto hash=AvalancheHash(HashWords({dst,seed}));
        Path path;
        if(tree.InterPod(src,dst)) path=tree.ViaCore(src,dst,hash%tree.cores);
        else {
            auto candidates=tree.Candidates(src,dst);
            path=candidates[hash%candidates.size()];
        }
        result.push_back({{static_cast<uint32_t>(result.size()),src,dst,0,std::move(path)},
                          t,std::max(1.0,std::ceil(size(rng))),0.01,true,{}});
    }
    return result;
}

void Place(const FatTree& tree,std::vector<Transfer>& active,const std::string& algorithm,
           GlobalFirstFit& gff,std::vector<uint32_t>& warm,std::mt19937_64& rng,
           uint32_t steps,bool warmStart) {
    std::vector<Endpoint> endpoints;
    std::vector<Flow> selected;
    for(auto& f:active) {
        f.large=f.large || f.rate>=0.1;
        if(f.large) {
            endpoints.push_back({f.flow.src,f.flow.dst});
            selected.push_back(f.flow);
        }
    }
    auto demands=EstimateDemands(endpoints,tree.hosts);
    for(size_t i=0;i<selected.size();++i) selected[i].demand=demands.demand[i];
    std::map<uint32_t,Path> paths;
    if(algorithm=="gff") paths=gff.Place(selected);
    else {
        auto result=Anneal(tree,selected,warmStart?warm:std::vector<uint32_t>{},steps,rng);
        warm=std::move(result.mapping);
        paths=std::move(result.paths);
    }
    for(auto& f:active) {
        auto it=paths.find(f.flow.id);
        if(it!=paths.end()) f.links=tree.PathLinks(it->second);
    }
}

double AvailableRate(const Transfer& flow,const std::vector<double>& loads) {
    double available=1;
    for(auto link:flow.links) available=std::min(available,1-loads[link]);
    return std::max(0.0,available);
}
}

int main(int argc,char** argv) {
    try {
        if(argc!=8) throw std::invalid_argument("usage: paper-flow-study k pattern algorithm seed iterations warm output-prefix");
        const FatTree tree(std::stoul(argv[1]));
        const std::string pattern=argv[2],algorithm=argv[3],prefix=argv[7];
        const uint32_t seed=std::stoul(argv[4]), steps=std::stoul(argv[5]);
        const bool warmStart=std::stoi(argv[6])!=0;
        if(algorithm!="ecmp" && algorithm!="gff" && algorithm!="sa" && algorithm!="nonblocking")
            throw std::invalid_argument("unknown algorithm");
        auto arrivals=Workload(tree,pattern,seed);
        std::ofstream input(prefix+".workload.csv");
        std::ofstream out(prefix+".csv");
        if(!out || !input) throw std::runtime_error("cannot open result files");
        input<<"flow_id,src,dst,start_s,bytes\n"<<std::setprecision(17);
        for(const auto& x:arrivals) input<<x.flow.id<<','<<x.flow.src<<','<<x.flow.dst<<','<<x.start<<','<<x.remaining<<'\n';
        out<<"time_s,active,completed,total_gbps,cut_gbps,max_link_load\n"<<std::setprecision(12);
        std::mt19937_64 orderRng(seed+491),saRng(seed+193);
        std::vector<Transfer> active;
        std::vector<double> loads(tree.links.size());
        std::vector<size_t> order;
        GlobalFirstFit gff(tree);
        std::vector<uint32_t> warm;
        size_t next=0,completed=0;
        for(int n=0;n<3000;++n) {
            const double time=n*tick;
            while(next<arrivals.size() && arrivals[next].start<=time) {
                auto f=std::move(arrivals[next++]);
                if(algorithm=="nonblocking")
                    f.links={tree.LinkId(f.flow.src,tree.Edge(f.flow.src)),tree.LinkId(tree.Edge(f.flow.dst),f.flow.dst)};
                else f.links=tree.PathLinks(f.flow.baseline);
                active.push_back(std::move(f));
            }
            if(n%50==0 && (algorithm=="gff" || algorithm=="sa"))
                Place(tree,active,algorithm,gff,warm,saRng,steps,warmStart);
            std::fill(loads.begin(),loads.end(),0);
            order.resize(active.size());
            std::iota(order.begin(),order.end(),0);
            std::shuffle(order.begin(),order.end(),orderRng);
            for(auto i:order) {
                auto& f=active[i];
                f.rate=std::min({f.rate,AvailableRate(f,loads),f.remaining/(nicBytes*tick)});
                for(auto link:f.links) loads[link]+=f.rate;
            }
            double total=0,cut=0;
            for(auto i:order) {
                auto& f=active[i];
                for(auto link:f.links) loads[link]-=f.rate;
                const double room=AvailableRate(f,loads);
                const double proposal=f.slow?std::max(0.01,2*f.rate):f.rate+increase;
                double desired=std::min(proposal,f.remaining/(nicBytes*tick));
                if(desired>room+1e-12) {
                    f.slow=false;
                    desired=std::max(f.rate/2,0.001);
                }
                f.rate=std::min({desired,room,f.remaining/(nicBytes*tick)});
                for(auto link:f.links) loads[link]+=f.rate;
                f.remaining=std::max(0.0,f.remaining-f.rate*nicBytes*tick);
                total+=f.rate;
                if((f.flow.src<tree.hosts/2)!=(f.flow.dst<tree.hosts/2)) cut+=f.rate;
            }
            const auto maxLoad=*std::max_element(loads.begin(),loads.end());
            if(maxLoad>1+1e-9 || cut>total+1e-9) throw std::logic_error("capacity/accounting violation");
            const auto end=std::remove_if(active.begin(),active.end(),[](const auto& f){return f.remaining<1e-6;});
            completed+=active.end()-end;
            active.erase(end,active.end());
            out<<(n+1)*tick<<','<<active.size()<<','<<completed<<','<<total<<','<<cut<<','<<maxLoad<<'\n';
        }
        return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
