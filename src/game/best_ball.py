# -*- coding: utf-8 -*-

import pygame
import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BestBallGame:
	def __init__(self, settings, parent=None, bowlers=None, session_config=None, game_modes=None, paired_lane=None, network_client=None):
		self.name = "Best Ball"
		self.parent = parent
		self.settings = settings
		self.network_client = network_client
		
		# Pin values [left-two, left-three, center-five, right-three, right-two]
		self.pin_values = [2, 3, 5, 3, 2]
		
		# Symbol patterns (1=knocked, 0=standing)
		self.patterns = {
			'00011': 'C\\O', '11000': 'C/O', '01001': 'A',
			'01111': 'L', '11110': 'R', '00100': 'HP',
			'10100': 'SL', '00101': 'SR', '11111': 'X', '00000': '-'
		}
		
		# Session configuration
		if session_config is None:
			session_config = {'mode': 'games', 'total_games': 1, 'total_time_minutes': None, 'frames_per_turn': 1}
		self.session_config = session_config
		self.current_game_number = 1
		self.session_start_time = datetime.now()
		self.session_expired = False
		self.session_complete = False
		self.between_games = False
		self.next_game_timer = None
		self.time_warning_given = {}
		
		# Paired lane support (for alternating lanes)
		self.paired_lane = paired_lane
		self.current_lane = 'primary'  # or 'paired'
		
		# Parse teams from bowlers list
		# Expected format: ["Bruce / Kevin", "Marie / Jessica"]
		if bowlers is None:
			bowlers = ["Bruce / Kevin", "Marie / Jessica"]
		
		self.teams = []
		for team_str in bowlers:
			names = [n.strip() for n in team_str.split('/')]
			if len(names) != 2:
				names = [team_str, "Partner"]  # Fallback if format is wrong
			
			self.teams.append({
				'bowler1': names[0],
				'bowler2': names[1],
				'frames': self._create_empty_frames(),
				'frame_totals': [None] * 10,
				'current_frame': 0,
				'current_ball': 0,
				'current_bowler': 1,  # 1 or 2
				'total_score': 0,
				'pins_standing': [0,0,0,0,0],
				'bowler1_result': None,  # Stores first bowler's throw result
				'bowler2_result': None,  # Stores second bowler's throw result
			})
		
		self.current_team_index = 0
		self.awaiting_selection = False  # True when showing ball selection screen
		self.game_over = False
		self.game_over_timer = None
		
		self.game_id = datetime.now().strftime("%Y%m%d_%H%M%S")
		
		# Save paths
		self.save_dir = "game_saves"
		self.current_game_file = os.path.join(self.save_dir, "current_game.json")
		self.completed_games_dir = os.path.join(self.save_dir, "completed")
		os.makedirs(self.save_dir, exist_ok=True)
		os.makedirs(self.completed_games_dir, exist_ok=True)
		
		# Fonts
		self.font_large = pygame.font.SysFont(None, 48)
		self.font_medium = pygame.font.SysFont(None, 36)
		self.font_small = pygame.font.SysFont(None, 28)
		
		# Pin display areas for selection (will be initialized in draw)
		self.selection_rects = {'bowler1': None, 'bowler2': None}

	def _create_empty_frames(self):
		return [{
			'balls': [None]*3, 
			'symbols': [None]*3, 
			'pins': [None]*3,
			'pins_before': [[0,0,0,0,0], [0,0,0,0,0], [0,0,0,0,0]]
		} for _ in range(10)]

	@property
	def current_team(self):
		return self.teams[self.current_team_index]
	
	@property
	def pins_standing(self):
		return self.current_team['pins_standing']
	
	@pins_standing.setter
	def pins_standing(self, value):
		self.current_team['pins_standing'] = value

	def process_ball(self, pins_result):
		if self.session_expired or self.session_complete or self.between_games or self.game_over:
			return
		if hasattr(self, 'hold_active') and self.hold_active:
			return
		if self.awaiting_selection:
			return  # Don't process balls during selection
		
		team = self.current_team
		if team['current_frame'] >= 10:
			return
		
		# Store pins before this ball
		team['frames'][team['current_frame']]['pins_before'][team['current_ball']] = team['pins_standing'].copy()
		
		# Calculate what was knocked down
		pins_knocked = []
		ball_score = 0
		for i in range(5):
			if team['pins_standing'][i] == 0 and pins_result[i] == 1:
				pins_knocked.append(1)
				ball_score += self.pin_values[i]
			else:
				pins_knocked.append(0)
		
		# Update pin state
		team['pins_standing'] = pins_result.copy()
		
		# Generate symbol
		symbol = None
		if team['current_ball'] == 0:
			pattern = ''.join(str(p) for p in pins_knocked)
			symbol = self.patterns.get(pattern, str(ball_score) if ball_score > 0 else '-')
			
			if sum(pins_knocked) == 5:  # Strike
				symbol = 'X'
		
		elif team['current_ball'] == 1:
			if sum(team['pins_standing']) == 5:  # Spare
				symbol = '/'
			else:
				symbol = str(ball_score) if ball_score > 0 else '-'
		
		elif team['current_ball'] == 2:
			if team['current_frame'] == 9 and sum(pins_knocked) == 5:
				symbol = 'X'
			elif team['current_frame'] == 9 and sum(team['pins_standing']) == 5:
				symbol = '/'
			else:
				symbol = str(ball_score) if ball_score > 0 else '-'
		
		if symbol is None:
			symbol = str(ball_score) if ball_score > 0 else '-'
		
		# Store this bowler's result
		result = {
			'pins_result': pins_result.copy(),
			'pins_knocked': pins_knocked,
			'ball_score': ball_score,
			'symbol': symbol,
			'pins_standing': team['pins_standing'].copy()
		}
		
		if team['current_bowler'] == 1:
			team['bowler1_result'] = result
			
			# Check if strike or spare on ball 1 - auto-select and continue
			if team['current_ball'] == 0 and symbol == 'X':
				self._apply_ball_result(result)
				self.next_frame()
				return
			elif team['current_ball'] == 1 and symbol == '/':
				self._apply_ball_result(result)
				if team['current_frame'] == 9:  # 10th frame spare
					team['current_ball'] = 2
					self.reset_pins()
					self.calculate_score()
				else:
					self.next_frame()
				return
			
			# Reset pins for bowler 2
			team['pins_standing'] = team['frames'][team['current_frame']]['pins_before'][team['current_ball']].copy()
			team['current_bowler'] = 2
			
			# Update ball button to reflect reset pins
			if self.parent and hasattr(self.parent, 'ball_button'):
				self.parent.ball_button.balls = team['pins_standing'].copy()
			
		elif team['current_bowler'] == 2:
			team['bowler2_result'] = result
			
			# Check if strike or spare - auto-select and continue
			if team['current_ball'] == 0 and symbol == 'X':
				self._apply_ball_result(result)
				self.next_frame()
				return
			elif team['current_ball'] == 1 and symbol == '/':
				self._apply_ball_result(result)
				if team['current_frame'] == 9:  # 10th frame spare
					team['current_ball'] = 2
					self.reset_pins()
					self.calculate_score()
				else:
					self.next_frame()
				return
			
			# Show selection screen
			self.awaiting_selection = True
		
		self.save_game()

	def _apply_ball_result(self, result):
		"""Apply the selected ball result to the frame"""
		team = self.current_team
		frame = team['frames'][team['current_frame']]
		
		frame['balls'][team['current_ball']] = result['ball_score']
		frame['symbols'][team['current_ball']] = result['symbol']
		frame['pins'][team['current_ball']] = result['pins_result'].copy()
		team['pins_standing'] = result['pins_standing'].copy()
		
		team['current_ball'] += 1
		team['current_bowler'] = 1  # Reset to bowler 1
		team['bowler1_result'] = None
		team['bowler2_result'] = None
		
		# Check if frame is done
		is_tenth_frame = (team['current_frame'] == 9)
		all_pins_down = (sum(team['pins_standing']) == 5)
		
		if is_tenth_frame:
			if team['current_ball'] >= 3:
				self.next_frame()
			elif team['current_ball'] == 1 and all_pins_down:
				self.reset_pins()
			elif team['current_ball'] == 2 and all_pins_down:
				self.reset_pins()
		else:
			if all_pins_down or team['current_ball'] >= 2:
				self.next_frame()
		
		self.calculate_score()

	def handle_selection(self, selected_bowler):
		"""Handle selection of best ball from either bowler 1 or 2"""
		if not self.awaiting_selection:
			return
		
		team = self.current_team
		
		if selected_bowler == 1:
			result = team['bowler1_result']
		else:
			result = team['bowler2_result']
		
		self._apply_ball_result(result)
		
		self.awaiting_selection = False
		self.save_game()
		
		# Update ball button pins
		if self.parent and hasattr(self.parent, 'ball_button'):
			self.parent.ball_button.balls = team['pins_standing'].copy()

	def reset_pins(self):
		self.current_team['pins_standing'] = [0,0,0,0,0]
		if self.parent and hasattr(self.parent, 'ball_button'):
			self.parent.ball_button.reset()

	def next_frame(self):
		team = self.current_team
		team['current_frame'] += 1
		team['current_ball'] = 0
		team['current_bowler'] = 1
		self.reset_pins()
		
		if team['current_frame'] >= 10:
			all_finished = all(t['current_frame'] >= 10 for t in self.teams)
			if all_finished:
				self.handle_game_complete()
				return
		
		# Move to next team
		self.teams.append(self.teams.pop(self.current_team_index))
		self.current_team_index = 0
		
		# Handle paired lane switching
		if self.paired_lane is not None:
			if self.current_lane == 'primary':
				self.current_lane = 'paired'
				# TODO_NETWORK: Signal lane switch to paired_lane
			else:
				self.current_lane = 'primary'
				# TODO_NETWORK: Signal lane switch back to primary

	def handle_game_complete(self):
		"""Handle completion of current game - may start next game or end session"""
		self.save_completed_game()
		
		# Check if there are more games to play
		if self.session_config['mode'] == 'games':
			if self.current_game_number >= self.session_config['total_games']:
				# All games complete
				self.game_over = True
				self.game_over_timer = datetime.now()
			else:
				# More games to play
				self.current_game_number += 1
				self.start_next_game()
		else:
			# Time-based mode - always end after game completes
			self.game_over = True
			self.game_over_timer = datetime.now()

	def start_next_game(self):
		"""Start the next game - swap lanes if paired_lane is set"""
		logger.info(f"Starting game {self.current_game_number}")
		
		# Handle lane swapping for even-numbered games (2, 4, 6, etc.)
		if self.paired_lane is not None and self.current_game_number % 2 == 0:
			logger.info(f"Game {self.current_game_number} - swapping all teams to paired lane {self.paired_lane}")
			self._send_all_teams_to_paired_lane()
		elif self.paired_lane is not None and self.current_game_number % 2 == 1:
			logger.info(f"Game {self.current_game_number} - teams return to primary lane")
		
		# Reset all teams for new game
		for team in self.teams:
			team['frames'] = self._create_empty_frames()
			team['frame_totals'] = [None] * 10
			team['current_frame'] = 0
			team['current_ball'] = 0
			team['current_bowler'] = 1
			team['total_score'] = 0
			team['pins_standing'] = [0,0,0,0,0]
			team['bowler1_result'] = None
			team['bowler2_result'] = None
		
		self.current_team_index = 0
		self.awaiting_selection = False
		self.reset_pins()
		self.save_game()
	
	def _send_all_teams_to_paired_lane(self):
		"""Send all teams to the paired lane for next game via network"""
		if not self.network_client:
			logger.error("No network client for Best Ball team swap")
			return
		
		teams_data = []
		for team in self.teams:
			team_data = {
				'bowler1': team['bowler1'],
				'bowler2': team['bowler2'],
				'game_number': self.current_game_number
			}
			teams_data.append(team_data)
		
		# Send via network
		message_data = {
			'type': 'best_ball_team_swap',
			'teams': teams_data,
			'game_number': self.current_game_number
		}
		
		# Use team_move but with best_ball identifier
		success = self.network_client.send_team_move(message_data, self.paired_lane)
		
		if success:
			logger.info(f"Sent {len(teams_data)} Best Ball teams to lane {self.paired_lane}")
			# Clear teams locally
			self.teams.clear()
			self.current_team_index = 0
		else:
			logger.error("Failed to send Best Ball teams")
	
	def receive_teams_from_paired_lane(self, teams_data):
		"""Receive teams from paired lane for new game (via network)"""
		logger.info(f"Receiving {len(teams_data)} teams from lane {self.paired_lane}")
		
		# Clear existing teams
		self.teams = []
		
		# Reconstruct teams from received data
		for team_data in teams_data:
			self.teams.append({
				'bowler1': team_data['bowler1'],
				'bowler2': team_data['bowler2'],
				'frames': self._create_empty_frames(),
				'frame_totals': [None] * 10,
				'current_frame': 0,
				'current_ball': 0,
				'current_bowler': 1,
				'total_score': 0,
				'pins_standing': [0,0,0,0,0],
				'bowler1_result': None,
				'bowler2_result': None,
			})
		
		self.current_team_index = 0
		self.awaiting_selection = False
		self.reset_pins()
		logger.info("Teams received and ready for new game")

	def calculate_score(self):
		"""Calculate score and populate bonus balls in frames"""
		team = self.current_team
		
		# First pass: populate bonus balls into strike/spare frames
		for frame_num in range(10):
			frame = team['frames'][frame_num]
			if frame['balls'][0] is None:
				break
			
			# Strike bonus - needs next 2 balls
			if frame['symbols'][0] == 'X':
				if frame['balls'][1] is None or frame['balls'][2] is None:
					bonus_balls = []
					bonus_symbols = []
					for next_frame_num in range(frame_num + 1, 10):
						next_frame = team['frames'][next_frame_num]
						for ball_idx, ball_score in enumerate(next_frame['balls']):
							if ball_score is not None:
								bonus_balls.append(ball_score)
								bonus_symbols.append(next_frame['symbols'][ball_idx])
							if len(bonus_balls) >= 2:
								break
						if len(bonus_balls) >= 2:
							break
					
					if len(bonus_balls) >= 1 and frame['balls'][1] is None:
						frame['balls'][1] = bonus_balls[0]
						frame['symbols'][1] = bonus_symbols[0]
					if len(bonus_balls) >= 2 and frame['balls'][2] is None:
						frame['balls'][2] = bonus_balls[1]
						frame['symbols'][2] = bonus_symbols[1]
			
			# Spare bonus - needs next 1 ball
			elif frame['symbols'][1] == '/':
				if frame_num < 9 and frame['balls'][2] is None:
					for next_frame_num in range(frame_num + 1, 10):
						next_frame = team['frames'][next_frame_num]
						if next_frame['balls'][0] is not None:
							frame['balls'][2] = next_frame['balls'][0]
							frame['symbols'][2] = next_frame['symbols'][0]
							break
		
		# Second pass: calculate cumulative totals
		total = 0
		for frame_num in range(10):
			frame = team['frames'][frame_num]
			if frame['balls'][0] is None:
				break
			
			frame_score = sum(score for score in frame['balls'] if score is not None)
			total += frame_score
			team['frame_totals'][frame_num] = total
		
		team['total_score'] = total

	def toggle_hold(self):
		if self.session_expired or self.session_complete or self.game_over:
			return False
		if not hasattr(self, 'hold_active'):
			self.hold_active = False
		self.hold_active = not self.hold_active
		return self.hold_active

	def draw(self, surface, game_area_rect):
		if self.game_over:
			self.draw_game_over_screen(surface, game_area_rect)
			return
		
		if self.awaiting_selection:
			self.draw_selection_screen(surface, game_area_rect)
			return
		
		self.draw_game_screen(surface, game_area_rect)
	
	def draw_game_screen(self, surface, game_area_rect):
		start_x, start_y = game_area_rect.x + 10, game_area_rect.y + 10
		bowler_height, name_width, frame_width, total_width = 220, 120, 108, 100
		header_y, header_height = start_y, 35
		
		# Header
		pygame.draw.rect(surface, (40,40,60), (start_x, header_y, name_width, header_height))
		pygame.draw.rect(surface, (255,255,255), (start_x, header_y, name_width, header_height), 1)
		label = self.font_small.render("Team", True, (255,255,255))
		surface.blit(label, label.get_rect(center=(start_x + name_width//2, header_y + header_height//2)))
		
		for i in range(10):
			fx = start_x + name_width + i * frame_width
			pygame.draw.rect(surface, (40,40,60), (fx, header_y, frame_width, header_height))
			pygame.draw.rect(surface, (255,255,255), (fx, header_y, frame_width, header_height), 1)
			txt = self.font_small.render(str(i+1), True, (255,255,255))
			surface.blit(txt, txt.get_rect(center=(fx + frame_width//2, header_y + header_height//2)))
		
		total_x = start_x + name_width + 10 * frame_width
		pygame.draw.rect(surface, (40,40,60), (total_x, header_y, total_width, header_height))
		pygame.draw.rect(surface, (255,255,255), (total_x, header_y, total_width, header_height), 1)
		tot_lbl = self.font_small.render("Total", True, (255,255,255))
		surface.blit(tot_lbl, tot_lbl.get_rect(center=(total_x + total_width//2, header_y + header_height//2)))
		
		# Teams
		for idx, team in enumerate(self.teams):
			row_y = header_y + header_height + idx * bowler_height
			color = (70,90,120) if idx == self.current_team_index else (50,50,70)
			
			# Name box - show both bowlers vertically
			pygame.draw.rect(surface, color, (start_x, row_y, name_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (start_x, row_y, name_width, bowler_height), 2)
			
			# Highlight current bowler
			bowler1_color = (255,255,255) if (idx == self.current_team_index and team['current_bowler'] == 1) else (200,200,200)
			bowler2_color = (255,255,255) if (idx == self.current_team_index and team['current_bowler'] == 2) else (200,200,200)
			
			name1_txt = self.font_small.render(team['bowler1'], True, bowler1_color)
			name2_txt = self.font_small.render(team['bowler2'], True, bowler2_color)
			surface.blit(name1_txt, name1_txt.get_rect(center=(start_x + name_width//2, row_y + bowler_height//3)))
			surface.blit(name2_txt, name2_txt.get_rect(center=(start_x + name_width//2, row_y + 2*bowler_height//3)))
			
			# Frames
			for fn in range(10):
				fx = start_x + name_width + fn * frame_width
				frame = team['frames'][fn]
				pygame.draw.rect(surface, (255,255,255), (fx, row_y, frame_width, bowler_height), 2)
				
				for ball in range(3):
					bx = fx + 5 + ball * 35
					by = row_y + 10
					pygame.draw.rect(surface, (255,255,255), (bx, by, 34, 30), 1)
					if frame['symbols'][ball]:
						sym = self.font_small.render(str(frame['symbols'][ball]), True, (255,255,255))
						surface.blit(sym, sym.get_rect(center=(bx + 17, by + 15)))
				
				tby = row_y + 50
				pygame.draw.rect(surface, (100,100,120), (fx + 5, tby, frame_width - 10, 50))
				pygame.draw.rect(surface, (255,255,255), (fx + 5, tby, frame_width - 10, 50), 1)
				if team['frame_totals'][fn]:
					ftxt = self.font_medium.render(str(team['frame_totals'][fn]), True, (255,255,255))
					surface.blit(ftxt, ftxt.get_rect(center=(fx + frame_width//2, tby + 25)))
			
			# Total score
			pygame.draw.rect(surface, color, (total_x, row_y, total_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (total_x, row_y, total_width, bowler_height), 2)
			score_txt = self.font_large.render(str(team['total_score']), True, (255,215,0))
			surface.blit(score_txt, score_txt.get_rect(center=(total_x + total_width//2, row_y + bowler_height//2)))
		
		# Current bowler indicator
		ind_y = header_y + header_height + len(self.teams) * bowler_height + 20
		ct = self.current_team
		bowler_name = ct['bowler1'] if ct['current_bowler'] == 1 else ct['bowler2']
		ind = self.font_medium.render(f"Bowling: {bowler_name} - Frame {ct['current_frame']+1}, Ball {ct['current_ball']+1}", True, (255,215,0))
		surface.blit(ind, (start_x + 20, ind_y))
	
	def draw_selection_screen(self, surface, game_area_rect):
		"""Draw the ball selection screen with pin displays"""
		# Semi-transparent overlay
		overlay = pygame.Surface((game_area_rect.width, game_area_rect.height))
		overlay.set_alpha(230)
		overlay.fill((40,40,60))
		surface.blit(overlay, (game_area_rect.x, game_area_rect.y))
		
		team = self.current_team
		
		# Title
		title = self.font_large.render("Select Best Ball", True, (255,255,255))
		surface.blit(title, title.get_rect(center=(game_area_rect.centerx, game_area_rect.y + 80)))
		
		# Two side-by-side pin displays
		box_width = 300
		box_height = 400
		spacing = 50
		left_x = game_area_rect.centerx - box_width - spacing//2
		right_x = game_area_rect.centerx + spacing//2
		box_y = game_area_rect.centery - box_height//2
		
		# Bowler 1 box
		self.selection_rects['bowler1'] = pygame.Rect(left_x, box_y, box_width, box_height)
		pygame.draw.rect(surface, (70,90,120), self.selection_rects['bowler1'], border_radius=10)
		pygame.draw.rect(surface, (255,255,255), self.selection_rects['bowler1'], 3, border_radius=10)
		
		b1_name = self.font_medium.render(team['bowler1'], True, (255,255,255))
		surface.blit(b1_name, b1_name.get_rect(center=(left_x + box_width//2, box_y + 30)))
		
		# Draw pins for bowler 1
		if team['bowler1_result']:
			self._draw_pin_display(surface, (left_x + box_width//2 - 80, box_y + 100), team['bowler1_result']['pins_result'])
			score_txt = self.font_large.render(f"Score: {team['bowler1_result']['ball_score']}", True, (255,215,0))
			surface.blit(score_txt, score_txt.get_rect(center=(left_x + box_width//2, box_y + 280)))
			sym_txt = self.font_medium.render(f"Symbol: {team['bowler1_result']['symbol']}", True, (200,200,200))
			surface.blit(sym_txt, sym_txt.get_rect(center=(left_x + box_width//2, box_y + 330)))
		
		# Bowler 2 box
		self.selection_rects['bowler2'] = pygame.Rect(right_x, box_y, box_width, box_height)
		pygame.draw.rect(surface, (70,90,120), self.selection_rects['bowler2'], border_radius=10)
		pygame.draw.rect(surface, (255,255,255), self.selection_rects['bowler2'], 3, border_radius=10)
		
		b2_name = self.font_medium.render(team['bowler2'], True, (255,255,255))
		surface.blit(b2_name, b2_name.get_rect(center=(right_x + box_width//2, box_y + 30)))
		
		# Draw pins for bowler 2
		if team['bowler2_result']:
			self._draw_pin_display(surface, (right_x + box_width//2 - 80, box_y + 100), team['bowler2_result']['pins_result'])
			score_txt = self.font_large.render(f"Score: {team['bowler2_result']['ball_score']}", True, (255,215,0))
			surface.blit(score_txt, score_txt.get_rect(center=(right_x + box_width//2, box_y + 280)))
			sym_txt = self.font_medium.render(f"Symbol: {team['bowler2_result']['symbol']}", True, (200,200,200))
			surface.blit(sym_txt, sym_txt.get_rect(center=(right_x + box_width//2, box_y + 330)))
		
		# Instructions
		inst = self.font_small.render("Tap a result to select it", True, (200,200,200))
		surface.blit(inst, inst.get_rect(center=(game_area_rect.centerx, box_y + box_height + 40)))
	
	def _draw_pin_display(self, surface, pos, pins_result):
		"""Draw a pin display showing which pins are up (0) or down (1)"""
		pin_positions = [
			(0, 0),	  # Far left
			(40, 60),	# Left
			(80, 120),   # Head pin
			(120, 60),   # Right
			(160, 0),	# Far right
		]
		
		for i, (dx, dy) in enumerate(pin_positions):
			x = pos[0] + dx
			y = pos[1] + dy
			# Pin down = black/dark, Pin up = white
			color = (50,50,50) if pins_result[i] == 1 else (255,255,255)
			pygame.draw.ellipse(surface, color, (x, y, 40, 80))
			pygame.draw.ellipse(surface, (220, 38, 38), (x+5, y+30, 30, 10))
	
	def draw_game_over_screen(self, surface, game_area_rect):
		"""Draw game over screen with 5 minute warning"""
		overlay = pygame.Surface((game_area_rect.width, game_area_rect.height))
		overlay.set_alpha(220)
		overlay.fill((60,40,40))
		surface.blit(overlay, (game_area_rect.x, game_area_rect.y))
		
		title = self.font_large.render("Game Complete!", True, (255,255,255))
		surface.blit(title, title.get_rect(center=(game_area_rect.centerx, game_area_rect.centery - 100)))
		
		msg1 = self.font_medium.render("See front desk for results", True, (255,215,0))
		surface.blit(msg1, msg1.get_rect(center=(game_area_rect.centerx, game_area_rect.centery)))
		
		msg2 = self.font_medium.render("Closing game in 5 min", True, (200,200,200))
		surface.blit(msg2, msg2.get_rect(center=(game_area_rect.centerx, game_area_rect.centery + 60)))
		
		# Show countdown
		if self.game_over_timer:
			elapsed = (datetime.now() - self.game_over_timer).total_seconds()
			remaining = int(300 - elapsed)
			if remaining > 0:
				mins, secs = divmod(remaining, 60)
				timer = self.font_large.render(f"{mins}:{secs:02d}", True, (255,100,100))
				surface.blit(timer, timer.get_rect(center=(game_area_rect.centerx, game_area_rect.centery + 130)))

	def handle_click(self, pos):
		if self.awaiting_selection:
			if self.selection_rects['bowler1'] and self.selection_rects['bowler1'].collidepoint(pos):
				self.handle_selection(1)
				return True
			elif self.selection_rects['bowler2'] and self.selection_rects['bowler2'].collidepoint(pos):
				self.handle_selection(2)
				return True
		return False
	
	def get_scroll_message(self):
		"""Get current scroll message"""
		if self.game_over:
			return "Game complete - see front desk for results"
		
		if self.awaiting_selection:
			team = self.current_team
			return f"Select the best ball for {team['bowler1']} / {team['bowler2']}"
		
		if self.paired_lane is not None:
			return f"Welcome to Best Ball! Currently on Lane {self.current_lane.upper()}"
		
		return "Welcome to Best Ball! Work together to score the highest!"
	
	def get_game_info_display(self):
		"""Get the game info text for top bar display"""
		return f"Game {self.current_game_number}"
	
	def save_game(self):
		try:
			data = {
				'game_id': self.game_id,
				'game_type': 'bestball',
				'current_team_index': self.current_team_index,
				'teams': self.teams,
				'awaiting_selection': self.awaiting_selection,
				'current_lane': self.current_lane,
				'paired_lane': self.paired_lane
			}
			temp = self.current_game_file + '.tmp'
			with open(temp, 'w') as f:
				json.dump(data, f, indent=2)
			os.replace(temp, self.current_game_file)
		except Exception as e:
			print(f"Save error: {e}")

	def save_completed_game(self):
		try:
			data = {
				'game_id': self.game_id,
				'game_type': 'bestball',
				'teams': [
					{
						'bowler1': t['bowler1'],
						'bowler2': t['bowler2'],
						'final_score': t['total_score']
					} for t in self.teams
				]
			}
			# TODO_NETWORK: Send completed game data to server for results processing
			with open(os.path.join(self.completed_games_dir, f"bestball_{self.game_id}.json"), 'w') as f:
				json.dump(data, f, indent=2)
		except Exception as e:
			print(f"Save error: {e}")

	def clear_current_game(self):
		try:
			if os.path.exists(self.current_game_file):
				os.remove(self.current_game_file)
		except:
			pass
	
	def update(self):
		"""Called each frame for timer updates"""
		if self.game_over:
			if self.check_game_over_timer():
				# TODO_NETWORK: Signal game closure to server
				if self.parent:
					# Close the game or return to main menu
					pass