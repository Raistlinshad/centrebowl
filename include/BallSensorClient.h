#pragma once
#include <string>
#include <vector>
#include <functional>
#include <thread>
#include <atomic>

class BallSensorClient {
public:
    // host: IP or hostname for the daemon, port: TCP port
    BallSensorClient(const std::string& host, int port);
    ~BallSensorClient();

    // connect to the daemon (TCP). Returns true on success.
    bool connectToDaemon();

    // start receiving sensor messages and calling the callback with parsed vector<int>
    void startReceiving(std::function<void(const std::vector<int>&)> onSensors);

    // send a 'LAST_BALL' command to daemon
    bool sendLastBall();

    // send a 'PIN_SET' command with JSON array (e.g. [5,6,13,19,26])
    bool sendPinSet(const std::vector<int>& pins);

private:
    std::string host_;
    int port_;
    int sockfd_;
    std::thread recvThread_;
    std::atomic<bool> running_;

    bool sendRaw(const std::string& data);
    void receiveLoop(std::function<void(const std::vector<int>&)> onSensors);
    std::vector<int> parseSensorLine(const std::string& line);
};
