#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <string>
#include <iostream>
#include <thread>
#include <atomic>
#include <sstream>
#include <vector>
#include <nlohmann/json.hpp> // optional: if you want JSON parsing (or parse manually)

class BallSensorClientUnix {
public:
    BallSensorClientUnix(const std::string& path = "/tmp/ball_sensor.sock")
        : path_(path), fd_(-1), running_(false) {}

    ~BallSensorClientUnix() {
        stop();
    }

    bool connectSocket(int timeout_ms = 2000) {
        fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            perror("socket");
            return false;
        }
        sockaddr_un addr{};
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, path_.c_str(), sizeof(addr.sun_path)-1);

        // Non-blocking connect with timeout
        int flags = fcntl(fd_, F_GETFL, 0);
        fcntl(fd_, F_SETFL, flags | O_NONBLOCK);
        int res = ::connect(fd_, (sockaddr*)&addr, sizeof(addr));
        if (res < 0 && errno != EINPROGRESS) {
            perror("connect");
            close(fd_);
            fd_ = -1;
            return false;
        }

        // Wait for writable or timeout
        fd_set wf;
        FD_ZERO(&wf);
        FD_SET(fd_, &wf);
        timeval tv{};
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;
        res = select(fd_ + 1, nullptr, &wf, nullptr, &tv);
        if (res <= 0) {
            std::cerr << "connect timeout or error\n";
            close(fd_);
            fd_ = -1;
            return false;
        }

        // Restore blocking mode
        fcntl(fd_, F_SETFL, flags);
        return true;
    }

    void start(std::function<void(const std::string&)> onMessage) {
        if (fd_ < 0) return;
        running_ = true;
        reader_ = std::thread([this, onMessage]() {
            std::string buffer;
            char tmp[4096];
            while (running_) {
                ssize_t n = read(fd_, tmp, sizeof(tmp)-1);
                if (n > 0) {
                    tmp[n] = '\0';
                    buffer.append(tmp, tmp + n);
                    size_t pos;
                    while ((pos = buffer.find('\n')) != std::string::npos) {
                        std::string line = buffer.substr(0, pos);
                        buffer.erase(0, pos + 1);
                        if (!line.empty()) onMessage(line);
                    }
                } else if (n == 0) {
                    std::cerr << "Socket closed by server\n";
                    running_ = false;
                    break;
                } else {
                    // EAGAIN/EINTR could be retried
                    std::this_thread::sleep_for(std::chrono::milliseconds(10));
                }
            }
        });
    }

    void sendLastBall() {
        sendRaw("LAST_BALL\n");
    }

    void sendPinSet(const std::vector<int>& pins) {
        std::ostringstream oss;
        oss << "PIN_SET [";
        for (size_t i = 0; i < pins.size(); ++i) {
            if (i) oss << ",";
            oss << pins[i];
        }
        oss << "]\n";
        sendRaw(oss.str());
    }

    void stop() {
        running_ = false;
        if (reader_.joinable()) reader_.join();
        if (fd_ != -1) close(fd_);
        fd_ = -1;
    }

private:
    void sendRaw(const std::string& s) {
        if (fd_ < 0) return;
        ssize_t n = write(fd_, s.c_str(), s.size());
        if (n < 0) perror("write");
    }

    std::string path_;
    int fd_;
    std::thread reader_;
    std::atomic<bool> running_;
};
