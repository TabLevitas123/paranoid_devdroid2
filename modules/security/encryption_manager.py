# security/encryption_manager.py

import logging
import os
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidKey
from modules.utilities.logging_manager import setup_logging
from modules.security.authentication import AuthenticationManager

class EncryptionManager:
    """
    Manages encryption and decryption of data using AES-256 in CBC mode.
    """

    def __init__(self, key=None, salt=None):
        """
        Initializes the EncryptionManager with a given key and salt.
        If no key is provided, it generates one using a password from environment variables.
        
        Args:
            key (bytes, optional): The encryption key. Defaults to None.
            salt (bytes, optional): The salt for key derivation. Defaults to None.
        """
        self.logger = setup_logging('EncryptionManager')
        self.backend = default_backend()
        self.block_size = 128  # Block size for padding

        if key and salt:
            self.key = key
            self.salt = salt
            self.logger.debug("Encryption key and salt provided explicitly.")
        else:
            # Generate key from environment variable
            password = os.getenv('ENCRYPTION_PASSWORD')
            if not password:
                self.logger.error("ENCRYPTION_PASSWORD environment variable not set.")
                raise EnvironmentError("ENCRYPTION_PASSWORD environment variable not set.")
            self.salt = os.getenv('ENCRYPTION_SALT')
            if not self.salt:
                self.logger.error("ENCRYPTION_SALT environment variable not set.")
                raise EnvironmentError("ENCRYPTION_SALT environment variable not set.")
            self.salt = self.salt.encode()
            self.key = self._derive_key(password.encode(), self.salt)
            self.logger.debug("Encryption key derived from password and salt.")

    def _derive_key(self, password, salt):
        """
        Derives a secret key from a given password and salt using PBKDF2 HMAC SHA256.
        
        Args:
            password (bytes): The password.
            salt (bytes): The salt.
        
        Returns:
            bytes: The derived key.
        """
        try:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,  # AES-256 key size
                salt=salt,
                iterations=100000,
                backend=self.backend
            )
            key = kdf.derive(password)
            self.logger.debug("Encryption key successfully derived.")
            return key
        except Exception as e:
            self.logger.error(f"Error deriving encryption key: {e}", exc_info=True)
            raise

    def encrypt_data(self, plaintext):
        """
        Encrypts plaintext data using AES-256-CBC.
        
        Args:
            plaintext (bytes): The data to encrypt.
        
        Returns:
            bytes: The encrypted data with IV prepended.
        """
        try:
            iv = os.urandom(16)  # 128-bit IV for AES
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=self.backend)
            encryptor = cipher.encryptor()
            padder = padding.PKCS7(self.block_size).padder()
            padded_data = padder.update(plaintext) + padder.finalize()
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()
            encrypted_data = iv + ciphertext  # Prepend IV for use in decryption
            self.logger.debug("Data encrypted successfully.")
            return encrypted_data
        except Exception as e:
            self.logger.error(f"Error encrypting data: {e}", exc_info=True)
            raise

    def decrypt_data(self, encrypted_data):
        """
        Decrypts data encrypted by encrypt_data.
        
        Args:
            encrypted_data (bytes): The data to decrypt, with IV prepended.
        
        Returns:
            bytes: The decrypted plaintext data.
        """
        try:
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=self.backend)
            decryptor = cipher.decryptor()
            padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = padding.PKCS7(self.block_size).unpadder()
            plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
            self.logger.debug("Data decrypted successfully.")
            return plaintext
        except (ValueError, InvalidKey) as e:
            self.logger.error(f"Invalid encryption key or corrupted data: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"Error decrypting data: {e}", exc_info=True)
            raise

    def rotate_key(self, new_password, new_salt):
        """
        Rotates the encryption key by deriving a new key from a new password and salt.
        This should be done periodically to enhance security.
        
        Args:
            new_password (str): The new password.
            new_salt (str): The new salt.
        
        Returns:
            None
        """
        try:
            self.logger.info("Rotating encryption key.")
            self.salt = new_salt.encode()
            self.key = self._derive_key(new_password.encode(), self.salt)
            self.logger.info("Encryption key rotated successfully.")
        except Exception as e:
            self.logger.error(f"Error rotating encryption key: {e}", exc_info=True)
            raise
