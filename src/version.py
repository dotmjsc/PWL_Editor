"""
PWL Editor Version Information
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic) - Code development and architecture
License: GPL-3.0-or-later
"""

__version__ = "1.4"
__author__ = "markus(at)schrodt.at"
__license__ = "GPL-3.0-or-later"
__ai_tools__ = "Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI)"

def get_version():
    """Get the current version string"""
    return __version__

def get_version_info():
    """Get detailed version information"""
    return {
        'version': __version__,
        'author': __author__,
        'license': __license__,
        'ai_tools': __ai_tools__
    }
