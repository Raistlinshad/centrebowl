# -*- coding: utf-8 -*-

import pygame
import json
import os
from datetime import datetime, timedelta
from game_logger import GameLogger, create_logger

class FivePinGame:
	def __init__(self, settings, parent=None, bowlers=None, session_config=None, game_modes=None, network_client=None):
		self.name = "5-Pin Bowling"
		self.parent = parent
		self.settings = settings
		self.game_over_pause = False
		self.game_over_pause_start = None
		self.game_over_pause_duration = 60  # seconds
		self.network_client = network_client
		
		# Initialize logger
		log_path = os.path.join(os.path.dirname(__file__), '..', 'logs')
		self.logger = create_logger(log_dir=log_path)

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

		# Initialize game modes from config
		self.game_modes = {}
		if game_modes:
			if 'three_six_nine' in game_modes:
				from game.game_modes import ThreeSixNineMode
				self.game_modes['three_six_nine'] = ThreeSixNineMode(**game_modes['three_six_nine'])
			
			if 'turkey' in game_modes:
				from game_modes import TurkeyGame
				self.game_modes['turkey'] = TurkeyGame(**game_modes['turkey'])
			
			if 'prize_frame' in game_modes:
				from game_modes import PrizeFrameMode
				self.game_modes['prize_frame'] = PrizeFrameMode(**game_modes['prize_frame'])
			
			if 'strike_13' in game_modes:
				from game.game_modes import Strike13Mode
				self.game_modes['strike_13'] = Strike13Mode(**game_modes['strike_13'])
				for bowler in self.bowlers:
					self.game_modes['strike_13'].initialize_bowler(bowler)
		
		# Bowlers
		if bowlers is None:
			bowlers = ["Iron Man", "Superman", "Snoopi"]

		self.bowlers = []
		for bowler in bowlers:
			# Check if bowler is already a dict (from network/league game)
			if isinstance(bowler, dict):
				# Ensure it has all required fields
				new_bowler = {
					'name': str(bowler.get('name', 'Unknown')),  # Force to string
					'frames': self._create_empty_frames(),
					'frame_totals': [None] * 10,
					'current_frame': 0,
					'current_ball': 0,
					'total_score': 0,
					'pins_standing': [0,0,0,0,0],
					# Add league-specific fields if they exist
					'average': bowler.get('average', 0),
					'handicap': bowler.get('handicap', 0),
					'pre_bowl': bowler.get('pre_bowl', None),
					'absent': bowler.get('absent', False),
					'frames_this_turn': bowler.get('frames_this_turn', 0),
					'waiting_for_swap': bowler.get('waiting_for_swap', False)
				}
				self.bowlers.append(new_bowler)
			elif isinstance(bowler, str):
				# Simple string name (for 5-pin games)
				self.bowlers.append({
					'name': bowler,
					'frames': self._create_empty_frames(),
					'frame_totals': [None] * 10,
					'current_frame': 0,
					'current_ball': 0,
					'total_score': 0,
					'pins_standing': [0,0,0,0,0]
				})
			else:
				# Unknown type - convert to string
				self.bowlers.append({
					'name': str(bowler),
					'frames': self._create_empty_frames(),
					'frame_totals': [None] * 10,
					'current_frame': 0,
					'current_ball': 0,
					'total_score': 0,
					'pins_standing': [0,0,0,0,0]
				})

		# Add mode data to each bowler
		for bowler in self.bowlers:
			bowler['mode_data'] = {}

		bowler_names = [b['name'] for b in self.bowlers]
		if bowlers and isinstance(bowlers[0], dict):
			bowler_names = [b.get('name', 'Unknown') for b in bowlers]
			self.logger.log_info(f"Bowlers: {', '.join(bowler_names)}")
		else:
			self.logger.log_info(f"Bowlers: {', '.join(bowlers)}")

		self.current_bowler_index = 0
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

	def _create_empty_frames(self):
		return [{
			'balls': [None]*3, 
			'symbols': [None]*3, 
			'pins': [None]*3,  # ADD: Pin state for each ball [0,0,0,0,0]
			'pins_before': [[0,0,0,0,0], [None]*2, [None]*2]
		} for _ in range(10)]

	@property
	def current_bowler(self):
		return self.bowlers[self.current_bowler_index]
	
	@property
	def pins_standing(self):
		return self.current_bowler['pins_standing']
	
	@pins_standing.setter
	def pins_standing(self, value):
		self.current_bowler['pins_standing'] = value

	def process_ball(self, pins_result):
		if self.session_expired or self.session_complete or self.between_games:
			self.logger.log_error("Ball processing blocked", {
				'expired': self.session_expired,
				'complete': self.session_complete,
				'between': self.between_games,
				'game_over_pause': self.game_over_pause
			})
			return
		
		if hasattr(self, 'hold_active') and self.hold_active:
			self.logger.log_error("Ball processing blocked - HOLD active")
			return
		
		bowler = self.current_bowler
		if bowler['current_frame'] >= 10:
			self.logger.log_error(f"Ball processing blocked - {bowler['name']} already finished (frame {bowler['current_frame']})")
			return
		
		# Log entry into 10th frame
		if bowler['current_frame'] == 9 and bowler['current_ball'] == 0:
			self.logger.log_frame_10_entry(bowler['name'], bowler['current_ball'])
		
		pins_before = bowler['pins_standing'].copy()
		
		# Check for auto-free strike application
		if 'strike_13' in self.game_modes:
			strike13 = self.game_modes['strike_13']
			if strike13.should_auto_apply_free_strikes(bowler, self.current_game_number):
				# Auto-apply free strike if it's first ball and no pins knocked
				if bowler['current_ball'] == 0 and sum(pins_result) == 0:
					pins_result = [1, 1, 1, 1, 1]  # Force all pins knocked
		
		bowler['frames'][bowler['current_frame']]['pins_before'][bowler['current_ball']] = bowler['pins_standing'].copy()
		
		pins_knocked = []
		ball_score = 0
		for i in range(5):
			if bowler['pins_standing'][i] == 0 and pins_result[i] == 1:
				pins_knocked.append(1)
				ball_score += self.pin_values[i]
			else:
				pins_knocked.append(0)
		
		# STRIKE 13 CHECK: L or R on first ball counts as strike
		is_strike_13 = False
		if 'strike_13' in self.game_modes and bowler['current_ball'] == 0:
			strike13 = self.game_modes['strike_13']
			if strike13.check_l_or_r_strike(pins_knocked):
				# L or R achieved - treat as strike
				pins_result = [1, 1, 1, 1, 1]
				pins_knocked = [1, 1, 1, 1, 1]
				ball_score = 15
				is_strike_13 = True
		
		bowler['pins_standing'] = pins_result.copy()
		bowler['frames'][bowler['current_frame']]['balls'][bowler['current_ball']] = ball_score
		bowler['frames'][bowler['current_frame']]['pins'][bowler['current_ball']] = pins_result.copy()
		
		symbol = None
		if bowler['current_ball'] == 0:
			# STRIKE 13 CHECK: Single pin remaining after FIRST BALL counts as strike
			single_pin_strike = False
			if 'strike_13' in self.game_modes:
				strike13 = self.game_modes['strike_13']
				if strike13.check_single_pin_remaining(bowler['pins_standing']):
					# Single pin remaining - treat as strike
					single_pin_strike = True
			
			pattern = ''.join(str(p) for p in pins_knocked)
			symbol = self.patterns.get(pattern, str(ball_score) if ball_score > 0 else '-')
			
			if sum(pins_knocked) == 5 or is_strike_13 or single_pin_strike:
				symbol = 'X'
				bowler['frames'][bowler['current_frame']]['symbols'][0] = symbol
				self.save_game()
				
				# Don't end the frame if it's the 10th frame - bowler needs 2 more balls
				if bowler['current_frame'] != 9:
					self.next_frame()
					self.calculate_score()
					return
		
		elif bowler['current_ball'] == 1:
			# Check if this is 10th frame after a strike (single pin rule applies)
			single_pin_strike_10th = False
			if bowler['current_frame'] == 9 and 'strike_13' in self.game_modes:
				# If first ball was a strike, treat this as a "first ball" for single pin rule
				if bowler['frames'][9]['symbols'][0] == 'X':
					strike13 = self.game_modes['strike_13']
					if strike13.check_single_pin_remaining(bowler['pins_standing']):
						single_pin_strike_10th = True
			
			# Handle 10th frame single pin strike
			if single_pin_strike_10th:
				symbol = 'X'
				bowler['frames'][bowler['current_frame']]['symbols'][1] = symbol
				bowler['current_ball'] = 2
				self.reset_pins()
				self.save_game()
				self.calculate_score()
				return
			
			# Normal spare logic
			if sum(bowler['pins_standing']) == 5:
				symbol = '/'
				bowler['frames'][bowler['current_frame']]['symbols'][1] = symbol
				
				if bowler['current_frame'] == 9:
					bowler['current_ball'] = 2
					self.reset_pins()
					self.save_game()
					self.calculate_score()
					return
				else:
					self.save_game()
					self.calculate_score()
					self.next_frame()
					return
			else:
				symbol = str(ball_score) if ball_score > 0 else '-'
		
		elif bowler['current_ball'] == 2:
			# 10th frame ball 3 - check for strike or single pin strike
			if bowler['current_frame'] == 9:
				single_pin_strike = False
				if 'strike_13' in self.game_modes:
					strike13 = self.game_modes['strike_13']
					# Single pin rule applies if previous ball was a strike OR spare (pins were reset)
					if bowler['frames'][9]['symbols'][1] in ['X', '/']:
						if strike13.check_single_pin_remaining(bowler['pins_standing']):
							single_pin_strike = True
				
				if sum(pins_knocked) == 5 or single_pin_strike:
					symbol = 'X'
				elif sum(bowler['pins_standing']) == 0:
					pattern = ''.join(str(p) for p in pins_knocked)
					symbol = self.patterns.get(pattern, str(ball_score) if ball_score > 0 else '-')
				else:
					symbol = str(ball_score) if ball_score > 0 else '-'
			else:
				symbol = str(ball_score) if ball_score > 0 else '-'
		
		if symbol is None:
			symbol = str(ball_score) if ball_score > 0 else '-'
		
		bowler['frames'][bowler['current_frame']]['symbols'][bowler['current_ball']] = symbol
		self.save_game()
		bowler['current_ball'] += 1

		# DETAILED DEBUG LOGGING
		self.logger.log_debug(
			f"{bowler['name']} | After increment: current_ball={bowler['current_ball']} | "
			f"Frame: {bowler['current_frame']} | Symbol just set: {symbol} | "
			f"Pins standing: {bowler['pins_standing']} (sum={sum(bowler['pins_standing'])})"
		)

		# Log the ball thrown
		self.logger.log_ball(
			bowler['name'],
			bowler['current_frame'],
			bowler['current_ball'],
			pins_before,
			pins_result,
			ball_score,
			symbol if symbol else 'pending'
		)
		
		# CRITICAL: Log 10th frame decision points
		is_tenth_frame = (bowler['current_frame'] == 9)
		all_pins_down = (sum(bowler['pins_standing']) == 5)
		
		if is_tenth_frame:
			self.logger.log_debug(
				f"{bowler['name']} Frame 10 decision point | "
				f"current_ball={bowler['current_ball']} | "
				f"all_pins_down={all_pins_down} | "
				f"Will check: ball>=3? {bowler['current_ball'] >= 3} | "
				f"ball==1 and all_down? {bowler['current_ball'] == 1 and all_pins_down} | "
				f"ball==2 and all_down? {bowler['current_ball'] == 2 and all_pins_down}"
			)
			
			self.logger.log_frame_10_ball(
				bowler['name'],
				bowler['current_ball'],
				bowler['pins_standing'],
				all_pins_down,
				bowler['current_ball'] < 3  # Will continue? (changed from < 2)
			)
			
			if bowler['current_ball'] >= 3:
				self.logger.log_frame_10_exit(
					bowler['name'],
					3,
					bowler['frames'][9]['symbols'],
					sum(s for s in bowler['frames'][9]['balls'] if s is not None)
				)
				self.next_frame()
			elif bowler['current_ball'] == 1 and all_pins_down:
				self.logger.log_info(f"{bowler['name']} Frame 10: Strike/Spare on ball 1 - resetting pins for ball 2")
				self.reset_pins()
			elif bowler['current_ball'] == 2 and all_pins_down:
				self.logger.log_info(f"{bowler['name']} Frame 10: Strike/Spare on ball 2 - resetting pins for ball 3")
				self.reset_pins()
		else:
			if all_pins_down or bowler['current_ball'] >= 3:
				self.logger.log_frame_complete(
					bowler['name'],
					bowler['current_frame'],
					bowler['frames'][bowler['current_frame']],
					bowler['frame_totals'][bowler['current_frame']]
				)
				self.next_frame()
		
		self.calculate_score()

	# New method: Handle free strike button click
	def use_free_strike(self, bowler_index):
		"""Apply a free strike to the current frame for the specified bowler"""
		if 'strike_13' not in self.game_modes:
			return False
		
		strike13 = self.game_modes['strike_13']
		bowler = self.bowlers[bowler_index]
		
		# Must be on first ball of a frame
		if bowler['current_ball'] != 0:
			return False
		
		# Must have free strikes remaining
		if not strike13.can_use_free_strike(bowler, self.current_game_number, bowler['current_frame'], 0):
			return False
		
		# Apply the free strike
		if strike13.use_free_strike(bowler, self.current_game_number, bowler['current_frame']):
			# Simulate perfect strike
			pins_result = [1, 1, 1, 1, 1]
			self.process_ball(pins_result)
			return True
		
		return False

	def reset_pins(self):
		self.current_bowler['pins_standing'] = [0,0,0,0,0]

		# Reset Pin Area
		if self.parent and hasattr(self.parent, 'pin_area'):
			self.parent.pin_area.reset_pins()
			
		if self.parent and hasattr(self.parent, 'ball_button'):
			self.parent.ball_button.reset()

	def next_frame(self):
		bowler = self.current_bowler
		old_frame = bowler['current_frame']
		bowler['current_frame'] += 1
		bowler['current_ball'] = 0
		self.reset_pins()

		# SEND FRAME DATA TO SERVER
		if self.network_client and old_frame < 10:
			frame_data = {
				'frame_num': old_frame,
				'balls': bowler['frames'][old_frame]['balls'],
				'symbols': bowler['frames'][old_frame]['symbols'],
				'total': bowler['frame_totals'][old_frame]
			}
			self.network_client.send_frame_data(
				bowler['name'],
				old_frame,
				frame_data
			)
		
		if bowler['current_frame'] >= 10:
			self.logger.log_bowler_complete(bowler['name'], bowler['total_score'])
			
			all_finished = all(b['current_frame'] >= 10 for b in self.bowlers)
			if all_finished:
				self.logger.log_info("All bowlers finished - game complete")
				self.handle_game_complete()
				return
			else:
				remaining = [b['name'] for b in self.bowlers if b['current_frame'] < 10]
				self.logger.logger.log_info(f"Bowlers still playing: {remaining}")
		
		old_bowler = self.bowlers[self.current_bowler_index]['name']
		self.bowlers.append(self.bowlers.pop(self.current_bowler_index))
		self.current_bowler_index = 0
		new_bowler = self.current_bowler['name']
		
		self.logger.log_turn_rotation(
			old_bowler,
			new_bowler,
			f"Frame {old_frame} complete"
		)

	def handle_game_complete(self):
		bowler_scores = [(b['name'], b['total_score']) for b in self.bowlers]
		self.logger.log_game_complete(bowler_scores)
		
		self.save_completed_game()

		# SEND GAME COMPLETE TO SERVER
		if self.network_client:
			game_data = {
				'game_type': '5-pin',
				'game_number': self.current_game_number,
				'bowlers': bowler_scores,
				'timestamp': datetime.now().isoformat()
			}
			self.network_client.send_game_complete(game_data)
		
		# Start game over pause timer
		self.game_over_pause = True
		self.game_over_pause_start = datetime.now()
		self.game_over_pause_duration = 60  # seconds
		
		if self.session_config['mode'] == 'games':
			if self.current_game_number >= self.session_config['total_games']:
				self.session_complete = True
			else:
				self.current_game_number += 1
				self.start_between_games_timer()
		elif self.session_config['mode'] == 'time':
			elapsed = (datetime.now() - self.session_start_time).total_seconds() / 60
			if elapsed >= self.session_config['total_time_minutes']:
				self.session_expired = True
			else:
				self.current_game_number += 1
				self.start_between_games_timer()
	
	def start_between_games_timer(self):
		self.between_games = True
		self.next_game_timer = datetime.now()
	
	def check_next_game_timer(self):
		if self.between_games and self.next_game_timer:
			elapsed = (datetime.now() - self.next_game_timer).total_seconds()
			if elapsed >= 300:
				self.start_next_game()
				return True
		return False
	
	def start_next_game(self):
		self.between_games = False
		self.next_game_timer = None
		
		for bowler in self.bowlers:
			bowler['frames'] = self._create_empty_frames()
			bowler['frame_totals'] = [None] * 10
			bowler['current_frame'] = 0
			bowler['current_ball'] = 0
			bowler['total_score'] = 0
			bowler['pins_standing'] = [0,0,0,0,0]
		
		self.current_bowler_index = 0
		self.reset_pins()
	
	def get_game_info_display(self):
		"""Get the game info text for top bar display"""
		# Safe access with defaults
		mode = self.session_config.get('mode', 'games')
	
		if mode == 'games':
			total = self.session_config.get('total_games', 1)
			return f"Game {self.current_game_number} of {total}"
		elif mode == 'time':
			total_time = self.session_config.get('total_time_minutes', 60)
			elapsed_mins = (datetime.now() - self.session_start_time).total_seconds() / 60
			remaining_mins = total_time - elapsed_mins
			if remaining_mins <= 0:
				return "Time: 0 min"
			return f"Time: {int(remaining_mins)} min"
	
		return f"Game {self.current_game_number}"
	
	def get_scroll_message(self):
		"""Get current scroll message based on session state"""
		# PRIORITY: Game over pause message
		if self.game_over_pause:
			if self.game_over_pause_start:
				elapsed = (datetime.now() - self.game_over_pause_start).total_seconds()
				remaining = int(self.game_over_pause_duration - elapsed)
				if remaining > 0:
					return f"Game Over! Thanks for Playing! Screen will close in {remaining} seconds, then you can start the next game when ready!"
				else:
					# Pause complete, transition to next state
					self.game_over_pause = False
					# Now check session status
					if self.session_config['mode'] == 'games':
						if self.current_game_number >= self.session_config['total_games']:
							self.session_complete = True
						else:
							self.current_game_number += 1
							self.start_between_games_timer()
					elif self.session_config['mode'] == 'time':
						elapsed_total = (datetime.now() - self.session_start_time).total_seconds() / 60
						if elapsed_total >= self.session_config['total_time_minutes']:
							self.session_expired = True
						else:
							self.current_game_number += 1
							self.start_between_games_timer()
		"""Get current scroll message based on session state"""
		if self.session_complete:
			return "Please see front desk"
		if self.session_expired:
			return "Time has expired! Please see front desk to add more time. Game will close in 5 min."
		if self.between_games:
			if self.next_game_timer:
				elapsed = (datetime.now() - self.next_game_timer).total_seconds()
				remaining = int(300 - elapsed)
				if remaining > 0:
					mins, secs = divmod(remaining, 60)
					return f"Next game starts in {mins}:{secs:02d}"
		
		if self.session_config['mode'] == 'games':
			if self.current_game_number == self.session_config['total_games']:
				return "Reminder: This is your last game"
		elif self.session_config['mode'] == 'time':
			elapsed_mins = (datetime.now() - self.session_start_time).total_seconds() / 60
			remaining_mins = self.session_config['total_time_minutes'] - elapsed_mins
			
			if remaining_mins <= 30:
				for interval in [30, 25, 20, 15, 10, 5]:
					if remaining_mins <= interval and remaining_mins > (interval - 5):
						key = f"warning_{interval}"
						if key not in self.time_warning_given:
							self.time_warning_given[key] = True
							return f"You have {int(remaining_mins)} minutes left to play. Contact front desk if you want to add more time."
		
		return "Welcome to Centrebowl! Good luck!"
	
	def update_session_config(self, new_config):
		if 'add_games' in new_config:
			self.session_config['total_games'] += new_config['add_games']
			self.session_complete = False
		if 'add_time_minutes' in new_config:
			self.session_config['total_time_minutes'] += new_config['add_time_minutes']
			self.session_expired = False

	def calculate_score(self):
		"""Calculate score and populate bonus balls in frames"""
		bowler = self.current_bowler
		
		# First pass: populate bonus balls into strike/spare frames
		for frame_num in range(10):
			frame = bowler['frames'][frame_num]
			if frame['balls'][0] is None:
				break
			
			# Strike bonus - needs next 2 balls
			if frame['symbols'][0] == 'X':
				if frame['balls'][1] is None or frame['balls'][2] is None:
					# Look ahead for bonus balls
					bonus_balls = []
					for next_frame_num in range(frame_num + 1, 10):
						next_frame = bowler['frames'][next_frame_num]
						for ball_idx, ball_score in enumerate(next_frame['balls']):
							if ball_score is not None:
								bonus_balls.append(ball_score)
							if len(bonus_balls) >= 2:
								break
						if len(bonus_balls) >= 2:
							break
					
					# Populate bonus balls - SHOW VALUES ONLY (not symbols from other frames)
					if len(bonus_balls) >= 1 and frame['balls'][1] is None:
						frame['balls'][1] = bonus_balls[0]
						frame['symbols'][1] = str(bonus_balls[0])  # ADD: Show the numeric value
					if len(bonus_balls) >= 2 and frame['balls'][2] is None:
						frame['balls'][2] = bonus_balls[1]
						frame['symbols'][2] = str(bonus_balls[1])  # ADD: Show the numeric value
			
			# Spare bonus - needs next 1 ball
			elif frame['symbols'][1] == '/':
				# For frames 0-8: need to get next ball from following frame
				# For frame 9 (10th frame): bonus is already in ball 3
				if frame_num < 9 and frame['balls'][2] is None:
					# Look ahead for the next ball
					for next_frame_num in range(frame_num + 1, 10):
						next_frame = bowler['frames'][next_frame_num]
						if next_frame['balls'][0] is not None:
							frame['balls'][2] = next_frame['balls'][0]
							frame['symbols'][2] = str(next_frame['balls'][0])  # ADD: Show the numeric value
							break
		
		# Second pass: calculate cumulative totals
		total = 0
		for frame_num in range(10):
			frame = bowler['frames'][frame_num]
			if frame['balls'][0] is None:
				break
			
			# Sum all balls in this frame (including bonuses)
			frame_score = sum(score for score in frame['balls'] if score is not None)
			total += frame_score
			bowler['frame_totals'][frame_num] = total
		
		bowler['total_score'] = total

	def toggle_hold(self):
		if self.session_expired or self.session_complete:
			return False
		if not hasattr(self, 'hold_active'):
			self.hold_active = False
		self.hold_active = not self.hold_active
		return self.hold_active

	def skip_bowler(self):
		if self.session_expired or self.session_complete or self.between_games:
			return
		self.save_game()
		self.current_bowler_index = (self.current_bowler_index + 1) % len(self.bowlers)
		self.reset_pins()

	def draw(self, surface, game_area_rect):
		# During game over pause, show the normal game screen with scores
		if self.game_over_pause:
			self.draw_game_screen(surface, game_area_rect)
			return
		
		if self.between_games:
			self.draw_between_games_screen(surface, game_area_rect)
			return
		if self.session_expired or self.session_complete:
			self.draw_session_end_screen(surface, game_area_rect)
			return
		
		self.draw_game_screen(surface, game_area_rect)
	
	def draw_game_screen(self, surface, game_area_rect):
		"""Draw the game screen with updated dimensions for 1920×1080"""
		
		# NEW LAYOUT DIMENSIONS with proper borders
		border_left = 18  # Left border space inside game area
		border_right = 18  # Right border space inside game area
		start_x = game_area_rect.x + border_left  # Shift right with border
		start_y = game_area_rect.y + 10
		
		# Row dimensions - HALF HEIGHT
		bowler_height = 110  # Was 220
		bowler_gap = 15  # Gap between bowler rows
		
		# Column widths - EXPANDED
		name_width = 160  # Was 120 (33% wider)
		frame_width = 118  # Was 108 (adjusted for fit)
		total_width = 133  # Was 100 (33% wider)
		
		# Header dimensions
		header_y = start_y
		header_height = 35
		
		# Internal frame dimensions (scaled for half height)
		ball_box_width = 38
		ball_box_height = 25  # Was 30
		ball_box_spacing = 40  # Space between ball boxes
		frame_total_height = 35  # Was 50
		
		# Calculate total width to verify fit
		# name(160) + 10*frames(118*10=1180) + total(133) = 1473px
		# Leaves ~240px for buttons/pins on right (plenty of space)
		
		# Determine which bowlers to show (MAX 6 VISIBLE)
		max_visible_bowlers = 6
		
		if len(self.bowlers) <= max_visible_bowlers:
			visible_bowlers = list(enumerate(self.bowlers))
		else:
			# Show current bowler plus context
			current_idx = self.current_bowler_index
			
			# Keep current bowler in positions 2-4 (middle of visible range)
			if current_idx < 2:
				start_idx = 0
			elif current_idx >= len(self.bowlers) - 3:
				start_idx = len(self.bowlers) - max_visible_bowlers
			else:
				start_idx = current_idx - 2
			
			visible_bowlers = [(i, self.bowlers[i]) for i in range(start_idx, start_idx + max_visible_bowlers)]
		
		# DRAW HEADER ROW
		pygame.draw.rect(surface, (40,40,60), (start_x, header_y, name_width, header_height))
		pygame.draw.rect(surface, (255,255,255), (start_x, header_y, name_width, header_height), 1)
		label = self.font_small.render("Bowler", True, (255,255,255))
		surface.blit(label, label.get_rect(center=(start_x + name_width//2, header_y + header_height//2)))
		
		# Frame number headers
		for i in range(10):
			fx = start_x + name_width + i * frame_width
			pygame.draw.rect(surface, (40,40,60), (fx, header_y, frame_width, header_height))
			pygame.draw.rect(surface, (255,255,255), (fx, header_y, frame_width, header_height), 1)
			txt = self.font_small.render(str(i+1), True, (255,255,255))
			surface.blit(txt, txt.get_rect(center=(fx + frame_width//2, header_y + header_height//2)))
		
		# Total column header
		total_x = start_x + name_width + 10 * frame_width
		pygame.draw.rect(surface, (40,40,60), (total_x, header_y, total_width, header_height))
		pygame.draw.rect(surface, (255,255,255), (total_x, header_y, total_width, header_height), 1)
		tot_lbl = self.font_small.render("Total", True, (255,255,255))
		surface.blit(tot_lbl, tot_lbl.get_rect(center=(total_x + total_width//2, header_y + header_height//2)))
		
		# Store button rects for Strike 13 mode
		if not hasattr(self, 'strike13_button_rects'):
			self.strike13_button_rects = []
		self.strike13_button_rects = []
		
		# DRAW BOWLER ROWS (max 6 visible)
		for display_idx, (actual_idx, bowler) in enumerate(visible_bowlers):
			row_y = header_y + header_height + display_idx * (bowler_height + bowler_gap)
			
			# Highlight current bowler
			is_current = (actual_idx == self.current_bowler_index)
			color = (70,90,120) if is_current else (50,50,70)
			
			# Name column
			pygame.draw.rect(surface, color, (start_x, row_y, name_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (start_x, row_y, name_width, bowler_height), 2)
			
			# Draw bowler name (centered vertically)
			name_y = row_y + bowler_height // 2
			name_txt = self.font_medium.render(bowler['name'], True, (255,255,255))
			surface.blit(name_txt, name_txt.get_rect(center=(start_x + name_width//2, name_y)))
			
			# STRIKE 13: Draw free strike button if applicable
			if 'strike_13' in self.game_modes:
				strike13 = self.game_modes['strike_13']
				display_info = strike13.get_display_info(bowler)
				
				if display_info['show_button']:
					btn_size = 40  # Smaller to fit half-height row
					btn_x = start_x + (name_width - btn_size) // 2
					btn_y = row_y + bowler_height - btn_size - 8
					btn_rect = pygame.Rect(btn_x, btn_y, btn_size, btn_size)
					
					self.strike13_button_rects.append((btn_rect, actual_idx))
					
					btn_color = (0, 150, 0) if is_current and bowler['current_ball'] == 0 else (100, 100, 100)
					pygame.draw.rect(surface, btn_color, btn_rect, border_radius=5)
					pygame.draw.rect(surface, (255,255,255), btn_rect, 2, border_radius=5)
					
					x_txt = self.font_small.render(display_info['button_text'], True, (255,255,255))
					surface.blit(x_txt, x_txt.get_rect(center=(btn_x + btn_size//2, btn_y + btn_size//2 - 3)))
					
					count_txt = self.font_small.render(display_info['count_text'], True, (255,215,0))
					surface.blit(count_txt, count_txt.get_rect(center=(btn_x + btn_size//2, btn_y + btn_size + 8)))
			
			# Draw 10 frames
			for fn in range(10):
				fx = start_x + name_width + fn * frame_width
				frame = bowler['frames'][fn]
				pygame.draw.rect(surface, (255,255,255), (fx, row_y, frame_width, bowler_height), 2)
				
				# Draw 3 ball boxes - TIGHTER SPACING with 5px margins
				frame_inner_margin = 5  # 5px from frame edge
				available_width = frame_width - (2 * frame_inner_margin)  # 108px available
				ball_box_width = 33  # Width of each ball box
				gap_between_boxes = (available_width - (3 * ball_box_width)) // 2  # Space between the 3 boxes
				
				for ball_idx in range(3):
					bx = fx + frame_inner_margin + ball_idx * (ball_box_width + gap_between_boxes)
					by = row_y + 8
					pygame.draw.rect(surface, (255,255,255), (bx, by, ball_box_width, ball_box_height), 1)
					
					if frame['symbols'][ball_idx]:
						sym = self.font_small.render(str(frame['symbols'][ball_idx]), True, (255,255,255))
						surface.blit(sym, sym.get_rect(center=(bx + ball_box_width//2, by + ball_box_height//2)))
				
				# Frame total box - also respects 5px margins
				tby = row_y + 8 + ball_box_height + 8
				total_box_width = frame_width - (2 * frame_inner_margin)
				pygame.draw.rect(surface, (100,100,120), (fx + frame_inner_margin, tby, total_box_width, frame_total_height))
				pygame.draw.rect(surface, (255,255,255), (fx + frame_inner_margin, tby, total_box_width, frame_total_height), 1)
				
				if bowler['frame_totals'][fn]:
					ftxt = self.font_medium.render(str(bowler['frame_totals'][fn]), True, (255,255,255))
					surface.blit(ftxt, ftxt.get_rect(center=(fx + frame_width//2, tby + frame_total_height//2)))
			
			# Total column
			pygame.draw.rect(surface, color, (total_x, row_y, total_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (total_x, row_y, total_width, bowler_height), 2)
			score_txt = self.font_large.render(str(bowler['total_score']), True, (255,215,0))
			surface.blit(score_txt, score_txt.get_rect(center=(total_x + total_width//2, row_y + bowler_height//2)))
		
		# BOTTOM INFO LINE
		ind_y = header_y + header_height + max_visible_bowlers * (bowler_height + bowler_gap) + 10
		
		cb = self.current_bowler
		ind = self.font_medium.render(f"Bowling: {cb['name']} - Frame {cb['current_frame']+1}, Ball {cb['current_ball']+1}", True, (255,215,0))
		surface.blit(ind, (start_x + 20, ind_y))
		
		tot = sum(b['total_score'] for b in self.bowlers)
		tot_txt = self.font_medium.render(f"Total: {tot}", True, (255,215,0))
		surface.blit(tot_txt, tot_txt.get_rect(right=total_x + total_width - 20, top=ind_y))
	
	def draw_between_games_screen(self, surface, game_area_rect):
		overlay = pygame.Surface((game_area_rect.width, game_area_rect.height))
		overlay.set_alpha(200)
		overlay.fill((40,40,60))
		surface.blit(overlay, (game_area_rect.x, game_area_rect.y))
		
		title = self.font_large.render(f"Game {self.current_game_number-1} Complete!", True, (255,255,255))
		surface.blit(title, title.get_rect(center=(game_area_rect.centerx, game_area_rect.centery - 150)))
		
		if self.next_game_timer:
			elapsed = (datetime.now() - self.next_game_timer).total_seconds()
			remaining = int(300 - elapsed)
			if remaining > 0:
				mins, secs = divmod(remaining, 60)
				timer = self.font_large.render(f"Next game in: {mins}:{secs:02d}", True, (255,215,0))
				surface.blit(timer, timer.get_rect(center=(game_area_rect.centerx, game_area_rect.centery - 50)))
		
		bw, bh = 300, 80
		bx, by = game_area_rect.centerx - bw//2, game_area_rect.centery + 50
		self.next_game_button_rect = pygame.Rect(bx, by, bw, bh)
		pygame.draw.rect(surface, (0,150,0), self.next_game_button_rect, border_radius=10)
		pygame.draw.rect(surface, (255,255,255), self.next_game_button_rect, 3, border_radius=10)
		btxt = self.font_large.render("START NEXT GAME", True, (255,255,255))
		surface.blit(btxt, btxt.get_rect(center=self.next_game_button_rect.center))
	
	def draw_session_end_screen(self, surface, game_area_rect):
		overlay = pygame.Surface((game_area_rect.width, game_area_rect.height))
		overlay.set_alpha(220)
		overlay.fill((60,40,40))
		surface.blit(overlay, (game_area_rect.x, game_area_rect.y))
		
		title = "All Games Complete!" if self.session_complete else "Time Expired!"
		msg = "Please see front desk" if self.session_complete else "Please see front desk to add more time"
		
		t = self.font_large.render(title, True, (255,255,255))
		surface.blit(t, t.get_rect(center=(game_area_rect.centerx, game_area_rect.centery - 100)))
		m = self.font_medium.render(msg, True, (255,215,0))
		surface.blit(m, m.get_rect(center=(game_area_rect.centerx, game_area_rect.centery)))
		c = self.font_small.render("Game will close in 5 minutes", True, (200,200,200))
		surface.blit(c, c.get_rect(center=(game_area_rect.centerx, game_area_rect.centery + 80)))
	
	def handle_click(self, pos):
		# Check between games button
		if self.between_games and hasattr(self, 'next_game_button_rect'):
			if self.next_game_button_rect.collidepoint(pos):
				self.start_next_game()
				return True
		
		# Check Strike 13 free strike buttons
		if hasattr(self, 'strike13_button_rects'):
			for btn_rect, bowler_idx in self.strike13_button_rects:
				if btn_rect.collidepoint(pos):
					# Only allow clicking for current bowler on first ball
					if bowler_idx == self.current_bowler_index:
						if self.use_free_strike(bowler_idx):
							return True
		
		return False

	def save_game(self):
		try:
			data = {'game_id': self.game_id, 'game_type': '5-pin', 'current_bowler_index': self.current_bowler_index, 'bowlers': self.bowlers}
			temp = self.current_game_file + '.tmp'
			with open(temp, 'w') as f:
				json.dump(data, f, indent=2)
			os.replace(temp, self.current_game_file)
		except Exception as e:
			print(f"Save error: {e}")

	def save_completed_game(self):
		try:
			data = {'game_id': self.game_id, 'game_type': '5-pin', 'bowlers': [{'name': b['name'], 'final_score': b['total_score']} for b in self.bowlers]}
			with open(os.path.join(self.completed_games_dir, f"5pin_{self.game_id}.json"), 'w') as f:
				json.dump(data, f, indent=2)
		except Exception as e:
			print(f"Save error: {e}")

	def clear_current_game(self):
		try:
			if os.path.exists(self.current_game_file):
				os.remove(self.current_game_file)
		except:
			pass
		
	def start_next_game(self):
		self.between_games = False
		self.next_game_timer = None
		
		for bowler in self.bowlers:
			bowler['frames'] = self._create_empty_frames()
			bowler['frame_totals'] = [None] * 10
			bowler['current_frame'] = 0
			bowler['current_ball'] = 0
			bowler['total_score'] = 0
			bowler['pins_standing'] = [0,0,0,0,0]
			
			# Reset Strike 13 mode data
			if 'strike_13' in self.game_modes:
				self.game_modes['strike_13'].reset_for_new_game(bowler)
		
		self.current_bowler_index = 0
		self.reset_pins()