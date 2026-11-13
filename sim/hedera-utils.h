#ifndef HEDERA_UTILS_H
#define HEDERA_UTILS_H
#include "hedera-core.h"
#include <chrono>
#include <sstream>
namespace hedera {
inline std::string PathText(const Path& path) {
    std::ostringstream out;
    for(size_t n=0;n<path.size();++n) { if(n) out<<'-'; out<<path[n]; }
    return out.str();
}
inline double Micros(std::chrono::steady_clock::time_point begin) {
    return std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-begin).count();
}
}
#endif
