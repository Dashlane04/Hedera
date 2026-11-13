#ifndef HEDERA_NETWORK_H
#define HEDERA_NETWORK_H
#include "hedera-core.h"
#include "hedera-monitoring.h"
#include "hedera-controller.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/traffic-control-module.h"
#include <fstream>
#include <string>
#include <tuple>

namespace hedera {
struct Settings {
    uint32_t k=4, seed=1, run=1, iterations=1000, queuePackets=100, flowCount=32;
    uint64_t flowBytes=8*1024*1024,meanFlowBytes=524288;
    double duration=3, drain=1, interval=0.1, controlDelay=0, threshold=0.1, idleTimeout=1;
    double localProbability=0.5,measureStart=0.2,measureEnd=-1,arrivalStop=-1;
    double edgeProbability=-1,podProbability=0,offeredLoad=0.6,minRtoMs=20,delAckMs=200;
    uint32_t delAckCount=2;
    int32_t packetTraceFlow=-1;
    uint32_t stride=0;
    bool checkEnergy=false, pcap=false,matchReferenceDelay=true,onePerHost=false,diagnostics=false;
    std::string algorithm="ecmp", workload="collision", workloadFile="";
    std::string rate="100Mbps", linkDelay="10us", output="results/demo";
    std::string trafficMode="finite",hashMode="flow",hashMix="legacy",demandMode="natural",controlPolicy="fifo";
    double maxPlanAge=0;
};
struct FlowKey {
    uint32_t srcIp=0,dstIp=0;
    uint16_t srcPort=0,dstPort=0;
    uint8_t protocol=6;
    bool operator<(const FlowKey& other) const {
        return std::tie(srcIp,dstIp,srcPort,dstPort,protocol)<std::tie(other.srcIp,other.dstIp,other.srcPort,other.dstPort,other.protocol);
    }
};
struct FlowState : FlowCounters {
    uint32_t id,src,dst;
    double start,stop;
    std::string cohort="default";
    uint64_t bytes;
    uint16_t port;
    uint64_t rx=0,windowRx=0;
    double finished=-1;
    uint32_t version=0,changes=0;
    Path baseline,current;
};
struct Hop { ns3::Ptr<ns3::NetDevice> device; ns3::Ipv4Address gateway; };
struct TcpSnapshot {
    uint32_t cwnd=0,inflight=0,congestion=0;
    uint64_t retransmissions=0,retransmittedBytes=0;
    double rtt=0,rto=0;
};
class Experiment;
class FlowRouting : public ns3::Ipv4RoutingProtocol {
public:
    static ns3::TypeId GetTypeId();
    void Configure(Experiment* experiment,uint32_t node);
    ns3::Ptr<ns3::Ipv4Route> RouteOutput(ns3::Ptr<ns3::Packet>,const ns3::Ipv4Header&,ns3::Ptr<ns3::NetDevice>,ns3::Socket::SocketErrno&) override;
    bool RouteInput(ns3::Ptr<const ns3::Packet>,const ns3::Ipv4Header&,ns3::Ptr<const ns3::NetDevice>,const UnicastForwardCallback&,const MulticastForwardCallback&,const LocalDeliverCallback&,const ErrorCallback&) override;
    void NotifyInterfaceUp(uint32_t) override {}
    void NotifyInterfaceDown(uint32_t) override {}
    void NotifyAddAddress(uint32_t,ns3::Ipv4InterfaceAddress) override {}
    void NotifyRemoveAddress(uint32_t,ns3::Ipv4InterfaceAddress) override {}
    void SetIpv4(ns3::Ptr<ns3::Ipv4> ipv4) override { m_ipv4=ipv4; }
    void PrintRoutingTable(ns3::Ptr<ns3::OutputStreamWrapper>,ns3::Time::Unit) const override;
private:
    ns3::Ptr<ns3::Ipv4Route> MakeRoute(const ns3::Ipv4Header&,uint32_t next);
    Experiment* m_experiment=nullptr;
    uint32_t m_node=0;
    ns3::Ptr<ns3::Ipv4> m_ipv4;
    std::map<FlowKey,ns3::Time> m_referenceRelease;
};
class Experiment {
public:
    explicit Experiment(Settings settings);
    void Run();
    const FatTree& Tree() const { return m_tree; }
    uint32_t HostFor(ns3::Ipv4Address ip) const;
    const Hop& GetHop(uint32_t from,uint32_t to) const;
    uint32_t FirstHop(uint32_t host) const;
    ns3::Time ForwardingDelay(uint32_t node,const ns3::Ipv4Header& header,uint32_t payloadBytes) const;
    Path PacketPath(uint32_t node,ns3::Ptr<const ns3::Packet> packet,const ns3::Ipv4Header& header);
private:
    Settings m_settings;
    FatTree m_tree;
    ns3::NodeContainer m_nodes;
    std::vector<ns3::Ipv4Address> m_hostIps;
    std::map<uint32_t,uint32_t> m_ipHosts;
    std::map<std::pair<uint32_t,uint32_t>,Hop> m_hops;
    std::vector<ns3::Ptr<ns3::QueueDisc>> m_queues;
    std::vector<Link> m_networkLinks;
    std::vector<uint64_t> m_linkBytes,m_lastLinkBytes;
    std::vector<FlowState> m_flows;
    std::map<std::tuple<uint32_t,uint32_t,uint16_t>,uint32_t> m_flowIds;
    std::map<FlowKey,uint32_t> m_backgroundVersions;
    std::vector<Path> m_versions;
    GlobalFirstFit m_gff;
    std::vector<uint32_t> m_mapping;
    std::mt19937_64 m_workloadRng,m_saRng;
    double m_rate=0,m_lastSample=0;
    uint64_t m_lastRx=0,m_routeChanges=0,m_measureRx=0,m_measureCutRx=0;
    uint64_t m_cutRx=0,m_lastCutRx=0;
    std::vector<double> m_schedulerTimes;
    ControlQueue m_controlQueue;
    uint64_t m_snapshotId=0,m_lastAppliedPlan=0,m_plansInstalled=0,m_plansReplaced=0,m_plansExpired=0,m_inactiveSkipped=0;
    size_t m_maxWaiting=0;
    std::vector<TcpSnapshot> m_tcp;
    std::ofstream m_linkCsv,m_controllerCsv,m_routeCsv,m_goodputCsv;
    std::ofstream m_tcpCsv,m_eventCsv,m_dropCsv,m_demandCsv,m_packetCsv;
    std::ofstream m_controlEvents;
    ns3::FlowMonitorHelper m_flowHelper;
    ns3::Ptr<ns3::FlowMonitor> m_monitor;
    void BuildNetwork();
    void MakeWorkload();
    void InstallApplications();
    void AttachTcp(uint32_t id,ns3::Ptr<ns3::BulkSendApplication> app);
    void Tick();
    void SubmitPlan(std::map<uint32_t,Path> paths,double snapshot);
    void StartNextPlan();
    void ApplyPlan(ControlPlan plan);
    void ControlEvent(const ControlPlan& plan,const std::string& event,int64_t flow=-1);
    void CollectStatistics(double now,double elapsed);
    void SetPath(FlowState& flow,const Path& path,const std::string& reason);
    void ExportResults();
    uint32_t NewVersion(const Path& path);
    Path Baseline(uint32_t src,uint32_t dst,const FlowKey& key) const;
    Path EcmpPath(uint32_t src,uint32_t dst,const FlowKey& key) const;
    static void SinkRx(Experiment*,uint32_t,ns3::Ptr<const ns3::Packet>,const ns3::Address&);
    static void LinkTx(Experiment*,uint32_t,ns3::Ptr<const ns3::Packet>);
    static void QueueDrop(Experiment*,uint32_t,ns3::Ptr<const ns3::QueueDiscItem>);
    static void TcpCwnd(Experiment*,uint32_t,uint32_t,uint32_t);
    static void TcpInflight(Experiment*,uint32_t,uint32_t,uint32_t);
    static void TcpRtt(Experiment*,uint32_t,ns3::Time,ns3::Time);
    static void TcpRto(Experiment*,uint32_t,ns3::Time,ns3::Time);
    static void TcpCongestion(Experiment*,uint32_t,ns3::TcpSocketState::TcpCongState_t,ns3::TcpSocketState::TcpCongState_t);
    static void TcpRetransmit(Experiment*,uint32_t,ns3::Ptr<const ns3::Packet>,const ns3::TcpHeader&,
                              const ns3::Address&,const ns3::Address&,ns3::Ptr<const ns3::TcpSocketBase>);
    static void TcpPacket(Experiment*,uint32_t,std::string,ns3::Ptr<const ns3::Packet>,const ns3::TcpHeader&,
                          ns3::Ptr<const ns3::TcpSocketBase>);
};
}
#endif
