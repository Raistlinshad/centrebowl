# -*- coding: utf-8 -*-

import logging
from game.five_pin import FivePinGame
from game.league import LeagueGame
from game.practice import PracticeMode

logger = logging.getLogger(__name__)

# TODO: add the other game modes as well. 

class GameManager:
    """Manages game lifecycle and transitions"""
    
    def __init__(self, main_screen, machine, settings, network_client=None):
        self.main_screen = main_screen
        self.machine = machine
        self.settings = settings
        self.network_client = network_client
        self.current_game = None
        
    def start_five_pin_game(self, bowlers, session_config, game_modes=None):
        """Start a 5-pin game"""
        try:
            logger.info(f"Starting 5-pin game with {len(bowlers)} bowlers")
            
            game = FivePinGame(
                settings=self.settings,
                parent=self.main_screen,
                bowlers=bowlers,
                session_config=session_config,
                game_modes=game_modes,
                network_client=self.network_client
            )
            
            self.current_game = game
            self.main_screen.start_game(game)
            logger.info("5-pin game started successfully")
            
        except Exception as e:
            logger.error(f"Error starting 5-pin game: {e}")
            import traceback
            traceback.print_exc()
    
    def start_league_game(self, bowlers, session_config, game_modes=None, league_config=None):
        """Start a league game (with optional practice mode first)"""
        try:
            logger.info(f"Starting league game with {len(bowlers)} bowlers")
            
            # Check if we should skip practice
            skip_practice = self.settings.get('skip_practice', False)
            
            if not skip_practice:
                # Start with practice mode first
                logger.info("Starting 30-minute practice mode before league game")
                
                # Create the league game config for after practice
                next_game_config = {
                    'type': 'league',
                    'bowlers': bowlers,
                    'session_config': session_config,
                    'game_modes': game_modes,
                    'league_config': league_config
                }
                
                # Start practice mode
                practice = PracticeMode(
                    settings=self.settings,
                    parent=self.main_screen,
                    duration_minutes=30,
                    next_game_config=next_game_config,
                    machine=self.machine
                )
                
                # Give practice mode a reference to game manager for transition
                practice.game_manager = self
                
                self.current_game = practice
                self.main_screen.start_game(practice)
                logger.info("Practice mode started (30 minutes)")
                
            else:
                # Skip practice, go straight to league game
                logger.info("Skipping practice mode, starting league game directly")
                self._start_league_game_direct(bowlers, session_config, game_modes, league_config)
                
        except Exception as e:
            logger.error(f"Error starting league game: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_league_game_direct(self, bowlers, session_config, game_modes, league_config):
        """Internal method to start league game without practice"""
        try:
            game = LeagueGame(
                settings=self.settings,
                parent=self.main_screen,
                bowlers=bowlers,
                session_config=session_config,
                game_modes=game_modes,
                league_config=league_config,
                network_client=self.network_client
            )
            
            self.current_game = game
            self.main_screen.start_game(game)
            logger.info("League game started successfully")
            
        except Exception as e:
            logger.error(f"Error starting league game direct: {e}")
            import traceback
            traceback.print_exc()
    
    def transition_from_practice_to_league(self, config):
        """Transition from practice mode to league game"""
        try:
            logger.info("Transitioning from practice to league game")
            
            self._start_league_game_direct(
                bowlers=config['bowlers'],
                session_config=config['session_config'],
                game_modes=config.get('game_modes'),
                league_config=config['league_config']
            )
            
        except Exception as e:
            logger.error(f"Error transitioning to league game: {e}")
            import traceback
            traceback.print_exc()
    
    def reset_pins(self):
        """Reset pins via machine"""
        if self.machine:
            self.machine.manual_reset()
        if self.current_game and hasattr(self.current_game, 'reset_pins'):
            self.current_game.reset_pins()