# security/security_module.py

"""
Security Module

This module provides advanced security functionalities for the application, encapsulated within the SecurityModule class:

- Password hashing and verification
- JWT token generation and verification
- Input validation and sanitization
- CSRF protection
- Rate limiting
- Security event logging
- Data encryption and decryption
- Authentication and authorization decorators
- Security headers middleware

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import hashlib
import hmac
import base64
import secrets
import threading
import time
from functools import wraps
from datetime import datetime, timedelta
from typing import Any, Dict, List, Callable, Optional

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jsonschema import validate, ValidationError

# Configure Logging
logger = logging.getLogger('security_module')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/security.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Constants and Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
JWT_ALGORITHM = 'HS256'
JWT_EXP_DELTA_SECONDS = int(os.environ.get('JWT_EXP_DELTA_SECONDS', 3600))
PASSWORD_HASH_ITERATIONS = int(os.environ.get('PASSWORD_HASH_ITERATIONS', 100_000))
PASSWORD_SALT_SIZE = int(os.environ.get('PASSWORD_SALT_SIZE', 32))  # bytes
CSRF_SECRET_KEY = os.environ.get('CSRF_SECRET_KEY', secrets.token_hex(32))
RATE_LIMIT_STORAGE = {}  # Thread-safe storage for rate limiting

# Exception Classes
class SecurityError(Exception):
    """Base class for security exceptions."""
    pass

class AuthenticationError(SecurityError):
    """Raised when authentication fails."""
    pass

class AuthorizationError(SecurityError):
    """Raised when authorization fails."""
    pass

class InputValidationError(SecurityError):
    """Raised when input validation fails."""
    pass

class CSRFError(SecurityError):
    """Raised when CSRF token validation fails."""
    pass

class RateLimitError(SecurityError):
    """Raised when rate limiting is exceeded."""
    pass

class EncryptionError(SecurityError):
    """Raised when encryption or decryption fails."""
    pass

class SecurityModule:
    """
    SecurityModule Class

    Encapsulates all security functionalities for easy integration and management.
    """

    def __init__(self):
        # Initialize any required attributes or configurations here
        self.logger = logger
        self.rate_limit_storage = RATE_LIMIT_STORAGE
        self.lock = threading.Lock()

    # Password Hashing and Verification
    def hash_password(self, password: str) -> str:
        """
        Hashes a password using PBKDF2 HMAC SHA-256 with a random salt.

        Args:
            password (str): The plaintext password.

        Returns:
            str: The base64-encoded salt and hash.
        """
        if not password:
            self.logger.error("Password cannot be empty.")
            raise ValueError("Password cannot be empty.")

        salt = os.urandom(PASSWORD_SALT_SIZE)
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            PASSWORD_HASH_ITERATIONS
        )
        result = base64.b64encode(salt + hashed).decode('utf-8')
        self.logger.debug("Password hashed successfully.")
        return result

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """
        Verifies a password against a given hash.

        Args:
            password (str): The plaintext password to verify.
            hashed_password (str): The base64-encoded salt and hash.

        Returns:
            bool: True if the password matches the hash, False otherwise.
        """
        if not password or not hashed_password:
            self.logger.error("Password and hashed_password cannot be empty.")
            raise ValueError("Password and hashed_password cannot be empty.")

        decoded = base64.b64decode(hashed_password.encode('utf-8'))
        salt = decoded[:PASSWORD_SALT_SIZE]
        stored_hash = decoded[PASSWORD_SALT_SIZE:]

        new_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            PASSWORD_HASH_ITERATIONS
        )

        is_valid = hmac.compare_digest(stored_hash, new_hash)
        self.logger.debug("Password verification completed.")
        return is_valid

    # JWT Token Generation and Verification
    def generate_token(self, user_id: str, roles: List[str]) -> str:
        """
        Generates a JWT token for authentication.

        Args:
            user_id (str): The user's unique identifier.
            roles (List[str]): List of roles assigned to the user.

        Returns:
            str: The encoded JWT token.
        """
        payload = {
            'user_id': user_id,
            'roles': roles,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
        }

        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        self.logger.debug(f"Token generated for user_id: {user_id}")
        return token

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verifies a JWT token.

        Args:
            token (str): The JWT token to verify.

        Returns:
            Dict[str, Any]: The decoded token payload.

        Raises:
            AuthenticationError: If token verification fails.
        """
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            self.logger.debug("Token verified successfully.")
            return payload
        except ExpiredSignatureError:
            self.logger.warning("Token has expired.")
            raise AuthenticationError("Token has expired.")
        except InvalidTokenError:
            self.logger.warning("Invalid token.")
            raise AuthenticationError("Invalid token.")

    # Input Validation and Sanitization
    def validate_input(self, data: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Validates input data against a JSON schema.

        Args:
            data (Dict[str, Any]): The data to validate.
            schema (Dict[str, Any]): The JSON schema.

        Raises:
            InputValidationError: If validation fails.
        """
        try:
            validate(instance=data, schema=schema)
            self.logger.debug("Input data validated successfully.")
        except ValidationError as e:
            self.logger.warning(f"Input validation error: {e.message}")
            raise InputValidationError(e.message)

    # CSRF Protection
    def generate_csrf_token(self, session_id: str) -> str:
        """
        Generates a CSRF token using HMAC SHA-256.

        Args:
            session_id (str): The session ID.

        Returns:
            str: The generated CSRF token.
        """
        token = hmac.new(
            key=CSRF_SECRET_KEY.encode('utf-8'),
            msg=session_id.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        self.logger.debug("CSRF token generated.")
        return token

    def verify_csrf_token(self, session_id: str, token: str) -> bool:
        """
        Verifies a CSRF token.

        Args:
            session_id (str): The session ID.
            token (str): The CSRF token to verify.

        Returns:
            bool: True if verification succeeds.

        Raises:
            CSRFError: If verification fails.
        """
        expected_token = self.generate_csrf_token(session_id)
        if not hmac.compare_digest(expected_token, token):
            self.logger.warning("CSRF token verification failed.")
            raise CSRFError("Invalid CSRF token.")
        self.logger.debug("CSRF token verified successfully.")
        return True

    # Rate Limiting
    def rate_limit(self, calls: int, period: int) -> Callable:
        """
        Decorator to implement rate limiting using a token bucket algorithm.

        Args:
            calls (int): Allowed number of calls.
            period (int): Time period in seconds.

        Returns:
            Callable: The decorator.
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                identifier = self._get_identifier(*args, **kwargs)
                current_time = time.time()

                with self.lock:
                    allowance, last_check = self.rate_limit_storage.get(identifier, (calls, current_time))
                    time_passed = current_time - last_check
                    allowance += time_passed * (calls / period)
                    if allowance > calls:
                        allowance = calls

                    if allowance < 1.0:
                        self.logger.warning(f"Rate limit exceeded for identifier: {identifier}")
                        raise RateLimitError("Rate limit exceeded.")
                    else:
                        allowance -= 1.0
                        self.rate_limit_storage[identifier] = (allowance, current_time)
                self.logger.debug(f"Rate limit check passed for identifier: {identifier}")
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def _get_identifier(self, *args, **kwargs) -> str:
        """
        Retrieves a unique identifier for rate limiting.

        Returns:
            str: The unique identifier.
        """
        request = kwargs.get('request')
        if request:
            identifier = request.remote_addr  # Flask example
            self.logger.debug(f"Identifier obtained from request: {identifier}")
            return identifier
        else:
            self.logger.error("Request object not found in arguments.")
            raise RateLimitError("Cannot determine identifier for rate limiting.")

    # Security Event Logging
    def log_security_event(self, event_type: str, user_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Logs security-related events.

        Args:
            event_type (str): Type of the event.
            user_id (Optional[str]): User ID associated with the event.
            details (Optional[Dict[str, Any]]): Additional event details.
        """
        event = {
            'event_type': event_type,
            'user_id': user_id,
            'details': details or {},
            'timestamp': datetime.utcnow().isoformat()
        }
        self.logger.info(f"Security event logged: {event}")

    # Data Encryption and Decryption
    def encrypt_data(self, plaintext: bytes, key: bytes) -> bytes:
        """
        Encrypts data using AES-256 GCM.

        Args:
            plaintext (bytes): The data to encrypt.
            key (bytes): The encryption key (32 bytes).

        Returns:
            bytes: The encrypted data (nonce + ciphertext).
        """
        if len(key) != 32:
            self.logger.error("Encryption key must be 32 bytes long.")
            raise ValueError("Key must be 32 bytes long.")

        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
        result = nonce + ciphertext
        self.logger.debug("Data encrypted successfully.")
        return result

    def decrypt_data(self, encrypted_data: bytes, key: bytes) -> bytes:
        """
        Decrypts data encrypted with AES-256 GCM.

        Args:
            encrypted_data (bytes): The encrypted data (nonce + ciphertext).
            key (bytes): The decryption key (32 bytes).

        Returns:
            bytes: The decrypted plaintext.

        Raises:
            EncryptionError: If decryption fails.
        """
        if len(key) != 32:
            self.logger.error("Decryption key must be 32 bytes long.")
            raise ValueError("Key must be 32 bytes long.")
        if len(encrypted_data) < 13:
            self.logger.error("Invalid encrypted data length.")
            raise ValueError("Invalid encrypted data.")

        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        aesgcm = AESGCM(key)

        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            self.logger.debug("Data decrypted successfully.")
            return plaintext
        except Exception as e:
            self.logger.error(f"Decryption failed: {e}")
            raise EncryptionError("Decryption failed.") from e

    # Authentication and Authorization Decorators
    def requires_authentication(self, func: Callable) -> Callable:
        """
        Decorator to ensure the user is authenticated.

        Args:
            func (Callable): The function to decorate.

        Returns:
            Callable: The wrapped function.
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = kwargs.get('token')
            if not token:
                self.logger.warning("Authentication token missing.")
                raise AuthenticationError("Authentication token required.")
            try:
                user_payload = self.verify_token(token)
                kwargs['user'] = user_payload
                self.logger.debug("User authenticated successfully.")
            except AuthenticationError as e:
                self.logger.warning(f"Authentication failed: {e}")
                raise
            return func(*args, **kwargs)
        return wrapper

    def requires_roles(self, required_roles: List[str]) -> Callable:
        """
        Decorator to ensure the user has the required roles.

        Args:
            required_roles (List[str]): The roles required to access the function.

        Returns:
            Callable: The decorator.
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                user = kwargs.get('user')
                if not user:
                    self.logger.warning("User payload missing in kwargs.")
                    raise AuthorizationError("User information is required.")
                user_roles = user.get('roles', [])
                if not any(role in user_roles for role in required_roles):
                    self.logger.warning(f"User '{user.get('user_id')}' lacks required roles: {required_roles}")
                    raise AuthorizationError("User lacks required permissions.")
                self.logger.debug(f"User '{user.get('user_id')}' authorized with roles: {user_roles}")
                return func(*args, **kwargs)
            return wrapper
        return decorator

    # Security Headers Middleware (for Flask)
    def security_headers_middleware(self, response):
        """
        Adds security-related headers to the HTTP response.

        Args:
            response: The Flask response object.

        Returns:
            The modified response object.
        """
        response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        self.logger.debug("Security headers added to response.")
        return response

    # Utility Functions
    def generate_secure_token(self, length: int = 64) -> str:
        """
        Generates a secure random token.

        Args:
            length (int): The length of the token in characters.

        Returns:
            str: The generated token.
        """
        token = secrets.token_hex(length // 2)
        self.logger.debug("Secure token generated.")
        return token

    def is_secure_password(self, password: str) -> bool:
        """
        Validates the strength of a password.

        Args:
            password (str): The password to validate.

        Returns:
            bool: True if the password is strong.

        Raises:
            ValueError: If the password does not meet the criteria.
        """
        import re
        if len(password) < 12:
            self.logger.error("Password must be at least 12 characters long.")
            raise ValueError("Password must be at least 12 characters long.")
        if not re.search(r"[A-Z]", password):
            self.logger.error("Password must contain at least one uppercase letter.")
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", password):
            self.logger.error("Password must contain at least one lowercase letter.")
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", password):
            self.logger.error("Password must contain at least one digit.")
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            self.logger.error("Password must contain at least one special character.")
            raise ValueError("Password must contain at least one special character.")
        self.logger.debug("Password meets security criteria.")
        return True

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    security_module = SecurityModule()

    # Password Hashing and Verification Example
    try:
        test_password = "StrongPassword!123"
        security_module.is_secure_password(test_password)
        hashed = security_module.hash_password(test_password)
        assert security_module.verify_password(test_password, hashed)
        print("Password hashing and verification succeeded.")
    except Exception as e:
        print(f"Password error: {e}")

    # JWT Token Generation and Verification Example
    try:
        token = security_module.generate_token(user_id="user123", roles=["admin", "user"])
        payload = security_module.verify_token(token)
        print(f"JWT payload: {payload}")
    except AuthenticationError as e:
        print(f"JWT error: {e}")

    # Input Validation Example
    try:
        input_data = {"username": "john_doe", "age": 30}
        input_schema = {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "age": {"type": "integer", "minimum": 18}
            },
            "required": ["username", "age"]
        }
        security_module.validate_input(input_data, input_schema)
        print("Input validation succeeded.")
    except InputValidationError as e:
        print(f"Validation error: {e}")

    # CSRF Protection Example
    try:
        session_id = "session_abc123"
        csrf_token = security_module.generate_csrf_token(session_id)
        assert security_module.verify_csrf_token(session_id, csrf_token)
        print("CSRF token verification succeeded.")
    except CSRFError as e:
        print(f"CSRF error: {e}")

    # Encryption and Decryption Example
    try:
        encryption_key = os.urandom(32)
        plaintext_data = b"Sensitive information"
        encrypted = security_module.encrypt_data(plaintext_data, encryption_key)
        decrypted = security_module.decrypt_data(encrypted, encryption_key)
        assert plaintext_data == decrypted
        print("Encryption and decryption succeeded.")
    except EncryptionError as e:
        print(f"Encryption error: {e}")

    # Security Event Logging Example
    security_module.log_security_event(
        event_type="user_login",
        user_id="user123",
        details={"ip_address": "192.168.1.1"}
    )
