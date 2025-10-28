"""
PWL Editor Application - Version Metadata
Author: markus(at)schrodt.at
AI Tools: Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI) - Code development and architecture
License: GPL-3.0-or-later
"""

__version__ = "2.0"
__author__ = "markus(at)schrodt.at"
__license__ = "GPL-3.0-or-later"
__ai_tools__ = "Claude Sonnet 4 (Anthropic); GPT-5 (OpenAI) - Code development and architecture"
__build_date__ = "2025-10-29"
__repo_url__ = "https://github.com/dotmjsc/PWL_Editor"

def get_version():
    """Get the current version string"""
    return __version__

def get_version_info():
    """Get detailed version information"""
    return {
        'version': __version__,
        'author': __author__,
        'license': __license__,
        'ai_tools': __ai_tools__,
        'build_date': __build_date__,
        'repo_url': __repo_url__,
    }
