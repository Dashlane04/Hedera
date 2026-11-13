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
Experiment::Experiment(Settings settings)
    :m_settings(std::move(settings)),m_tree(m_settings.k),m_gff(m_tree),
     m_workloadRng((uint64_t(m_settings.seed)<<32)|m_settings.run),
     m_saRng(HashWords({m_settings.seed,m_settings.run,0x5341})),m_controlQueue(m_settings.controlPolicy) {
    if(m_settings.measureEnd<0) m_settings.measureEnd=m_settings.duration;
    if(m_settings.arrivalStop<0) m_settings.arrivalStop=m_settings.measureEnd;
    const auto& s=m_settings;
    for(double value:{s.duration,s.drain,s.interval,s.controlDelay,s.threshold,s.idleTimeout,s.localProbability,s.measureStart,s.measureEnd,s.arrivalStop,s.edgeProbability,s.podProbability,s.offeredLoad,s.minRtoMs,s.delAckMs,s.maxPlanAge})
        if(!std::isfinite(value)) throw std::invalid_argument("numeric settings must be finite");
    if(!s.seed) throw std::invalid_argument("seed must be positive");
    if(s.algorithm!="ecmp" && s.algorithm!="gff" && s.algorithm!="sa" && s.algorithm!="nonblocking") throw std::invalid_argument("unknown algorithm");
    if(s.trafficMode!="finite" && s.trafficMode!="sustained") throw std::invalid_argument("trafficMode must be finite or sustained");
    if(s.hashMode!="flow" && s.hashMode!="destination") throw std::invalid_argument("unknown hashMode");
    if(s.hashMix!="legacy" && s.hashMix!="avalanche") throw std::invalid_argument("unknown hashMix");
    if(s.demandMode!="natural" && s.demandMode!="measured") throw std::invalid_argument("unknown demandMode");
    if(s.minRtoMs<=0) throw std::invalid_argument("minRtoMs must be positive");
    if(s.delAckMs<=0 || !s.delAckCount || s.packetTraceFlow < -1 || (s.packetTraceFlow>=0 && !s.diagnostics))
        throw std::invalid_argument("invalid delayed ACK or packet trace settings");
    if(s.measureEnd<=s.measureStart || s.measureEnd>s.duration || s.arrivalStop<=0.2 || s.arrivalStop>s.duration)
        throw std::invalid_argument("invalid measurement/arrival window");
    if(s.edgeProbability < -1 || s.edgeProbability>1 || s.podProbability<0 || s.edgeProbability+s.podProbability>1 || s.offeredLoad<=0 || !s.meanFlowBytes)
        throw std::invalid_argument("invalid workload parameters");
    if(s.duration<=0.3 || s.drain<=0 || s.interval<=0 || s.controlDelay<0 || s.maxPlanAge<0 || s.idleTimeout<s.interval)
        throw std::invalid_argument("invalid duration/drain/interval/delay/idleTimeout");
    if(s.threshold<=0 || s.threshold>=1 || s.localProbability<0 || s.localProbability>1 || !s.flowBytes || !s.queuePackets || s.measureStart<0 || s.measureStart>=s.duration)
        throw std::invalid_argument("invalid threshold/localProbability/flowBytes/queuePackets");
    for(double value:{s.schedulePeriod,s.failAt,s.failureNotice,s.controlComputeMs})
        if(!std::isfinite(value)) throw std::invalid_argument("invalid experiment timing");
    if(s.schedulePeriod<0 || s.failureNotice<0 || s.controlComputeMs<0 ||
       (s.failAt>=0 && (s.failAt>=s.duration || s.algorithm=="nonblocking")))
        throw std::invalid_argument("invalid scheduling period or fabric outage");
    m_nextPlacement=s.schedulePeriod>0?s.schedulePeriod:s.interval;
    m_rate=DataRate(s.rate).GetBitRate();
    if(m_rate<=0) throw std::invalid_argument("rate must be positive");
}

void Experiment::Run() {
    std::filesystem::create_directories(m_settings.output);
    if(std::filesystem::exists(m_settings.output+"/summary.json")) throw std::runtime_error("output already contains summary.json; choose a new --output");
    RngSeedManager::SetSeed(m_settings.seed); RngSeedManager::SetRun(m_settings.run);
    Config::SetDefault("ns3::TcpL4Protocol::SocketType",TypeIdValue(TcpNewReno::GetTypeId()));
    Config::SetDefault("ns3::TcpSocket::SegmentSize",UintegerValue(1448));
    Config::SetDefault("ns3::TcpSocket::SndBufSize",UintegerValue(4*1024*1024));
    Config::SetDefault("ns3::TcpSocket::RcvBufSize",UintegerValue(4*1024*1024));
    Config::SetDefault("ns3::TcpSocketBase::MinRto",TimeValue(Seconds(m_settings.minRtoMs/1000.0)));
    Config::SetDefault("ns3::TcpSocket::DelAckTimeout",TimeValue(Seconds(m_settings.delAckMs/1000.0)));
    Config::SetDefault("ns3::TcpSocket::DelAckCount",UintegerValue(m_settings.delAckCount));
    m_linkCsv.open(m_settings.output+"/links.csv"); m_linkCsv<<"time,link_id,from,to,tx_bytes,utilization,queue_packets,drops_total\n";
    m_controllerCsv.open(m_settings.output+"/controller.csv"); m_controllerCsv<<"time,large_flows,demand_rounds,estimate_us,placement_us,initial_energy,best_energy,accepted\n";
    m_routeCsv.open(m_settings.output+"/routes.csv"); m_routeCsv<<"time,flow_id,reason,old_path,new_path\n";
    m_goodputCsv.open(m_settings.output+"/goodput.csv"); m_goodputCsv<<"time,payload_bps,cumulative_payload_bytes,cut_payload_bps,cumulative_cut_payload_bytes\n";
    if(m_settings.diagnostics) {
        m_tcpCsv.open(m_settings.output+"/tcp-samples.csv");
        m_tcpCsv<<std::setprecision(12)<<"time,flow_id,rx_bytes,observed_payload_bps,cwnd_bytes,inflight_bytes,rtt_s,rto_s,congestion_state,retransmissions,retransmitted_bytes\n";
        m_eventCsv.open(m_settings.output+"/tcp-events.csv");
        m_eventCsv<<std::setprecision(12)<<"time,flow_id,event,old_value,new_value,payload_bytes\n";
        m_dropCsv.open(m_settings.output+"/queue-drops.csv");
        m_dropCsv<<std::setprecision(12)<<"time,flow_id,direction,link_id,from,to,payload_bytes,sequence,tcp_flags\n";
        m_demandCsv.open(m_settings.output+"/controller-flows.csv");
        m_demandCsv<<std::setprecision(12)<<"time,flow_id,demand_mode,measured_fraction,selected_demand,current_path,planned_path\n";
        if(m_settings.packetTraceFlow>=0) {
            m_packetCsv.open(m_settings.output+"/tcp-packets.csv");
            m_packetCsv<<std::setprecision(12)<<"time,flow_id,direction,sequence,ack,tcp_flags,packet_trace_bytes\n";
        }
    }
    m_controlEvents.open(m_settings.output+"/control-events.csv");
    m_controlEvents<<std::setprecision(12)<<"time,plan_id,snapshot_time,event,flow_id,age_s,waiting\n";
    if(m_settings.switchControl) {
        m_switchEvents.open(m_settings.output+"/switch-control.csv");
        m_switchEvents<<std::setprecision(12)<<"plan_id,time,phase,switch,entries,bytes\n";
    }
    if(m_settings.failAt>=0) {
        m_failureEvents.open(m_settings.output+"/failure.csv");
        m_failureEvents<<"time,event,from,to,affected_flows\n";
        Simulator::Schedule(Seconds(m_settings.failAt),&Experiment::FailFabricLink,this);
    }
    BuildNetwork(); MakeWorkload(); InstallApplications(); m_monitor=m_flowHelper.InstallAll();
    Simulator::Schedule(Seconds(m_settings.interval),&Experiment::Tick,this);
    Simulator::Stop(Seconds(m_settings.duration+m_settings.drain)); Simulator::Run();
    ExportResults(); Simulator::Destroy();
}
}
