#include "hedera-controller.h"
#include "hedera-monitoring.h"
#include "hedera-oracle.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace hedera;
static void Check(bool value,const char* text) { if(!value) throw std::runtime_error(text); }
int main() {
    FlowCounters f; f.discovered=true;
    ObserveSource(f,125000,0.1,false);
    Check(PollLargeFlow(f,0.2,0.1,20000000,0.1,1),"large flow detection");
    Check(f.firstDetected==0.2 && f.measuredRate==10000000,"detector rate/time");
    Check(PollLargeFlow(f,0.3,0.1,20000000,0.1,1),"sticky large classification");
    Check(!SwitchFlowActive(f,1.2,1),"idle soft state expiry");
    ObserveSource(f,0,0.4,true);
    Check(!SwitchFlowActive(f,0.5,1),"FIN prevents delayed installation");
    for(const auto& policy:{"fifo","coalesce"}) {
        ControlQueue queue(policy);
        Check(!queue.Submit({1,0,{}}),"first submission");
        auto first=queue.Start();
        Check(first.id==1 && !queue.CanStart(),"one in-service plan");
        queue.Submit({2,0.1,{}});
        uint64_t replaced=queue.Submit({3,0.2,{}});
        Check(replaced==(std::string(policy)=="coalesce"?2u:0u),"waiting replacement policy");
        queue.Finish(1);
        auto next=queue.Start();
        Check(next.id==(std::string(policy)=="coalesce"?3u:2u),"ordered next plan");
        queue.Finish(next.id);
        if(queue.CanStart()) { auto last=queue.Start(); Check(last.id==3,"FIFO retains waiting plan"); queue.Finish(last.id); }
        Check(queue.Waiting()==0 && queue.BusyId()==0,"drained controller");
        bool rejected=false; try { queue.Submit({3,0.3,{}}); } catch(const std::invalid_argument&) { rejected=true; }
        Check(rejected,"reject stale snapshot ID");
    }
    FatTree tree(4);
    auto empty=ExactDestinationCore(tree,{});
    Check(empty.states==1 && empty.energy==0,"empty oracle");
    std::vector<Flow> flows={{0,0,8,0.6,tree.ViaCore(0,8,0)},{1,4,9,0.6,tree.ViaCore(4,9,0)}};
    auto exact=ExactDestinationCore(tree,flows);
    Check(exact.states==12 && exact.energy<1e-10,"all 4P2 distinct active assignments enumerated");
    // Independently enumerate all 24 full permutations of the destination pod.
    auto map=InitialMapping(tree); double minimum=1e9;
    do {
        std::map<uint32_t,Path> paths;
        for(const auto& flow:flows) paths[flow.id]=tree.ViaCore(flow.src,flow.dst,map[flow.dst]);
        minimum=std::min(minimum,Energy(tree,ComputeLoads(tree,flows,paths)));
    } while(std::next_permutation(map.begin()+8,map.begin()+12));
    Check(std::abs(minimum-exact.energy)<1e-10,"oracle matches independent full permutation search");
    bool bounded=false; try { ExactDestinationCore(tree,flows,11); } catch(const std::length_error&) { bounded=true; }
    Check(bounded,"oracle refuses partial search");
    bool duplicate=false;
    auto duplicates=flows; duplicates.push_back(flows[0]);
    try { ExactDestinationCore(tree,duplicates); } catch(const std::invalid_argument&) { duplicate=true; }
    Check(duplicate,"oracle rejects duplicate flow identities");
    std::mt19937_64 rng(7);
    for(uint32_t steps:{0u,10u,100u,1000u}) {
        auto result=Anneal(tree,flows,{},steps,rng,true);
        Check(result.bestEnergy+1e-9>=exact.energy,"heuristic cannot beat exact objective");
    }
    std::cout<<"PASS: monitoring, FIFO/coalesce lifecycle, exact enumeration, state bound, SA objective\n";
}
