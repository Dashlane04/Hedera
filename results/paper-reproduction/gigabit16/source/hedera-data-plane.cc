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
namespace {
class PathVersionTag : public Tag {
public:
    uint32_t version=0;
    static TypeId GetTypeId() { static TypeId tid=TypeId("ns3::HederaPathVersionTag").SetParent<Tag>().AddConstructor<PathVersionTag>(); return tid; }
    TypeId GetInstanceTypeId() const override { return GetTypeId(); }
    uint32_t GetSerializedSize() const override { return 4; }
    void Serialize(TagBuffer b) const override { b.WriteU32(version); }
    void Deserialize(TagBuffer b) override { version=b.ReadU32(); }
    void Print(std::ostream& out) const override { out<<version; }
};
}
NS_OBJECT_ENSURE_REGISTERED(FlowRouting);
TypeId FlowRouting::GetTypeId() {
    static TypeId tid=TypeId("ns3::HederaFlowRouting").SetParent<Ipv4RoutingProtocol>().AddConstructor<FlowRouting>();
    return tid;
}

void FlowRouting::Configure(Experiment* experiment,uint32_t node) { m_experiment=experiment; m_node=node; }

Ptr<Ipv4Route> FlowRouting::MakeRoute(const Ipv4Header& header,uint32_t next) {
    const auto& hop=m_experiment->GetHop(m_node,next);
    int32_t interface=m_ipv4->GetInterfaceForDevice(hop.device);
    auto route=Create<Ipv4Route>();
    route->SetSource(m_ipv4->GetAddress(interface,0).GetLocal());
    route->SetDestination(header.GetDestination()); route->SetGateway(hop.gateway); route->SetOutputDevice(hop.device);
    return route;
}

Ptr<Ipv4Route> FlowRouting::RouteOutput(Ptr<Packet>,const Ipv4Header& header,Ptr<NetDevice> oif,Socket::SocketErrno& error) {
    if(m_node>=m_experiment->Tree().hosts) { error=Socket::ERROR_NOROUTETOHOST; return nullptr; }
    auto route=MakeRoute(header,m_experiment->FirstHop(m_node));
    if(oif && route->GetOutputDevice()!=oif) { error=Socket::ERROR_NOROUTETOHOST; return nullptr; }
    error=Socket::ERROR_NOTERROR; return route;
}

bool FlowRouting::RouteInput(Ptr<const Packet> packet,const Ipv4Header& header,Ptr<const NetDevice> incoming,
                            const UnicastForwardCallback& forward,const MulticastForwardCallback&,
                            const LocalDeliverCallback& local,const ErrorCallback& error) {
    int32_t interface=m_ipv4->GetInterfaceForDevice(incoming);
    if(m_ipv4->IsDestinationAddress(header.GetDestination(),interface)) {
        local(packet,header,interface); return true;
    }
    if(!m_ipv4->IsForwarding(interface)) { error(packet,header,Socket::ERROR_NOROUTETOHOST); return true; }
    auto path=m_experiment->PacketPath(m_node,packet,header);
    auto position=std::find(path.begin(),path.end(),m_node);
    if(position==path.end() || std::next(position)==path.end()) {
        error(packet,header,Socket::ERROR_NOROUTETOHOST); return true;
    }
    auto route=MakeRoute(header,*std::next(position));
    auto delay=m_experiment->ForwardingDelay(m_node,header,packet->GetSize());
    if(delay.IsStrictlyPositive()) {
        FlowKey key{header.GetSource().Get(),header.GetDestination().Get(),0,0,header.GetProtocol()};
        if(header.GetProtocol()==6) {
            TcpHeader tcp; packet->PeekHeader(tcp);
            key.srcPort=tcp.GetSourcePort(); key.dstPort=tcp.GetDestinationPort();
        }
        // A shorter trailing packet must not overtake the previous packet in
        // the virtual unloaded pipeline used by the reference model.
        auto release=std::max(Simulator::Now()+delay,m_referenceRelease[key]);
        m_referenceRelease[key]=release;
        Simulator::Schedule(release-Simulator::Now(),[forward,route,packet,header]() { forward(route,packet,header); });
    }
    else forward(route,packet,header);
    return true;
}

void FlowRouting::PrintRoutingTable(Ptr<OutputStreamWrapper> out,Time::Unit) const {
    *out->GetStream()<<"Hedera versioned per-flow routing, model node "<<m_node<<'\n';
}

const Hop& Experiment::GetHop(uint32_t a,uint32_t b) const { return m_hops.at({a,b}); }

uint32_t Experiment::HostFor(Ipv4Address ip) const { return m_ipHosts.at(ip.Get()); }

uint32_t Experiment::FirstHop(uint32_t host) const {
    return m_settings.algorithm=="nonblocking"?m_tree.hosts:m_tree.Edge(host);
}

Time Experiment::ForwardingDelay(uint32_t node,const Ipv4Header& header,uint32_t payloadBytes) const {
    if(m_settings.algorithm!="nonblocking" || !m_settings.matchReferenceDelay || node!=m_tree.hosts) return Seconds(0);
    uint32_t src=HostFor(header.GetSource()),dst=HostFor(header.GetDestination());
    uint32_t hops=m_tree.Edge(src)==m_tree.Edge(dst)?2:m_tree.Pod(src)==m_tree.Pod(dst)?4:6;
    auto propagation=Time(m_settings.linkDelay);
    // Replace the missing unloaded store-and-forward links by an infinite-
    // capacity delay, preserving latency without creating internal contention.
    auto serialization=Seconds(8.0*(payloadBytes+header.GetSerializedSize()+2)/m_rate);
    return (propagation+serialization)*int64_t(hops-2);
}

void Experiment::BuildNetwork() {
    bool reference=m_settings.algorithm=="nonblocking";
    m_nodes.Create(reference?m_tree.hosts+1:m_tree.nodes);
    m_networkLinks=m_tree.links;
    if(reference) {
        m_networkLinks.clear();
        for(uint32_t h=0;h<m_tree.hosts;++h) {
            m_networkLinks.push_back({h,m_tree.hosts,1});
            m_networkLinks.push_back({m_tree.hosts,h,1});
        }
    }
    InternetStackHelper stack; stack.Install(m_nodes);
    m_hostIps.resize(m_tree.hosts); m_queues.resize(m_networkLinks.size());
    m_linkBytes.assign(m_networkLinks.size(),0); m_lastLinkBytes=m_linkBytes;
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate",StringValue(m_settings.rate));
    p2p.SetChannelAttribute("Delay",StringValue(m_settings.linkDelay));
    p2p.SetDeviceAttribute("Mtu",UintegerValue(1500));
    p2p.SetQueue("ns3::DropTailQueue<Packet>","MaxSize",QueueSizeValue(QueueSize("1p")));
    TrafficControlHelper tc;
    tc.SetRootQueueDisc("ns3::FifoQueueDisc","MaxSize",QueueSizeValue(QueueSize(std::to_string(m_settings.queuePackets)+"p")));
    Ipv4AddressHelper addresses; addresses.SetBase("10.0.0.0","255.255.255.252");
    for(uint32_t l=0;l<m_networkLinks.size();l+=2) {
        auto from=m_networkLinks[l].from,to=m_networkLinks[l].to;
        auto devices=p2p.Install(m_nodes.Get(from),m_nodes.Get(to));
        auto queues=tc.Install(devices);
        auto ips=addresses.Assign(devices); addresses.NewNetwork();
        m_hops[{from,to}]={devices.Get(0),ips.GetAddress(1)};
        m_hops[{to,from}]={devices.Get(1),ips.GetAddress(0)};
        m_queues[l]=queues.Get(0); m_queues[l+1]=queues.Get(1);
        if(m_settings.diagnostics) {
            queues.Get(0)->TraceConnectWithoutContext("Drop",MakeBoundCallback(&Experiment::QueueDrop,this,l));
            queues.Get(1)->TraceConnectWithoutContext("Drop",MakeBoundCallback(&Experiment::QueueDrop,this,l+1));
        }
        devices.Get(0)->TraceConnectWithoutContext("PhyTxBegin",MakeBoundCallback(&Experiment::LinkTx,this,l));
        devices.Get(1)->TraceConnectWithoutContext("PhyTxBegin",MakeBoundCallback(&Experiment::LinkTx,this,l+1));
        if(from<m_tree.hosts) m_hostIps[from]=ips.GetAddress(0);
        if(to<m_tree.hosts) m_hostIps[to]=ips.GetAddress(1);
        if(m_settings.pcap) p2p.EnablePcap(m_settings.output+"/link",devices,false);
    }
    for(uint32_t h=0;h<m_tree.hosts;++h) m_ipHosts[m_hostIps[h].Get()]=h;
    for(uint32_t n=0;n<m_nodes.GetN();++n) {
        auto ipv4=m_nodes.Get(n)->GetObject<Ipv4>();
        auto protocol=CreateObject<FlowRouting>(); protocol->Configure(this,n); ipv4->SetRoutingProtocol(protocol);
        for(uint32_t i=1;i<ipv4->GetNInterfaces();++i) ipv4->SetForwarding(i,n>=m_tree.hosts);
    }
}

Path Experiment::EcmpPath(uint32_t src,uint32_t dst,const FlowKey& key) const {
    auto paths=m_tree.Candidates(src,dst);
    auto hash=m_settings.hashMode=="destination"?HashWords({key.dstIp,m_settings.seed}):
        HashWords({key.srcIp,key.dstIp,key.srcPort,key.dstPort,key.protocol,m_settings.seed});
    if(m_settings.hashMix=="avalanche") hash=AvalancheHash(hash);
    return paths.at(hash%paths.size());
}

Path Experiment::Baseline(uint32_t src,uint32_t dst,const FlowKey& key) const {
    if(m_settings.algorithm=="nonblocking") return {src,m_tree.hosts,dst};
    return EcmpPath(src,dst,key);
}

uint32_t Experiment::NewVersion(const Path& path) {
    if(m_versions.size()>=std::numeric_limits<uint32_t>::max()) throw std::runtime_error("path version overflow");
    m_versions.push_back(path); return m_versions.size()-1;
}

Path Experiment::PacketPath(uint32_t node,Ptr<const Packet> packet,const Ipv4Header& header) {
    uint32_t src=HostFor(header.GetSource()),dst=HostFor(header.GetDestination());
    FlowKey key{header.GetSource().Get(),header.GetDestination().Get(),0,0,header.GetProtocol()};
    TcpHeader tcp; uint32_t tcpSize=0;
    if(header.GetProtocol()==6 && header.GetFragmentOffset()==0) {
        tcpSize=packet->PeekHeader(tcp); key.srcPort=tcp.GetSourcePort(); key.dstPort=tcp.GetDestinationPort();
    }
    auto registered=m_flowIds.find({key.srcIp,key.dstIp,key.dstPort});
    FlowState* flow=registered==m_flowIds.end()?nullptr:&m_flows.at(registered->second);
    if(flow && node==FirstHop(src)) {
        if(!flow->discovered) {
            flow->baseline=Baseline(src,dst,key); flow->discovered=true;
            uint32_t fixtureCore=m_settings.workload=="phased" && flow->cohort=="background"?flow->src/2:0;
            if(m_settings.algorithm!="nonblocking" && (m_settings.workload=="collision" || m_settings.workload=="phased") && m_settings.workloadFile.empty() && flow->baseline!=m_tree.ViaCore(src,dst,fixtureCore))
                throw std::runtime_error("collision fixture ephemeral-port assumption failed; use permutation workload");
            SetPath(*flow,flow->baseline,"initial");
        }
        if(tcpSize && packet->GetSize()>tcpSize) {
            ObserveSource(*flow,packet->GetSize()-tcpSize,Simulator::Now().GetSeconds(),false);
        }
        if(tcpSize && (tcp.GetFlags()&(TcpHeader::FIN|TcpHeader::RST)))
            ObserveSource(*flow,0,Simulator::Now().GetSeconds(),true);
    }
    PathVersionTag tag;
    if(packet->PeekPacketTag(tag)) return m_versions.at(tag.version);
    if(flow && flow->discovered) tag.version=flow->version;
    else {
        auto it=m_backgroundVersions.find(key);
        if(it==m_backgroundVersions.end()) it=m_backgroundVersions.emplace(key,NewVersion(Baseline(src,dst,key))).first;
        tag.version=it->second;
    }
    packet->AddPacketTag(tag); return m_versions.at(tag.version);
}

void Experiment::SetPath(FlowState& flow,const Path& path,const std::string& reason) {
    if(flow.current==path) return;
    bool changed=!flow.current.empty();
    m_routeCsv<<Simulator::Now().GetSeconds()<<','<<flow.id<<','<<reason<<','<<PathText(flow.current)<<','<<PathText(path)<<'\n';
    flow.current=path; flow.version=NewVersion(path);
    if(changed) { ++flow.changes; ++m_routeChanges; }
}
}
