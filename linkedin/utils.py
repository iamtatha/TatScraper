import time
import random

def get_human_delay(min_seconds=1.0, max_seconds=3.0):
    """Returns a random float in the given range for human-like delays."""
    return random.uniform(min_seconds, max_seconds)

def human_typing(element, text, delay=0.1):
    """Types text into an element with a small random delay between keystrokes to simulate human typing."""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(delay / 2, delay * 1.5))
