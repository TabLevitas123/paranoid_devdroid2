# paranoid_devdroid2.data.shared_memory module initialization
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging
from modules.security.authentication import AuthenticationManager
import threading
from typing import Any, Dict, Optional
from multiprocessing import shared_memory
import logging
from modules.utilities.config_loader import ConfigLoader
import struct
