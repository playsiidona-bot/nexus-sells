import os
import sys
import asyncio

# Ensure bot root is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nNexus Hub Bot terminated gracefully.")
