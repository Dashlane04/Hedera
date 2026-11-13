#ifndef HEDERA_ORACLE_H
#define HEDERA_ORACLE_H
#include "hedera-core.h"
namespace hedera {
struct OracleResult {
    std::vector<uint32_t> mapping;
    std::map<uint32_t,Path> paths;
    double energy=0;
    uint64_t states=0;
};
// Exact only over the same destination-core bijection space as SA. Inactive
// destination permutations are equivalent and enumerated once. Throws before
// search if the complete enumeration would exceed maxStates; never truncates.
OracleResult ExactDestinationCore(const FatTree& tree,const std::vector<Flow>& flows,
                                  uint64_t maxStates=1000000);
}
#endif
