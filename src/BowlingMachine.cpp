/*
  BowlingMachine.cpp
  Initial conversion of machine_poll.py core behaviors:
  - pin state management
  - manual_reset / reset_pins
  - apply pin breaks (sysfs fallback for GPIO)
  - non-blocking process_ball_event() entry point
  This is a minimal, synchronous implementation that mirrors the Python logic.
  Later commits will integrate this with the Asio event loop and the unix-domain
  socket detector (ball_sensor_daemon).
*/

#include "BowlingMachine.h"
#include <chrono>
#include <thread>
#include <fstream>
#include <sstream>
#include <iostream>

using json = nlohmann::json;

static void log_default(const std::string& s) {
    std::cerr << s << std::endl;
}

BowlingMachine::BowlingMachine(const json& settings, std::function<void(const std::string&)> logger, int detection_fd, int control_fd)
    : settings_(settings),
      logger_(logger ? logger : log_default),
      running_(false),
      detection_fd_(detection_fd),
      control_fd_(control_fd),
      gp1_(-1), gp2_(-1), gp3_(-1), gp4_(-1), gp5_(-1),
      gp6_(-1), gp7_(-1), gp8_(-1)
{
    // load lane config (mirror Python behavior)
    std::string lane_id = "1";
    if (settings_.contains("Lane")) lane_id = std::to_string(settings_["Lane"].get<int>());
    json lane_cfg = json::object();
    if (settings_.contains(lane_id)) lane_cfg = settings_[lane_id];

    gp1_ = lane_cfg.value("GP1", 17);
    gp2_ = lane_cfg.value("GP2", 27);
    gp3_ = lane_cfg.value("GP3", 22);
    gp4_ = lane_cfg.value("GP4", 23);
    gp5_ = lane_cfg.value("GP5", 24);
    gp6_ = lane_cfg.value("GP6", 25);
    gp7_ = lane_cfg.value("GP7", 5);
    gp8_ = lane_cfg.value("GP8", 6);

    pins_standing_ = {0,0,0,0,0};
    pin_state_ = {0,0,0,0,0};

    logger_("BowlingMachine: initialized");
}

BowlingMachine::~BowlingMachine() {
    stop();
    cleanup();
}

void BowlingMachine::start() {
    if (running_) return;
    running_ = true;
    logger_("BowlingMachine: start()");
    // Future: spawn background workers if needed (currently synchronous)
}

void BowlingMachine::stop() {
    if (!running_) return;
    running_ = false;
    logger_("BowlingMachine: stop()");
}

void BowlingMachine::manual_reset() {
    std::lock_guard<std::mutex> lk(mtx_);
    logger_("BowlingMachine: Manual reset called");
    _machine_reset();
    pins_standing_ = {0,0,0,0,0};
    pin_state_ = {0,0,0,0,0};
    logger_("BowlingMachine: All pins reset to standing position");
}

void BowlingMachine::reset_pins() {
    manual_reset();
}

std::vector<int> BowlingMachine::get_pin_state() {
    std::lock_guard<std::mutex> lk(mtx_);
    return pins_standing_;
}

void BowlingMachine::cleanup() {
    logger_("BowlingMachine: cleanup()");
    // Unexport GPIOs if sysfs method used
    unexport_gpio(gp1_); unexport_gpio(gp2_); unexport_gpio(gp3_);
    unexport_gpio(gp4_); unexport_gpio(gp5_);
}

void BowlingMachine::process_ball_event() {
    // Non-blocking wrapper for full ball processing. For now, call synchronously.
    logger_("BowlingMachine: process_ball_event()");
    // Example flow: compute control dict and apply pin breaks
    std::vector<int> control(5, 0);
    {
        std::lock_guard<std::mutex> lk(mtx_);
        // control: 1 means apply break (raise pin), mimic Python mapping
        control[0] = pins_standing_[0] == 0 ? 1 : 0; // lTwo
        control[1] = pins_standing_[1] == 0 ? 1 : 0; // lThree
        control[2] = pins_standing_[2] == 0 ? 1 : 0; // cFive
        control[3] = pins_standing_[3] == 0 ? 1 : 0; // rThree
        control[4] = pins_standing_[4] == 0 ? 1 : 0; // rTwo
    }

    _apply_pin_breaks(control);

    // After applying breaks, update pin_state_ and pins_standing_ (placeholder)
    {
        std::lock_guard<std::mutex> lk(mtx_);
        for (size_t i=0;i<pins_standing_.size();++i) {
            // simple heuristic for now: if break applied, mark down
            if (control[i] == 1) {
                pins_standing_[i] = 1;
                pin_state_[i] = 1;
            }
        }
    }

    logger_("BowlingMachine: ball processing completed");
}

void BowlingMachine::_machine_reset() {
    // Basic reset logic: write GPIOs to standing (0) as needed
    logger_("BowlingMachine: _machine_reset()");
    // Sysfs GPIO writes could be used here; for now, log and return
}

void BowlingMachine::_apply_pin_breaks(const std::vector<int>& control) {
    logger_("BowlingMachine: _apply_pin_breaks()");
    // control order: lTwo, lThree, cFive, rThree, rTwo
    // Try sysfs GPIO writes (best-effort); if not available, log the intended state
    auto write_pin = [&](int gpio, int val){
        if (gpio <= 0) return false;
        return write_gpio(gpio, val);
    };

    write_pin(gp1_, control[0]);
    write_pin(gp2_, control[1]);
    write_pin(gp3_, control[2]);
    write_pin(gp4_, control[3]);
    write_pin(gp5_, control[4]);

    // small delay like Python's time.sleep(0.1)
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    // reset all pins to high (1) or to standing depending on hardware polarity
    write_pin(gp1_, 1);
    write_pin(gp2_, 1);
    write_pin(gp3_, 1);
    write_pin(gp4_, 1);
    write_pin(gp5_, 1);

    logger_("BowlingMachine: _apply_pin_breaks finished");
}

bool BowlingMachine::export_gpio(int gpio) {
    if (gpio <= 0) return false;
    try {
        std::ofstream f("/sys/class/gpio/export");
        if (!f) return false;
        f << gpio << std::endl;
        return true;
    } catch(...) {
        return false;
    }
}

bool BowlingMachine::unexport_gpio(int gpio) {
    if (gpio <= 0) return false;
    try {
        std::ofstream f("/sys/class/gpio/unexport");
        if (!f) return false;
        f << gpio << std::endl;
        return true;
    } catch(...) {
        return false;
    }
}

bool BowlingMachine::write_gpio(int gpio, int value) {
    if (gpio <= 0) return false;
    try {
        std::ostringstream path;
        path << "/sys/class/gpio/gpio" << gpio << "/value";
        std::ofstream f(path.str());
        if (!f) return false;
        f << (value ? "1" : "0") << std::endl;
        return true;
    } catch(...) {
        return false;
    }
}