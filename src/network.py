# -*- coding: utf-8 -*-

# network.py - Client-side network implementation for bowling lanes
import asyncio
import json
import socket
import logging
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

class LaneClient:
	def __init__(self, lane_id, settings, event_bus=None, game_manager=None):
		"""
		Initialize the lane client for network communication
		
		Args:
			lane_id: Unique identifier for this lane
			settings: Settings dict with ServerIP and ServerPort
			event_bus: Event bus for internal communication
			game_manager: Reference to game manager for handling game commands
		"""
		self.lane_id = lane_id
		self.settings = settings
		self.event_bus = event_bus
		self.game_manager = game_manager
		
		# Connection state - GET FROM SETTINGS
		self.server_host = settings.get('ServerIP', 'localhost')
		self.server_port = settings.get('ServerPort', 50005)
		self.reader = None
		self.writer = None
		self.connected = False
		self.registered = False
		
		# Threading
		self.loop = None
		self.network_thread = None
		self.running = False
		
		# Heartbeat
		self.heartbeat_interval = 30  # seconds
		self.last_heartbeat = None
		
		# Move tracking for confirmations
		self.pending_moves = {}  # move_id -> callback
		
		logger.info(f"LaneClient initialized for lane {lane_id}")
		logger.info(f"Server configured: {self.server_host}:{self.server_port}")
	
	def start(self):
		"""Start the network client in a separate thread"""
		if self.running:
			logger.warning("Network client already running")
			return
		
		self.running = True
		self.network_thread = threading.Thread(target=self._run_network_loop, daemon=True)
		self.network_thread.start()
		logger.info("Network client thread started")
	
	def stop(self):
		"""Stop the network client"""
		self.running = False
		if self.loop and self.loop.is_running():
			asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
		if self.network_thread:
			self.network_thread.join(timeout=5)
		logger.info("Network client stopped")
	
	def _run_network_loop(self):
		"""Run the asyncio event loop in the network thread"""
		self.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.loop)
		
		try:
			self.loop.run_until_complete(self._network_main())
		except Exception as e:
			logger.error(f"Network loop error: {e}")
		finally:
			self.loop.close()
	
	async def _network_main(self):
		"""Main network coroutine"""
		# Connect directly to configured server (no discovery needed)
		await self.connect_to_server()
		
		if not self.connected:
			logger.error("Failed to connect to server")
			return
		
		# Start background tasks
		tasks = [
			asyncio.create_task(self._heartbeat_loop()),
			asyncio.create_task(self._receive_messages())
		]
		
		# Wait for tasks
		try:
			await asyncio.gather(*tasks)
		except Exception as e:
			logger.error(f"Network tasks error: {e}")
	
	async def connect_to_server(self, force_new=False):
		"""Connect to the server and register"""
		try:
			logger.info(f"Connecting to server at {self.server_host}:{self.server_port}...")
			
			# Open connection
			self.reader, self.writer = await asyncio.open_connection(
				self.server_host, self.server_port
			)
			self.connected = True
			logger.info(f"Connected to server at {self.server_host}:{self.server_port}")
			
			# Register with server
			registration = {
				'type': 'registration',
				'lane_id': self.lane_id,
				'force_new': force_new,
				'startup': True,
				'client_ip': self._get_local_ip(),
				'listen_port': 0,  # Not listening as client
				'timestamp': datetime.now().isoformat()
			}
			
			await self._send_message(registration)
			
			# Wait for registration response
			response = await self._read_message()
			if response and response.get('type') == 'registration_response':
				if response.get('status') == 'success':
					self.registered = True
					logger.info(f"Successfully registered as lane {self.lane_id}")
					return True
				else:
					logger.error(f"Registration failed: {response.get('message')}")
					return False
			
			logger.error("No registration response received")
			return False
			
		except Exception as e:
			logger.error(f"Connection error: {e}")
			self.connected = False
			return False
	
	async def _disconnect(self):
		"""Disconnect from server"""
		if self.writer and not self.writer.is_closing():
			self.writer.close()
			await self.writer.wait_closed()
		self.connected = False
		self.registered = False
		logger.info("Disconnected from server")
	
	async def _send_message(self, message):
		"""Send a JSON message to the server"""
		if not self.writer or self.writer.is_closing():
			logger.error("Cannot send message - not connected")
			return False
		
		try:
			message_json = json.dumps(message).encode('utf-8') + b'\n'
			self.writer.write(message_json)
			await self.writer.drain()
			logger.debug(f"Sent message: {message.get('type')}")
			return True
		except Exception as e:
			logger.error(f"Error sending message: {e}")
			return False
	
	async def _read_message(self):
		"""Read a JSON message from the server"""
		if not self.reader:
			return None
		
		try:
			data = await self.reader.readline()
			if not data:
				return None
			
			message = json.loads(data.decode('utf-8').strip())
			return message
		except Exception as e:
			logger.error(f"Error reading message: {e}")
			return None
	
	async def _heartbeat_loop(self):
		"""Send periodic heartbeats to server"""
		while self.running and self.connected:
			try:
				heartbeat = {
					'type': 'heartbeat',
					'lane_id': self.lane_id,
					'timestamp': datetime.now().isoformat()
				}
				await self._send_message(heartbeat)
				self.last_heartbeat = datetime.now()
				await asyncio.sleep(self.heartbeat_interval)
			except Exception as e:
				logger.error(f"Heartbeat error: {e}")
				await asyncio.sleep(5)
	
	async def _receive_messages(self):
		"""Receive and process messages from server"""
		while self.running and self.connected:
			try:
				message = await self._read_message()
				if message:
					await self._process_message(message)
				else:
					# Connection closed
					logger.warning("Connection closed by server")
					self.connected = False
					break
			except Exception as e:
				logger.error(f"Error receiving message: {e}")
				await asyncio.sleep(1)
	
	async def _process_message(self, message):
		"""Process incoming messages from server"""
		msg_type = message.get('type')
		logger.info(f"Processing message: {msg_type}")
		
		if msg_type == 'heartbeat_response':
			logger.debug("Heartbeat acknowledged")
		
		elif msg_type == 'validation_response':
			logger.info(f"Connection validation: {message.get('status')}")
		
		elif msg_type == 'quick_game':
			# Start a quick game (5-pin)
			await self._handle_quick_game(message)
		
		elif msg_type == 'league_game':
			# Start a league game
			await self._handle_league_game(message)
		
		elif msg_type == 'individual_bowler_move':
			# Receive an individual bowler
			await self._handle_bowler_received(message)
		
		elif msg_type == 'bowler_move_confirmation':
			# Confirmation that a bowler was successfully moved
			await self._handle_move_confirmation(message)
		
		elif msg_type == 'team_move':
			# Receive a team for next game
			await self._handle_team_received(message)
		
		elif msg_type == 'lane_command':
			# Generic lane command
			await self._handle_lane_command(message)
		
		else:
			logger.warning(f"Unknown message type: {msg_type}")
	
	async def _handle_quick_game(self, message):
		"""Handle quick game start command from server"""
		try:
			data = message.get('data', {})
			logger.info(f"Starting quick game: {data}")
			
			# Extract game configuration
			bowlers = data.get('bowlers', [])
			session_config = data.get('session_config', {})
			game_modes = data.get('game_modes', {})
			
			# Call game manager to start the game
			if self.game_manager:
				self.game_manager.start_five_pin_game(
					bowlers=bowlers,
					session_config=session_config,
					game_modes=game_modes
				)
				logger.info("Quick game started successfully")
			else:
				logger.error("No game manager available")
		except Exception as e:
			logger.error(f"Error handling quick game: {e}")
	
	async def _handle_league_game(self, message):
		"""Handle league game start command from server"""
		try:
			data = message.get('data', {})
			logger.info(f"Starting league game: {data}")
		
			# Extract from server data
			bowlers_raw = data.get('bowlers', [])
			total_games = data.get('games', 3)
			frames_per_turn = data.get('frames_per_turn', 1)
			paired_lane = data.get('paired_lane')
			settings = data.get('settings', {})
		
			# BUILD PROPER session_config with required 'mode' key
			session_config = {
				'mode': 'games',  # CRITICAL - was missing!
				'total_games': total_games,
				'total_time_minutes': None,
				'frames_per_turn': frames_per_turn
			}
		
			# Build league_config
			league_config = {
				'paired_lane': paired_lane,
				'move_mode': 'team',  # or extract from data
				'frames_per_turn': frames_per_turn,
				'total_config': settings.get('total_display', '1a'),
				'heads_up': False,
				'options_enabled': False,
				'absent_score': 230
			}
		
			# Format bowlers with all required fields
			bowlers = []
			for b in bowlers_raw:
				bowlers.append({
					'name': b.get('name', 'Unknown'),
					'average': b.get('average', 150),
					'handicap': b.get('handicap', 0),
					'pre_bowl': b.get('pre_bowl', None),
					'absent': False,
					'frames_this_turn': 0,
					'waiting_for_swap': False
				})
		
			# Call game manager with properly formatted data
			if self.game_manager:
				self.game_manager.start_league_game(
					bowlers=bowlers,
					session_config=session_config,
					game_modes=None,  # or extract from data
					league_config=league_config
				)
				logger.info("League game command processed successfully")
			else:
				logger.error("No game manager available")
			
		except Exception as e:
			logger.error(f"Error handling league game: {e}")
			import traceback
			traceback.print_exc()

	
	async def _handle_bowler_received(self, message):
		"""Handle receiving a bowler from another lane"""
		try:
			data = message.get('data', {})
			bowler_data = data.get('bowler', {})
			move_id = data.get('move_id')
			from_lane = data.get('from_lane')
			
			logger.info(f"Received bowler {bowler_data.get('name')} from lane {from_lane}")
			
			# Pass to game manager to add bowler
			if self.game_manager and self.game_manager.current_game:
				game = self.game_manager.current_game
				if hasattr(game, 'receive_bowler_from_paired_lane'):
					game.receive_bowler_from_paired_lane(bowler_data)
					logger.info(f"Bowler added to game: {bowler_data.get('name')}")
				else:
					logger.error("Current game doesn't support receiving bowlers")
			else:
				logger.error("No active game to receive bowler")
		except Exception as e:
			logger.error(f"Error handling bowler received: {e}")
	
	async def _handle_move_confirmation(self, message):
		"""Handle bowler move confirmation from server"""
		try:
			data = message.get('data', {})
			move_id = data.get('move_id')
			confirmed = data.get('confirmed')
			bowler_name = data.get('bowler_name')
			
			logger.info(f"Move confirmation for {bowler_name}: {'SUCCESS' if confirmed else 'FAILED'}")
			
			# Call pending callback if exists
			if move_id in self.pending_moves:
				callback = self.pending_moves.pop(move_id)
				if callback:
					callback(confirmed, data.get('message', ''))
		except Exception as e:
			logger.error(f"Error handling move confirmation: {e}")
	
	async def _handle_team_received(self, message):
		"""Handle receiving a team from paired lane"""
		try:
			data = message.get('data', {})
			logger.info("Received team for new game")
			
			# Pass to game manager
			if self.game_manager and self.game_manager.current_game:
				game = self.game_manager.current_game
				if hasattr(game, 'receive_bowlers_for_new_game'):
					bowlers_data = data.get('bowlers', [])
					game.receive_bowlers_for_new_game(bowlers_data)
					logger.info(f"Team received: {len(bowlers_data)} bowlers")
				else:
					logger.error("Current game doesn't support team moves")
			else:
				logger.error("No active game to receive team")
		except Exception as e:
			logger.error(f"Error handling team received: {e}")
	
	async def _handle_lane_command(self, message):
		"""Handle generic lane commands"""
		try:
			data = message.get('data', {})
			command_type = data.get('type')
			
			logger.info(f"Processing lane command: {command_type}")
			
			# Route to appropriate handler
			if command_type == 'reset_pins':
				if self.game_manager:
					self.game_manager.reset_pins()
			elif command_type == 'skip_bowler':
				if self.game_manager and self.game_manager.current_game:
					self.game_manager.current_game.skip_bowler()
			else:
				logger.warning(f"Unknown lane command: {command_type}")
		except Exception as e:
			logger.error(f"Error handling lane command: {e}")
	
	def send_bowler_move(self, bowler_data, to_lane, move_id, callback=None):
		"""Send a bowler to another lane"""
		if not self.connected:
			logger.error("Cannot send bowler - not connected")
			return False
		
		message = {
			'type': 'bowler_move',
			'data': {
				'to_lane': to_lane,
				'bowler_data': bowler_data,
				'move_id': move_id
			}
		}
		
		# Store callback for confirmation
		if callback:
			self.pending_moves[move_id] = callback
		
		# Send via asyncio
		future = asyncio.run_coroutine_threadsafe(
			self._send_message(message),
			self.loop
		)
		
		try:
			result = future.result(timeout=5)
			logger.info(f"Bowler move sent: {bowler_data.get('name')} to lane {to_lane}")
			return result
		except Exception as e:
			logger.error(f"Error sending bowler move: {e}")
			return False
	
	def send_team_move(self, team_data, to_lane):
		"""Send team data for lane swap"""
		if not self.connected:
			logger.error("Cannot send team - not connected")
			return False
		
		message = {
			'type': 'team_move',
			'data': {
				'to_lane': to_lane,
				'from_lane': self.lane_id,
				'bowlers': team_data.get('bowlers', []),
				'game_number': team_data.get('game_number', 1)
			}
		}
		
		# Send via asyncio
		future = asyncio.run_coroutine_threadsafe(
			self._send_message(message),
			self.loop
		)
		
		try:
			result = future.result(timeout=5)
			logger.info(f"Team move sent to lane {to_lane}")
			return result
		except Exception as e:
			logger.error(f"Error sending team move: {e}")
			return False
	
	def send_frame_data(self, bowler_name, frame_num, frame_data):
		"""Send frame completion data to server"""
		if not self.connected:
			return False
		
		message = {
			'type': 'frame_data',
			'data': {
				'lane_id': self.lane_id,
				'bowler_name': bowler_name,
				'frame_num': frame_num,
				'frame_data': frame_data,
				'timestamp': datetime.now().isoformat()
			}
		}
		
		future = asyncio.run_coroutine_threadsafe(
			self._send_message(message),
			self.loop
		)
		
		try:
			return future.result(timeout=2)
		except Exception as e:
			logger.error(f"Error sending frame data: {e}")
			return False
	
	def send_game_complete(self, game_data):
		"""Send game completion data to server"""
		if not self.connected:
			return False
		
		message = {
			'type': 'game_complete',
			'data': {
				'lane_id': self.lane_id,
				'game_data': game_data,
				'timestamp': datetime.now().isoformat()
			}
		}
		
		future = asyncio.run_coroutine_threadsafe(
			self._send_message(message),
			self.loop
		)
		
		try:
			return future.result(timeout=5)
		except Exception as e:
			logger.error(f"Error sending game complete: {e}")
			return False
	
	def _get_local_ip(self):
		"""Get local IP address"""
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			s.connect(('8.8.8.8', 80))
			ip = s.getsockname()[0]
			s.close()
			return ip
		except Exception:
			return '127.0.0.1'