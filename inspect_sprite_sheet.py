"""
Visual sprite sheet inspector to check grid alignment
Run from project root: python inspect_sprite_sheet.py
"""
import pygame
import sys

def main():
    pygame.init()
    
    # Create a temporary window first
    temp_screen = pygame.display.set_mode((800, 600))
    
    # Load the sprite sheet
    sprite_path = 'src/assets/animations/pin_sprite_sheet_10x10_85x96.png'
    sprite_sheet = pygame.image.load(sprite_path).convert_alpha()
    
    # Get dimensions
    sheet_width, sheet_height = sprite_sheet.get_size()
    
    # Resize window to fit sprite sheet
    screen = pygame.display.set_mode((sheet_width + 400, sheet_height + 200))
    pygame.display.set_caption("Sprite Sheet Inspector - Check Grid Alignment")
    clock = pygame.time.Clock()
    
    # Grid settings
    cell_width = 85
    cell_height = 96
    sprite_offset_x = 1  # Offset within each cell
    sprite_offset_y = 1  # Offset within each cell
    actual_width = 84    # Actual sprite size (excluding border)
    actual_height = 95   # Actual sprite size (excluding border)
    show_grid = True
    show_extract_boxes = True
    
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_g:
                    show_grid = not show_grid
                elif event.key == pygame.K_e:
                    show_extract_boxes = not show_extract_boxes
        
        # Draw
        screen.fill((40, 40, 40))
        
        # Draw sprite sheet
        sheet_x, sheet_y = 50, 50
        screen.blit(sprite_sheet, (sheet_x, sheet_y))
        
        # Draw grid overlay (cell boundaries)
        if show_grid:
            for row in range(11):  # 10 rows + 1 for bottom edge
                y = sheet_y + row * cell_height
                pygame.draw.line(screen, (255, 0, 0), (sheet_x, y), (sheet_x + sheet_width, y), 1)
            
            for col in range(11):  # 10 cols + 1 for right edge
                x = sheet_x + col * cell_width
                pygame.draw.line(screen, (255, 0, 0), (x, sheet_y), (x, sheet_y + sheet_height), 1)
        
        # Draw extraction boxes (where sprites are actually extracted from)
        if show_extract_boxes:
            for row in range(10):
                for col in range(10):
                    x = sheet_x + col * cell_width + sprite_offset_x
                    y = sheet_y + row * cell_height + sprite_offset_y
                    pygame.draw.rect(screen, (0, 255, 0), (x, y, actual_width, actual_height), 1)
        
        if show_grid:
            # Label columns
            font = pygame.font.SysFont(None, 24)
            for col in range(10):
                x = sheet_x + col * cell_width + cell_width // 2
                label = font.render(str(col), True, (255, 255, 0))
                screen.blit(label, (x - 5, sheet_y - 30))
            
            # Label rows
            for row in range(10):
                y = sheet_y + row * cell_height + cell_height // 2
                label = font.render(str(row), True, (255, 255, 0))
                screen.blit(label, (sheet_x - 30, y - 10))
        
        # Instructions
        font = pygame.font.SysFont(None, 32)
        info_y = sheet_y + sheet_height + 20
        
        instructions = [
            "Press G to toggle grid (RED = cell boundaries)",
            "Press E to toggle extract boxes (GREEN = actual sprite area)",
            "Check if green boxes avoid grey borders",
            f"Sheet size: {sheet_width}x{sheet_height}",
            f"Cell grid: {cell_width}x{cell_height}",
            f"Sprite offset: ({sprite_offset_x}, {sprite_offset_y}) pixels",
            f"Sprite size: {actual_width}x{actual_height}",
        ]
        
        for i, text in enumerate(instructions):
            label = font.render(text, True, (200, 200, 200))
            screen.blit(label, (sheet_x, info_y + i * 35))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()

if __name__ == "__main__":
    main()