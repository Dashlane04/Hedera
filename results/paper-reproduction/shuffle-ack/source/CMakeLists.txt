build_exec(
  EXECNAME hedera-sim
  SOURCE_FILES hedera-sim.cc hedera-core.cc hedera-monitoring.cc hedera-controller.cc
               hedera-network.cc hedera-data-plane.cc hedera-workload.cc
               hedera-control-plane.cc hedera-telemetry.cc
  LIBRARIES_TO_LINK ${libcore} ${libnetwork} ${libinternet}
                    ${libpoint-to-point} ${libapplications}
                    ${libtraffic-control} ${libflow-monitor}
  EXECUTABLE_DIRECTORY_PATH ${CMAKE_OUTPUT_DIRECTORY}/scratch/hedera
)
