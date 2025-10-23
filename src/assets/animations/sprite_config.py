"""
Sprite animation configuration
Edit this file to add new themes or modify sprite positions
"""

# Grid cell dimensions (the full cell size in the sprite sheet)
CELL_WIDTH = 85
CELL_HEIGHT = 96

# Actual sprite dimensions (what we extract, excluding grey borders)
SPRITE_WIDTH = 83
SPRITE_HEIGHT = 94

# Theme layouts - Define grid positions for each animation
# Format: (row, column) in the 10x10 sprite sheet grid
THEME_LAYOUT = {
    "normal": {
        "idle": [(0, 0), (0, 1)],    # Sprite 1 and 2: Row 0, Columns 0-1
        "blink": [(0, 2), (0, 3)],   # Row 0, Columns 2-3
        "fell": [(1, 0), (1, 1)],    # Row 1, Columns 0-1
        "watch": [(1, 2), (1, 3)],   # Row 1, Columns 2-3
    },
    
    "easter": {
        "idle": [(0, 4), (0, 5)],
        "blink": [(0, 6), (0, 7)],
        "fell": [(1, 4), (1, 5)],
        "watch": [(1, 6), (1, 7)],
    },
    
    "halloween": {
        "idle": [(2, 0), (2, 1)],
        "blink": [(2, 2), (2, 3)],
        "fell": [(3, 0), (3, 1)],
        "watch": [(3, 2), (3, 3)],
    },
    
    "christmas": {
        "idle": [(2, 4), (2, 5)],
        "blink": [(2, 6), (2, 7)],
        "fell": [(3, 4), (3, 5)],
        "watch": [(3, 6), (3, 7)],
    },
    
    # Add more themes here!
    # "valentines": {
    #     "idle": [(4, 0), (4, 1)],
    #     "blink": [(4, 2), (4, 3)],
    #     "fell": [(5, 0), (5, 1)],
    #     "watch": [(5, 2), (5, 3)],
    # },
}

# Grid reference for easier mapping:
# Each CELL is 85x96 pixels
# Each SPRITE extracted is 83x94 pixels (removes 1px borders on all sides)
# 
#       Col 0   Col 1   Col 2   Col 3   Col 4   Col 5   Col 6   Col 7   Col 8   Col 9
# Row 0: (0,0)  (85,0)  (170,0) (255,0) (340,0) (425,0) (510,0) (595,0) (680,0) (765,0)
# Row 1: (0,96) (85,96) (170,96)...
# Row 2: (0,192) (85,192)...
# etc.