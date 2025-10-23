#include "PinManager.h"
#include <thread>
#include <chrono>

PinManager::PinManager(const std::vector<int>& pins) : pinMap_(pins) {
    // Setup pins for output if you have a GPIO library.
    std::cout << "[PinManager] Initialized with " << pins.size() << " pins\n";
}

void PinManager::setPinMap(const std::vector<int>& pins) {
    std::lock_guard<std::mutex> lock(mtx_);
    pinMap_ = pins;
    std::cout << "[PinManager] Pin map updated: ";
    for (size_t i = 0; i < pinMap_.size(); ++i) {
        std::cout << pinMap_[i] << (i + 1 < pinMap_.size() ? "," : "");
    }
    std::cout << "\n";
    // If you need to call GPIO library to reconfigure pins, do so here.
}

int PinManager::getPinForSensor(size_t sensorIndex) const {
    std::lock_guard<std::mutex> lock(mtx_);
    if (sensorIndex >= pinMap_.size()) return -1;
    return pinMap_[sensorIndex];
}

void PinManager::pulsePinForSensor(size_t sensorIndex, int ms) {
    int pin = getPinForSensor(sensorIndex);
    if (pin < 0) {
        std::cerr << "[PinManager] No pin mapped for sensor " << sensorIndex << "\n";
        return;
    }
    // In production replace pinWrite with your GPIO calls (wiringPi/digitalWrite/etc.)
    pinWrite(pin, true);
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    pinWrite(pin, false);
}

void PinManager::pinWrite(int pin, bool value) {
    // Placeholder: integrate real GPIO library here.
    std::cout << "[PinManager] pin " << pin << " -> " << (value ? "HIGH" : "LOW") << "\n";
}
