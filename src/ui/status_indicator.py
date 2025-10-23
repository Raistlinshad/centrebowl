import pygame

class StatusIndicator:
    def __init__(self, pos):
        self.pos = pos
        self.radius = 20
        self.status = "connected"  # or "disconnected"

    def draw(self, surface):
        color = (0, 200, 0) if self.status == "connected" else (200, 0, 0)
        pygame.draw.circle(surface, color, self.pos, self.radius)