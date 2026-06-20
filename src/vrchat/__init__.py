"""
VRChat Module for CriTTS
Handles VRChat OSC chatbox integration and viseme/lip-sync animation.
"""

from .osc_client import VRChatOSCClient
from .viseme_mapper import VisemeMapper, AmplitudeAnalyzer, Viseme, VisemeFrame

__all__ = ['VRChatOSCClient', 'VisemeMapper', 'AmplitudeAnalyzer', 'Viseme', 'VisemeFrame']