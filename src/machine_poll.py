import RPi.GPIO as GPIO
import time
import threading
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn as AIN
from datetime import datetime
import subprocess
import socket
import json
import queue
import logging

class BowlingMachine:
	"""Controls physical bowling machine hardware - QUEUE-BASED BALL SENSOR"""
	
	def __init__(self, settings, logger, detection_queue=None, control_queue=None):
		self.settings = settings
		self.logger = logger
		self.active_game = None
		self.pin_area = None
		self.last_ball = False  # Flag: if True, reset pins instead of applying breaks
		self.detection_queue = detection_queue
		self.control_queue = control_queue
		
		# Load lane configuration
		lane_id = str(settings.get('Lane', 1))
		lane_config = settings.get(lane_id, {})
		
		# GPIO pins
		self.gp1 = int(lane_config.get("GP1", 17))
		self.gp2 = int(lane_config.get("GP2", 27))
		self.gp3 = int(lane_config.get("GP3", 22))
		self.gp4 = int(lane_config.get("GP4", 23))
		self.gp5 = int(lane_config.get("GP5", 24))
		self.gp6 = int(lane_config.get("GP6", 25))
		self.gp7 = int(lane_config.get("GP7", 5))  # Ball sensor
		self.gp8 = int(lane_config.get("GP8", 6))
		
		# Pin position mappings
		self.pb10 = lane_config.get("B10", "lTwo")
		self.pb11 = lane_config.get("B11", "lThree")
		self.pb12 = lane_config.get("B12", "cFive")
		self.pb13 = lane_config.get("B13", "rThree")
		self.pb20 = lane_config.get("B20", "rTwo")
		
		# Initialize GPIO
		try:
			GPIO.setmode(GPIO.BCM)
		except RuntimeError as e:
			self.logger.warning(f"GPIO mode already set: {e}")
		
		GPIO.setup([self.gp1, self.gp2, self.gp3, self.gp4, self.gp5, self.gp6], GPIO.OUT)
		GPIO.setup([self.gp7, self.gp8], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
		GPIO.output([self.gp1, self.gp2, self.gp3, self.gp4, self.gp5, self.gp6], 1)
		
		# Initialize I2C and ADS sensors
		self._init_ads_sensors()
		
		# Pin state tracking
		self.pins_standing = [0, 0, 0, 0, 0]
		
		# Machine timing
		self.mp = 5.8
		self.moppo = 0
		
		# Ball sensor configuration
		self.sensor_running = False
		self.sensor_suspended = False
		self.last_detection_time = None
		self.queue_listener_thread = None
		self.polling_thread = None
		
		# Determine detection method
		if self.detection_queue:
			self.use_queue = True
			self.logger.info("Bowling machine initialized - QUEUE-BASED BALL SENSOR (daemon process)")
		else:
			# No detection queue provided: start socket-feed thread and use an internal Queue
			self.logger.info("No detection_queue provided - attempting socket-based feed")
			self.detection_queue = queue.Queue()
			self.use_queue = True
			self._start_socket_feed_thread()
			self.logger.info("Bowling machine initialized - SOCKET FEED MODE (daemon process)")

	def _init_ads_sensors(self):
		"""Initialize ADS1115 sensors with retry logic"""
		retry_count = 0
		max_retries = 5
		
		while retry_count < max_retries:
			try:
				subprocess.call(['i2cdetect', '-y', '1'])
				i2c = busio.I2C(board.SCL, board.SDA)
				ads1 = ADS.ADS1115(i2c, address=0x48)
				ads2 = ADS.ADS1115(i2c, address=0x49)
				
				# Initialize analog inputs
				self.b10 = AIN(ads1, ADS.P0)
				self.b11 = AIN(ads1, ADS.P1)
				self.b12 = AIN(ads1, ADS.P2)
				self.b13 = AIN(ads1, ADS.P3)
				self.b20 = AIN(ads2, ADS.P0)
				self.b21 = AIN(ads2, ADS.P1)  # Machine pin sensor
				self.b22 = AIN(ads2, ADS.P2)
				self.b23 = AIN(ads2, ADS.P3)
				
				self.logger.info("ADS sensors initialized successfully")
				return
				
			except (OSError, ValueError) as e:
				retry_count += 1
				self.logger.error(f"ADS init attempt {retry_count} failed: {e}")
				time.sleep(0.5)
				continue
		
		self.logger.error("Failed to initialize ADS sensors after max retries")
		raise RuntimeError("Could not initialize ADS sensors")

	# --- socket feed helpers -------------------------------------------------
	def _start_socket_feed_thread(self):
		self.socket_thread = threading.Thread(target=self._socket_feed_loop, daemon=True)
		self.socket_thread.start()

	def _socket_feed_loop(self):
		"""Connect to daemon unix socket and push JSON messages into self.detection_queue"""
		SOCKET_PATH = '/tmp/ball_sensor.sock'
		while True:
			try:
				sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
				self.logger.info(f"Connecting to ball sensor socket at {SOCKET_PATH}...")
				sock.connect(SOCKET_PATH)
				self.logger.info("Connected to ball sensor socket")
				f = sock.makefile('r', encoding='utf-8', newline='\n')
				while True:
					line = f.readline()
					if not line:
						self.logger.info("Ball sensor socket closed by daemon")
						f.close()
						sock.close()
						break
					line = line.strip()
					if not line:
						continue
					try:
						msg = json.loads(line)
						if isinstance(msg, dict):
							self.detection_queue.put(msg)
						else:
							self.logger.debug(f"Unexpected message (not dict) from socket: {msg}")
					except Exception as e:
						self.logger.error(f"Failed to parse JSON from socket: {e} -- raw: {line}")
			except Exception as e:
				self.logger.debug(f"Socket feed connection failed or disconnected: {e}")
			time.sleep(0.5)
	# -------------------------------------------------------------------------

	def set_active_game(self, game):
		"""Set the currently active game"""
		self.active_game = game
		self.logger.info(f"Active game set: {game.name if game else 'None'}")
	
	def set_pin_area(self, pin_area):
		"""Set reference to UI pin display"""
		self.pin_area = pin_area
	
	
	def start_ball_sensor(self):
		"""Start ball sensor (queue-based or polling)"""
		if self.use_queue:
			# Queue-based: start listener thread
			if not self.queue_listener_thread or not self.queue_listener_thread.is_alive():
				self.sensor_running = True
				self.queue_listener_thread = threading.Thread(target=self._queue_listener, daemon=True)
				self.queue_listener_thread.start()
				self.logger.info("Queue listener thread started")
		else:
			# Fallback: polling thread
			if not self.polling_thread or not self.polling_thread.is_alive():
				self.sensor_running = True
				self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
				self.polling_thread.start()
				self.logger.info("Polling thread started (fallback mode)")
	
	
	def stop_ball_sensor(self):
		"""Stop ball sensor"""
		self.sensor_running = False
		if self.queue_listener_thread:
			self.queue_listener_thread.join(timeout=2.0)
		if self.polling_thread:
			self.polling_thread.join(timeout=2.0)
		self.logger.info("Ball sensor stopped")
	
	
	def _queue_listener(self):
		"""Listen for ball detections from daemon process"""
		self.logger.info("Queue listener started - waiting for detections from daemon")
		
		while self.sensor_running:
			try:
				if self.detection_queue and not self.detection_queue.empty():
					detection = self.detection_queue.get(timeout=0.1)
					
					msg_type = detection.get('type')
					if msg_type == 'ball_detected':
						current_time = detection.get('timestamp', time.time())
						self.logger.info(f"[DAEMON] Ball detected from sensor daemon")
						self.last_detection_time = current_time
						self._handle_ball_detected()
					elif msg_type == 'last_ball':
						self.logger.info("[DAEMON] LAST_BALL received - calling manual_reset")
						try:
							self.manual_reset()
						except Exception as e:
							self.logger.error(f"manual_reset failed: {e}")
					elif msg_type == 'pin_set':
						pins = detection.get('pins')
						self.logger.info(f"[DAEMON] PIN_SET received: {pins}")
						# TODO: map pins into lane_config or update pin mappings as needed
					else:
						self.logger.debug(f"Queue listener got unhandled message type: {msg_type}")
				else:
					time.sleep(0.01)
					
			except Exception as e:
				self.logger.debug(f"Queue listener error: {e}")
				time.sleep(0.01)
