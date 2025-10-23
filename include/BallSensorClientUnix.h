#pragma once
#include <string>
#include <vector>
#include <functional>
#include <thread>
#include <atomic>

class BallSensorClientUnix {
public:
    BallSensorClientUnix(const std::string& path = "/tmp/ball_sensor.sock");
    ~BallSensorClientUnix();

    bool connectSocket(int timeout_ms = 2000);
    void start(std::function<void(const std::string&)> onMessage);
    void sendLastBall();
    void sendPinSet(const std::vector<int>& pins);
    void stop();

private:
    void sendRaw(const std::string& s);

    std::string path_;
    int fd_;
    std::thread reader_;
    std::atomic<bool> running_;
};
