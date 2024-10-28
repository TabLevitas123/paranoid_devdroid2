# services/cryptocurrency_wallet_service.py

import logging
import threading
from typing import Any, Dict, List, Optional
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.exceptions import BlockNotFound
from eth_account import Account
from eth_keys import key
from eth_utils import to_checksum_address
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class CryptocurrencyWalletServiceError(Exception):
    """Custom exception for CryptocurrencyWalletService-related errors."""
    pass


class CryptocurrencyWalletService:
    """
    Provides cryptocurrency wallet management capabilities, including wallet creation,
    private key management, balance inquiries, sending and receiving funds, and transaction
    history retrieval. Utilizes the web3.py library for blockchain interactions and ensures
    secure handling of private keys and sensitive data.
    """

    def __init__(self):
        """
        Initializes the CryptocurrencyWalletService with necessary configurations and authentication.
        """
        self.logger = setup_logging('CryptocurrencyWalletService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.web3: Optional[Web3] = None
        self.default_chain = 'ethereum'
        self.logger.info("CryptocurrencyWalletService initialized successfully.")
        self._initialize_connection()

    def _initialize_connection(self):
        """
        Initializes the connection to the blockchain network based on configuration settings.
        """
        try:
            self.logger.debug("Initializing blockchain network connection.")
            blockchain_config = self.config_loader.get('BLOCKCHAIN_CONFIG', {})
            node_type = blockchain_config.get('node_type', 'http')  # 'http' or 'ws'
            node_url_encrypted = blockchain_config.get('node_url')
            if not node_url_encrypted:
                self.logger.error("Blockchain node URL not provided in configuration.")
                raise CryptocurrencyWalletServiceError("Blockchain node URL not provided in configuration.")
            node_url = self.encryption_manager.decrypt_data(node_url_encrypted).decode('utf-8')

            if node_type.lower() == 'http':
                provider = Web3.HTTPProvider(node_url)
            elif node_type.lower() == 'ws':
                provider = Web3.WebsocketProvider(node_url)
            else:
                self.logger.error(f"Unsupported node type '{node_type}'.")
                raise CryptocurrencyWalletServiceError(f"Unsupported node type '{node_type}'.")

            self.web3 = Web3(Web3.HTTPProvider('https://<your-ethereum-node>'))

            # For networks like Binance Smart Chain or others using PoA
            if blockchain_config.get('use_poa', False):
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

            if not self.web3.isConnected():
                self.logger.error("Failed to connect to the blockchain network.")
                raise CryptocurrencyWalletServiceError("Failed to connect to the blockchain network.")

            self.logger.debug("Blockchain network connection established successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing blockchain connection: {e}", exc_info=True)
            raise CryptocurrencyWalletServiceError(f"Error initializing blockchain connection: {e}")

    def create_wallet(self) -> Optional[Dict[str, str]]:
        """
        Creates a new cryptocurrency wallet with a unique private and public key pair.

        Returns:
            Optional[Dict[str, str]]: A dictionary containing the wallet's address and private key, or None if creation fails.
        """
        try:
            self.logger.debug("Creating a new cryptocurrency wallet.")
            with self.lock:
                account = Account.create()
                wallet_address = account.address
                private_key = account.privateKey.hex()
            self.logger.info(f"New wallet created successfully. Address: {wallet_address}.")
            return {'address': wallet_address, 'private_key': private_key}
        except Exception as e:
            self.logger.error(f"Error creating wallet: {e}", exc_info=True)
            return None

    def encrypt_private_key(self, private_key: str, password: str) -> Optional[str]:
        """
        Encrypts a private key using a provided password.

        Args:
            private_key (str): The private key to encrypt.
            password (str): The password to use for encryption.

        Returns:
            Optional[str]: The encrypted private key, or None if encryption fails.
        """
        try:
            self.logger.debug("Encrypting private key.")
            encrypted_key = self.encryption_manager.encrypt_data(private_key.encode('utf-8'), password)
            self.logger.info("Private key encrypted successfully.")
            return encrypted_key.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error encrypting private key: {e}", exc_info=True)
            return None

    def decrypt_private_key(self, encrypted_key: str, password: str) -> Optional[str]:
        """
        Decrypts an encrypted private key using a provided password.

        Args:
            encrypted_key (str): The encrypted private key.
            password (str): The password used for decryption.

        Returns:
            Optional[str]: The decrypted private key, or None if decryption fails.
        """
        try:
            self.logger.debug("Decrypting private key.")
            decrypted_key = self.encryption_manager.decrypt_data(encrypted_key.encode('utf-8'), password)
            self.logger.info("Private key decrypted successfully.")
            return decrypted_key.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error decrypting private key: {e}", exc_info=True)
            return None

    def get_balance(self, address: str) -> Optional[float]:
        """
        Retrieves the balance of a cryptocurrency address.

        Args:
            address (str): The blockchain address to query.

        Returns:
            Optional[float]: The balance in Ether, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Fetching balance for address '{address}'.")
            with self.lock:
                balance_wei = self.web3.eth.get_balance(address)
                balance_eth = self.web3.fromWei(balance_wei, 'ether')
            self.logger.info(f"Balance for address '{address}': {balance_eth} Ether.")
            return balance_eth
        except Exception as e:
            self.logger.error(f"Error fetching balance for address '{address}': {e}", exc_info=True)
            return None

    def send_funds(self, from_address: str, to_address: str, amount_eth: float, private_key: str,
                  gas: int = 21000, gas_price_gwei: float = 20.0) -> Optional[str]:
        """
        Sends Ether from one address to another.

        Args:
            from_address (str): The sender's blockchain address.
            to_address (str): The recipient's blockchain address.
            amount_eth (float): The amount of Ether to send.
            private_key (str): The private key of the sender's address.
            gas (int, optional): The gas limit for the transaction. Defaults to 21000.
            gas_price_gwei (float, optional): The gas price in Gwei. Defaults to 20.0.

        Returns:
            Optional[str]: The transaction hash if sent successfully, or None otherwise.
        """
        try:
            self.logger.debug(f"Preparing to send {amount_eth} Ether from '{from_address}' to '{to_address}'.")
            with self.lock:
                nonce = self.web3.eth.get_transaction_count(from_address)
                tx = {
                    'nonce': nonce,
                    'to': to_address,
                    'value': self.web3.toWei(amount_eth, 'ether'),
                    'gas': gas,
                    'gasPrice': self.web3.toWei(gas_price_gwei, 'gwei'),
                    'chainId': self.web3.eth.chain_id
                }
                signed_tx = self.web3.eth.account.sign_transaction(tx, private_key)
                tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = self.web3.toHex(tx_hash)
            self.logger.info(f"Transaction sent successfully with hash {tx_hash_hex}.")
            return tx_hash_hex
        except Exception as e:
            self.logger.error(f"Error sending funds from '{from_address}' to '{to_address}': {e}", exc_info=True)
            return None

    def get_transaction_history(self, address: str, start_block: int, end_block: int) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves the transaction history for a given address within a block range.

        Args:
            address (str): The blockchain address to query.
            start_block (int): The starting block number.
            end_block (int): The ending block number.

        Returns:
            Optional[List[Dict[str, Any]]]: A list of transactions, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Fetching transaction history for address '{address}' from block {start_block} to {end_block}.")
            transactions = []
            for block_num in range(start_block, end_block + 1):
                try:
                    block = self.web3.eth.get_block(block_num, full_transactions=True)
                    for tx in block.transactions:
                        if tx['from'].lower() == address.lower() or tx['to'] and tx['to'].lower() == address.lower():
                            tx_details = {
                                'hash': tx.hash.hex(),
                                'from': tx['from'],
                                'to': tx['to'],
                                'value': self.web3.fromWei(tx['value'], 'ether'),
                                'gas': tx['gas'],
                                'gasPrice': self.web3.fromWei(tx['gasPrice'], 'gwei'),
                                'nonce': tx['nonce'],
                                'blockNumber': tx['blockNumber']
                            }
                            transactions.append(tx_details)
                    self.logger.debug(f"Processed block {block_num}.")
                except BlockNotFound:
                    self.logger.warning(f"Block number {block_num} not found. Skipping.")
                    continue
            self.logger.info(f"Transaction history for address '{address}' retrieved successfully with {len(transactions)} transactions.")
            return transactions
        except Exception as e:
            self.logger.error(f"Error fetching transaction history for address '{address}': {e}", exc_info=True)
            return None

    def import_wallet(self, encrypted_private_key: str, password: str) -> Optional[str]:
        """
        Imports a wallet by decrypting the provided encrypted private key.

        Args:
            encrypted_private_key (str): The encrypted private key.
            password (str): The password used for decryption.

        Returns:
            Optional[str]: The wallet's address if import is successful, or None otherwise.
        """
        try:
            self.logger.debug("Importing wallet from encrypted private key.")
            private_key = self.decrypt_private_key(encrypted_private_key, password)
            if not private_key:
                self.logger.error("Failed to decrypt the private key.")
                return None
            account = Account.privateKeyToAccount(private_key)
            self.logger.info(f"Wallet imported successfully. Address: {account.address}.")
            return account.address
        except Exception as e:
            self.logger.error(f"Error importing wallet: {e}", exc_info=True)
            return None

    def generate_mnemonic(self, strength: int = 128) -> Optional[str]:
        """
        Generates a mnemonic phrase for wallet backup.

        Args:
            strength (int, optional): Strength of the mnemonic in bits. Defaults to 128.

        Returns:
            Optional[str]: The mnemonic phrase, or None if generation fails.
        """
        try:
            from mnemonic import Mnemonic
            self.logger.debug(f"Generating mnemonic phrase with strength {strength} bits.")
            mnemo = Mnemonic("english")
            mnemonic_phrase = mnemo.generate(strength=strength)
            self.logger.info("Mnemonic phrase generated successfully.")
            return mnemonic_phrase
        except Exception as e:
            self.logger.error(f"Error generating mnemonic phrase: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing CryptocurrencyWalletService resources.")
            # Currently, web3.py does not require explicit session closure.
            self.logger.info("CryptocurrencyWalletService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing CryptocurrencyWalletService: {e}", exc_info=True)
            raise CryptocurrencyWalletServiceError(f"Error closing CryptocurrencyWalletService: {e}")
