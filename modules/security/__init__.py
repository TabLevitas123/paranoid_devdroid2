# paranoid_devdroid2.modules.security module initialization
import hashlib
from modules.security.authentication import AuthenticationManager
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import threading
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import padding, hashes
from functools import wraps
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
from cryptography.exceptions import InvalidKey
import re
from modules.security.encryption_manager import EncryptionManager
import base64
import logging
import hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import time
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from modules.utilities.logging_manager import setup_logging
import os
from jsonschema import validate, ValidationError
import secrets
import jwt
from typing import Any, Dict, List, Callable, Optional
import bcrypt
