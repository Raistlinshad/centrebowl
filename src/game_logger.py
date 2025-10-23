import logging
import os
from datetime import datetime

class GameLogger:
    def __init__(self, log_dir="logs"):
        """Initialize game logger with timestamped log file"""
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"game_{timestamp}.log")
        
        # Configure logger
        self.logger = logging.getLogger('FivePinGame')
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler (optional - set to INFO to reduce console noise)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info(f"=== Game Log Started ===")
        self.logger.info(f"Log file: {log_file}")
    
    def log_game_start(self, bowlers, session_config):
        """Log game initialization"""
        self.logger.info("=== GAME START ===")
        self.logger.info(f"Bowlers: {', '.join(bowlers)}")
        self.logger.info(f"Session: {session_config}")
    
    def log_ball(self, bowler_name, frame, ball, pins_before, pins_after, score, symbol):
        """Log each ball thrown"""
        self.logger.debug(
            f"{bowler_name} | Frame {frame+1} Ball {ball+1} | "
            f"Pins before: {pins_before} → after: {pins_after} | "
            f"Score: {score} | Symbol: {symbol}"
        )
    
    def log_frame_complete(self, bowler_name, frame, frame_data, cumulative_score):
        """Log when a frame is completed"""
        balls = frame_data['balls']
        symbols = frame_data['symbols']
        self.logger.info(
            f"{bowler_name} completed Frame {frame+1} | "
            f"Balls: {balls} | Symbols: {symbols} | "
            f"Cumulative: {cumulative_score}"
        )
    
    def log_frame_10_entry(self, bowler_name, current_ball):
        """Log entry into 10th frame"""
        self.logger.info(
            f">>> {bowler_name} entering Frame 10 | Starting at ball {current_ball+1}"
        )
    
    def log_frame_10_ball(self, bowler_name, ball, pins_standing, all_pins_down, will_continue):
        """Log 10th frame ball details"""
        self.logger.debug(
            f"{bowler_name} Frame 10 Ball {ball+1} | "
            f"Pins standing: {sum(pins_standing)}/5 down | "
            f"All down: {all_pins_down} | Continue: {will_continue}"
        )
    
    def log_frame_10_exit(self, bowler_name, total_balls, final_symbols, frame_score):
        """Log completion of 10th frame"""
        self.logger.info(
            f"<<< {bowler_name} completed Frame 10 | "
            f"Balls thrown: {total_balls} | Symbols: {final_symbols} | "
            f"Frame score: {frame_score}"
        )
    
    def log_bowler_complete(self, bowler_name, final_score):
        """Log when bowler finishes all frames"""
        self.logger.info(
            f"*** {bowler_name} FINISHED | Final score: {final_score} ***"
        )
    
    def log_game_complete(self, bowler_scores):
        """Log game completion"""
        self.logger.info("=== GAME COMPLETE ===")
        for name, score in bowler_scores:
            self.logger.info(f"{name}: {score}")
    
    def log_error(self, error_msg, context=None):
        """Log errors with context"""
        self.logger.error(f"ERROR: {error_msg}")
        if context:
            self.logger.error(f"Context: {context}")
    
    def log_info(self, message):
        """Log general info message"""
        self.logger.info(message)
    
    def log_debug(self, message):
        """Log debug message"""
        self.logger.debug(message)
    
    def log_turn_rotation(self, from_bowler, to_bowler, reason):
        """Log when turn rotates between bowlers"""
        self.logger.debug(f"Turn: {from_bowler} → {to_bowler} ({reason})")

# Convenience function for easy import
def create_logger(log_dir="logs"):
    return GameLogger(log_dir)