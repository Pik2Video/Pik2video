# src/pik2video/application/editor/managers/player_manager.py
"""
Менеджер плеера — обёртка над QMediaPlayer.

TODO: перенос из gui/editor/player/engine.py (поэтапно).
"""

from src.pik2video.gui.editor.player.engine import PlayerEngine  # noqa: F401

# После переноса — PlayerManager станет основным именем,
# а PlayerEngine исчезнет.
PlayerManager = PlayerEngine

__all__ = ["PlayerManager"]
