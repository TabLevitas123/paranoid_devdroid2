# paranoid_devdroid2.modules.user_interface module initialization
from typing import Any, Dict, Callable, Optional
import threading
from modules.utilities.event_dispatcher import EventDispatcher
from modules.agent.agent_monitor import AgentMonitor
import psutil
from modules.security.encryption_manager import EncryptionManager
import base64
from modules.user_interface.alert_dialog import AlertDialog
import logging
from tkinter import ttk
import tkinter as tk
from modules.utilities.formatting_utils import format_bytes, format_time, format_datetime
from cryptography.fernet import Fernet, InvalidToken
from modules.environment.environment_module import EnvironmentModule, EnvironmentError
from user_interface.metrics_display import MetricsDisplay
from modules.communication.communication_module import CommunicationModule
from pathlib import Path
import json
from modules.utilities.logging_manager import setup_logging
import os
from user_interface.notification_system import NotificationSystem
from hashlib import sha256
from typing import Optional, Callable, Dict, Any
