#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ball Sensor Daemon - Runs in separate process with minimal overhead
Communicates with main game via Unix socket or queue
"""

import RPi.GPIO as GPIO
import time
import json
import os
import signal
import sys
from multiprocessing import Queue, Process
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger('BallSensorDaemon')


class BallSensorDaemon:
	"""Runs in separate process - minimal overhead"""
	
	def __init__(self, gpio_pin, detection_queue, control_queue):
		"""
		gpio_pin: GPIO pin number for ball sensor
		detection_queue: multiprocessing Queue to send detections to main process
		control_queue: multiprocessing Queue to receive suspend/resume commands
		"""
		self.gpio_pin = gpio_pin
		self.detection_queue = detection_queue
		self.control_queue = control_queue
		self.running = False
		self.suspended = False
		self.last_detection_time = None
		self.debounce_ms = 500  # 500ms debounce - prevents multiple detections from single ball pass
		
	def setup(self):
		"""Initialize GPIO"""
		try:
			GPIO.setmode(GPIO.BCM)
			GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
			logger.info(f"GPIO {self.gpio_pin} initialized")
		except Exception as e:
			logger.error(f"GPIO setup failed: {e}")
			raise
	
	def run(self):
		"""Main sensor loop - runs in separate process"""
		self.setup()
		self.running = True
		last_state = 0
		
		logger.info("Ball sensor daemon started")
		
		# This loop has almost ZERO overhead - just GPIO polling
		while self.running:
			try:
				current_state = GPIO.input(self.gpio_pin)
				current_time = time.time()
				
				# Detect rising edge (LOW -> HIGH)
				if current_state == 1 and last_state == 0:
					# Check debounce
					if self.last_detection_time is None or \
					   (current_time - self.last_detection_time) * 1000 >= self.debounce_ms:
						
						logger.info(f"Ball detected at {current_time}")
						self.last_detection_time = current_time
						
						# Send detection to main process
						self.detection_queue.put({'type': 'ball_detected', 'timestamp': current_time})
				
				last_state = current_state
				
				# Ultra-tight polling - no sleep means we catch EVERYTHING
				# (this is why it works as standalone - no other overhead)
				
			except KeyboardInterrupt:
				break
			except Exception as e:
				logger.error(f"Sensor error: {e}")
				time.sleep(0.01)
		
		GPIO.cleanup()
		logger.info("Ball sensor daemon stopped")
	
	def stop(self):
		"""Stop the daemon"""
		self.running = False


# Global daemon reference for signal handling
daemon = None
detection_queue = None


def start_ball_sensor_daemon(gpio_pin):
	"""
	Start the ball sensor in a separate process
	Returns: Queue to listen for detections
	"""
	global daemon, detection_queue
	
	detection_queue = Queue()
	daemon = BallSensorDaemon(gpio_pin, detection_queue)
	
	# Start daemon process
	process = Process(target=daemon.run, daemon=True)
	process.start()
	
	logger.info(f"Ball sensor daemon process started (PID: {process.pid})")
	
	return detection_queue, process


def signal_handler(signum, frame):
	"""Handle shutdown gracefully"""
	global daemon
	if daemon:
		daemon.stop()
	sys.exit(0)


if __name__ == '__main__':
	# Example standalone usage
	GPIO_PIN = 24
	
	signal.signal(signal.SIGINT, signal_handler)
	
	queue, process = start_ball_sensor_daemon(GPIO_PIN)
	
	logger.info("Listening for detections (press Ctrl+C to stop)...")
	
	try:
		while True:
			if not queue.empty():
				detection = queue.get()
				logger.info(f"Main process received: {detection}")
			time.sleep(0.01)
	except KeyboardInterrupt:
		logger.info("Shutting down")
		process.terminate()
		process.join()