"""
Debug script to test sprite loading
Place this in your project root (self-bowling-system/) and run it from there
"""
import pygame
import sys
import os

# Add src directory to path
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_path)

# Now we can import from src
from src.assets.animations.sprite_sheet import SpriteSheet
from src.assets.animations.sprite_config import THEME_LAYOUT, SPRITE_WIDTH, SPRITE_HEIGHT

def main():
    pygame.init()
    screen = pygame.display.set_mode((1200, 800))
    pygame.display.set_caption("Sprite Debug Test")
    clock = pygame.time.Clock()
    
    # Build path to sprite sheet - should be in src/assets/animations/
    sprite_path = os.path.join('src', 'assets', 'animations', 'pin_sprite_sheet_10x10_85x96.png')
    
    print(f"Current working directory: {os.getcwd()}")
    print(f"Loading sprite sheet from: {sprite_path}")
    print(f"Absolute path: {os.path.abspath(sprite_path)}")
    print(f"File exists: {os.path.exists(sprite_path)}")
    
    if not os.path.exists(sprite_path):
        print("\n❌ Cannot find sprite sheet!")
        print(f"Make sure you run this script from the 'self-bowling-system' directory")
        print(f"Command: cd ~/Documents/self-bowling-system && python debug_sprite_test.py")
        return
    
    try:
        sprite_sheet = SpriteSheet(sprite_path)
        print(f"✓ Sprite sheet loaded successfully!")
        print(f"✓ Available themes: {sprite_sheet.get_available_themes()}")
        
        # Check what animations loaded
        for theme in sprite_sheet.get_available_themes():
            print(f"\n  Theme '{theme}':")
            anims = sprite_sheet.get_available_animations(theme)
            print(f"    Animations: {anims}")
            for anim in anims:
                frames = sprite_sheet.get_animation(theme, anim)
                print(f"      - {anim}: {len(frames)} frames loaded")
                
    except Exception as e:
        print(f"✗ Error loading sprite sheet: {e}")
        return
    
    # Test rendering
    current_theme = "normal"
    current_anim = "idle"
    frame_index = 0
    frame_timer = 0
    animation_speed = 500  # ms per frame
    
    running = True
    while running:
        dt = clock.tick(60)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    # Cycle through animations
                    anims = sprite_sheet.get_available_animations(current_theme)
                    current_idx = anims.index(current_anim)
                    current_anim = anims[(current_idx + 1) % len(anims)]
                    frame_index = 0
                    print(f"Switched to animation: {current_anim}")
        
        # Update animation
        frame_timer += dt
        if frame_timer >= animation_speed:
            frame_timer = 0
            frames = sprite_sheet.get_animation(current_theme, current_anim)
            if frames:
                frame_index = (frame_index + 1) % len(frames)
        
        # Draw
        screen.fill((40, 40, 40))
        
        # Get current frame
        frames = sprite_sheet.get_animation(current_theme, current_anim)
        if frames:
            current_frame = frames[frame_index]
            
            # Draw large version centered
            x = (screen.get_width() - SPRITE_WIDTH) // 2
            y = (screen.get_height() - SPRITE_HEIGHT) // 2
            screen.blit(current_frame, (x, y))
            
            # Draw info text
            font = pygame.font.SysFont(None, 36)
            info_text = f"Theme: {current_theme} | Animation: {current_anim} | Frame: {frame_index + 1}/{len(frames)}"
            text_surface = font.render(info_text, True, (255, 255, 255))
            screen.blit(text_surface, (20, 20))
            
            help_text = font.render("SPACE: Next Animation | ESC: Quit", True, (200, 200, 200))
            screen.blit(help_text, (20, 60))
            
            # Draw all frames in a row at the bottom
            frame_y = screen.get_height() - SPRITE_HEIGHT - 20
            for i, frame in enumerate(frames):
                frame_x = 100 + i * (SPRITE_WIDTH + 10)
                screen.blit(frame, (frame_x, frame_y))
                
                # Highlight current frame
                if i == frame_index:
                    pygame.draw.rect(screen, (255, 255, 0), 
                                   (frame_x - 2, frame_y - 2, SPRITE_WIDTH + 4, SPRITE_HEIGHT + 4), 3)
        else:
            # No frames loaded - show error
            font = pygame.font.SysFont(None, 48)
            error_text = font.render(f"NO FRAMES LOADED FOR {current_anim}!", True, (255, 0, 0))
            screen.blit(error_text, (200, 300))
        
        pygame.display.flip()
    
    pygame.quit()

if __name__ == "__main__":
    main()