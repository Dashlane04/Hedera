#ifndef HEDERA_MONITORING_H
#define HEDERA_MONITORING_H
#include <cstdint>

namespace hedera {
// Switch-observable soft state. Receiver completion/application stop are not inputs.
struct FlowCounters {
    uint64_t observed=0,lastObserved=0;
    double lastSeen=-1,measuredRate=0,firstDetected=-1;
    bool discovered=false,finObserved=false,large=false;
};
void ObserveSource(FlowCounters& state,uint32_t payload,double now,bool terminated);
bool PollLargeFlow(FlowCounters& state,double now,double elapsed,double nicRate,
                   double threshold,double idleTimeout);
bool SwitchFlowActive(const FlowCounters& state,double now,double idleTimeout);
}
#endif
