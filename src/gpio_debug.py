#!/usr/bin/env python3

import RPi.GPIO as GPIO
import time

print("Testing GPIO setup...")

try:
    GPIO.setmode(GPIO.BCM)
    print("? GPIO mode set")
except Exception as e:
    print(f"? GPIO mode failed: {e}")
    exit(1)

# Test pin setup
try:
    GPIO.setup(24, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    print("? GPIO 24 setup as input")
except Exception as e:
    print(f"? GPIO 24 setup failed: {e}")
    GPIO.cleanup()
    exit(1)

# Test basic read
try:
    state = GPIO.input(24)
    print(f"? GPIO 24 read successful: {state}")
except Exception as e:
    print(f"? GPIO 24 read failed: {e}")
    GPIO.cleanup()
    exit(1)

# Test edge detection
try:
    def callback(channel):
        print("Edge detected!")
    
    GPIO.add_event_detect(24, GPIO.RISING, callback=callback, bouncetime=50)
    print("? Edge detection added successfully")
    
    print("Waiting 10 seconds... trigger the sensor now")
    time.sleep(10)
    
    GPIO.remove_event_detect(5)
    print("? Edge detection removed")
except Exception as e:
    print(f"? Edge detection failed: {e}")
finally:
    GPIO.cleanup()
    print("? GPIO cleanup complete")