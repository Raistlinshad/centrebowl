# -*- coding: utf-8 -*-

import pygame
import json
import os
from ui.buttons import BallButton
from ui.pin_area import PinArea

class MainScreen:
	def __init__(self, screen, game, settings, machine=None):
		self.screen = screen
		self.game = game
		self.settings = settings
		self.machine = machine
		self.running = True

		# Get actual screen dimensions
		screen_info = pygame.display.Info()
		self.screen_width = screen_info.current_w
		self.screen_height = screen_info.current_h
		print(f"Screen resolution: {self.screen_width}X{self.screen_height}")

		# Button names and positions - NOW WITH 4 BUTTONS
		self.button_names = ["RESET", "CALL", "SKIP", "START"]
		button_start_y = 140
		button_x = 1700
		self.buttons = [
			BallButton(name, (button_x, button_start_y + i * 110)) 
			for i, name in enumerate(self.button_names)
		]

		# Pin area positioned BELOW buttons in bottom right
		self.pin_area = PinArea(pos=(1630, 700))
		
		# Connect machine to pin area
		if self.machine:
			self.machine.set_pin_area(self.pin_area)
			self.machine.start_ball_sensor()
		
		self.font = pygame.font.SysFont(None, 48)
		self.small_font = pygame.font.SysFont(None, 32)
		
		# Game area rectangle - MAXIMIZED for 1920×1080
		self.game_area_rect = pygame.Rect(12, 120, 1635, 850)

		# pin display timer
		self.pin_display_timer = None
		self.pin_display_duration = 3000  # milliseconds

	def draw_top_bar(self):
		pygame.draw.rect(self.screen, (40, 40, 60), (0, 0, 1920, 80))
		game_type = getattr(self.game, "name", "5-Pin Bowling") if self.game else "No Game Active"
		text = self.font.render(game_type, True, (255, 255, 255))
		self.screen.blit(text, (30, 20))
		centre = self.font.render("Centrebowl", True, (255, 255, 255))
		centre_rect = centre.get_rect(center=(960, 40))
		self.screen.blit(centre, centre_rect)
		import datetime
		now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		dt = self.small_font.render(now, True, (200, 200, 200))
		self.screen.blit(dt, (1500, 30))
		
		# Get game info from the game (if it has the method)
		if self.game and hasattr(self.game, 'get_game_info_display'):
			game_info_text = self.game.get_game_info_display()
		else:
			game_info_text = ""
		
		game_info = self.small_font.render(game_info_text, True, (200, 200, 200))
		self.screen.blit(game_info, (1750, 30))

	def draw_bottom_bar(self):
		# Full-width scroll message bar at the bottom - LOWERED
		bar_height = 100
		bar_y = 1080 - bar_height - 10  # 10px from bottom instead of flush
		pygame.draw.rect(self.screen, (40, 40, 60), (0, bar_y, 1920, bar_height))
		
		# Get scroll message from game if available
		if self.game and hasattr(self.game, 'get_scroll_message'):
			scroll_text = self.game.get_scroll_message()
		else:
			scroll_text = "Welcome to Centrebowl! Good luck!"
		
		scroll_msg = self.small_font.render(scroll_text, True, (255, 255, 0))
		scroll_rect = scroll_msg.get_rect(center=(960, bar_y + bar_height // 2))
		self.screen.blit(scroll_msg, scroll_rect)

	def draw_game_area(self):
		"""Draw the main game UI area - background and delegate to active game"""
		# Main game area background
		pygame.draw.rect(self.screen, (60, 60, 80), self.game_area_rect, border_radius=20)
		
		# Let the active game draw itself within the game area
		if self.game and hasattr(self.game, 'draw'):
			self.game.draw(self.screen, self.game_area_rect)

	def handle_button_click(self, button_name):
		"""Handle button interactions with the active game"""
		if not self.game:
			print("No active game")
			return
		
		if button_name == "RESET":
			# FIXED: Properly reset via machine AND game
			print("RESET button pressed")
			
			# Reset machine hardware
			if self.machine:
				self.machine.manual_reset()
				print("Machine reset called")
			
			# Reset game pins if game supports it
			if hasattr(self.game, 'reset_pins'):
				self.game.reset_pins()
				print("Game pins reset called")
		
		elif button_name == "CALL":
			# Call front desk (works for practice mode and games)
			print("CALL button pressed")
			if hasattr(self.game, 'call_front_desk'):
				self.game.call_front_desk()
			else:
				print("Front desk call - game doesn't support this")
				# TODO: Send network message to server
		
		elif button_name == "SKIP":
			# Skip to next bowler
			print("SKIP button pressed")
			if hasattr(self.game, 'skip_bowler'):
				self.game.skip_bowler()
			else:
				print("Skip not available for this game")
		
		elif button_name == "START":
			# START GAME button - only works in practice mode
			print("START GAME button pressed")
			if self.game and self.game.name == "Practice Mode":
				if hasattr(self.game, '_transition_to_game'):
					self.game._transition_to_game()
					print("Transitioning from practice to league game")
				else:
					print("Practice mode doesn't support game transition")
			else:
				print("START GAME only available in practice mode")

	def start_game(self, game):
		"""Start a new game (called from server or for testing)"""
		self.game = game
		
		# Set active game in machine
		if self.machine:
			self.machine.set_active_game(game)
		
		print(f"Starting {game.name}")

	def stop_game(self):
		"""Stop the current game"""
		if self.game:
			print(f"Stopping {self.game.name}")
		
		# Clear active game from machine
		if self.machine:
			self.machine.set_active_game(None)
		
		self.game = None

	def run(self):
		clock = pygame.time.Clock()
		
		print("Starting main loop...")
		
		try:
			# Do one frame manually to catch initialization errors
			print("Attempting first frame update...")
			dt = clock.tick(30)
			
			print("Updating pin area...")
			self.pin_area.update(dt)
			
			print("Checking game timers...")
			if self.game and hasattr(self.game, 'check_next_game_timer'):
				self.game.check_next_game_timer()
			
			if self.game and hasattr(self.game, 'check_game_over_pause'):
				self.game.check_game_over_pause()
			
			print("Clearing screen...")
			self.screen.fill((30, 30, 30))
			
			print("Drawing top bar...")
			self.draw_top_bar()
			
			print("Drawing bottom bar...")
			self.draw_bottom_bar()
			
			print("Drawing game area...")
			self.draw_game_area()
			
			print("Drawing pin area...")
			self.pin_area.draw(self.screen)
			
			print("Drawing buttons...")
			for button in self.buttons:
				button.draw(self.screen)
			
			print("Flipping display...")
			pygame.display.flip()
			
			print("First frame completed successfully!")
			
		except Exception as e:
			print(f"ERROR during first frame: {e}")
			import traceback
			traceback.print_exc()
			raise
	
		while self.running:
			dt = clock.tick(30)
			
			try:
				# Update pin animations
				self.pin_area.update(dt)
			except Exception as e:
				print(f"ERROR in pin_area.update: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				# Auto-Start next game after 5 min timer
				if self.game and hasattr(self.game, 'check_next_game_timer'):
					self.game.check_next_game_timer()
			except Exception as e:
				print(f"ERROR in check_next_game_timer: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				# Check game over pause timer
				if self.game and hasattr(self.game, 'check_game_over_pause'):
					self.game.check_game_over_pause()
			except Exception as e:
				print(f"ERROR in check_game_over_pause: {e}")
				import traceback
				traceback.print_exc()

			for event in pygame.event.get():
				if event.type == pygame.QUIT:
					self.running = False
				if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
					self.running = False
					
				# Handle button clicks
				for i, button in enumerate(self.buttons):
					if button.handle_event(event):
						self.handle_button_click(self.button_names[i])
				
				# Handle game area clicks
				if event.type == pygame.MOUSEBUTTONDOWN:
					if self.game and hasattr(self.game, 'handle_click'):
						self.game.handle_click(event.pos)
			
			# Clear screen
			self.screen.fill((30, 30, 30))
			
			try:
				# Draw in correct order
				self.draw_top_bar()
			except Exception as e:
				print(f"ERROR in draw_top_bar: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				self.draw_bottom_bar()
			except Exception as e:
				print(f"ERROR in draw_bottom_bar: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				self.draw_game_area()
			except Exception as e:
				print(f"ERROR in draw_game_area: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				# Draw pin area and buttons
				self.pin_area.draw(self.screen)
			except Exception as e:
				print(f"ERROR in pin_area.draw: {e}")
				import traceback
				traceback.print_exc()
			
			try:
				for button in self.buttons:
					button.draw(self.screen)
			except Exception as e:
				print(f"ERROR drawing buttons: {e}")
				import traceback
				traceback.print_exc()
			
			pygame.display.flip()
			clock.tick(60)
		
		# Cleanup on exit
		if self.machine:
			self.machine.cleanup()
			
class LaneSetupScreen:
	def __init__(self, screen, settings_file='settings.json'):
		self.screen = screen
		self.settings_file = settings_file
		self.font_large = pygame.font.SysFont(None, 64)
		self.font_medium = pygame.font.SysFont(None, 40)
		self.font_small = pygame.font.SysFont(None, 32)
		
		# Grid layout for 100 buttons (10x10)
		self.grid_cols = 10
		self.grid_rows = 10
		self.button_size = 80
		self.button_spacing = 10
		self.buttons = []
		
		# Calculate starting position to center the grid
		grid_width = self.grid_cols * (self.button_size + self.button_spacing)
		grid_height = self.grid_rows * (self.button_size + self.button_spacing)
		start_x = (1920 - grid_width) // 2
		start_y = 200
		
		# Create button rectangles
		for i in range(100):
			row = i // self.grid_cols
			col = i % self.grid_cols
			x = start_x + col * (self.button_size + self.button_spacing)
			y = start_y + row * (self.button_size + self.button_spacing)
			self.buttons.append({
				'rect': pygame.Rect(x, y, self.button_size, self.button_size),
				'lane_id': i + 1
			})
	
	def draw(self):
		self.screen.fill((30, 30, 50))
		
		# Title
		title = self.font_large.render("SET LANE ID", True, (255, 255, 255))
		title_rect = title.get_rect(center=(960, 80))
		self.screen.blit(title, title_rect)
		
		# Instructions
		inst = self.font_medium.render("Select your lane number", True, (200, 200, 200))
		inst_rect = inst.get_rect(center=(960, 140))
		self.screen.blit(inst, inst_rect)
		
		# Draw buttons
		for button in self.buttons:
			# Button background
			pygame.draw.rect(self.screen, (70, 70, 90), button['rect'], border_radius=8)
			pygame.draw.rect(self.screen, (255, 255, 255), button['rect'], 2, border_radius=8)
			
			# Lane number
			num_text = self.font_medium.render(str(button['lane_id']), True, (255, 255, 255))
			num_rect = num_text.get_rect(center=button['rect'].center)
			self.screen.blit(num_text, num_rect)
		
		pygame.display.flip()
	
	def handle_click(self, pos):
		"""Handle button click, returns lane_id if clicked"""
		for button in self.buttons:
			if button['rect'].collidepoint(pos):
				return button['lane_id']
		return None
	
	def save_lane_id(self, lane_id):
		"""Save lane ID to settings.json - preserves ALL existing settings"""
		try:
			# Load existing settings
			if os.path.exists(self.settings_file):
				with open(self.settings_file, 'r') as f:
					settings = json.load(f)
				print(f"Loaded existing settings with keys: {list(settings.keys())}")
			else:
				# Create minimal default settings if file doesn't exist
				settings = {}
				print("No existing settings file found, creating new one")
		
			# Update ONLY the Lane field
			settings['Lane'] = str(lane_id)  # Store as string to match your format
		
			# Add defaults ONLY if they don't exist (don't overwrite!)
			if 'ServerIP' not in settings:
				settings['ServerIP'] = '192.168.2.243'
				print("Added default ServerIP")
			if 'ServerPort' not in settings:
				settings['ServerPort'] = 50005
				print("Added default ServerPort")
		
			# Save everything back with proper formatting
			with open(self.settings_file, 'w') as f:
				json.dump(settings, f, indent=4)
		
			print(f"? Lane ID {lane_id} saved to {self.settings_file}")
			print(f"? Preserved {len(settings)} top-level settings fields")
			return True
		
		except Exception as e:
			print(f"? Error saving lane ID: {e}")
			import traceback
			traceback.print_exc()
			return False