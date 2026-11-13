#include "hedera-controller.h"
#include <stdexcept>

namespace hedera {
ControlQueue::ControlQueue(std::string policy):m_policy(std::move(policy)) {
    if(m_policy!="fifo" && m_policy!="coalesce") throw std::invalid_argument("controlPolicy must be fifo or coalesce");
}
uint64_t ControlQueue::Submit(ControlPlan plan) {
    if(!plan.id || plan.id<=m_lastSubmitted) throw std::invalid_argument("non-monotone snapshot ID");
    m_lastSubmitted=plan.id;
    uint64_t replaced=0;
    if(m_policy=="coalesce" && !m_waiting.empty()) {
        replaced=m_waiting.back().id; m_replacedSnapshot=m_waiting.back().snapshot; m_waiting.back()=std::move(plan);
    } else m_waiting.push_back(std::move(plan));
    return replaced;
}
ControlPlan ControlQueue::Start() {
    if(!CanStart()) throw std::logic_error("controller cannot start another plan");
    auto plan=std::move(m_waiting.front()); m_waiting.pop_front(); m_busy=plan.id; return plan;
}
void ControlQueue::Finish(uint64_t id) {
    if(!id || m_busy!=id) throw std::logic_error("controller completion ID mismatch");
    m_busy=0;
}
}
