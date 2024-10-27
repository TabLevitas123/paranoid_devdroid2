#!/usr/bin/env python3
# run.py

import logging
import threading
import time
from marvin.marvin_agent import Marvin
from modules.utilities.logging_manager import setup_logging
from modules.communication.communication_module import CommunicationModule
from modules.memory.shared_memory import SharedMemory
from modules.security.encryption_manager import EncryptionManager

# Configure logging
logger = setup_logging('run')

def main():
    try:
        logger.info("Starting main program...")
        marvin = Marvin()
        communication_module = CommunicationModule()
        shared_memory = SharedMemory()
        encryption_manager = EncryptionManager()

        # Initialize Marvin and related modules
        marvin.initialize(communication_module, shared_memory, encryption_manager)

        # Start the main event loop
        while True:
            # Check for new tasks
            task = marvin.get_current_task()
            if task:
                logger.info(f"New task detected: {task}")
                marvin.process_task()
                result = marvin.get_result()
                logger.info(f"Task completed with result: {result}")
                # Reset task
                marvin.clear_current_task()
            else:
                logger.debug("No new tasks. Idle...")
            time.sleep(5)  # Adjust sleep duration as needed

    except KeyboardInterrupt:
        logger.info("Program interrupted by user. Shutting down...")
    except Exception as e:
        logger.critical(f"Unexpected error in run.py: {e}", exc_info=True)
    finally:
        # Perform any necessary cleanup
        logger.info("Cleanup complete. Exiting.")

if __name__ == "__main__":
    main()
