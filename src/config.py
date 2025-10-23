# -*- coding: utf-8 -*-

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.json')

def load_settings():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(settings, f, indent=2)