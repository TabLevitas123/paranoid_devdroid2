# services/payment_gateway_service.py

import logging
import threading
from typing import Any, Dict, Optional
import requests
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class PaymentGatewayServiceError(Exception):
    """Custom exception for PaymentGatewayService-related errors."""
    pass


class PaymentGatewayService:
    """
    Provides payment processing capabilities, including handling transactions, refunds,
    and payment method management. Integrates with third-party payment gateways like Stripe
    or PayPal to facilitate secure and reliable financial transactions. Ensures secure
    handling of payment information and adheres to compliance standards such as PCI DSS.
    """

    def __init__(self):
        """
        Initializes the PaymentGatewayService with necessary configurations and authentication.
        """
        self.logger = setup_logging('PaymentGatewayService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.payment_api_config = self._load_payment_api_config()
        self.session = requests.Session()
        self.logger.info("PaymentGatewayService initialized successfully.")

    def _load_payment_api_config(self) -> Dict[str, Any]:
        """
        Loads payment API configurations securely.

        Returns:
            Dict[str, Any]: A dictionary containing payment API configurations.
        """
        try:
            self.logger.debug("Loading payment API configurations.")
            api_config_encrypted = self.config_loader.get('PAYMENT_API_CONFIG', {})
            api_key_encrypted = api_config_encrypted.get('api_key')
            base_url = api_config_encrypted.get('base_url')
            if not api_key_encrypted or not base_url:
                self.logger.error("Payment API configuration is incomplete.")
                raise PaymentGatewayServiceError("Payment API configuration is incomplete.")
            api_key = self.encryption_manager.decrypt_data(api_key_encrypted).decode('utf-8')
            self.logger.debug("Payment API configurations loaded successfully.")
            return {
                'api_key': api_key,
                'base_url': base_url
            }
        except Exception as e:
            self.logger.error(f"Error loading payment API configurations: {e}", exc_info=True)
            raise PaymentGatewayServiceError(f"Error loading payment API configurations: {e}")

    def process_payment(self, amount: float, currency: str, payment_method: Dict[str, Any], description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Processes a payment transaction.

        Args:
            amount (float): The amount to be charged.
            currency (str): The currency in which the payment is made (e.g., 'USD').
            payment_method (Dict[str, Any]): The payment method details (e.g., card information).
            description (Optional[str], optional): A description for the transaction. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing transaction details if successful, else None.
        """
        try:
            self.logger.debug(f"Processing payment of {amount} {currency} with payment method: {payment_method}.")
            with self.lock:
                headers = {
                    'Authorization': f"Bearer {self.payment_api_config['api_key']}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'amount': amount,
                    'currency': currency,
                    'payment_method': payment_method,
                    'description': description or "Payment Transaction"
                }
                response = self.session.post(f"{self.payment_api_config['base_url']}/payments", json=payload, headers=headers, timeout=15)
                if response.status_code == 201:
                    transaction = response.json()
                    self.logger.info(f"Payment processed successfully: Transaction ID {transaction.get('id')}.")
                    return transaction
                else:
                    self.logger.error(f"Failed to process payment. Status Code: {response.status_code}, Response: {response.text}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during payment processing: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during payment processing: {e}", exc_info=True)
            return None

    def refund_payment(self, transaction_id: str, amount: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Processes a refund for a specific transaction.

        Args:
            transaction_id (str): The unique identifier of the transaction to refund.
            amount (Optional[float], optional): The amount to refund. If None, full refund is processed. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing refund details if successful, else None.
        """
        try:
            self.logger.debug(f"Processing refund for Transaction ID '{transaction_id}' with amount: {amount}.")
            with self.lock:
                headers = {
                    'Authorization': f"Bearer {self.payment_api_config['api_key']}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'transaction_id': transaction_id,
                    'amount': amount
                } if amount else {
                    'transaction_id': transaction_id
                }
                response = self.session.post(f"{self.payment_api_config['base_url']}/refunds", json=payload, headers=headers, timeout=15)
                if response.status_code in [200, 201]:
                    refund = response.json()
                    self.logger.info(f"Refund processed successfully: Refund ID {refund.get('id')}.")
                    return refund
                else:
                    self.logger.error(f"Failed to process refund. Status Code: {response.status_code}, Response: {response.text}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during refund processing: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during refund processing: {e}", exc_info=True)
            return None

    def get_transaction_status(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the status of a specific transaction.

        Args:
            transaction_id (str): The unique identifier of the transaction.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing transaction status details if successful, else None.
        """
        try:
            self.logger.debug(f"Retrieving status for Transaction ID '{transaction_id}'.")
            with self.lock:
                headers = {
                    'Authorization': f"Bearer {self.payment_api_config['api_key']}",
                    'Content-Type': 'application/json'
                }
                response = self.session.get(f"{self.payment_api_config['base_url']}/payments/{transaction_id}", headers=headers, timeout=10)
                if response.status_code == 200:
                    transaction_status = response.json()
                    self.logger.info(f"Transaction status retrieved successfully for Transaction ID '{transaction_id}'.")
                    return transaction_status
                else:
                    self.logger.error(f"Failed to retrieve transaction status. Status Code: {response.status_code}, Response: {response.text}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during transaction status retrieval: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during transaction status retrieval: {e}", exc_info=True)
            return None

    def add_payment_method(self, user_id: str, payment_method: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Adds a new payment method for a user.

        Args:
            user_id (str): The unique identifier of the user.
            payment_method (Dict[str, Any]): The payment method details (e.g., card information).

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing payment method details if successful, else None.
        """
        try:
            self.logger.debug(f"Adding payment method for User ID '{user_id}': {payment_method}.")
            with self.lock:
                headers = {
                    'Authorization': f"Bearer {self.payment_api_config['api_key']}",
                    'Content-Type': 'application/json'
                }
                payload = {
                    'user_id': user_id,
                    'payment_method': payment_method
                }
                response = self.session.post(f"{self.payment_api_config['base_url']}/users/{user_id}/payment_methods", json=payload, headers=headers, timeout=15)
                if response.status_code == 201:
                    payment_method_response = response.json()
                    self.logger.info(f"Payment method added successfully for User ID '{user_id}': Method ID {payment_method_response.get('id')}.")
                    return payment_method_response
                else:
                    self.logger.error(f"Failed to add payment method. Status Code: {response.status_code}, Response: {response.text}")
                    return None
        except requests.RequestException as e:
            self.logger.error(f"Request exception during adding payment method: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during adding payment method: {e}", exc_info=True)
            return None

    def remove_payment_method(self, user_id: str, payment_method_id: str) -> bool:
        """
        Removes an existing payment method for a user.

        Args:
            user_id (str): The unique identifier of the user.
            payment_method_id (str): The unique identifier of the payment method to remove.

        Returns:
            bool: True if the payment method is removed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Removing payment method ID '{payment_method_id}' for User ID '{user_id}'.")
            with self.lock:
                headers = {
                    'Authorization': f"Bearer {self.payment_api_config['api_key']}",
                    'Content-Type': 'application/json'
                }
                response = self.session.delete(f"{self.payment_api_config['base_url']}/users/{user_id}/payment_methods/{payment_method_id}", headers=headers, timeout=10)
                if response.status_code == 200:
                    self.logger.info(f"Payment method ID '{payment_method_id}' removed successfully for User ID '{user_id}'.")
                    return True
                else:
                    self.logger.error(f"Failed to remove payment method. Status Code: {response.status_code}, Response: {response.text}")
                    return False
        except requests.RequestException as e:
            self.logger.error(f"Request exception during removing payment method: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during removing payment method: {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing PaymentGatewayService resources.")
            if self.session:
                self.session.close()
                self.logger.debug("HTTP session closed.")
            self.logger.info("PaymentGatewayService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing PaymentGatewayService: {e}", exc_info=True)
            raise PaymentGatewayServiceError(f"Error closing PaymentGatewayService: {e}")
