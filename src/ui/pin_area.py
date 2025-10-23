# -*- coding: utf-8 -*-

import pygame
import os
import random

class PinArea:
    def __init__(self, pos=(1700, 500), theme='normal', use_simple_display=False):
        self.pos = pos
        self.current_theme = theme
        self.pins_down = [False] * 5
        self.use_simple_display = use_simple_display
        
        # Layout: classic 5-pin formation
        self.pin_positions = [
            (0, 0),      # Far left (2-pin)
            (50, 70),    # Left (3-pin)
            (100, 140),  # Head pin (5-pin)
            (150, 70),   # Right (3-pin)
            (200, 0),    # Far right (2-pin)
        ]
        
        if use_simple_display:
            # Load simple pin images
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            pin_up_path = os.path.join(base_dir, 'assets', 'images', '5pin_up.png')
            pin_down_path = os.path.join(base_dir, 'assets', 'images', '5pin_down.png')
            
            self.pin_up_image = pygame.image.load(pin_up_path)
            self.pin_down_image = pygame.image.load(pin_down_path)
            
            # Get dimensions from loaded image
            self.pin_width = self.pin_up_image.get_width()
            self.pin_height = self.pin_up_image.get_height()
        else:
            # Use sprite sheet animations
            self.pin_width = 83   # Actual sprite width
            self.pin_height = 94  # Actual sprite height
            
            # Load sprite sheet
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sprite_path = os.path.join(base_dir, 'assets', 'animations', 'pin_sprite_sheet_10x10_85x96.png')
            
            from assets.animations.sprite_sheet import SpriteSheet
            self.sprite_sheet = SpriteSheet(sprite_path)
            
            # Load animations for current theme
            self.load_theme_animations()
            
            # Animation state for each pin
            self.pin_states = []
            for i in range(5):
                self.pin_states.append({
                    'current_animation': 'idle',
                    'frame_index': 0,
                    'frame_timer': 0,
                    'idle_timer': 0,
                    'animation_speed': 500  # milliseconds per frame
                })
    
    def load_theme_animations(self):
        """Load all animations for the current theme."""
        self.animations = {}
        available_animations = self.sprite_sheet.get_available_animations(self.current_theme)
        
        for anim_name in available_animations:
            self.animations[anim_name] = self.sprite_sheet.get_animation(self.current_theme, anim_name)
        
        # Fallback to 'normal' theme if current theme has no animations
        if not self.animations and self.current_theme != 'normal':
            self.current_theme = 'normal'
            self.load_theme_animations()
    
    def set_theme(self, theme_name):
        """
        Change the current theme.
        
        Args:
            theme_name: Name of the theme to switch to (e.g., 'normal', 'easter')
        """
        if self.use_simple_display:
            return False  # Simple display doesn't support themes
            
        available_themes = self.sprite_sheet.get_available_themes()
        if theme_name in available_themes:
            self.current_theme = theme_name
            self.load_theme_animations()
            
            # Reset all pin animations to idle with the new theme
            for state in self.pin_states:
                state['current_animation'] = 'idle'
                state['frame_index'] = 0
                state['idle_timer'] = 0
            return True
        return False
    
    def get_available_themes(self):
        """Return list of available themes."""
        if self.use_simple_display:
            return ['simple']
        return self.sprite_sheet.get_available_themes()
    
    def update(self, dt):
        """Update animation states for all pins"""
        if self.use_simple_display:
            return  # No animations in simple mode
            
        for i, state in enumerate(self.pin_states):
            # If pin is down, use fell animation
            if self.pins_down[i]:
                state['current_animation'] = 'fell'
                state['idle_timer'] = 0
            else:
                # Pin is standing - handle idle animations
                state['idle_timer'] += dt
                
                # After 10 seconds of idle, chance to switch animation
                if state['idle_timer'] >= 10000:  # 10 seconds in milliseconds
                    if state['current_animation'] == 'idle':
                        # 15% chance to switch to blink or watch
                        if random.random() < 0.15:
                            # Only use animations that exist in current theme
                            available_anims = [anim for anim in ['blink', 'watch'] if anim in self.animations]
                            if available_anims:
                                state['current_animation'] = random.choice(available_anims)
                                state['frame_index'] = 0
                                state['idle_timer'] = 0
                    else:
                        # If currently blinking or watching, go back to idle
                        state['current_animation'] = 'idle'
                        state['frame_index'] = 0
                        state['idle_timer'] = 0
            
            # Update animation frame
            state['frame_timer'] += dt
            if state['frame_timer'] >= state['animation_speed']:
                state['frame_timer'] = 0
                
                # Make sure the animation exists before accessing it
                if state['current_animation'] in self.animations:
                    anim_length = len(self.animations[state['current_animation']])
                    if anim_length > 0:
                        state['frame_index'] = (state['frame_index'] + 1) % anim_length

    def reset_pins(self):
        """Reset all pins to standing (up) state"""
        self.pins_down = [False] * 5
        
        if not self.use_simple_display:
            # Reset animation states to idle
            for state in self.pin_states:
                state['current_animation'] = 'idle'
                state['frame_index'] = 0
                state['idle_timer'] = 0

    def draw(self, surface):
        """Draw all pins"""
        if self.use_simple_display:
            self.draw_simple(surface)
        else:
            self.draw_animated(surface)
    
    def draw_simple(self, surface):
        """Draw pins using simple up/down images"""
        for i, (dx, dy) in enumerate(self.pin_positions):
            x = self.pos[0] + dx
            y = self.pos[1] + dy
            
            # Draw appropriate image
            if self.pins_down[i]:
                surface.blit(self.pin_down_image, (x, y))
            else:
                surface.blit(self.pin_up_image, (x, y))
            
            # Draw pin value labels below each pin
            font = pygame.font.SysFont(None, 24)
            pin_values = [2, 3, 5, 3, 2]
            value_text = font.render(str(pin_values[i]), True, (200, 200, 200))
            value_rect = value_text.get_rect(center=(x + self.pin_width//2, y + self.pin_height + 15))
            surface.blit(value_text, value_rect)
    
    def draw_animated(self, surface):
        """Draw all pins with current animations"""
        for i, (dx, dy) in enumerate(self.pin_positions):
            x = self.pos[0] + dx
            y = self.pos[1] + dy
            
            # Get current frame for this pin
            state = self.pin_states[i]
            
            # Make sure animation and frame exist
            if state['current_animation'] in self.animations:
                frames = self.animations[state['current_animation']]
                if frames and len(frames) > 0:
                    frame_index = min(state['frame_index'], len(frames) - 1)
                    current_frame = frames[frame_index]
                    
                    # Draw the sprite
                    surface.blit(current_frame, (x, y))
            
            # Draw pin value labels below each pin
            font = pygame.font.SysFont(None, 24)
            pin_values = [2, 3, 5, 3, 2]
            value_text = font.render(str(pin_values[i]), True, (200, 200, 200))
            value_rect = value_text.get_rect(center=(x + self.pin_width//2, y + self.pin_height + 15))
            surface.blit(value_text, value_rect)