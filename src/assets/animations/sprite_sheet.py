import pygame
import sys
import os

# Add src directory to Python path so sprite_config can be imported
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
	sys.path.insert(0, src_dir)

from sprite_config import CELL_WIDTH, CELL_HEIGHT, SPRITE_WIDTH, SPRITE_HEIGHT, THEME_LAYOUT

class SpriteSheet:
	def __init__(self, image_file):
		"""Load the sprite sheet and pre-load all animations."""
		try:
			if not os.path.exists(image_file):
				raise FileNotFoundError(f"Sprite sheet not found: {image_file}")
			
			self.sprite_sheet = pygame.image.load(image_file).convert_alpha()
			print(f"Successfully loaded sprite sheet: {image_file}")
		except Exception as e:
			print(f"ERROR loading sprite sheet: {e}")
			print(f"Attempted path: {image_file}")
			# Create a dummy surface to prevent crashes
			self.sprite_sheet = pygame.Surface((850, 960), pygame.SRCALPHA)
			self.sprite_sheet.fill((255, 0, 255, 128))
			
		self.themes = {}
		
		# Offset within each cell to skip grey borders
		self.sprite_offset_x = 1  # Skip 1 pixel from left of each cell
		self.sprite_offset_y = 1  # Skip 1 pixel from top of each cell
		
		self._load_all_themes()
	
	def _grid_to_pixels(self, row, col):
		"""Convert grid position to pixel coordinates, with offset for borders."""
		# Use CELL dimensions for grid positioning, not SPRITE dimensions
		x = (col * CELL_WIDTH) + self.sprite_offset_x
		y = (row * CELL_HEIGHT) + self.sprite_offset_y
		return (x, y)
	
	def _load_all_themes(self):
		"""Pre-load all sprites for all themes."""
		for theme_name, animations in THEME_LAYOUT.items():
			self.themes[theme_name] = {}
			for anim_name, grid_positions in animations.items():
				self.themes[theme_name][anim_name] = []
				for row, col in grid_positions:
					x, y = self._grid_to_pixels(row, col)
					# Extract using the actual SPRITE dimensions (not CELL dimensions)
					sprite = self.get_image(x, y, SPRITE_WIDTH, SPRITE_HEIGHT)
					self.themes[theme_name][anim_name].append(sprite)
	
	def get_image(self, x, y, width, height):
		"""Extract a single image from the sprite sheet."""
		# Create a transparent surface
		sprite = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
		
		# Fill with transparent background (just to be sure)
		sprite.fill((0, 0, 0, 0))
		
		# Blit the section from the sprite sheet
		# The (x, y, width, height) defines the area to copy FROM the source
		sprite.blit(self.sprite_sheet, (0, 0), (x, y, width, height))
		
		return sprite
	
	def get_animation(self, theme, animation_name):
		"""Get all frames for a specific animation in a theme."""
		if theme in self.themes and animation_name in self.themes[theme]:
			return self.themes[theme][animation_name]
		return []
	
	def get_available_themes(self):
		"""Return list of available theme names."""
		return list(self.themes.keys())
	
	def get_available_animations(self, theme):
		"""Return list of available animation names for a theme."""
		if theme in self.themes:
			return list(self.themes[theme].keys())
		return []