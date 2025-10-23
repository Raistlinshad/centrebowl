import RPi.GPIO as GPIO
import time
import threading
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn as AIN
from datetime import datetime
import subprocess

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
			self.use_queue = False
			self.logger.info("Bowling machine initialized - POLLING MODE (fallback)")

	
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
					
					if detection.get('type') == 'ball_detected':
						current_time = detection.get('timestamp', time.time())
						self.logger.info(f"[DAEMON] Ball detected from sensor daemon")
						self.last_detection_time = current_time
						self._handle_ball_detected()
				else:
					time.sleep(0.01)
					
			except Exception as e:
				self.logger.debug(f"Queue listener error: {e}")
				time.sleep(0.01)
	
	
	def _polling_loop(self):
		"""Fallback: Background thread polling GPIO for state changes"""
		self.logger.info("Polling loop started (fallback - daemon not available)")
		
		last_pin_state = None
		debounce_active = False
		debounce_until = 0
		
		while self.sensor_running:
			if self.sensor_suspended:
				time.sleep(0.05)
				continue
			
			try:
				current_state = GPIO.input(self.gp7)
				current_time = time.time()
				
				# Detect rising edge (LOW → HIGH transition)
				if current_state == 1 and last_pin_state == 0:
					self.logger.info(f"[POLLING] Rising edge at {current_time}")
					
					# Check debounce window
					if not debounce_active:
						# Valid detection
						if self.last_detection_time:
							time_delta = (current_time - self.last_detection_time) * 1000
							self.logger.info(f"[POLLING] Ball detected (Δ {time_delta:.1f}ms)")
						else:
							self.logger.info(f"[POLLING] Ball detected (initial)")
						
						self.last_detection_time = current_time
						
						# Set debounce (150ms)
						debounce_active = True
						debounce_until = current_time + 0.15
						
						# Process ball
						self._handle_ball_detected()
					else:
						self.logger.debug(f"[POLLING] Edge ignored - within debounce window")
				
				# Check if debounce expired
				if debounce_active and current_time >= debounce_until:
					debounce_active = False
				
				last_pin_state = current_state
				time.sleep(0.002)  # 2ms polling interval
				
			except Exception as e:
				self.logger.error(f"Polling error: {e}")
				time.sleep(0.01)
	
	
	def _handle_ball_detected(self):
		"""Handle ball detection event"""
		if not self.active_game:
			self.logger.info("Ball detected but no active game - ignoring")
			return
		
		if hasattr(self.active_game, 'session_expired') and self.active_game.session_expired:
			self.logger.info("Ball detected but session expired - ignoring")
			return
		
		if hasattr(self.active_game, 'session_complete') and self.active_game.session_complete:
			self.logger.info("Ball detected but session complete - ignoring")
			return
		
		if hasattr(self.active_game, 'hold_active') and self.active_game.hold_active:
			self.logger.info("Ball detected but game on hold - ignoring")
			return
		
		self.logger.info("Ball detected - processing throw")
		self.sensor_suspended = True
		
		# Suspend daemon from sending more detections
		if self.control_queue:
			self.control_queue.put({'action': 'suspend'})
			self.logger.info("Daemon suspended")
		
		try:
			pin_state = self._process_ball_throw()
			
			if self.pin_area:
				self.pin_area.pins_down = [bool(p) for p in pin_state]
			
			if self.active_game and hasattr(self.active_game, 'process_ball'):
				self.active_game.process_ball(pin_state)
			
		except Exception as e:
			self.logger.error(f"Error processing ball throw: {e}")
			import traceback
			self.logger.error(traceback.format_exc())
		
		finally:
			# Resume daemon
			if self.control_queue:
				self.control_queue.put({'action': 'resume'})
				self.logger.info("Daemon resumed")
			
			self.sensor_suspended = False

	def _process_ball_throw(self):
		"""
		Process a ball throw - detect pins down and apply machine operations
		Returns: [int, int, int, int, int] representing final pin state (1=down, 0=standing)
		"""
		start_time = time.time()
		self.logger.info(f"Ball throw processing started at {start_time}")
		
		# Control dictionary - starts with current pin state
		control = {
			'lTwo': 1 if self.pins_standing[0] == 0 else 0,
			'lThree': 1 if self.pins_standing[1] == 0 else 0,
			'cFive': 1 if self.pins_standing[2] == 0 else 0,
			'rThree': 1 if self.pins_standing[3] == 0 else 0,
			'rTwo': 1 if self.pins_standing[4] == 0 else 0
		}
		
		control_start = control.copy()
		
		# Detect pins knocked down
		pins_knocked = self._detect_pins_down(control)
		
		self.logger.debug(f"Control start: {control_start}, Control end: {control}")
		
		# Check if no pins knocked
		if pins_knocked == 0:
			self.logger.info("No pins knocked - returning")
			return [0, 0, 0, 0, 0]
		
		# Check if all pins down
		if all(c == 0 for c in control.values()):
			self.logger.info("All pins knocked down - full reset")
			self.reset_pins()
			return [1, 1, 1, 1, 1]
		
		# Pins were knocked but not all - reset machine
		self.logger.info(f"{pins_knocked} pins knocked - cycling machine")
		self._machine_reset()
		
		# Wait for machine pin
		self._wait_for_machine_pin()
		
		# Apply pin breaks
		self._apply_pin_breaks(control)
		
		# Update internal pin state
		self.pins_standing = [
			1 if control['lTwo'] == 0 else 0,
			1 if control['lThree'] == 0 else 0,
			1 if control['cFive'] == 0 else 0,
			1 if control['rThree'] == 0 else 0,
			1 if control['rTwo'] == 0 else 0
		]
		
		end_time = time.time()
		total_time = end_time - start_time
		self.logger.info(f"Ball throw processing completed in {total_time:.2f}s")
		
		return self.pins_standing.copy()
	
	def _detect_pins_down(self, control):
		"""
		Detect which pins have been knocked down
		Returns: number of pins knocked
		"""
		detection_start = time.time()
		pins_knocked = 0
		detection_timeout = 3.0  # 3 seconds to detect pins
		
		self.logger.debug("Starting pin detection")
		
		while time.time() - detection_start <= detection_timeout:
			try:
				# Check each pin sensor
				if self.b20.voltage >= 4 and control[self.pb20] != 0:
					control[self.pb20] = 0
					pins_knocked += 1
					self.logger.debug(f"{self.pb20} knocked down")
				
				time.sleep(0.02)
				
				if self.b12.voltage >= 4 and control[self.pb12] != 0:
					control[self.pb12] = 0
					pins_knocked += 1
					self.logger.debug(f"{self.pb12} knocked down")
				
				time.sleep(0.02)
				
				if self.b11.voltage >= 4 and control[self.pb11] != 0:
					control[self.pb11] = 0
					pins_knocked += 1
					self.logger.debug(f"{self.pb11} knocked down")
				
				time.sleep(0.02)
				
				if self.b13.voltage >= 4 and control[self.pb13] != 0:
					control[self.pb13] = 0
					pins_knocked += 1
					self.logger.debug(f"{self.pb13} knocked down")
				
				time.sleep(0.02)
				
				if self.b10.voltage >= 4 and control[self.pb10] != 0:
					control[self.pb10] = 0
					pins_knocked += 1
					self.logger.debug(f"{self.pb10} knocked down")
				
				time.sleep(0.5)
				
			except Exception as e:
				self.logger.error(f"Pin detection error: {e}")
				continue
		
		self.logger.info(f"Pin detection complete: {pins_knocked} pins knocked")
		return pins_knocked
	
	def _machine_reset(self):
		"""Trigger machine reset cycle"""
		self.logger.debug("Machine reset triggered")
		GPIO.output(self.gp6, 0)
		time.sleep(0.35)
		GPIO.output(self.gp6, 1)
	
	def _wait_for_machine_pin(self):
		"""Wait for machine pin detection"""
		start_time = time.time()
		
		if self.mp < 5.3 or self.mp > 6:
			self.mp = 5.7
			self.logger.debug(f"Machine pin timing reset to {self.mp}")
		
		self.logger.debug(f"Waiting for machine pin (timeout: {self.mp}s)")
		
		while True:
			if time.time() - start_time <= self.mp:
				try:
					if self.b21.voltage >= 4:
						elapsed = time.time() - start_time
						self.logger.info(f"Machine pin detected at {elapsed:.2f}s")
						self.moppo = 1
						# Update timing
						if self.moppo == 1:
							self.mp = elapsed + 0.01
							self.logger.debug(f"Updated machine pin timing to {self.mp}")
							self.moppo = 0
						break
				except Exception as e:
					self.logger.error(f"Machine pin detection error: {e}")
					continue
				time.sleep(0.02)
			else:
				self.logger.info("Machine pin timeout - manually activating breaks")
				break
	
	def _apply_pin_breaks(self, control):
		"""Apply pin breaks based on control state"""
		self.logger.debug(f"Applying pin breaks: {control}")
		
		GPIO.output(self.gp1, control["lTwo"])
		GPIO.output(self.gp2, control["lThree"])
		GPIO.output(self.gp3, control["cFive"])
		GPIO.output(self.gp4, control["rThree"])
		GPIO.output(self.gp5, control["rTwo"])
		
		time.sleep(0.1)
		
		# Reset all pins to high
		GPIO.output([self.gp1, self.gp2, self.gp3, self.gp4, self.gp5], 1)
		
		self.logger.debug("Pin breaks applied")
	
	def manual_reset(self):
		"""Manual reset triggered by RESET button"""
		print("BowlingMachine: Manual reset called")
		
		self._machine_reset()
	
		# Reset all pins to standing (GPIO low)
		self.pins_standing = [0, 0, 0, 0, 0]
	
		# Update internal state
		self.pin_state = [0, 0, 0, 0, 0]
	
		# Update pin area display if connected
		if self.pin_area:
			self.pin_area.reset_pins()
	
		print("All pins reset to standing position")

	def reset_pins(self):
		"""Alias for manual_reset for compatibility"""
		self.manual_reset()
	
	def get_pin_state(self):
		"""Get current pin state"""
		return self.pins_standing.copy()

	def cleanup(self):
		"""Cleanup GPIO and stop sensor"""
		self.logger.info("Cleaning up bowling machine")
		self.stop_ball_sensor()
		GPIO.cleanup()