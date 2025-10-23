# -*- coding: utf-8 -*-

# league.py
from game.five_pin import FivePinGame
import pygame

class LeagueGame(FivePinGame):
	def __init__(self, settings, parent=None, bowlers=None, session_config=None, 
				 game_modes=None, league_config=None, network_client=None):
		
		# Enhance bowlers with league data
		if bowlers:
			for bowler in bowlers:
				bowler.setdefault('average', 0)
				bowler.setdefault('handicap', 0)
				bowler.setdefault('pre_bowl', None)
				bowler.setdefault('absent', False)
				bowler.setdefault('frames_this_turn', 0)
				bowler.setdefault('waiting_for_swap', False)
		
		# Call parent __init__ with network_client
		super().__init__(settings, parent, bowlers, session_config, game_modes, network_client)
		
		self.name = "League Game"
		self.league_config = league_config or {}
		self.paired_lane = self.league_config.get('paired_lane')
		self.move_mode = self.league_config.get('move_mode', 'bowler')
		self.frames_per_turn = self.league_config.get('frames_per_turn', 1)
		self.total_config = self.league_config.get('total_config', '1a')
		self.heads_up = self.league_config.get('heads_up', False)
		self.options_enabled = self.league_config.get('options_enabled', False)
		self.absent_score = self.league_config.get('absent_score', 230)
		
		self.paired_lane_data = {}  # Bowler position -> score data
		self.absent_frame_threshold = 3

		# Track pending move confirmations
		self.pending_move_ids = {}
	
	def next_frame(self):
		"""Override to handle turn counting and team/bowler moves"""
		bowler = self.current_bowler

		# Check for pre-bowl
		if bowler.get('pre_bowl') and not bowler.get('absent'):
			if self.process_pre_bowl_turn(bowler):
				return

		bowler['current_frame'] += 1
		bowler['current_ball'] = 0
		bowler['frames_this_turn'] += 1
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
		
		# Check for absent bowlers
		self.check_absent_bowlers()
		
		if bowler['current_frame'] >= 10:
			# Bowler finished game
			all_finished = all(b['current_frame'] >= 10 for b in self.bowlers)
			if all_finished:
				self.handle_game_complete()
				return
		
		# Check if bowler completed their turn
		if bowler['frames_this_turn'] >= self.frames_per_turn:
			bowler['frames_this_turn'] = 0
			
			if self.move_mode == 'bowler':
				# Move individual bowler to paired lane
				# TODO_NETWORK: Send bowler to paired lane
				self.bowlers.remove(bowler)
				print(f"{bowler['name']} moving to lane {self.paired_lane}")
				# Server will add them to paired lane
			elif self.move_mode == 'team':
				# Mark waiting for team swap
				bowler['waiting_for_swap'] = True
				self.bowlers.append(self.bowlers.pop(self.current_bowler_index))
				self.current_bowler_index = 0
				
				# Check if all bowlers waiting
				if all(b['waiting_for_swap'] or b['current_frame'] >= 10 for b in self.bowlers):
					# TODO_NETWORK: Signal ready for team swap
					print("Team ready to swap lanes")
		else:
			# Continue turn, rotate to next bowler
			self.bowlers.append(self.bowlers.pop(self.current_bowler_index))
			self.current_bowler_index = 0
	
	def calculate_total_display(self, bowler, frame_num):
		"""Calculate total based on total_config"""
		raw_total = bowler['frame_totals'][frame_num]
		if raw_total is None:
			return None
		
		handicap = bowler['handicap']
		config = self.total_config
		
		# Base configs
		if config == '1a':
			return str(raw_total)
		elif config == '2a':
			return str(raw_total + handicap)
		elif config == '3a':
			return f"{raw_total + handicap} ({raw_total})"
		elif config == '4a':
			return f"{raw_total} ({raw_total + handicap})"
		elif config == '5a':
			max_potential = self.calculate_max_potential(bowler, frame_num)
			return f"{raw_total} ({max_potential})"
		elif config == '6a':
			max_potential = self.calculate_max_potential(bowler, frame_num)
			return f"{raw_total + handicap} ({max_potential})"
		
		# Heads-up configs (b, c, d variants)
		base_display = self.calculate_total_display_base(raw_total, handicap, config[:-1] + 'a')
		
		if config.endswith('b') and self.heads_up:
			# Get paired bowler score
			paired_score = self.get_paired_bowler_score(bowler)
			if paired_score:
				return f"{base_display}\n({paired_score})"
		
		elif config.endswith('c') and self.heads_up:
			paired_score = self.get_paired_bowler_score(bowler)
			if paired_score:
				diff = raw_total - paired_score
				sign = '+' if diff > 0 else ''
				return f"{base_display}\n({sign}{diff})"
		
		return base_display
	
	def calculate_total_display_base(self, raw, hdcp, config):
		"""Helper for base total calculation"""
		if config == '1a': return str(raw)
		elif config == '2a': return str(raw + hdcp)
		elif config == '3a': return f"{raw + hdcp} ({raw})"
		elif config == '4a': return f"{raw} ({raw + hdcp})"
		return str(raw)
	
	def calculate_max_potential(self, bowler, current_frame):
		"""Calculate max score if all remaining frames are strikes"""
		current_total = bowler['frame_totals'][current_frame] or 0
		remaining_frames = 10 - current_frame - 1
		# Strikes worth 15 + 15 + 15 in 5-pin = 45 per frame
		max_remaining = remaining_frames * 45
		return current_total + max_remaining
	
	def get_paired_bowler_score(self, bowler):
		"""Get corresponding bowler's score from paired lane"""
		bowler_position = self.bowlers.index(bowler)
		return self.paired_lane_data.get(bowler_position)
	
	def update_paired_lane_data(self, data):
		"""Receive paired lane scores from server"""
		# data = {position: score, ...}
		self.paired_lane_data = data

	def draw_game_screen(self, surface, game_area_rect):
		# DEBUG: Log bowler data structure
		if not hasattr(self, '_debug_logged'):
			print("=" * 60)
			print("LEAGUE GAME BOWLERS DEBUG:")
			for i, b in enumerate(self.bowlers):
				print(f"  Bowler {i}: type={type(b)}, keys={list(b.keys()) if isinstance(b, dict) else 'N/A'}")
				if isinstance(b, dict):
					print(f"	name={b.get('name')} (type: {type(b.get('name'))})")
					print(f"	average={b.get('average')}")
					print(f"	handicap={b.get('handicap')}")
			print("=" * 60)
			self._debug_logged = True

		"""Override to add league-specific displays"""
		start_x, start_y = game_area_rect.x + 18, game_area_rect.y + 10  # Match five_pin
		bowler_height = 110  # FIXED: was 220, should match five_pin
		bowler_gap = 15
		name_width = 160  # FIXED: was 120
		frame_width = 118  # FIXED: was 108  
		total_width = 133  # FIXED: was 100
		header_y, header_height = start_y, 35
		
		# Draw header (same as parent)
		pygame.draw.rect(surface, (40,40,60), (start_x, header_y, name_width, header_height))
		pygame.draw.rect(surface, (255,255,255), (start_x, header_y, name_width, header_height), 1)
		label = self.font_small.render("Bowler", True, (255,255,255))
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
		
		# Bowlers with league enhancements
		for idx, bowler in enumerate(self.bowlers):
			row_y = header_y + header_height + idx * bowler_height
			
			# Highlight: current (blue), waiting (yellow), other (gray)
			if idx == self.current_bowler_index:
				color = (70,90,120)
			elif bowler.get('waiting_for_swap'):
				color = (120,100,30)  # Yellow for waiting
			else:
				color = (50,50,70)
			
			# Name area
			pygame.draw.rect(surface, color, (start_x, row_y, name_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (start_x, row_y, name_width, bowler_height), 2)

			# Draw bowler name (centered vertically)
			name_y = row_y + 40

			# SAFETY CHECK: Ensure name is a string
			bowler_name = bowler.get('name', 'Unknown')
			if not isinstance(bowler_name, str):
				bowler_name = str(bowler_name)

			name_txt = self.font_medium.render(bowler_name, True, (255,255,255))
			surface.blit(name_txt, name_txt.get_rect(center=(start_x + name_width//2, name_y)))
			
			# 3-6-9 dots (if active)
			dots_y = name_y + 30
			if 'three_six_nine' in self.game_modes:
				mode_data = bowler.get('mode_data', {}).get('369', {})
				dots_text = self.game_modes['three_six_nine'].get_display_text()
				if dots_text:
					dots = self.font_small.render(dots_text, True, (255,215,0))
					surface.blit(dots, dots.get_rect(center=(start_x + name_width//2, dots_y)))
					dots_y += 25
			
			# AVG and HDCP
			avg_txt = self.font_small.render(f"AVG: {bowler['average']}", True, (200,200,200))
			surface.blit(avg_txt, (start_x + 10, dots_y))
			hdcp_txt = self.font_small.render(f"HDCP: {bowler['handicap']}", True, (200,200,200))
			surface.blit(hdcp_txt, (start_x + 10, dots_y + 20))
			
			# Frames (same as parent)
			for fn in range(10):
				fx = start_x + name_width + fn * frame_width
				frame = bowler['frames'][fn]
				pygame.draw.rect(surface, (255,255,255), (fx, row_y, frame_width, bowler_height), 2)
				
				for ball in range(3):
					bx = fx + 5 + ball * 35
					by = row_y + 10
					pygame.draw.rect(surface, (255,255,255), (bx, by, 34, 30), 1)
					if frame['symbols'][ball]:
						sym = self.font_small.render(str(frame['symbols'][ball]), True, (255,255,255))
						surface.blit(sym, sym.get_rect(center=(bx + 17, by + 15)))
				
				# Frame total with league config
				tby = row_y + 50
				pygame.draw.rect(surface, (100,100,120), (fx + 5, tby, frame_width - 10, 50))
				pygame.draw.rect(surface, (255,255,255), (fx + 5, tby, frame_width - 10, 50), 1)
				
				total_display = self.calculate_total_display(bowler, fn)
				if total_display:
					# Handle multi-line totals (for b/c configs)
					if '\n' in total_display:
						lines = total_display.split('\n')
						ftxt1 = self.font_small.render(lines[0], True, (255,255,255))
						ftxt2 = self.font_small.render(lines[1], True, (180,180,180))
						surface.blit(ftxt1, ftxt1.get_rect(center=(fx + frame_width//2, tby + 15)))
						surface.blit(ftxt2, ftxt2.get_rect(center=(fx + frame_width//2, tby + 35)))
					else:
						ftxt = self.font_medium.render(total_display, True, (255,255,255))
						surface.blit(ftxt, ftxt.get_rect(center=(fx + frame_width//2, tby + 25)))
			
			# Game total
			pygame.draw.rect(surface, color, (total_x, row_y, total_width, bowler_height))
			pygame.draw.rect(surface, (255,255,255), (total_x, row_y, total_width, bowler_height), 2)
			
			# Use last frame's total display config
			last_frame = 9
			for i in range(9, -1, -1):
				if bowler['frame_totals'][i] is not None:
					last_frame = i
					break
			
			total_display = self.calculate_total_display(bowler, last_frame)
			if total_display:
				if '\n' in total_display:
					lines = total_display.split('\n')
					t1 = self.font_large.render(lines[0], True, (255,215,0))
					t2 = self.font_medium.render(lines[1], True, (200,200,150))
					surface.blit(t1, t1.get_rect(center=(total_x + total_width//2, row_y + bowler_height//2 - 15)))
					surface.blit(t2, t2.get_rect(center=(total_x + total_width//2, row_y + bowler_height//2 + 20)))
				else:
					score_txt = self.font_large.render(total_display, True, (255,215,0))
					surface.blit(score_txt, score_txt.get_rect(center=(total_x + total_width//2, row_y + bowler_height//2)))
		
		# Bottom indicator
		ind_y = header_y + header_height + len(self.bowlers) * bowler_height + 20
		game_info = f"Game {self.current_game_number}"
		if self.session_config['mode'] == 'games':
			game_info += f" of {self.session_config['total_games']}"
		game_info += f" vs Lane {self.paired_lane}"
		surface.blit(self.font_small.render(game_info, True, (200,200,200)), (start_x + 20, ind_y - 25))
		
		cb = self.current_bowler
		cb_name = str(cb.get('name', 'Unknown'))
		ind = self.font_medium.render(f"Bowling: {cb_name} - Frame {cb['current_frame']+1}, Ball {cb['current_ball']+1}", True, (255,215,0))
		surface.blit(ind, (start_x + 20, ind_y))
		
		tot = sum(b['total_score'] for b in self.bowlers)
		tot_txt = self.font_medium.render(f"Total: {tot}", True, (255,215,0))
		surface.blit(tot_txt, tot_txt.get_rect(right=total_x + total_width - 20, top=ind_y))

	def receive_bowler_from_paired_lane(self, bowler_data):
		"""Receive a bowler moving from paired lane via network"""
		self.logger.log_info(f"Receiving bowler {bowler_data['name']} from lane {self.paired_lane}")
		
		# Reconstruct bowler dict
		new_bowler = {
			'name': bowler_data['name'],
			'average': bowler_data['average'],
			'handicap': bowler_data['handicap'],
			'frames': bowler_data['frames'],
			'frame_totals': bowler_data['frame_totals'],
			'current_frame': bowler_data['current_frame'],
			'current_ball': bowler_data['current_ball'],
			'total_score': bowler_data['total_score'],
			'pins_standing': bowler_data['pins_standing'],
			'pre_bowl': bowler_data.get('pre_bowl'),
			'absent': bowler_data.get('absent', False),
			'frames_this_turn': 0,
			'waiting_for_swap': False,
			'mode_data': bowler_data.get('mode_data', {})
		}
		
		# Add to end of queue
		self.bowlers.append(new_bowler)
		self.logger.log_info(f"Added {new_bowler['name']} to bowling queue")

	def send_bowler_to_paired_lane(self, bowler):
		"""Send bowler to paired lane using network client"""
		if not self.network_client:
			self.logger.log_error("No network client available for bowler move")
			return
		
		# Generate unique move ID
		move_id = f"{self.network_client.lane_id}_{bowler['name']}_{datetime.now().timestamp()}"
		
		# Package bowler data
		bowler_data = {
			'name': bowler['name'],
			'average': bowler['average'],
			'handicap': bowler['handicap'],
			'frames': bowler['frames'],
			'frame_totals': bowler['frame_totals'],
			'current_frame': bowler['current_frame'],
			'current_ball': bowler['current_ball'],
			'total_score': bowler['total_score'],
			'pins_standing': bowler['pins_standing'],
			'pre_bowl': bowler.get('pre_bowl'),
			'absent': bowler.get('absent', False),
			'mode_data': bowler.get('mode_data', {})
		}
		
		# Callback for confirmation
		def on_confirm(success, message):
			if success:
				self.logger.log_info(f"Bowler {bowler['name']} successfully moved to lane {self.paired_lane}")
			else:
				self.logger.log_error(f"Failed to move bowler {bowler['name']}: {message}")
				# Re-add bowler to this lane
				self.bowlers.append(bowler)
		
		# Send via network
		success = self.network_client.send_bowler_move(
			bowler_data,
			self.paired_lane,
			move_id,
			callback=on_confirm
		)
		
		if success:
			# Remove from local list
			if bowler in self.bowlers:
				self.bowlers.remove(bowler)
				if self.current_bowler_index >= len(self.bowlers):
					self.current_bowler_index = 0
			
			self.logger.log_info(f"Sent {bowler['name']} to lane {self.paired_lane} (move_id: {move_id})")
		else:
			self.logger.log_error(f"Failed to send {bowler['name']} to paired lane")

	def execute_team_swap(self):
		"""Execute team swap using network client"""
		if not self.network_client:
			self.logger.log_error("No network client available for team swap")
			return
		
		# Clear waiting flags
		for bowler in self.bowlers:
			bowler['waiting_for_swap'] = False
		
		self.logger.log_info(f"Executing team swap with lane {self.paired_lane}")
		
		# Package team data
		team_data = {
			'bowlers': [
				{
					'name': b['name'],
					'average': b['average'],
					'handicap': b['handicap'],
					'frames': b['frames'],
					'frame_totals': b['frame_totals'],
					'current_frame': b['current_frame'],
					'current_ball': b['current_ball'],
					'total_score': b['total_score'],
					'pins_standing': b['pins_standing'],
					'pre_bowl': b.get('pre_bowl'),
					'absent': b.get('absent', False),
					'mode_data': b.get('mode_data', {})
				}
				for b in self.bowlers
			],
			'game_number': self.current_game_number
		}
		
		# Send via network
		success = self.network_client.send_team_move(team_data, self.paired_lane)
		
		if success:
			self.logger.log_info("Team swap initiated - waiting for reciprocal team")
			# Don't clear bowlers yet - wait for receive_bowlers_for_new_game
		else:
			self.logger.log_error("Failed to initiate team swap")

	def receive_team_from_paired_lane(self, team_data):
		"""Receive entire team after swap"""
		# Clear current bowlers
		self.bowlers.clear()
		
		# Reconstruct team from data
		for bowler_data in team_data['bowlers']:
			self.bowlers.append({
				'name': bowler_data['name'],
				'average': bowler_data['average'],
				'handicap': bowler_data['handicap'],
				'frames': bowler_data['frames'],
				'frame_totals': bowler_data['frame_totals'],
				'current_frame': bowler_data['current_frame'],
				'current_ball': bowler_data['current_ball'],
				'total_score': bowler_data['total_score'],
				'pins_standing': bowler_data['pins_standing'],
				'pre_bowl': bowler_data.get('pre_bowl'),
				'absent': bowler_data.get('absent', False),
				'frames_this_turn': 0,
				'waiting_for_swap': False,
				'mode_data': bowler_data.get('mode_data', {})
			})
		
		self.current_bowler_index = 0
		print(f"Received team from lane {self.paired_lane}")

	def move_bowler_to_lane(self, bowler_name, target_lane):
		"""Move specific bowler to a different lane (server command)"""
		# Check if heads-up mode prevents moves
		if self.total_config.endswith('b') or self.total_config.endswith('c'):
			print(f"Cannot move bowler in heads-up mode (config: {self.total_config})")
			return False
		
		# Find bowler
		bowler = None
		for b in self.bowlers:
			if b['name'] == bowler_name:
				bowler = b
				break
		
		if not bowler:
			print(f"Bowler {bowler_name} not found")
			return False
		
		# Package bowler data
		bowler_data = {
			'name': bowler['name'],
			'average': bowler['average'],
			'handicap': bowler['handicap'],
			'frames': bowler['frames'],
			'frame_totals': bowler['frame_totals'],
			'current_frame': bowler['current_frame'],
			'current_ball': bowler['current_ball'],
			'total_score': bowler['total_score'],
			'pins_standing': bowler['pins_standing'],
			'pre_bowl': bowler.get('pre_bowl'),
			'absent': bowler.get('absent', False),
			'mode_data': bowler.get('mode_data', {})
		}
		
		print(f"Moving {bowler_name} to lane {target_lane}")
		# TODO_NETWORK: Send move command to server with bowler_data and target_lane
		
		# Remove locally
		self.bowlers.remove(bowler)
		if self.current_bowler_index >= len(self.bowlers):
			self.current_bowler_index = 0
		
		return True

	def move_team_to_lane(self, target_lane):
		"""Move entire team to different lane (server command)"""
		old_paired = self.paired_lane
		
		# Package team
		team_data = {
			'bowlers': [
				{
					'name': b['name'],
					'average': b['average'],
					'handicap': b['handicap'],
					'frames': b['frames'],
					'frame_totals': b['frame_totals'],
					'current_frame': b['current_frame'],
					'current_ball': b['current_ball'],
					'total_score': b['total_score'],
					'pins_standing': b['pins_standing'],
					'pre_bowl': b.get('pre_bowl'),
					'absent': b.get('absent', False),
					'mode_data': b.get('mode_data', {})
				}
				for b in self.bowlers
			],
			'game_state': {
				'current_game_number': self.current_game_number,
				'session_config': self.session_config,
				'league_config': self.league_config
			}
		}
		
		print(f"Moving team from current lane to lane {target_lane}, paired with lane {old_paired}")
		# TODO_NETWORK: Send team move to server
		# Server handles the lane reassignment

	def load_pre_bowl_data(self, bowler):
		"""Load pre-bowl frames for a bowler"""
		pre_bowl = bowler.get('pre_bowl')
		if not pre_bowl:
			return
		
		pre_bowl_type = pre_bowl['type']
		pre_bowl_frames = pre_bowl['frames']
		
		if pre_bowl_type == 1:
			# Type 1: Pre-populate all frames immediately
			for i, frame_data in enumerate(pre_bowl_frames):
				if i >= 10:
					break
				bowler['frames'][i] = {
					'balls': frame_data['balls'][:],
					'symbols': frame_data['symbols'][:],
					'pins': frame_data['pins'][:],
					'pins_before': [[0,0,0,0,0], [None]*2, [None]*2]
				}
			
			# Calculate totals
			self.calculate_score_for_bowler(bowler)
			bowler['current_frame'] = 10  # Mark as complete
			print(f"Pre-bowl loaded for {bowler['name']} (Type 1 - immediate)")
		
		elif pre_bowl_type in [2, 3]:
			# Type 2/3: Load frames as turn arrives
			bowler['pre_bowl_loaded'] = False
			bowler['pre_bowl_frames_loaded'] = 0
			print(f"Pre-bowl ready for {bowler['name']} (Type {pre_bowl_type})")

	def process_pre_bowl_turn(self, bowler):
		"""Handle pre-bowl when it's their turn (Type 2/3)"""
		pre_bowl = bowler.get('pre_bowl')
		if not pre_bowl or pre_bowl['type'] == 1:
			return False
		
		# Initialize animation state
		bowler['pre_bowl_animation'] = {
			'active': True,
			'start_frame': bowler['pre_bowl_frames_loaded'],
			'end_frame': min(bowler['pre_bowl_frames_loaded'] + self.frames_per_turn, 10),
			'current_frame': bowler['pre_bowl_frames_loaded'],
			'current_ball': 0,
			'last_update': pygame.time.get_ticks(),
			'type': pre_bowl['type']
		}
		
		print(f"Starting pre-bowl animation for {bowler['name']}")
		return True

	def update_pre_bowl_animation(self):
		"""Animate pre-bowl frames, revealing one ball per second"""
		for bowler in self.bowlers:
			anim = bowler.get('pre_bowl_animation')
			if not anim or not anim['active']:
				continue
			
			# Check if 1 second elapsed
			current_time = pygame.time.get_ticks()
			if current_time - anim['last_update'] < 1000:
				continue
			
			anim['last_update'] = current_time
			
			# Get current frame data
			frame_idx = anim['current_frame']
			ball_idx = anim['current_ball']
			pre_bowl_frames = bowler['pre_bowl']['frames']
			
			if frame_idx >= len(pre_bowl_frames) or frame_idx >= anim['end_frame']:
				# Animation complete
				self.finish_pre_bowl_animation(bowler)
				continue
			
			frame_data = pre_bowl_frames[frame_idx]
			
			# Populate ball
			if bowler['frames'][frame_idx]['balls'][ball_idx] is None:
				bowler['frames'][frame_idx]['balls'][ball_idx] = frame_data['balls'][ball_idx]
				bowler['frames'][frame_idx]['symbols'][ball_idx] = frame_data['symbols'][ball_idx]
				bowler['frames'][frame_idx]['pins'][ball_idx] = frame_data['pins'][ball_idx]
				
				# Recalculate score after each ball
				if anim['type'] == 3:
					# Progressive total
					self.calculate_score_for_bowler(bowler)
				else:  # Type 2
					# Show final score (but update frame totals for display)
					self.calculate_score_for_bowler(bowler)
					bowler['display_final_score'] = bowler.get('display_final_score', bowler['total_score'])
			
			# Move to next ball
			anim['current_ball'] += 1
			
			# Check if frame complete
			if anim['current_ball'] >= 3 or frame_data['balls'][anim['current_ball']] is None:
				# Move to next frame
				anim['current_frame'] += 1
				anim['current_ball'] = 0
				bowler['current_frame'] = anim['current_frame']

	def check_pre_bowl_wait(self):
		"""Check if pre-bowl 3-second wait is complete"""
		for bowler in self.bowlers:
			if bowler.get('pre_bowl_wait_time'):
				elapsed = pygame.time.get_ticks() - bowler['pre_bowl_wait_time']
				if elapsed >= 3000:  # 3 seconds
					bowler['pre_bowl_wait_time'] = None
					if self.move_mode == 'bowler':
						self.send_bowler_to_paired_lane(bowler)
					elif self.move_mode == 'team':
						bowler['waiting_for_swap'] = True
					return True
		return False

	def calculate_score_for_bowler(self, bowler):
		"""Calculate score for specific bowler (needed for pre-bowl)"""
		total = 0
		for frame_num in range(10):
			frame = bowler['frames'][frame_num]
			if frame['balls'][0] is None:
				break
			
			frame_score = sum(score for score in frame['balls'] if score is not None)
			
			# Strike bonus
			if frame['symbols'][0] == 'X':
				bonus = 0
				balls_counted = 0
				for next_frame_num in range(frame_num + 1, 10):
					next_frame = bowler['frames'][next_frame_num]
					for ball_score in next_frame['balls']:
						if ball_score is not None and balls_counted < 2:
							bonus += ball_score
							balls_counted += 1
						if balls_counted >= 2:
							break
					if balls_counted >= 2:
						break
				
				if balls_counted == 2:
					frame_score += bonus
				else:
					bowler['frame_totals'][frame_num] = None
					total = None
					continue
			
			# Spare bonus
			elif frame['symbols'][1] == '/':
				if frame['balls'][2] is not None:
					frame_score += frame['balls'][2]
				else:
					bowler['frame_totals'][frame_num] = None
					total = None
					continue
			
			if total is not None:
				total += frame_score
				bowler['frame_totals'][frame_num] = total
			else:
				bowler['frame_totals'][frame_num] = None
		
		if total is not None:
			bowler['total_score'] = total

	def mark_bowler_absent(self, bowler):
		"""Mark bowler as absent and populate with absent scores"""
		bowler['absent'] = True
		absent_per_frame = self.absent_score // 10
		
		for frame_num in range(10):
			if bowler['frames'][frame_num]['balls'][0] is None:
				# Populate empty frames with absent score
				bowler['frames'][frame_num] = {
					'balls': [absent_per_frame, 0, 0],
					'symbols': [str(absent_per_frame), '-', '-'],
					'pins': [[1,1,1,1,1], [1,1,1,1,1], [1,1,1,1,1]],
					'pins_before': [[0,0,0,0,0], [None]*2, [None]*2]
				}
				bowler['frame_totals'][frame_num] = absent_per_frame * (frame_num + 1)
		
		bowler['total_score'] = self.absent_score
		bowler['current_frame'] = 10
		print(f"{bowler['name']} marked absent - {self.absent_score} score applied")

	def finish_pre_bowl_animation(self, bowler):
		"""Complete pre-bowl animation and move bowler"""
		anim = bowler['pre_bowl_animation']
		anim['active'] = False
		
		# Update loaded count
		bowler['pre_bowl_frames_loaded'] = anim['end_frame']
		
		print(f"Pre-bowl animation complete for {bowler['name']}")
		
		# Move bowler after animation
		if self.move_mode == 'bowler':
			self.send_bowler_to_paired_lane(bowler)
		elif self.move_mode == 'team':
			bowler['waiting_for_swap'] = True
			# Check if all ready for swap
			all_waiting = all(b.get('waiting_for_swap') or b['current_frame'] >= 10 for b in self.bowlers)
			if all_waiting:
				self.execute_team_swap()

	def check_absent_bowlers(self):
		"""Check for bowlers that should be marked absent (3+ frames behind)"""
		if not self.bowlers:
			return
		
		# Find max frame bowled
		max_frame = max(b['current_frame'] for b in self.bowlers if not b.get('absent'))
		
		for bowler in self.bowlers:
			if bowler.get('absent') or bowler.get('pre_bowl'):
				continue
			
			# If 3+ frames behind and another bowler started frame 4+
			frames_behind = max_frame - bowler['current_frame']
			if frames_behind >= 3 and max_frame >= 4:
				if bowler['frames'][0]['balls'][0] is None:
					# No balls recorded at all
					self.mark_bowler_absent(bowler)

	def clear_absent_status(self, bowler_name):
		"""Server command to clear absent and let bowler bowl"""
		for bowler in self.bowlers:
			if bowler['name'] == bowler_name:
				if bowler.get('absent'):
					# Clear absent frames but keep them in history
					bowler['absent'] = False
					# Reset to frame 0 or current lowest frame
					min_frame = min(b['current_frame'] for b in self.bowlers if not b.get('absent'))
					bowler['current_frame'] = min_frame
					print(f"{bowler_name} absent status cleared, resuming at frame {min_frame + 1}")
					return True
		return False

	def handle_game_complete(self):
		"""Override with network game completion"""
		self.logger.log_info(f"Game {self.current_game_number} complete")
		
		# SEND GAME COMPLETE TO SERVER
		if self.network_client:
			game_data = {
				'game_type': 'league',
				'game_number': self.current_game_number,
				'paired_lane': self.paired_lane,
				'bowlers': [
					{
						'name': b['name'],
						'score': b['total_score'],
						'average': b['average'],
						'handicap': b['handicap']
					}
					for b in self.bowlers
				],
				'timestamp': datetime.now().isoformat()
			}
			self.network_client.send_game_complete(game_data)
		
		# Check if more games remain
		if self.session_config['mode'] == 'games':
			if self.current_game_number < self.session_config['total_games']:
				# More games to play - initiate lane swap for next game
				self.start_next_game()
			else:
				self.logger.log_info("All games complete!")
				self.session_complete = True
		else:
			self.logger.log_info("Session complete!")
			self.session_complete = True
	
	def start_next_game(self):
		"""Start next game with network-based lane swapping"""
		self.current_game_number += 1
		game_num = self.current_game_number
		
		self.logger.log_info(f"Starting game {game_num}...")
		
		# Determine if we need to swap lanes
		# Game 1: Start on assigned lane
		# Game 2: Swap to paired lane (even game)
		# Game 3: Swap back (odd game)
		
		if game_num % 2 == 0:
			# Even game - send all bowlers to paired lane
			self.logger.log_info(f"Game {game_num}: Sending team to lane {self.paired_lane}")
			self._send_all_bowlers_to_paired_lane()
		else:
			# Odd game after game 1
			if game_num > 1:
				self.logger.log_info(f"Game {game_num}: Waiting for team from lane {self.paired_lane}")
				# Wait for receive_bowlers_for_new_game() to be called via network
			else:
				# Game 1 - start with current bowlers
				self._reset_bowlers_for_new_game()
	
	def _send_all_bowlers_to_paired_lane(self):
		"""Send all bowlers to paired lane for next game via network"""
		if not self.network_client:
			self.logger.log_error("No network client for lane swap")
			return
		
		bowlers_data = []
		
		for bowler in self.bowlers:
			bowler_package = {
				'name': bowler['name'],
				'average': bowler['average'],
				'handicap': bowler['handicap'],
				'pre_bowl': bowler.get('pre_bowl'),
				'absent': False,
			}
			bowlers_data.append(bowler_package)
		
		# Send via network client
		team_data = {
			'bowlers': bowlers_data,
			'game_number': self.current_game_number
		}
		
		success = self.network_client.send_team_move(team_data, self.paired_lane)
		
		if success:
			self.logger.log_info(f"Sent {len(bowlers_data)} bowlers to lane {self.paired_lane}")
			# Clear local bowler list - they're moving
			self.bowlers.clear()
			self.current_bowler_index = 0
		else:
			self.logger.log_error("Failed to send team to paired lane")
	
	def receive_bowlers_for_new_game(self, bowlers_data):
		"""Receive bowlers from paired lane for new game (via network)"""
		self.logger.log_info(f"Receiving {len(bowlers_data)} bowlers for game {self.current_game_number}")
		
		# Clear existing bowlers
		self.bowlers.clear()
		
		# Reconstruct bowler objects with fresh game state
		for bowler_data in bowlers_data:
			new_bowler = {
				'name': bowler_data['name'],
				'average': bowler_data['average'],
				'handicap': bowler_data['handicap'],
				'pre_bowl': bowler_data.get('pre_bowl'),
				'absent': False,
				'frames_this_turn': 0,
				'waiting_for_swap': False,
				'frames': self._create_empty_frames(),
				'frame_totals': [None] * 10,
				'current_frame': 0,
				'current_ball': 0,
				'total_score': 0,
				'pins_standing': [0,0,0,0,0],
				'mode_data': {}
			}
			
			self.bowlers.append(new_bowler)
			
			# Load pre-bowl if exists
			if new_bowler.get('pre_bowl'):
				self.load_pre_bowl_data(new_bowler)
		
		self.current_bowler_index = 0
		self.reset_pins()
		
		self.logger.log_info(f"Game {self.current_game_number} ready with new team")
	
	def _reset_bowlers_for_new_game(self):
		"""Reset current bowlers for a new game (no lane swap)"""
		for bowler in self.bowlers:
			bowler['frames'] = [{'balls': [None]*3, 'symbols': [None]*3, 'pins': [None]*3,
								 'pins_before': [[0,0,0,0,0], [None]*2, [None]*2]} for _ in range(10)]
			bowler['frame_totals'] = [None] * 10
			bowler['current_frame'] = 0
			bowler['current_ball'] = 0
			bowler['total_score'] = 0
			bowler['pins_standing'] = [0,0,0,0,0]
			bowler['frames_this_turn'] = 0
			bowler['waiting_for_swap'] = False
			bowler['absent'] = False
			bowler['mode_data'] = {}
			
			# Reload pre-bowl if exists
			if bowler.get('pre_bowl'):
				self.load_pre_bowl_data(bowler)
		
		self.current_bowler_index = 0
		self.reset_pins()
		print(f"Game {self.current_game_number} started with same team")

	def update(self):
		"""Called each frame - update animations"""
		super().update()
		self.update_pre_bowl_animation()