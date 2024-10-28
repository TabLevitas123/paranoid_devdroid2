# paranoid_devdroid2.modules.communication module initialization
import time
from modules.communication.message_broker import MessageBroker
from typing import Dict, Any, Optional, List
from modules.security.encryption_manager import EncryptionManager
import json
from modules.utilities.logging_manager import setup_logging
import os
import threading
from typing import Optional, Dict, Any, Callable
import queue
import logging
import uuid
from modules.communication.communication_module import CommunicationModule
