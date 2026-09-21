"""Desktop application theme and palette configuration."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def light_palette() -> QPalette:
    """Return the application's light palette, independent of the OS theme."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: '#f1f5f7',
        QPalette.ColorRole.WindowText: '#192d3b',
        QPalette.ColorRole.Base: '#ffffff',
        QPalette.ColorRole.AlternateBase: '#f1f5f7',
        QPalette.ColorRole.ToolTipBase: '#ffffff',
        QPalette.ColorRole.ToolTipText: '#192d3b',
        QPalette.ColorRole.Text: '#192d3b',
        QPalette.ColorRole.Button: '#e3edf2',
        QPalette.ColorRole.ButtonText: '#192d3b',
        QPalette.ColorRole.BrightText: '#ffffff',
        QPalette.ColorRole.Highlight: '#087e8b',
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.PlaceholderText: '#8998a1',
        QPalette.ColorRole.Link: '#087e8b',
        QPalette.ColorRole.Light: '#ffffff',
        QPalette.ColorRole.Midlight: '#edf3f6',
        QPalette.ColorRole.Mid: '#c6d5de',
        QPalette.ColorRole.Dark: '#8998a1',
        QPalette.ColorRole.Shadow: '#536875',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#8998a1'))
    return palette
