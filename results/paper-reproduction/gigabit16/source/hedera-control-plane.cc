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
void Experiment::ControlEvent(const ControlPlan& plan,const std::string& event,int64_t flow) {
    m_controlEvents<<Simulator::Now().GetSeconds()<<','<<plan.id<<','<<plan.snapshot<<','<<event<<','<<flow<<','
                   <<Simulator::Now().GetSeconds()-plan.snapshot<<','<<m_controlQueue.Waiting()<<'\n';
}

void Experiment::SubmitPlan(std::map<uint32_t,Path> paths,double snapshot) {
    ControlPlan plan{++m_snapshotId,snapshot,std::move(paths)};
    ControlEvent(plan,"submit");
    uint64_t replaced=m_controlQueue.Submit(std::move(plan));
    if(replaced) { ++m_plansReplaced; ControlEvent({replaced,m_controlQueue.ReplacedSnapshot(),{}},"replaced"); }
    m_maxWaiting=std::max(m_maxWaiting,m_controlQueue.Waiting()); StartNextPlan();
}

void Experiment::StartNextPlan() {
    if(!m_controlQueue.CanStart()) return;
    auto plan=m_controlQueue.Start(); ControlEvent(plan,"start");
    Simulator::Schedule(Seconds(m_settings.controlDelay),&Experiment::ApplyPlan,this,std::move(plan));
}

void Experiment::ApplyPlan(ControlPlan plan) {
    double now=Simulator::Now().GetSeconds();
    if(plan.id<=m_lastAppliedPlan) throw std::logic_error("stale controller plan order");
    if(m_settings.maxPlanAge>0 && now-plan.snapshot>m_settings.maxPlanAge+1e-9) {
        ++m_plansExpired; ControlEvent(plan,"expired");
    } else {
        for(const auto& [id,path]:plan.paths) {
            auto& flow=m_flows.at(id);
            if(!SwitchFlowActive(flow,now,m_settings.idleTimeout)) {
                ++m_inactiveSkipped; ControlEvent(plan,"skip_inactive",id); continue;
            }
            SetPath(flow,path,m_settings.algorithm); ControlEvent(plan,"flow_install",id);
        }
        ++m_plansInstalled; m_lastAppliedPlan=plan.id; ControlEvent(plan,"install");
    }
    m_controlQueue.Finish(plan.id); StartNextPlan();
}

void Experiment::Tick() {
    double now=Simulator::Now().GetSeconds(),elapsed=now-m_lastSample;
    CollectStatistics(now,elapsed);
    if(now<=m_settings.duration+1e-9) {
        std::vector<Endpoint> endpoints; std::vector<uint32_t> ids;
        for(auto& flow:m_flows) {
            bool selected=PollLargeFlow(flow,now,elapsed,m_rate,m_settings.threshold,m_settings.idleTimeout);
            if(selected) { endpoints.push_back({flow.src,flow.dst}); ids.push_back(flow.id); }
            if(m_settings.diagnostics) {
                const auto& tcp=m_tcp.at(flow.id);
                m_tcpCsv<<now<<','<<flow.id<<','<<flow.rx<<','<<flow.measuredRate<<','<<tcp.cwnd<<','<<tcp.inflight<<','
                        <<tcp.rtt<<','<<tcp.rto<<','<<tcp.congestion<<','<<tcp.retransmissions<<','<<tcp.retransmittedBytes<<'\n';
            }
        }
        if(m_settings.algorithm=="gff" || m_settings.algorithm=="sa") {
            auto start=std::chrono::steady_clock::now();
            DemandResult estimated;
            if(m_settings.demandMode=="natural") estimated=EstimateDemands(endpoints,m_tree.hosts);
            else {
                // Ablation: only replace scheduler demand. Detection, sticky
                // classification and placement are identical. Retransmissions
                // remain in the source-edge observed rate, as in the detector.
                for(auto id:ids) estimated.demand.push_back(m_flows.at(id).measuredRate/m_rate);
            }
            double estimateUs=Micros(start);
            std::vector<Flow> flows;
            for(size_t n=0;n<ids.size();++n) {
                auto& f=m_flows[ids[n]]; flows.push_back({f.id,f.src,f.dst,estimated.demand[n],f.baseline});
            }
            start=std::chrono::steady_clock::now();
            std::map<uint32_t,Path> paths;
            double initialEnergy=0,bestEnergy=0; uint32_t accepted=0;
            if(m_settings.algorithm=="gff") {
                std::map<uint32_t,Path> before;
                for(const auto& f:flows) before[f.id]=m_flows.at(f.id).current;
                initialEnergy=Energy(m_tree,ComputeLoads(m_tree,flows,before));
                paths=m_gff.Place(flows);
                bestEnergy=Energy(m_tree,ComputeLoads(m_tree,flows,paths));
            }
            else {
                auto result=Anneal(m_tree,flows,m_mapping,m_settings.iterations,m_saRng,m_settings.checkEnergy);
                m_mapping=result.mapping; paths=result.paths;
                initialEnergy=result.initialEnergy; bestEnergy=result.bestEnergy; accepted=result.accepted;
            }
            double placementUs=Micros(start); m_schedulerTimes.push_back(estimateUs+placementUs);
            if(m_settings.diagnostics) for(size_t n=0;n<ids.size();++n) {
                const auto& f=m_flows.at(ids[n]);
                m_demandCsv<<now<<','<<f.id<<','<<m_settings.demandMode<<','<<f.measuredRate/m_rate<<','<<estimated.demand[n]<<','
                          <<PathText(f.current)<<','<<PathText(paths.at(f.id))<<'\n';
            }
            m_controllerCsv<<now<<','<<ids.size()<<','<<estimated.rounds<<','<<estimateUs<<','<<placementUs<<','
                           <<initialEnergy<<','<<bestEnergy<<','<<accepted<<'\n';
            SubmitPlan(std::move(paths),now);
        }
    }
    if(now+m_settings.interval<m_settings.duration+m_settings.drain-1e-9)
        Simulator::Schedule(Seconds(m_settings.interval),&Experiment::Tick,this);
}
}
