# security/authentication.py

import logging
import os
import threading
import jwt
import bcrypt
from datetime import datetime, timedelta
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager

class AuthenticationManager:
    """
    Manages user and agent authentication, including registration, login, and token verification.
    """

    def __init__(self):
        """
        Initializes the AuthenticationManager with necessary configurations.
        """
        self.logger = setup_logging('AuthenticationManager')
        self.encryption_manager = EncryptionManager()
        self.jwt_secret = os.getenv('JWT_SECRET')
        self.jwt_algorithm = 'HS256'
        self.token_expiry_minutes = 60  # Token validity duration

        if not self.jwt_secret:
            self.logger.error("JWT_SECRET environment variable not set.")
            raise EnvironmentError("JWT_SECRET environment variable not set.")
        
        self.user_db = {}  # In-memory user database; replace with persistent storage in production
        self.lock = threading.Lock()
        self.logger.info("AuthenticationManager initialized successfully.")

    def register_user(self, username, password):
        """
        Registers a new user with a username and password.
        
        Args:
            username (str): The desired username.
            password (str): The desired password.
        
        Returns:
            bool: True if registration is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Attempting to register user: {username}")
            with self.lock:
                if username in self.user_db:
                    self.logger.warning(f"Registration failed: Username '{username}' already exists.")
                    return False
                hashed_password = self._hash_password(password)
                self.user_db[username] = hashed_password
            self.logger.info(f"User '{username}' registered successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error registering user '{username}': {e}", exc_info=True)
            return False

    def authenticate_user(self, username, password):
        """
        Authenticates a user and returns a JWT token if successful.
        
        Args:
            username (str): The username.
            password (str): The password.
        
        Returns:
            str: JWT token if authentication is successful, None otherwise.
        """
        try:
            self.logger.debug(f"Attempting to authenticate user: {username}")
            with self.lock:
                if username not in self.user_db:
                    self.logger.warning(f"Authentication failed: Username '{username}' not found.")
                    return None
                hashed_password = self.user_db[username]
            if self._verify_password(password, hashed_password):
                token = self._generate_token(username)
                self.logger.info(f"User '{username}' authenticated successfully.")
                return token
            else:
                self.logger.warning(f"Authentication failed: Incorrect password for user '{username}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error authenticating user '{username}': {e}", exc_info=True)
            return None

    def verify_token(self, token):
        """
        Verifies a JWT token and returns the username if valid.
        
        Args:
            token (str): The JWT token.
        
        Returns:
            str: The username if token is valid, None otherwise.
        """
        try:
            self.logger.debug("Verifying JWT token.")
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            username = payload.get('sub')
            self.logger.info(f"Token verified successfully for user '{username}'.")
            return username
        except jwt.ExpiredSignatureError:
            self.logger.warning("Token verification failed: Token has expired.")
            return None
        except jwt.InvalidTokenError:
            self.logger.warning("Token verification failed: Invalid token.")
            return None
        except Exception as e:
            self.logger.error(f"Error verifying token: {e}", exc_info=True)
            return None

    def _hash_password(self, password):
        """
        Hashes a password using bcrypt.
        
        Args:
            password (str): The password to hash.
        
        Returns:
            bytes: The hashed password.
        """
        try:
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode(), salt)
            self.logger.debug("Password hashed successfully.")
            return hashed
        except Exception as e:
            self.logger.error(f"Error hashing password: {e}", exc_info=True)
            raise

    def _verify_password(self, password, hashed):
        """
        Verifies a password against a hashed password.
        
        Args:
            password (str): The plaintext password.
            hashed (bytes): The hashed password.
        
        Returns:
            bool: True if password matches, False otherwise.
        """
        try:
            result = bcrypt.checkpw(password.encode(), hashed)
            self.logger.debug(f"Password verification result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error verifying password: {e}", exc_info=True)
            return False

    def _generate_token(self, username):
        """
        Generates a JWT token for a given username.
        
        Args:
            username (str): The username.
        
        Returns:
            str: The JWT token.
        """
        try:
            expiration = datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes)
            payload = {
                'sub': username,
                'iat': datetime.utcnow(),
                'exp': expiration
            }
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            self.logger.debug("JWT token generated successfully.")
            return token
        except Exception as e:
            self.logger.error(f"Error generating JWT token: {e}", exc_info=True)
            raise

    def rotate_jwt_secret(self, new_secret):
        """
        Rotates the JWT secret key.
        
        Args:
            new_secret (str): The new secret key.
        
        Returns:
            None
        """
        try:
            self.logger.info("Rotating JWT secret key.")
            self.jwt_secret = new_secret
            self.logger.info("JWT secret key rotated successfully.")
        except Exception as e:
            self.logger.error(f"Error rotating JWT secret key: {e}", exc_info=True)
            raise
