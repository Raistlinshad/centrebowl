#ifndef BOWLINGMACHINE_H
#define BOWLINGMACHINE_H

#include <vector>
#include <string>
#include <functional>
#include <mutex>
#include <atomic>
#include <nlohmann/json.hpp>

class BowlingMachine {
public:
    // logger: function taking a log string (simple abstraction)
    BowlingMachine(const nlohmann::json& settings, std::function<void(const std::string&)> logger, int detection_fd = -1, int control_fd = -1);
    ~BowlingMachine();

    // Start/stop any internal threads if used
    void start();
    void stop();

    // Core operations
    void manual_reset();
    void reset_pins();
    std::vector<int> get_pin_state();
    void cleanup();

    // Process a detected ball event (non-blocking wrapper)
    void process_ball_event();

private:
    nlohmann::json settings_;
    std::function<void(const std::string&)> logger_;
    std::mutex mtx_;
    std::atomic<bool> running_;

    // GPIO pins (BCM numbering)
    int gp1_, gp2_, gp3_, gp4_, gp5_, gp6_, gp7_, gp8_;

    // Pin states: 0 = standing, 1 = down
    std::vector<int> pins_standing_;
    std::vector<int> pin_state_;

    // File descriptors for detection/control sockets (if used)
    int detection_fd_;
    int control_fd_;

    // Internal helpers
    void _machine_reset();
    void _apply_pin_breaks(const std::vector<int>& control);

    // Low-level GPIO helpers (sysfs-based fallback)
    bool export_gpio(int gpio);
    bool unexport_gpio(int gpio);
    bool write_gpio(int gpio, int value);
};

#endif // BOWLINGMACHINE_H
