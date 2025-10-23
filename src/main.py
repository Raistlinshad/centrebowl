# -*- coding: utf-8 -*-

import pygame
import json
import os
import sys
import ctypes
import logging

# Import your existing classes
from ui.screens import MainScreen, LaneSetupScreen
from network import LaneClient
from game_manager import GameManager
from machine_poll import BowlingMachine
from ball_sensor_daemon import start_ball_sensor_daemon

# Configure logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_settings():
	"""Load settings from settings.json"""
	settings_file = 'settings.json'
	
	if not os.path.exists(settings_file):
		logger.error(f"Settings file '{settings_file}' not found!")
		return {}
	
	try:
		with open(settings_file, 'r') as f:
			settings = json.load(f)
		logger.info(f"Settings loaded from {settings_file}")
		
		# Convert Lane to int if it's a string
		if 'Lane' in settings:
			settings['Lane'] = int(settings['Lane'])
		
		return settings
	except Exception as e:
		logger.error(f"Error loading settings: {e}")
		return {}


def save_settings(settings):
	"""Save settings to settings.json"""
	try:
		with open('settings.json', 'w') as f:
			json.dump(settings, f, indent=4)
		logger.info("Settings saved")
		return True
	except Exception as e:
		logger.error(f"Error saving settings: {e}")
		return False


def main():
	# Load settings FIRST
	settings = load_settings()
	
	# Force DPI awareness on Windows
	if os.name == 'nt':
		try:
			ctypes.windll.shcore.SetProcessDpiAwareness(2)
		except:
			try:
				ctypes.windll.user32.SetProcessDPIAware()
			except:
				pass
	
	pygame.init()
	
	screen_info = pygame.display.Info()
	screen = pygame.display.set_mode(
		(screen_info.current_w, screen_info.current_h), 
		pygame.FULLSCREEN
	)
	pygame.display.set_caption("Self Bowling System")
	
	# Give pygame a moment to initialize
	pygame.time.wait(500)
	pygame.event.pump()
	
	# Check lane ID from settings
	lane_id = settings.get('Lane', 0)
	
	# If lane_id is 0 or None, show setup screen
	if not lane_id or lane_id == 0:
		logger.info("Lane ID not set - showing lane setup screen")
		
		setup_screen = LaneSetupScreen(screen)
		running = True
		pygame.event.clear()
		
		while running:
			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					running = False
					pygame.quit()
					exit()
				
				if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					running = False
					pygame.quit()
					exit()
				
				if event.type == pygame.MOUSEBUTTONDOWN:
					selected_lane = setup_screen.handle_click(event.pos)
					if selected_lane:
						# Save to settings
						if setup_screen.save_lane_id(selected_lane):
							lane_id = selected_lane
							# UPDATE settings dict with new lane ID
							settings['Lane'] = lane_id
							save_settings(settings)
							running = False
			
			setup_screen.draw()
	
	logger.info(f"Lane ID set to: {lane_id}")
	
	# Verify we have server settings
	if not settings.get('ServerIP'):
		logger.error("ServerIP not configured in settings.json")
		logger.error("Please set ServerIP and ServerPort in settings.json")
		pygame.quit()
		exit()
	
	# ==================== START BALL SENSOR DAEMON ====================
	lane_config = settings.get(str(lane_id), {})
	gp7 = int(lane_config.get('GP7', 5))
	
	detection_queue = None
	sensor_process = None
	
	try:
		logger.info(f"Starting ball sensor daemon on GPIO {gp7}...")
		detection_queue, control_queue, sensor_process = start_ball_sensor_daemon(gp7)
		logger.info(f"Ball sensor daemon started (PID: {sensor_process.pid})")
	except Exception as e:
		logger.error(f"Failed to start ball sensor daemon: {e}")
		logger.warning("Will fall back to polling mode")
		detection_queue = None
		control_queue = None
		sensor_process = None
	
	# ==================== INITIALIZE HARDWARE ====================
	# Initialize hardware (BowlingMachine) with detection_queue
	try:
		machine = BowlingMachine(settings, logger, detection_queue=detection_queue, control_queue=control_queue)
		logger.info("BowlingMachine initialized")
	except Exception as e:
		logger.error(f"Error initializing BowlingMachine: {e}")
		machine = None
	
	# Initialize network client (WITHOUT game_manager reference yet)
	logger.info(f"Connecting to server: {settings.get('ServerIP')}:{settings.get('ServerPort')}")
	network_client = LaneClient(
		lane_id=lane_id,
		settings=settings,
		event_bus=None,
		game_manager=None  # Will set this after creating game_manager
	)
	
	# Initialize main screen without a game
	main_screen = MainScreen(screen, None, settings, machine=machine)
	
	# Initialize game manager
	game_manager = GameManager(
		main_screen=main_screen,
		machine=machine,
		settings=settings,
		network_client=network_client
	)
	
	# NOW connect network_client to game_manager
	network_client.game_manager = game_manager
	
	# Store references in main_screen
	main_screen.network_client = network_client
	main_screen.game_manager = game_manager
	
	# Start network client
	network_client.start()
	logger.info("Network client started")
	
	# FOR TESTING: Uncomment to start a test game locally
	# names = ["Bruce", "Steve", "Kevin", "Phillip", "Michael", "Alex", "Tom", "John"]
	# session_config = {
	#	 'mode': 'time',
	#	 'total_games': None,
	#	 'total_time_minutes': 30,
	#	 'frames_per_turn': 1
	# }
	# game_manager.start_five_pin_game(
	#	 bowlers=names,
	#	 session_config=session_config,
	#	 game_modes={
	#		 "three_six_nine": {
	#			 "target_frames": {1: [3,6,9], 2: [3,6,9], 3: [3,6,9]}
	#		 }
	#	 }
	# )
	
	logger.info("System initialized - waiting for server commands")
	
	# Start main loop
	try:
		main_screen.run()
	except KeyboardInterrupt:
		logger.info("Interrupted by user")
	except Exception as e:
		logger.error(f"Fatal error in main loop: {e}")
		import traceback
		traceback.print_exc()
	finally:
		# Cleanup on exit
		logger.info("Shutting down...")
		network_client.stop()
		if machine:
			machine.cleanup()
		
		# Stop sensor daemon
		if sensor_process:
			logger.info("Stopping ball sensor daemon...")
			sensor_process.terminate()
			sensor_process.join(timeout=2)
			logger.info("Ball sensor daemon stopped")
		
		pygame.quit()
		logger.info("Shutdown complete")


if __name__ == "__main__":
	main()