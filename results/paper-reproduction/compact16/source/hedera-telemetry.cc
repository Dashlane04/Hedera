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
void Experiment::AttachTcp(uint32_t id,Ptr<BulkSendApplication> app) {
    auto socket=app->GetSocket();
    if(!socket) throw std::runtime_error("diagnostic TCP socket not created");
    socket->TraceConnectWithoutContext("CongestionWindow",MakeBoundCallback(&Experiment::TcpCwnd,this,id));
    socket->TraceConnectWithoutContext("BytesInFlight",MakeBoundCallback(&Experiment::TcpInflight,this,id));
    socket->TraceConnectWithoutContext("RTT",MakeBoundCallback(&Experiment::TcpRtt,this,id));
    socket->TraceConnectWithoutContext("RTO",MakeBoundCallback(&Experiment::TcpRto,this,id));
    socket->TraceConnectWithoutContext("CongState",MakeBoundCallback(&Experiment::TcpCongestion,this,id));
    socket->TraceConnectWithoutContext("Retransmission",MakeBoundCallback(&Experiment::TcpRetransmit,this,id));
    if(int64_t(id)==m_settings.packetTraceFlow) {
        socket->TraceConnectWithoutContext("Tx",MakeBoundCallback(&Experiment::TcpPacket,this,id,std::string("tx")));
        socket->TraceConnectWithoutContext("Rx",MakeBoundCallback(&Experiment::TcpPacket,this,id,std::string("rx")));
    }
}

void Experiment::TcpCwnd(Experiment* e,uint32_t id,uint32_t,uint32_t value) { e->m_tcp.at(id).cwnd=value; }

void Experiment::TcpInflight(Experiment* e,uint32_t id,uint32_t,uint32_t value) { e->m_tcp.at(id).inflight=value; }

void Experiment::TcpRtt(Experiment* e,uint32_t id,Time,Time value) { e->m_tcp.at(id).rtt=value.GetSeconds(); }

void Experiment::TcpRto(Experiment* e,uint32_t id,Time old,Time value) {
    e->m_tcp.at(id).rto=value.GetSeconds();
    e->m_eventCsv<<Simulator::Now().GetSeconds()<<','<<id<<",rto,"<<old.GetSeconds()<<','<<value.GetSeconds()<<",0\n";
}

void Experiment::TcpCongestion(Experiment* e,uint32_t id,TcpSocketState::TcpCongState_t old,TcpSocketState::TcpCongState_t value) {
    e->m_tcp.at(id).congestion=value;
    e->m_eventCsv<<Simulator::Now().GetSeconds()<<','<<id<<",congestion,"<<old<<','<<value<<",0\n";
}

void Experiment::TcpRetransmit(Experiment* e,uint32_t id,Ptr<const Packet> packet,const TcpHeader& header,
                              const Address&,const Address&,Ptr<const TcpSocketBase>) {
    auto& state=e->m_tcp.at(id); ++state.retransmissions; state.retransmittedBytes+=packet->GetSize();
    e->m_eventCsv<<Simulator::Now().GetSeconds()<<','<<id<<",retransmission,0,"<<header.GetSequenceNumber().GetValue()<<','<<packet->GetSize()<<'\n';
}

void Experiment::TcpPacket(Experiment* e,uint32_t id,std::string direction,Ptr<const Packet> packet,
                           const TcpHeader& header,Ptr<const TcpSocketBase>) {
    e->m_packetCsv<<Simulator::Now().GetSeconds()<<','<<id<<','<<direction<<','<<header.GetSequenceNumber().GetValue()<<','
                 <<header.GetAckNumber().GetValue()<<','<<uint32_t(header.GetFlags())<<','<<packet->GetSize()<<'\n';
}

void Experiment::QueueDrop(Experiment* e,uint32_t link,Ptr<const QueueDiscItem> item) {
    auto ipv4=DynamicCast<const Ipv4QueueDiscItem>(item); if(!ipv4) return;
    const auto& header=ipv4->GetHeader(); if(header.GetProtocol()!=6) return;
    TcpHeader tcp; auto packet=ipv4->GetPacket(); auto tcpBytes=packet->PeekHeader(tcp);
    auto found=e->m_flowIds.find({header.GetSource().Get(),header.GetDestination().Get(),tcp.GetDestinationPort()});
    std::string direction="data";
    if(found==e->m_flowIds.end()) {
        found=e->m_flowIds.find({header.GetDestination().Get(),header.GetSource().Get(),tcp.GetSourcePort()});
        direction="ack";
    }
    if(found==e->m_flowIds.end()) return;
    const auto& edge=e->m_networkLinks.at(link);
    e->m_dropCsv<<Simulator::Now().GetSeconds()<<','<<found->second<<','<<direction<<','<<link<<','<<edge.from<<','<<edge.to<<','
               <<packet->GetSize()-tcpBytes<<','<<tcp.GetSequenceNumber().GetValue()<<','<<uint32_t(tcp.GetFlags())<<'\n';
}

void Experiment::SinkRx(Experiment* self,uint32_t id,Ptr<const Packet> packet,const Address&) {
    auto& flow=self->m_flows.at(id); flow.rx+=packet->GetSize();
    bool acrossCut=(flow.src<self->m_tree.hosts/2)!=(flow.dst<self->m_tree.hosts/2);
    if(acrossCut) self->m_cutRx+=packet->GetSize();
    double now=Simulator::Now().GetSeconds();
    if(now>=self->m_settings.measureStart && now<=self->m_settings.measureEnd) {
        self->m_measureRx+=packet->GetSize(); flow.windowRx+=packet->GetSize();
        if(acrossCut) self->m_measureCutRx+=packet->GetSize();
    }
    if(flow.bytes && flow.finished<0 && flow.rx>=flow.bytes) {
        flow.finished=Simulator::Now().GetSeconds();
        const uint32_t next=id+1;
        if(self->m_settings.workload=="shuffle" && self->m_settings.workloadFile.empty() &&
           next<self->m_flows.size() && self->m_flows[next].src==flow.src)
            Simulator::ScheduleNow(&Experiment::InstallSender,self,next);
    }
}

void Experiment::LinkTx(Experiment* self,uint32_t id,Ptr<const Packet> packet) { self->m_linkBytes.at(id)+=packet->GetSize(); }

void Experiment::CollectStatistics(double now,double elapsed) {
    uint64_t rx=0;
    for(const auto& f:m_flows) rx+=f.rx;
    m_goodputCsv<<now<<','<<(rx-m_lastRx)*8/elapsed<<','<<rx<<','<<(m_cutRx-m_lastCutRx)*8/elapsed<<','<<m_cutRx<<'\n';
    m_lastRx=rx; m_lastCutRx=m_cutRx;
    for(size_t l=0;l<m_networkLinks.size();++l) {
        auto delta=m_linkBytes[l]-m_lastLinkBytes[l];
        m_linkCsv<<now<<','<<l<<','<<m_networkLinks[l].from<<','<<m_networkLinks[l].to<<','<<delta<<','
                 <<delta*8/(elapsed*m_rate)<<','<<m_queues[l]->GetNPackets()<<','<<m_queues[l]->GetStats().nTotalDroppedPackets<<'\n';
        m_lastLinkBytes[l]=m_linkBytes[l];
    }
    m_lastSample=now;
}

void Experiment::ExportResults() {
    uint64_t received=0; uint32_t completed=0,detected=0,finite=0;
    std::vector<double> fcts;
    std::ofstream out(m_settings.output+"/flows.csv");
    out<<"flow_id,src,dst,start,bytes,rx_bytes,completed,finish,fct,detected_large,route_changes,window_rx_bytes,observed_payload_bytes,stop,cohort,first_detected_s\n"<<std::setprecision(12);
    for(const auto& f:m_flows) {
        received+=f.rx; detected+=f.large; bool done=f.finished>=0; completed+=done; finite+=(f.bytes>0);
        if(done) fcts.push_back(f.finished-f.start);
        out<<f.id<<','<<f.src<<','<<f.dst<<','<<f.start<<','<<f.bytes<<','<<f.rx<<','<<done<<','<<f.finished<<','
           <<(done?f.finished-f.start:-1)<<','<<f.large<<','<<f.changes<<','<<f.windowRx<<','<<f.observed<<','<<f.stop<<','<<f.cohort<<','<<f.firstDetected<<'\n';
    }
    std::sort(fcts.begin(),fcts.end());
    double mean=fcts.empty()?0:std::accumulate(fcts.begin(),fcts.end(),0.0)/fcts.size();
    double p95=fcts.empty()?0:fcts.at(std::min(fcts.size()-1,size_t(std::ceil(fcts.size()*0.95)-1)));
    double runtime=m_schedulerTimes.empty()?0:std::accumulate(m_schedulerTimes.begin(),m_schedulerTimes.end(),0.0)/m_schedulerTimes.size();
    std::ofstream summary(m_settings.output+"/summary.json");
    summary<<std::setprecision(12)<<"{\n"
      <<"  \"schema_version\": 4,\n  \"ns3_version\": \"3.47\",\n"
      <<"  \"energy_verification\": "<<(m_settings.checkEnergy?"true":"false")<<",\n"
      <<"  \"algorithm\": \""<<m_settings.algorithm<<"\",\n"
      <<"  \"traffic_mode\": \""<<m_settings.trafficMode<<"\",\n"
      <<"  \"demand_mode\": \""<<m_settings.demandMode<<"\",\n"
      <<"  \"diagnostics\": "<<(m_settings.diagnostics?"true":"false")<<",\n"
      <<"  \"tcp_min_rto_ms\": "<<m_settings.minRtoMs<<",\n"
      <<"  \"tcp_del_ack_ms\": "<<m_settings.delAckMs<<",\n  \"tcp_del_ack_count\": "<<m_settings.delAckCount<<",\n"
      <<"  \"packet_trace_flow\": "<<m_settings.packetTraceFlow<<",\n"
      <<"  \"hash_mode\": \""<<m_settings.hashMode<<"\",\n  \"hash_mix\": \""<<m_settings.hashMix<<"\",\n"
      <<"  \"workload\": \""<<(m_settings.workloadFile.empty()?m_settings.workload:"csv")<<"\",\n"
      <<"  \"k\": "<<m_settings.k<<",\n  \"hosts\": "<<m_tree.hosts<<",\n"
      <<"  \"seed\": "<<m_settings.seed<<",\n  \"run\": "<<m_settings.run<<",\n"
      <<"  \"flows\": "<<m_flows.size()<<",\n  \"finite_flows\": "<<finite<<",\n  \"completed\": "<<completed<<",\n"
      <<"  \"completion_fraction\": ";
    if(finite) summary<<double(completed)/finite; else summary<<"null";
    summary<<",\n"
      <<"  \"received_payload_bytes\": "<<received<<",\n  \"detected_large\": "<<detected<<",\n"
      <<"  \"measurement_start_s\": "<<m_settings.measureStart<<",\n"
      <<"  \"measurement_end_s\": "<<m_settings.measureEnd<<",\n"
      <<"  \"window_goodput_mbps\": "<<m_measureRx*8.0/(m_settings.measureEnd-m_settings.measureStart)/1e6<<",\n"
      <<"  \"cut_payload_goodput_mbps\": "<<m_measureCutRx*8.0/(m_settings.measureEnd-m_settings.measureStart)/1e6<<",\n"
      <<"  \"cut_capacity_mbps\": "<<m_tree.hosts*m_rate/1e6<<",\n"
      <<"  \"cut_definition\": \"bidirectional payload crossing host halves; not aggregate goodput\",\n"
      <<"  \"route_changes\": "<<m_routeChanges<<",\n  \"mean_fct_completed_s\": ";
    if(fcts.empty()) summary<<"null"; else summary<<mean;
    summary<<",\n  \"p95_fct_completed_s\": ";
    if(fcts.empty()) summary<<"null"; else summary<<p95;
    summary<<",\n  \"control_policy\": \""<<m_settings.controlPolicy<<"\",\n"
      <<"  \"control_service_delay_s\": "<<m_settings.controlDelay<<",\n"
      <<"  \"max_plan_age_s\": "<<m_settings.maxPlanAge<<",\n"
      <<"  \"plans_submitted\": "<<m_snapshotId<<",\n  \"plans_installed\": "<<m_plansInstalled<<",\n"
      <<"  \"plans_replaced\": "<<m_plansReplaced<<",\n  \"plans_expired\": "<<m_plansExpired<<",\n"
      <<"  \"inactive_install_skips\": "<<m_inactiveSkipped<<",\n  \"max_waiting_plans\": "<<m_maxWaiting<<",\n"
      <<"  \"pending_plans_at_stop\": "<<(m_controlQueue.Waiting()+(m_controlQueue.BusyId()?1:0))<<",\n"
      <<"  \"mean_scheduler_wall_us\": "<<runtime<<",\n"
      <<"  \"duration_s\": "<<m_settings.duration<<",\n  \"drain_s\": "<<m_settings.drain<<",\n"
      <<"  \"interval_s\": "<<m_settings.interval<<",\n  \"control_delay_s\": "<<m_settings.controlDelay<<",\n"
      <<"  \"link_rate_bps\": "<<m_rate<<",\n  \"threshold_fraction\": "<<m_settings.threshold<<",\n"
      <<"  \"local_probability\": "<<m_settings.localProbability<<",\n"
      <<"  \"edge_probability\": "<<m_settings.edgeProbability<<",\n  \"pod_probability\": "<<m_settings.podProbability<<",\n"
      <<"  \"arrival_stop_s\": "<<m_settings.arrivalStop<<",\n  \"offered_load\": "<<m_settings.offeredLoad<<",\n"
      <<"  \"mean_flow_bytes\": "<<m_settings.meanFlowBytes<<",\n  \"stride\": "<<m_settings.stride<<",\n"
      <<"  \"large_flow_bytes\": "<<m_settings.flowBytes<<",\n  \"requested_flows\": "<<m_settings.flowCount<<",\n"
      <<"  \"sa_iterations\": "<<m_settings.iterations<<",\n  \"idle_timeout_s\": "<<m_settings.idleTimeout<<",\n"
      <<"  \"link_delay\": \""<<m_settings.linkDelay<<"\",\n  \"queue_packets\": "<<m_settings.queuePackets<<",\n"
      <<"  \"tcp\": \"TcpNewReno\",\n  \"forwarding\": \"atomic versioned paths; simulation-only packet tag\",\n"
      <<"  \"reference_delay_matched\": "<<(m_settings.matchReferenceDelay?"true":"false")<<",\n"
      <<"  \"reference_delay_model\": \"missing unloaded propagation and serialization; infinite-capacity internal delay\",\n"
      <<"  \"one_per_host\": "<<(m_settings.onePerHost?"true":"false")<<",\n"
      <<"  \"gff_capacity_boundary\": \"inclusive with 1e-12 tolerance (Fig.5 boundary variant)\",\n"
      <<"  \"detector\": \"source-edge TCP payload bytes, includes retransmissions; FIN/RST or idle expiry\"\n}\n";
    std::cout<<"algorithm="<<m_settings.algorithm<<" hosts="<<m_tree.hosts<<" flows="<<m_flows.size()
             <<" completed="<<completed<<" detected="<<detected<<" reroutes="<<m_routeChanges
             <<" mean_fct_s="<<(fcts.empty()?std::string("n/a"):std::to_string(mean))<<" output="<<m_settings.output<<'\n';
    m_monitor->CheckForLostPackets();
    m_monitor->SerializeToXmlFile(m_settings.output+"/flow-monitor.xml",false,false);
    std::ofstream nodes(m_settings.output+"/nodes.csv"); nodes<<"model_node,ns3_node,kind,host_ip\n";
    for(uint32_t n=0;n<m_nodes.GetN();++n) {
        std::string kind=n<m_tree.hosts?"host":m_settings.algorithm=="nonblocking"?"nonblocking":n<m_tree.hosts+m_tree.edgeCount?"edge":n<m_tree.hosts+2*m_tree.edgeCount?"aggregation":"core";
        nodes<<n<<','<<m_nodes.Get(n)->GetId()<<','<<kind<<',';
        if(n<m_tree.hosts) nodes<<m_hostIps[n];
        nodes<<'\n';
    }
}
}
