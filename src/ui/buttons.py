# -*- coding: utf-8 -*-

import pygame
import random

class BallButton:
	def __init__(self, name, pos, color=None):
		self.rect = pygame.Rect(pos[0], pos[1], 200, 100)
		
		# Set color based on button name if not provided
		if color is None:
			if name == "RESET":
				self.color = (70, 130, 180)  # Blue
			elif name == "CALL":
				self.color = (200, 100, 50)  # Orange
			elif name == "SKIP":
				self.color = (150, 150, 150)  # Gray
			elif name == "START":
				self.color = (50, 180, 80)  # Green
			else:
				self.color = (255, 165, 0)  # Default orange
		else:
			self.color = color
		
		self.font = pygame.font.SysFont(None, 48 if len(name) <= 5 else 36)
		self.text = self.font.render(str(name), True, (255, 255, 255))  # White text
		self.balls = [0,0,0,0,0]
		self.is_final_ball = False

	def draw(self, surface):
		pygame.draw.rect(surface, self.color, self.rect)
		surface.blit(self.text, (self.rect.x + 50, self.rect.y + 25))

	def handle_event(self, event):
		if event.type == pygame.MOUSEBUTTONDOWN:
			if self.rect.collidepoint(event.pos):
				return True
		return False
	
	def handle_ball(self):
		# Process ball
		for i in range(len(self.balls)):
			if self.balls[i] == 0:
				if random.random() < 0.75:
					self.balls[i] = 1
		
		# Save Current State
		current_state = self.balls.copy()

		# Check if last ball or not but proceed
		if self.is_final_ball:
			self.reset()
			self.is_final_ball = False
		
		return current_state
	
	def set_final_ball(self, is_final):
		# Swap Flags
		self.is_final_ball = is_final

	
	def reset(self):
		self.balls = [0,0,0,0,0]
		return self.balls
	
	def hold(self):
		print("Pressed Hold Button") #TODO: Create a game hold system
		#TODO: Call server if pressed, if called from server, make server updates if any and resume game
		pass

	def skip(self):
		print("Pressed Skip Button") #TODO: move to next bowler / skip turn
		pass
	