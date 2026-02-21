#!/usr/bin/env python3
"""
Molty Royale AI Agent - Main Entry Point
Optimized for Railway deployment
"""

import os
import sys
import time
from loguru import logger
from agent import MoltyAgent
from datetime import datetime, timezone

# Configure logging
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level=os.getenv("LOG_LEVEL", "INFO")
)
logger.add(
    "agent_{time}.log",
    rotation="100 MB",
    retention="7 days",
    level="DEBUG"
)

def main():
    """Main function"""
    # Get agent name from environment or use default
    agent_name = os.getenv("AGENT_NAME", "ProBot")
    
    logger.info("=" * 50)
    logger.info(f"Molty Royale AI Agent - {agent_name}")
    logger.info(f"Start time: {datetime.now(timezone.utc).isoformat()} UTC")
    logger.info("=" * 50)
    
    # Create and run agent
    agent = MoltyAgent(agent_name)
    
    try:
        success = agent.run()
        if success:
            logger.info("Agent finished successfully")
            return 0
        else:
            logger.error("Agent failed")
            return 1
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
