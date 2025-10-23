#pragma once
#include <vector>
#include <iostream>
#include <mutex>

class PinManager {
public:
    // pins: vector where index -> pin number for that sensor
    PinManager(const std::vector<int>& pins);

    // update mapping
    void setPinMap(const std::vector<int>& pins);

    // get pin for sensor index (returns -1 if out of range)
    int getPinForSensor(size_t sensorIndex) const;

    // pulse the pin mapped to sensorIndex for ms milliseconds
    void pulsePinForSensor(size_t sensorIndex, int ms);

private:
    mutable std::mutex mtx_;
    std::vector<int> pinMap_;

    // low-level pin operations - replace with real GPIO library
    void pinWrite(int pin, bool value);
};
