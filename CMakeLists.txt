cmake_minimum_required(VERSION 3.10)
project(centrebowl_cpp VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

find_package(nlohmann_json QUIET)

if (NOT nlohmann_json_FOUND)
  message(STATUS "nlohmann_json not found by find_package. You can install libnlohmann-json-dev or add single-header to include/")
endif()

add_executable(centrebowl_cpp
    src/main.cpp
    src/LaneClient.cpp
)

target_include_directories(centrebowl_cpp PRIVATE include)

if (nlohmann_json_FOUND)
  target_link_libraries(centrebowl_cpp PRIVATE nlohmann_json::nlohmann_json)
else()
  message(STATUS "Building without find_package; ensure nlohmann/json.hpp is available in include/")
endif()

find_package(Threads REQUIRED)
target_link_libraries(centrebowl_cpp PRIVATE Threads::Threads)
