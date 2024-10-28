# services/blockchain_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Union
import os
from web3 import Web3, HTTPProvider, WebsocketProvider
from web3.middleware import geth_poa_middleware
from web3.exceptions import BlockNotFound, TransactionNotFound, BadFunctionCallOutput
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class BlockchainServiceError(Exception):
    """Custom exception for BlockchainService-related errors."""
    pass


class BlockchainService:
    """
    Provides blockchain interaction capabilities, including connecting to blockchain networks,
    querying blocks and transactions, submitting transactions, interacting with smart contracts,
    and listening to blockchain events. Utilizes the web3.py library to ensure comprehensive
    blockchain handling. Ensures secure handling of private keys and configurations.
    """

    def __init__(self):
        """
        Initializes the BlockchainService with necessary configurations and authentication.
        """
        self.logger = setup_logging('BlockchainService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.web3: Optional[Web3] = None
        self.logger.info("BlockchainService initialized successfully.")
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
                raise BlockchainServiceError("Blockchain node URL not provided in configuration.")
            node_url = self.encryption_manager.decrypt_data(node_url_encrypted).decode('utf-8')

            if node_type.lower() == 'http':
                provider = HTTPProvider(node_url)
            elif node_type.lower() == 'ws':
                provider = WebsocketProvider(node_url)
            else:
                self.logger.error(f"Unsupported node type '{node_type}'.")
                raise BlockchainServiceError(f"Unsupported node type '{node_type}'.")

            self.web3 = Web3(provider)

            # For networks like Binance Smart Chain or others using PoA
            if blockchain_config.get('use_poa', False):
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

            if not self.web3.isConnected():
                self.logger.error("Failed to connect to the blockchain network.")
                raise BlockchainServiceError("Failed to connect to the blockchain network.")

            self.logger.debug("Blockchain network connection established successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing blockchain connection: {e}", exc_info=True)
            raise BlockchainServiceError(f"Error initializing blockchain connection: {e}")

    def get_latest_block_number(self) -> Optional[int]:
        """
        Retrieves the latest block number from the blockchain.

        Returns:
            Optional[int]: The latest block number, or None if retrieval fails.
        """
        try:
            self.logger.debug("Fetching the latest block number.")
            with self.lock:
                block_number = self.web3.eth.block_number
            self.logger.info(f"Latest block number retrieved: {block_number}.")
            return block_number
        except Exception as e:
            self.logger.error(f"Error fetching latest block number: {e}", exc_info=True)
            return None

    def get_block_by_number(self, block_number: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves a block's details by its number.

        Args:
            block_number (int): The number of the block to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The block details as a dictionary, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Fetching block details for block number {block_number}.")
            with self.lock:
                block = self.web3.eth.get_block(block_number, full_transactions=True)
            block_dict = dict(block)
            self.logger.info(f"Block {block_number} details retrieved successfully.")
            return block_dict
        except BlockNotFound:
            self.logger.error(f"Block number {block_number} not found.")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching block {block_number}: {e}", exc_info=True)
            return None

    def get_transaction_by_hash(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves transaction details by its hash.

        Args:
            tx_hash (str): The hash of the transaction to retrieve.

        Returns:
            Optional[Dict[str, Any]]: The transaction details as a dictionary, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Fetching transaction details for hash {tx_hash}.")
            with self.lock:
                tx = self.web3.eth.get_transaction(tx_hash)
            tx_dict = dict(tx)
            self.logger.info(f"Transaction {tx_hash} details retrieved successfully.")
            return tx_dict
        except TransactionNotFound:
            self.logger.error(f"Transaction hash {tx_hash} not found.")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching transaction {tx_hash}: {e}", exc_info=True)
            return None

    def send_transaction(self, tx: Dict[str, Any], private_key: str) -> Optional[str]:
        """
        Sends a signed transaction to the blockchain.

        Args:
            tx (Dict[str, Any]): The transaction dictionary containing fields like 'to', 'value', 'gas', etc.
            private_key (str): The private key to sign the transaction.

        Returns:
            Optional[str]: The transaction hash if sent successfully, or None otherwise.
        """
        try:
            self.logger.debug(f"Sending transaction: {tx}.")
            with self.lock:
                account = self.web3.eth.account.privateKeyToAccount(private_key)
                tx['nonce'] = self.web3.eth.get_transaction_count(account.address)
                signed_tx = self.web3.eth.account.sign_transaction(tx, private_key)
                tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = self.web3.toHex(tx_hash)
            self.logger.info(f"Transaction sent successfully with hash {tx_hash_hex}.")
            return tx_hash_hex
        except Exception as e:
            self.logger.error(f"Error sending transaction: {e}", exc_info=True)
            return None

    def interact_with_contract(self, contract_address: str, abi: List[Dict[str, Any]], function_name: str, *args, **kwargs) -> Optional[Any]:
        """
        Interacts with a smart contract by calling a function.

        Args:
            contract_address (str): The address of the smart contract.
            abi (List[Dict[str, Any]]): The ABI of the smart contract.
            function_name (str): The name of the function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Optional[Any]: The result of the contract function call, or None if interaction fails.
        """
        try:
            self.logger.debug(f"Interacting with contract at {contract_address}, function '{function_name}'.")
            with self.lock:
                contract = self.web3.eth.contract(address=contract_address, abi=abi)
                contract_function = getattr(contract.functions, function_name)(*args, **kwargs)
                if contract_function.abi['stateMutability'] in ['view', 'pure']:
                    result = contract_function.call()
                    self.logger.info(f"Contract function '{function_name}' called successfully.")
                    return result
                else:
                    self.logger.error(f"Function '{function_name}' is not a read-only function.")
                    return None
        except BadFunctionCallOutput as e:
            self.logger.error(f"Bad function call output for function '{function_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Error interacting with contract function '{function_name}': {e}", exc_info=True)
            return None

    def listen_to_events(self, contract_address: str, abi: List[Dict[str, Any]], event_name: str, callback: Any) -> None:
        """
        Listens to a specific event emitted by a smart contract and triggers a callback upon event detection.

        Args:
            contract_address (str): The address of the smart contract.
            abi (List[Dict[str, Any]]): The ABI of the smart contract.
            event_name (str): The name of the event to listen for.
            callback (Callable): The callback function to execute when the event is detected.
        """
        try:
            self.logger.debug(f"Setting up event listener for event '{event_name}' on contract '{contract_address}'.")
            contract = self.web3.eth.contract(address=contract_address, abi=abi)
            event = getattr(contract.events, event_name)()

            def handle_event(event):
                self.logger.info(f"Event '{event_name}' detected: {event}.")
                callback(event)

            event_filter = event.createFilter(fromBlock='latest')

            self.logger.debug(f"Event listener for '{event_name}' set up successfully.")

            while True:
                for evt in event_filter.get_new_entries():
                    handle_event(evt)
                self.web3.provider.sleep(2)
        except Exception as e:
            self.logger.error(f"Error setting up event listener for '{event_name}': {e}", exc_info=True)

    def get_balance(self, address: str) -> Optional[int]:
        """
        Retrieves the balance of an address.

        Args:
            address (str): The blockchain address to query.

        Returns:
            Optional[int]: The balance in wei, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Fetching balance for address '{address}'.")
            with self.lock:
                balance = self.web3.eth.get_balance(address)
            self.logger.info(f"Balance for address '{address}': {balance} wei.")
            return balance
        except Exception as e:
            self.logger.error(f"Error fetching balance for address '{address}': {e}", exc_info=True)
            return None

    def deploy_contract(self, abi: List[Dict[str, Any]], bytecode: str, constructor_args: Optional[List[Any]] = None,
                       private_key: str = "") -> Optional[str]:
        """
        Deploys a smart contract to the blockchain.

        Args:
            abi (List[Dict[str, Any]]): The ABI of the smart contract.
            bytecode (str): The bytecode of the smart contract.
            constructor_args (Optional[List[Any]], optional): Arguments for the contract constructor. Defaults to None.
            private_key (str): The private key to sign the deployment transaction.

        Returns:
            Optional[str]: The transaction hash of the deployment transaction, or None if deployment fails.
        """
        try:
            self.logger.debug("Deploying smart contract.")
            with self.lock:
                account = self.web3.eth.account.privateKeyToAccount(private_key)
                contract = self.web3.eth.contract(abi=abi, bytecode=bytecode)
                transaction = contract.constructor(*constructor_args).buildTransaction({
                    'from': account.address,
                    'nonce': self.web3.eth.get_transaction_count(account.address),
                    'gas': 5000000,
                    'gasPrice': self.web3.toWei('20', 'gwei')
                })
                signed_tx = self.web3.eth.account.sign_transaction(transaction, private_key=private_key)
                tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = self.web3.toHex(tx_hash)
            self.logger.info(f"Smart contract deployed successfully with transaction hash {tx_hash_hex}.")
            return tx_hash_hex
        except Exception as e:
            self.logger.error(f"Error deploying smart contract: {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing BlockchainService resources.")
            # Currently, web3.py does not require explicit session closure.
            self.logger.info("BlockchainService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing BlockchainService: {e}", exc_info=True)
            raise BlockchainServiceError(f"Error closing BlockchainService: {e}")
