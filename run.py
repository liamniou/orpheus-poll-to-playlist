#!/usr/bin/env python3
"""Run script for Orpheus Poll to Playlist."""

import logging
import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    """Run the application."""
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "7575"))
    debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    
    print(f"\n🎵 Orpheus Poll to Playlist v1.0.0")
    print(f"   Starting server at http://{host}:{port}")
    print(f"   Debug mode: {'enabled' if debug else 'disabled'}")
    print(f"   Press Ctrl+C to stop\n")
    
    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        reload=debug,
        reload_dirs=["backend"] if debug else None,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
