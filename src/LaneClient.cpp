#include "LaneClient.h"

#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <netdb.h>
#include <sstream>
#include <iostream>
#include <cstring>
#include <chrono>

using json = nlohmann::json;

LaneClient::LaneClient(const LaneClientConfig& cfg)
    : cfg_(cfg), running_(false), connected_(false), sockfd_(-1) {}

LaneClient::~LaneClient() {
    stop();
}

bool LaneClient::start() {
    if (running_) return true;
    running_ = true;

    // start threads
    reader_thread_ = std::thread(&LaneClient::reader_loop, this);
    heartbeat_thread_ = std::thread(&LaneClient::heartbeat_loop, this);
    return true;
}

void LaneClient::stop() {
    if (!running_) return;
    running_ = false;
    disconnect_from_server();
    if (reader_thread_.joinable()) reader_thread_.join();
    if (heartbeat_thread_.joinable()) heartbeat_thread_.join();
}

bool LaneClient::is_connected() const { return connected_; }

bool LaneClient::connect_to_server() {
    if (connected_) return true;

    sockfd_ = socket(AF_INET, SOCK_STREAM, 0);
    if (sockfd_ < 0) {
        perror("socket");
        return false;
    }

    struct sockaddr_in serv_addr;
    memset(&serv_addr, 0, sizeof(serv_addr));
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(cfg_.server_port);

    struct hostent* he = gethostbyname(cfg_.server_host.c_str());
    if (!he) {
        std::cerr << "Hostname resolution failed for " << cfg_.server_host << "\n";
        close(sockfd_);
        sockfd_ = -1;
        return false;
    }
    memcpy(&serv_addr.sin_addr, he->h_addr_list[0], he->h_length);

    if (connect(sockfd_, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) < 0) {
        perror("connect");
        close(sockfd_);
        sockfd_ = -1;
        return false;
    }

    connected_ = true;

    json registration = {
        {"type", "registration"},
        {"lane_id", cfg_.lane_id},
        {"startup", true},
        {"client_ip", get_local_ip()},
        {"listen_port", 0},
        {"timestamp", std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::system_clock::now().time_since_epoch()).count()}
    };
    send_json(registration);

    std::cerr << "[LaneClient] Connected to server " << cfg_.server_host << ":" << cfg_.server_port << "\n";
    return true;
}

void LaneClient::disconnect_from_server() {
    if (sockfd_ != -1) {
        shutdown(sockfd_, SHUT_RDWR);
        close(sockfd_);
        sockfd_ = -1;
    }
    connected_ = false;
}

bool LaneClient::send_json(const json& j) {
    if (!connected_ || sockfd_ < 0) return false;
    std::string s = j.dump();
    s.push_back('\n');

    std::lock_guard<std::mutex> lock(send_mutex_);
    ssize_t n = send(sockfd_, s.data(), s.size(), 0);
    if (n < 0) {
        perror("send");
        disconnect_from_server();
        return false;
    }
    return true;
}

void LaneClient::reader_loop() {
    const int reconnect_delay_ms = 2000;
    std::string buffer;
    buffer.reserve(4096);

    while (running_) {
        if (!connected_) {
            if (!connect_to_server()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms));
                continue;
            }
        }

        char tmp[4096];
        ssize_t n = recv(sockfd_, tmp, sizeof(tmp), 0);
        if (n > 0) {
            buffer.append(tmp, tmp + n);
            size_t pos;
            while ((pos = buffer.find('\n')) != std::string::npos) {
                std::string line = buffer.substr(0, pos);
                buffer.erase(0, pos + 1);
                if (line.empty()) continue;
                try {
                    json msg = json::parse(line);
                    if (incoming_cb_) incoming_cb_(msg);
                } catch (const std::exception& ex) {
                    std::cerr << "[LaneClient] JSON parse error: " << ex.what() << " raw: " << line << "\n";
                }
            }
        } else if (n == 0) {
            std::cerr << "[LaneClient] Server closed connection\n";
            disconnect_from_server();
            std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms));
        } else {
            perror("recv");
            disconnect_from_server();
            std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms));
        }
    }
}

void LaneClient::heartbeat_loop() {
    while (running_) {
        if (connected_) {
            json heartbeat = {
                {"type", "heartbeat"},
                {"lane_id", cfg_.lane_id},
                {"timestamp", std::chrono::duration_cast<std::chrono::seconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count()}
            };
            send_json(heartbeat);
        }
        std::this_thread::sleep_for(std::chrono::seconds(cfg_.heartbeat_interval_seconds));
    }
}

void LaneClient::set_message_callback(std::function<void(const json&)> cb) {
    incoming_cb_ = std::move(cb);
}

std::string LaneClient::get_local_ip() {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) return "127.0.0.1";
    sockaddr_in serv{};
    serv.sin_family = AF_INET;
    serv.sin_port = htons(80);
    inet_pton(AF_INET, "8.8.8.8", &serv.sin_addr);
    int res = connect(sock, (sockaddr*)&serv, sizeof(serv));
    if (res < 0) { close(sock); return "127.0.0.1"; }
    sockaddr_in name{};
    socklen_t namelen = sizeof(name);
    getsockname(sock, (sockaddr*)&name, &namelen);
    char buf[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &name.sin_addr, buf, sizeof(buf));
    close(sock);
    return std::string(buf);
}

// API methods:
bool LaneClient::send_bowler_move(const json& bowler_data, const std::string& to_lane, const std::string& move_id) {
    if (!connected_) return false;
    json message = {
        {"type", "bowler_move"},
        {"data", {
            {"to_lane", to_lane},
            {"bowler_data", bowler_data},
            {"move_id", move_id}
        }}
    };
    return send_json(message);
}

bool LaneClient::send_team_move(const json& team_data, const std::string& to_lane) {
    if (!connected_) return false;
    json message = {
        {"type", "team_move"},
        {"data", {
            {"to_lane", to_lane},
            {"from_lane", cfg_.lane_id},
            {"bowlers", team_data.value("bowlers", json::array())},
            {"game_number", team_data.value("game_number", 1)}
        }}
    };
    return send_json(message);
}

bool LaneClient::send_frame_data(const std::string& bowler_name, int frame_num, const json& frame_data) {
    if (!connected_) return false;
    json message = {
        {"type", "frame_data"},
        {"data", {
            {"lane_id", cfg_.lane_id},
            {"bowler_name", bowler_name},
            {"frame_num", frame_num},
            {"frame_data", frame_data},
            {"timestamp", std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::system_clock::now().time_since_epoch()).count()}
        }}
    };
    return send_json(message);
}

bool LaneClient::send_game_complete(const json& game_data) {
    if (!connected_) return false;
    json message = {
        {"type", "game_complete"},
        {"data", {
            {"lane_id", cfg_.lane_id},
            {"game_data", game_data},
            {"timestamp", std::chrono::duration_cast<std::chrono::seconds>(
                std::chrono::system_clock::now().time_since_epoch()).count()}
        }}
    };
    return send_json(message);
}
