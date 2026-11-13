#include "hedera-network.h"
#include <iostream>
int main(int argc,char** argv) {
    hedera::Settings s;
    ns3::CommandLine cmd(__FILE__);
    cmd.AddValue("algorithm","ecmp, gff, sa, nonblocking",s.algorithm);
    cmd.AddValue("k","Even fat-tree radix >=4",s.k);
    cmd.AddValue("workload","single, collision, permutation, mixed, staggered, hotspot, stride, random-bijection, poisson, phased",s.workload);
    cmd.AddValue("workloadFile","CSV src,dst,start,bytes[,port,stop,cohort] overrides generated workload",s.workloadFile);
    cmd.AddValue("flows","Flow count for mixed/staggered/hotspot",s.flowCount);
    cmd.AddValue("flowBytes","Bytes per large transfer",s.flowBytes);
    cmd.AddValue("duration","Source stop time in seconds",s.duration);
    cmd.AddValue("measureStart","Goodput measurement window begins here, seconds",s.measureStart);
    cmd.AddValue("measureEnd","Measurement end, seconds; -1 means source stop",s.measureEnd);
    cmd.AddValue("trafficMode","finite or sustained (MaxBytes=0)",s.trafficMode);
    cmd.AddValue("hashMode","flow (5-tuple) or destination (paper-style fields)",s.hashMode);
    cmd.AddValue("hashMix","legacy FNV low bits or avalanche finalization",s.hashMix);
    cmd.AddValue("demandMode","natural estimator or measured source-edge payload rate / NIC",s.demandMode);
    cmd.AddValue("diagnostics","Log TCP, queue-drop and per-flow scheduling diagnostics",s.diagnostics);
    cmd.AddValue("minRtoMs","TCP minimum retransmission timeout, milliseconds",s.minRtoMs);
    cmd.AddValue("delAckMs","TCP delayed ACK timeout, milliseconds",s.delAckMs);
    cmd.AddValue("delAckCount","ACK every N packets (1 disables delayed ACK waiting)",s.delAckCount);
    cmd.AddValue("packetTraceFlow","Diagnostic sender packet trace flow id; -1 disables",s.packetTraceFlow);
    cmd.AddValue("matchReferenceDelay","Match unloaded nonblocking propagation and serialization",s.matchReferenceDelay);
    cmd.AddValue("onePerHost","Use each source once before repeating in staggered/mixed",s.onePerHost);
    cmd.AddValue("stride","Host offset for stride workload; 0 means N/2",s.stride);
    cmd.AddValue("arrivalStop","Last Poisson arrival, seconds; -1 means measureEnd",s.arrivalStop);
    cmd.AddValue("meanFlowBytes","Mean exponential flow size for poisson workload",s.meanFlowBytes);
    cmd.AddValue("offeredLoad","Poisson offered bytes / aggregate NIC capacity",s.offeredLoad);
    cmd.AddValue("edgeProbability","Same-edge probability; -1 uses legacy locality mode",s.edgeProbability);
    cmd.AddValue("podProbability","Same-pod but different-edge probability",s.podProbability);
    cmd.AddValue("drain","Extra time with sinks running",s.drain);
    cmd.AddValue("interval","Statistics/scheduling interval, seconds",s.interval);
    cmd.AddValue("controlDelay","Serial controller service/install delay per plan, seconds",s.controlDelay);
    cmd.AddValue("controlPolicy","fifo or coalesce waiting snapshots",s.controlPolicy);
    cmd.AddValue("maxPlanAge","Skip plans older than this many seconds; 0 disables age limit",s.maxPlanAge);
    cmd.AddValue("threshold","Large-flow threshold as fraction of NIC rate",s.threshold);
    cmd.AddValue("idleTimeout","Flow idle expiry time, seconds; >= interval",s.idleTimeout);
    cmd.AddValue("iterations","SA steps per period",s.iterations);
    cmd.AddValue("checkEnergy","Check every SA delta against full recomputation",s.checkEnergy);
    cmd.AddValue("rate","Link rate",s.rate);
    cmd.AddValue("linkDelay","Propagation delay per link",s.linkDelay);
    cmd.AddValue("queuePackets","FIFO queue disc capacity; device queue is 1 packet",s.queuePackets);
    cmd.AddValue("localProbability","Same-pod probability in staggered workload",s.localProbability);
    cmd.AddValue("seed","Independent scenario seed",s.seed);
    cmd.AddValue("run","ns-3 RNG run index",s.run);
    cmd.AddValue("output","New output directory",s.output);
    cmd.AddValue("pcap","Enable packet capture on all links (large files)",s.pcap);
    cmd.Parse(argc,argv);
    try { hedera::Experiment experiment(s); experiment.Run(); }
    catch(const std::exception& error) { std::cerr<<"ERROR: "<<error.what()<<'\n'; ns3::Simulator::Destroy(); return 1; }
    return 0;
}
