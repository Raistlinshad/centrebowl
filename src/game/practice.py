# -*- coding: utf-8 -*-

# practice.py - Updated with pin display
import pygame
from datetime import datetime

class PracticeMode:
	def __init__(self, settings, parent=None, duration_minutes=30, next_game_config=None, machine=None):
		"""
		next_game_config: dict with game type and config to start after practice
		Example: {'type': 'league', 'bowlers': [...], 'session_config': {...}, 'game_modes': [...]}
		machine: Reference to BowlingMachine instance
		"""
		self.name = "Practice Mode"
		self.parent = parent
		self.settings = settings
		self.next_game_config = next_game_config
		self.machine = machine
	
		self.duration_seconds = duration_minutes * 60
		self.start_time = datetime.now()
	
		self.font_huge = pygame.font.SysFont(None, 72)
		self.font_large = pygame.font.SysFont(None, 56)
		self.font_medium = pygame.font.SysFont(None, 40)
		self.font_small = pygame.font.SysFont(None, 32)
	
		# Define pin dimensions FIRST
		self.pin_width = 50
		self.pin_height = 70
	
		# Pin display area at top right
		self.pin_display_pos = (1650, 150)
		self.pin_images = self._load_pin_images()  # Now this works!
	
		# Pin layout for display
		self.pin_layout = [
			(0, 0),	  # L2
			(60, 50),	# L3
			(120, 100),  # C5
			(180, 50),   # R3
			(240, 0),	# R2
		]
	
	def _load_pin_images(self):
		"""Load simple pin up/down images"""
		import os
		base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		pin_up_path = os.path.join(base_dir, 'assets', 'images', '5pin_up.png')
		pin_down_path = os.path.join(base_dir, 'assets', 'images', '5pin_down.png')
		
		pin_up = pygame.image.load(pin_up_path)
		pin_down = pygame.image.load(pin_down_path)
		
		# Scale images to appropriate size
		pin_up = pygame.transform.scale(pin_up, (self.pin_width, self.pin_height))
		pin_down = pygame.transform.scale(pin_down, (self.pin_width, self.pin_height))
		
		return {'up': pin_up, 'down': pin_down}
	
	def update(self):
		"""Update timer each frame"""
		pass  # Timer calculated on-demand in get_time_remaining()
	
	def get_time_remaining(self):
		elapsed = (datetime.now() - self.start_time).total_seconds()
		return max(0, self.duration_seconds - elapsed)
	
	def get_time_display(self):
		remaining = self.get_time_remaining()
		mins = int(remaining // 60)
		secs = int(remaining % 60)
		return f"{mins:02d}:{secs:02d}"
	
	def reset_pins(self):
		"""Reset pins via machine"""
		if self.machine:
			self.machine.reset_pins()
	
	def call_front_desk(self):
		print("Practice: Front desk called")
		# TODO_NETWORK: Alert server
	
	def get_scroll_message(self):
		return "Practice Mode - Use RESET to clear pins, CALL for assistance, START GAME when ready"
	
	def draw(self, surface, game_area_rect):
		pygame.draw.rect(surface, (45, 45, 65), game_area_rect, border_radius=20)
	
		cx, cy = game_area_rect.centerx, game_area_rect.centery
	
		# Title
		title = self.font_large.render("PRACTICE MODE", True, (255, 255, 255))
		surface.blit(title, title.get_rect(center=(cx, cy - 300)))
	
		# Timer
		timer = self.font_huge.render(self.get_time_display(), True, (255, 215, 0))
		surface.blit(timer, timer.get_rect(center=(cx, cy - 150)))
	
		label = self.font_medium.render("Time Remaining", True, (200, 200, 200))
		surface.blit(label, label.get_rect(center=(cx, cy - 100)))
	
		# Instructions - updated text
		inst1 = self.font_medium.render("Practice your throws", True, (200, 200, 200))
		surface.blit(inst1, inst1.get_rect(center=(cx, cy - 20)))
	
		inst2 = self.font_medium.render("Use buttons on the right to:", True, (200, 200, 200))
		surface.blit(inst2, inst2.get_rect(center=(cx, cy + 20)))
	
		inst3 = self.font_small.render("RESET - Clear pins  |  CALL - Contact desk  |  START GAME - Begin league game", True, (180, 180, 180))
		surface.blit(inst3, inst3.get_rect(center=(cx, cy + 60)))
	
		# Draw pin display (outside game area, in top right)
		self.draw_pin_display(surface)
	
	def draw_pin_display(self, surface):
		"""Draw current pin state display"""
		if not self.machine:
			return
		
		# Get current pin state from machine
		pin_state = self.machine.get_pin_state()
		
		# Draw background panel
		panel_x = self.pin_display_pos[0] - 20
		panel_y = self.pin_display_pos[1] - 20
		panel_width = 320
		panel_height = 220
		pygame.draw.rect(surface, (40, 40, 60), (panel_x, panel_y, panel_width, panel_height), border_radius=10)
		pygame.draw.rect(surface, (255, 255, 255), (panel_x, panel_y, panel_width, panel_height), 2, border_radius=10)
		
		# Title
		title = self.font_small.render("Pin Status", True, (255, 255, 255))
		surface.blit(title, (panel_x + 10, panel_y + 5))
		
		# Draw pins
		pin_values = [2, 3, 5, 3, 2]
		pin_labels = ["L2", "L3", "C5", "R3", "R2"]
		
		for i, (dx, dy) in enumerate(self.pin_layout):
			x = self.pin_display_pos[0] + dx
			y = self.pin_display_pos[1] + dy + 30
			
			# Draw pin image
			if pin_state[i] == 1:  # Pin is down
				surface.blit(self.pin_images['down'], (x, y))
			else:  # Pin is standing
				surface.blit(self.pin_images['up'], (x, y))
			
			# Draw label below pin
			label = self.font_small.render(pin_labels[i], True, (200, 200, 200))
			label_rect = label.get_rect(center=(x + self.pin_width // 2, y + self.pin_height + 12))
			surface.blit(label, label_rect)
	
	def handle_click(self, pos):
		# Nothing to click on in practice screen for now, till adding 5-pin buttons
		return None

	def _transition_to_game(self):
		"""Transition from practice to the configured game"""
		if not self.next_game_config:
			print("No game configured after practice")
			return
	
		config = self.next_game_config
	
		# Use game_manager if available (better approach)
		if hasattr(self, 'game_manager') and self.game_manager:
			if config['type'] == 'league':
				self.game_manager.transition_from_practice_to_league(config)
			else:
				print(f"Game type {config['type']} not supported yet")
			return
	
		# Fallback: direct transition (if no game manager)
		if config['type'] == 'league':
			from game.league import LeagueGame
		
			game = LeagueGame(
				settings=self.settings,
				parent=self.parent,
				bowlers=config['bowlers'],
				session_config=config['session_config'],
				game_modes=config.get('game_modes'),
				league_config=config['league_config'],
				network_client=getattr(self.parent, 'network_client', None)
			)
		
			self.parent.stop_game()
			self.parent.start_game(game)
			print("Transitioned to league game")