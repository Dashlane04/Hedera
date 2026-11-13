#ifndef HEDERA_CONTROLLER_H
#define HEDERA_CONTROLLER_H
#include "hedera-core.h"
#include <deque>
#include <string>

namespace hedera {
struct ControlPlan {
    uint64_t id=0;
    double snapshot=0;
    std::map<uint32_t,Path> paths;
};
// One in-service plan. Coalescing only replaces a waiting plan, never the one
// already in service, so a continuous stream of snapshots cannot starve installs.
class ControlQueue {
public:
    explicit ControlQueue(std::string policy="fifo");
    uint64_t Submit(ControlPlan plan); // replaced waiting ID, or zero
    bool CanStart() const { return !m_busy && !m_waiting.empty(); }
    ControlPlan Start();
    void Finish(uint64_t id);
    size_t Waiting() const { return m_waiting.size(); }
    uint64_t BusyId() const { return m_busy; }
    double ReplacedSnapshot() const { return m_replacedSnapshot; }
private:
    std::string m_policy;
    std::deque<ControlPlan> m_waiting;
    uint64_t m_busy=0,m_lastSubmitted=0;
    double m_replacedSnapshot=0;
};
}
#endif
