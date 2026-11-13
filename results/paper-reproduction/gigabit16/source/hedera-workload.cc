#include "hedera-network.h"
#include "hedera-utils.h"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <numeric>
#include <sstream>
#include <set>
#include <stdexcept>
namespace hedera {
using namespace ns3;
void Experiment::MakeWorkload() {
    std::set<std::pair<uint32_t,uint16_t>> listeners;
    auto add=[&](uint32_t src,uint32_t dst,double start,uint64_t bytes,uint16_t port=0,double stop=-1,const std::string& cohort="default") {
        if(stop<0) stop=m_settings.duration;
        if(src>=m_tree.hosts || dst>=m_tree.hosts || src==dst || !std::isfinite(start) || !std::isfinite(stop) || start<0 || stop<=start || stop>m_settings.duration || (!bytes && m_settings.trafficMode=="finite") || m_flows.size()>=40000 || cohort.find_first_of(",\r\n")!=std::string::npos)
            throw std::invalid_argument("invalid workload row or too many flows");
        uint32_t id=m_flows.size();
        if(!port) port=10000+id;
        FlowState state{}; state.id=id; state.src=src; state.dst=dst; state.start=start;
        state.bytes=m_settings.trafficMode=="sustained"?0:bytes; state.port=port; state.stop=stop; state.cohort=cohort;
        auto key=std::make_tuple(m_hostIps[src].Get(),m_hostIps[dst].Get(),port);
        if(m_flowIds.count(key)) throw std::invalid_argument("duplicate source/destination/listener in workload");
        // Each flow has its own receiver port, so evaluator Rx callbacks cannot mix streams.
        if(!listeners.insert({dst,port}).second) throw std::invalid_argument("receiver port must be unique per destination");
        m_flowIds[key]=id; m_flows.push_back(state);
    };
    auto& s=m_settings;
    std::uniform_real_distribution<double> uniform(0,1);
    auto chooseDestination=[&](uint32_t src) {
        uint32_t dst=src;
        double draw=uniform(m_workloadRng);
        if(s.edgeProbability>=0) {
            if(draw<s.edgeProbability) {
                do { dst=(src/m_tree.half)*m_tree.half+m_workloadRng()%m_tree.half; } while(dst==src);
            } else if(draw<s.edgeProbability+s.podProbability) {
                do { dst=m_tree.Pod(src)*m_tree.perPod+m_workloadRng()%m_tree.perPod; } while(m_tree.Edge(src)==m_tree.Edge(dst));
            } else {
                do { dst=m_workloadRng()%m_tree.hosts; } while(m_tree.Pod(dst)==m_tree.Pod(src));
            }
        } else if(s.workload=="staggered" && draw<s.localProbability) {
            do { dst=m_tree.Pod(src)*m_tree.perPod+m_workloadRng()%m_tree.perPod; } while(dst==src);
        } else {
            do { dst=m_workloadRng()%m_tree.hosts; }
            while(dst==src || (s.workload=="staggered" && m_tree.Pod(dst)==m_tree.Pod(src)));
        }
        return dst;
    };
    if(!s.workloadFile.empty()) {
        std::ifstream in(s.workloadFile); if(!in) throw std::runtime_error("cannot open workload CSV");
        std::string line; bool first=true;
        while(std::getline(in,line)) {
            if(line.empty() || line[0]=='#') continue;
            if(first && line.rfind("src,",0)==0) { first=false; continue; }
            first=false;
            std::vector<std::string> cells; std::istringstream input(line); std::string cell;
            while(std::getline(input,cell,',')) { if(!cell.empty() && cell.back()=='\r') cell.pop_back(); cells.push_back(cell); }
            if(cells.size()<4 || cells.size()>7) throw std::invalid_argument("CSV needs src,dst,start,bytes[,port,stop,cohort]");
            auto number=[](const std::string& text) { size_t n=0; double value=std::stod(text,&n); if(n!=text.size() || !std::isfinite(value)) throw std::invalid_argument("invalid CSV number"); return value; };
            auto integer=[&](const std::string& text,uint64_t limit) { double v=number(text); if(v<0 || v>double(limit) || std::floor(v)!=v) throw std::invalid_argument("invalid CSV integer"); return uint64_t(v); };
            uint32_t src=integer(cells[0],m_tree.hosts-1),dst=integer(cells[1],m_tree.hosts-1);
            uint32_t port=cells.size()>4 && !cells[4].empty()?integer(cells[4],65535):0;
            double stop=cells.size()>5 && !cells[5].empty()?number(cells[5]):-1;
            add(src,dst,number(cells[2]),integer(cells[3],uint64_t(1)<<53),port,stop,cells.size()>6?cells[6]:"default");
        }
    } else if(s.workload=="phased") {
        if(s.trafficMode!="sustained" || s.k!=4 || s.duration<3)
            throw std::invalid_argument("phased requires k=4, sustained, duration>=3");
        double burst=s.duration/3,recovery=2*s.duration/3;
        auto portFor=[&](uint32_t src,uint32_t dst,uint32_t core) {
            for(uint32_t port=10000;port<60000;++port) {
                FlowKey key{m_hostIps[src].Get(),m_hostIps[dst].Get(),49153,uint16_t(port),6};
                if(EcmpPath(src,dst,key)==m_tree.ViaCore(src,dst,core)) return uint16_t(port);
            }
            throw std::runtime_error("could not select phased fixture path");
        };
        for(uint32_t i=0;i<4;++i) add(2*i,8+2*i,0.2,0,portFor(2*i,8+2*i,i),s.duration,"background");
        for(uint32_t i=0;i<4;++i) add(2*i+1,9+2*i,burst,0,portFor(2*i+1,9+2*i,0),recovery,"burst");
        std::ofstream phases(s.output+"/phases.csv"); phases<<"phase_id,name,start,end\n"<<std::setprecision(17);
        phases<<"0,baseline,0.2,"<<burst<<"\n1,burst,"<<burst<<','<<recovery<<"\n2,recovery,"<<recovery<<','<<s.duration<<'\n';
    } else if(s.workload=="single") add(0,m_tree.hosts/2,0.2,s.flowBytes);
    else if(s.workload=="collision") {
        // Deliberately adversarial fixture: one outgoing connection per source,
        // ns-3.47's first ephemeral port is 49153. Search destination ports that
        // hash to core zero. PacketPath checks this assumption at runtime.
        for(uint32_t src=0;src<m_tree.hosts/2;++src) {
            uint32_t dst=src+m_tree.hosts/2;
            uint16_t chosen=0;
            for(uint32_t port=10000;port<60000;++port) {
                FlowKey key{m_hostIps[src].Get(),m_hostIps[dst].Get(),49153,uint16_t(port),6};
                if(EcmpPath(src,dst,key)==m_tree.ViaCore(src,dst,0)) { chosen=port; break; }
            }
            if(!chosen) throw std::runtime_error("could not generate collision fixture");
            add(src,dst,0.2,s.flowBytes,chosen);
        }
    } else if(s.workload=="stride") {
        uint32_t stride=s.stride?s.stride:m_tree.hosts/2;
        if(stride%m_tree.hosts==0) throw std::invalid_argument("stride must not route to self");
        for(uint32_t src=0;src<m_tree.hosts;++src) add(src,(src+stride)%m_tree.hosts,0.2,s.flowBytes);
    } else if(s.workload=="random-bijection") {
        std::vector<uint32_t> dest(m_tree.hosts); std::iota(dest.begin(),dest.end(),0);
        bool deranged=false;
        for(int attempt=0;attempt<1000 && !deranged;++attempt) {
            std::shuffle(dest.begin(),dest.end(),m_workloadRng); deranged=true;
            for(uint32_t h=0;h<m_tree.hosts;++h) if(dest[h]==h) { deranged=false; break; }
        }
        if(!deranged) throw std::runtime_error("failed to generate derangement");
        for(uint32_t src=0;src<m_tree.hosts;++src) add(src,dest[src],0.2,s.flowBytes);
    } else if(s.workload=="poisson") {
        if(s.trafficMode!="finite") throw std::invalid_argument("poisson workload requires finite trafficMode");
        double lambda=s.offeredLoad*m_tree.hosts*m_rate/(8.0*s.meanFlowBytes);
        std::exponential_distribution<double> interarrival(lambda),size(1.0/s.meanFlowBytes);
        for(double t=0.2+interarrival(m_workloadRng);t<s.arrivalStop;t+=interarrival(m_workloadRng)) {
            uint32_t src=m_workloadRng()%m_tree.hosts;
            add(src,chooseDestination(src),t,std::max<uint64_t>(1,uint64_t(std::ceil(size(m_workloadRng)))));
        }
    } else if(s.workload=="permutation") {
        std::vector<uint32_t> permutation(m_tree.hosts); std::iota(permutation.begin(),permutation.end(),0);
        std::shuffle(permutation.begin(),permutation.end(),m_workloadRng);
        for(uint32_t i=0;i<m_tree.hosts;++i) add(permutation[i],permutation[(i+1)%m_tree.hosts],0.2,s.flowBytes);
    } else if(s.workload=="mixed" || s.workload=="staggered" || s.workload=="hotspot") {
        for(uint32_t i=0;i<s.flowCount;++i) {
            uint32_t src=s.onePerHost?i%m_tree.hosts:m_workloadRng()%m_tree.hosts,dst;
            if(s.workload=="hotspot") { dst=m_tree.hosts-1; if(src==dst) src=0; }
            else dst=chooseDestination(src);
            double start=s.trafficMode=="sustained"?0.2:0.2+uniform(m_workloadRng)*(s.duration*0.6-0.2);
            uint64_t bytes=(s.workload=="mixed" && uniform(m_workloadRng)<0.5)?65536:s.flowBytes;
            add(src,dst,start,bytes);
        }
    } else throw std::invalid_argument("unknown workload");
    if(m_flows.empty()) throw std::invalid_argument("workload is empty");
    if(m_settings.packetTraceFlow>=int64_t(m_flows.size())) throw std::invalid_argument("packetTraceFlow out of range");
    std::ofstream out(s.output+"/workload.csv"); out<<"src,dst,start,bytes,port,stop,cohort\n"<<std::setprecision(17);
    std::ofstream events(s.output+"/workload-events.csv"); events<<"time,flow_id,event,cohort\n"<<std::setprecision(17);
    for(const auto& f:m_flows) {
        out<<f.src<<','<<f.dst<<','<<f.start<<','<<f.bytes<<','<<f.port<<','<<f.stop<<','<<f.cohort<<'\n';
        events<<f.start<<','<<f.id<<",source_start,"<<f.cohort<<'\n'<<f.stop<<','<<f.id<<",source_stop,"<<f.cohort<<'\n';
    }
}

void Experiment::InstallApplications() {
    m_tcp.resize(m_flows.size());
    for(const auto& f:m_flows) {
        PacketSinkHelper receiver("ns3::TcpSocketFactory",InetSocketAddress(Ipv4Address::GetAny(),f.port));
        auto sinkApps=receiver.Install(m_nodes.Get(f.dst)); sinkApps.Start(Seconds(0));
        sinkApps.Stop(Seconds(m_settings.duration+m_settings.drain));
        auto sink=DynamicCast<PacketSink>(sinkApps.Get(0));
        sink->TraceConnectWithoutContext("Rx",MakeBoundCallback(&Experiment::SinkRx,this,f.id));
        BulkSendHelper sender("ns3::TcpSocketFactory",InetSocketAddress(m_hostIps[f.dst],f.port));
        sender.SetAttribute("MaxBytes",UintegerValue(f.bytes));
        sender.SetAttribute("SendSize",UintegerValue(1448));
        auto sourceApps=sender.Install(m_nodes.Get(f.src)); sourceApps.Start(Seconds(f.start));
        sourceApps.Stop(Seconds(f.stop));
        if(m_settings.diagnostics) {
            // StartApplication creates/connects the socket at start; attach a
            // nanosecond later, before any SYN reply traverses even one link.
            Simulator::Schedule(Seconds(f.start)+NanoSeconds(1),&Experiment::AttachTcp,this,f.id,
                                DynamicCast<BulkSendApplication>(sourceApps.Get(0)));
        }
    }
}
}
