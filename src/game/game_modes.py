

class ThreeSixNineMode:
	def __init__(self, target_frames):
		"""
		target_frames: dict like {1: [3,6,9], 2: [3,6,9], 3: [3,6,9]}
		game_number: list of frame numbers
		"""
		self.target_frames = target_frames
		self.dots_remaining = 2  # Start with 2 dots
		self.completed = False
	
	def check_frame(self, game_num, frame_num, is_strike):
		"""Called after each frame to check if it's a target frame"""
		if game_num in self.target_frames:
			if frame_num in self.target_frames[game_num]:
				if not is_strike:
					self.dots_remaining -= 1
					if self.dots_remaining == 0:
						return {'status': 'lost', 'dots': 0}
		
		# Check if all target frames completed with strikes
		# (implementation depends on tracking)
		
		return {'status': 'active', 'dots': self.dots_remaining}
	
	def get_display_text(self):
		if self.dots_remaining == 2:
			return "••"
		elif self.dots_remaining == 1:
			return "•"
		elif self.completed:
			return "3-6-9"
		return ""

class PrizeFrameMode:
	def __init__(self, prize_frames):
		"""prize_frames: dict like {2: 5} means game 2, frame 5"""
		self.prize_frames = prize_frames
		self.prizes_won = []
	
	def check_frame(self, game_num, frame_num, is_strike):
		if game_num in self.prize_frames:
			if frame_num == self.prize_frames[game_num] and is_strike:
				return {'won': True, 'game': game_num, 'frame': frame_num}
		return {'won': False}
	
class TurkeyGame:
	def __init__(self):
		"Getting 3 turkeys over 3 games wins a prize"
		self.consecutive_strikes = 0
		self.turkeys = []  # List of (game_num, frame_num) where turkeys were achieved
	
	def check_strike(self, game_num, frame_num, is_strike):
		"""Check if a strike was made and update counters"""
		if is_strike:
			self.consecutive_strikes += 1
			if self.consecutive_strikes == 3:
				self.turkeys.append((game_num, frame_num))
				self.consecutive_strikes = 0  # Reset after turkey
				return True
		else:
			self.consecutive_strikes = 0  # Reset on non-strike
		return False
	
	def get_display_info(self):
		"""Get display info for UI"""
		return {
			'consecutive_strikes': self.consecutive_strikes,
			'turkeys': self.turkeys
		}
	
class Strike13Mode:
	def __init__(self, free_count=0, auto_free=False):
		"""
		Strike 13 Mode - Optional modifications to 5-pin scoring
		
		Args:
			free_count: Number of free strikes each bowler gets per game
			auto_free: If True, auto-apply remaining free strikes when possible
		"""
		self.free_count = free_count
		self.auto_free = auto_free
		self.initial_free_count = free_count
		
	def initialize_bowler(self, bowler):
		"""Initialize Strike 13 data for a bowler"""
		if 'mode_data' not in bowler:
			bowler['mode_data'] = {}
		
		bowler['mode_data']['strike13'] = {
			'free_remaining': self.free_count,
			'free_used': []  # Track which frames used free strikes: [(game_num, frame_num), ...]
		}
	
	def check_l_or_r_strike(self, pins_knocked):
		"""
		Check if first ball achieved L or R (value = 13)
		L pattern: [0,1,1,1,1] (knocks left-three, center-five, right-three, right-two)
		R pattern: [1,1,1,1,0] (knocks left-two, left-three, center-five, right-three)
		
		Returns True if either pattern achieved
		"""
		pattern = ''.join(str(p) for p in pins_knocked)
		return pattern in ['01111', '11110']
	
	def check_single_pin_remaining(self, pins_standing):
		"""
		Check if exactly one pin remains standing
		Valid single pin patterns:
		- Any single pin: [1,0,0,0,0], [0,1,0,0,0], [0,0,1,0,0], [0,0,0,1,0], [0,0,0,0,1]
		- Any L/R combo: [1,0,1,1,1], [1,1,1,0,1], [1,1,0,1,1]
		
		Returns True if exactly one pin standing
		"""
		return sum(pins_standing) == 4  # 4 pins down = 1 standing
	
	def can_use_free_strike(self, bowler, game_num, frame_num, ball_num):
		"""Check if bowler can use a free strike"""
		if ball_num != 0:  # Only first ball of frame
			return False
		
		strike13_data = bowler['mode_data'].get('strike13', {})
		return strike13_data.get('free_remaining', 0) > 0
	
	def get_remaining_balls_in_game(self, bowler):
		"""Calculate how many balls remain in the game for this bowler"""
		current_frame = bowler['current_frame']
		current_ball = bowler['current_ball']
		
		if current_frame >= 10:
			return 0
		
		# Count balls already thrown in current frame
		balls_thrown_in_current = current_ball
		
		# Frames 0-8: max 3 balls per frame (but usually 1-2 with strikes/spares)
		# Frame 9: always 3 balls
		# Simplified: assume worst case (no strikes/spares) for calculation
		
		if current_frame < 9:
			# Remaining frames before 10th
			remaining_normal_frames = 9 - current_frame - 1
			# Current frame balls (3 - already thrown)
			current_frame_balls = 3 - balls_thrown_in_current
			# Each remaining normal frame: max 3 balls
			# 10th frame: 3 balls
			return current_frame_balls + (remaining_normal_frames * 3) + 3
		elif current_frame == 9:
			# Only 10th frame left
			return 3 - balls_thrown_in_current
		
		return 0
	
	def should_auto_apply_free_strikes(self, bowler, game_num):
		"""Check if we should auto-apply remaining free strikes"""
		if not self.auto_free:
			return False
		
		strike13_data = bowler['mode_data'].get('strike13', {})
		free_remaining = strike13_data.get('free_remaining', 0)
		
		if free_remaining == 0:
			return False
		
		# Get maximum possible balls that could be strikes
		remaining_balls = self.get_remaining_balls_in_game(bowler)
		
		# If free count >= remaining possible first balls, auto-apply
		# Rough estimate: remaining_balls / 2 (since strikes skip second ball)
		max_first_balls = (remaining_balls + 1) // 2
		
		return free_remaining >= max_first_balls
	
	def use_free_strike(self, bowler, game_num, frame_num):
		"""Use a free strike for the bowler"""
		strike13_data = bowler['mode_data'].get('strike13', {})
		
		if strike13_data['free_remaining'] > 0:
			strike13_data['free_remaining'] -= 1
			strike13_data['free_used'].append((game_num, frame_num))
			return True
		return False
	
	def get_display_info(self, bowler):
		"""Get display info for UI rendering"""
		strike13_data = bowler['mode_data'].get('strike13', {})
		free_remaining = strike13_data.get('free_remaining', 0)
		
		return {
			'show_button': free_remaining > 0,
			'free_count': free_remaining,
			'button_text': 'X',
			'count_text': str(free_remaining)
		}
	
	def reset_for_new_game(self, bowler):
		"""Reset Strike 13 data for a new game"""
		if 'mode_data' in bowler and 'strike13' in bowler['mode_data']:
			bowler['mode_data']['strike13'] = {
				'free_remaining': self.initial_free_count,
				'free_used': []
			}