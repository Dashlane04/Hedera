#include "hedera-monitoring.h"
#include <stdexcept>

namespace hedera {
void ObserveSource(FlowCounters& state,uint32_t payload,double now,bool terminated) {
    state.lastSeen=now; state.observed+=payload;
    if(terminated) state.finObserved=true;
}
bool SwitchFlowActive(const FlowCounters& state,double now,double idleTimeout) {
    return state.discovered && !state.finObserved && state.lastSeen>=0 && now-state.lastSeen<=idleTimeout;
}
bool PollLargeFlow(FlowCounters& state,double now,double elapsed,double nicRate,
                   double threshold,double idleTimeout) {
    if(elapsed<=0 || nicRate<=0) throw std::invalid_argument("invalid detector interval/rate");
    state.measuredRate=(state.observed-state.lastObserved)*8.0/elapsed;
    state.lastObserved=state.observed;
    bool active=SwitchFlowActive(state,now,idleTimeout);
    if(active && state.measuredRate>=threshold*nicRate && !state.large) {
        state.large=true; state.firstDetected=now;
    }
    return active && state.large;
}
}
