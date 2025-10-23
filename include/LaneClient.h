#ifndef LANECLIENT_H
#define LANECLIENT_H

#include <string>
#include <thread>
#include <atomic>
#include <functional>
#include <map>
#include <mutex>
#include <nlohmann/json.hpp>

// Minimal settings struct so we can pass config easily
struct LaneClientConfig {
    std::string lane_id;
    std::string server_host = "127.0.0.1";
    int server_port = 50005;
    int heartbeat_interval_seconds = 30;
};

class LaneClient {
public:
    explicit LaneClient(const LaneClientConfig& cfg);
    ~LaneClient();

    // Start network client threads and connect to server
    bool start();

    // Stop client and threads
    void stop();

    // API methods
    bool send_bowler_move(const nlohmann::json& bowler_data, const std::string& to_lane, const std::string& move_id);
    bool send_team_move(const nlohmann::json& team_data, const std::string& to_lane);
    bool send_frame_data(const std::string& bowler_name, int frame_num, const nlohmann::json& frame_data);
    bool send_game_complete(const nlohmann::json& game_data);

    // Register callback for generic incoming messages
    void set_message_callback(std::function<void(const nlohmann::json&)> cb);

    bool is_connected() const;

private:
    LaneClientConfig cfg_;
    std::atomic<bool> running_;
    std::atomic<bool> connected_;
    int sockfd_;

    std::thread reader_thread_;
    std::thread heartbeat_thread_;
    std::mutex send_mutex_;

    std::function<void(const nlohmann::json&)> incoming_cb_;

    bool connect_to_server();
    void disconnect_from_server();
    bool send_json(const nlohmann::json& j);
    void reader_loop();
    void heartbeat_loop();
    std::string get_local_ip();
};

#endif // LANECLIENT_H
