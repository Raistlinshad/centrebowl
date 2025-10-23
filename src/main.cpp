#include "LaneClient.h"
#include "BallSensorClientUnix.h"
#include <iostream>
#include <csignal>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <cstring>
#include <nlohmann/json.hpp>

static volatile sig_atomic_t running = 1;
static pid_t daemon_pid = -1;

void signal_handler(int sig) {
    running = 0;
}

bool wait_for_socket(const std::string& path, int max_seconds = 10) {
    for (int i = 0; i < max_seconds * 10; ++i) {
        struct stat st;
        if (stat(path.c_str(), &st) == 0) {
            return true;
        }
        usleep(100000); // 100ms
    }
    return false;
}

int main() {
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // Fork and exec Python daemon
    daemon_pid = fork();
    if (daemon_pid == 0) {
        // Child process - exec Python daemon
        execlp("python3", "python3", "src/ball_sensor_daemon.py", nullptr);
        perror("execlp failed");
        return 1;
    } else if (daemon_pid < 0) {
        perror("fork failed");
        return 1;
    }

    std::cout << "Started Python daemon with PID " << daemon_pid << std::endl;

    // Wait for socket file to appear
    const std::string socket_path = "/tmp/ball_sensor.sock";
    if (!wait_for_socket(socket_path)) {
        std::cerr << "Socket file " << socket_path << " did not appear" << std::endl;
        kill(daemon_pid, SIGTERM);
        waitpid(daemon_pid, nullptr, 0);
        return 1;
    }

    std::cout << "Socket file ready, connecting..." << std::endl;

    // Create and start LaneClient
    LaneClientConfig config;
    config.lane_id = "lane_01";
    config.server_host = "127.0.0.1";
    config.server_port = 50005;
    
    LaneClient lane_client(config);
    if (!lane_client.start()) {
        std::cerr << "Failed to start LaneClient" << std::endl;
        kill(daemon_pid, SIGTERM);
        waitpid(daemon_pid, nullptr, 0);
        return 1;
    }

    std::cout << "LaneClient started" << std::endl;

    // Connect to ball sensor daemon via Unix socket
    BallSensorClientUnix sensor_client(socket_path);
    
    if (!sensor_client.connectSocket(5000)) {
        std::cerr << "Failed to connect to ball sensor daemon" << std::endl;
        lane_client.stop();
        kill(daemon_pid, SIGTERM);
        waitpid(daemon_pid, nullptr, 0);
        return 1;
    }

    std::cout << "Connected to ball sensor daemon" << std::endl;

    // Start receiving messages
    sensor_client.start([&sensor_client](const std::string& line) {
        try {
            auto j = nlohmann::json::parse(line);
            if (j.contains("event") && j["event"] == "ball_detected") {
                std::cout << "Ball detected! Sending LAST_BALL command" << std::endl;
                sensor_client.sendLastBall();
            }
        } catch (const std::exception& e) {
            std::cerr << "Error parsing JSON: " << e.what() << std::endl;
        }
    });

    // Main loop
    while (running) {
        sleep(1);
    }

    std::cout << "Shutting down..." << std::endl;

    // Stop sensor client
    sensor_client.stop();

    // Stop lane client
    lane_client.stop();

    // Terminate Python daemon
    if (daemon_pid > 0) {
        kill(daemon_pid, SIGTERM);
        waitpid(daemon_pid, nullptr, 0);
        std::cout << "Python daemon terminated" << std::endl;
    }

    return 0;
}
