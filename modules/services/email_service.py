# services/email_service.py

import logging
import smtplib
import ssl
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager

class EmailService:
    """
    Manages sending and receiving emails, including handling attachments, templates,
    and secure email transmission.
    """

    def __init__(self):
        """
        Initializes the EmailService with necessary configurations and secure connections.
        """
        self.logger = setup_logging('EmailService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.smtp_server = self.config_loader.get('SMTP_SERVER')
        self.smtp_port = self.config_loader.get('SMTP_PORT')
        self.sender_email = self.config_loader.get('SENDER_EMAIL')
        self.sender_password = self._decrypt_password(self.config_loader.get('SENDER_PASSWORD'))
        self.context = ssl.create_default_context()
        self.lock = threading.Lock()
        self.logger.info("EmailService initialized successfully.")

    def _decrypt_password(self, encrypted_password: bytes) -> str:
        """
        Decrypts the sender's email password.
        
        Args:
            encrypted_password (bytes): The encrypted password.
        
        Returns:
            str: The decrypted password.
        """
        try:
            decrypted_bytes = self.encryption_manager.decrypt_data(encrypted_password)
            decrypted_password = decrypted_bytes.decode('utf-8')
            self.logger.debug("Sender email password decrypted successfully.")
            return decrypted_password
        except Exception as e:
            self.logger.error(f"Error decrypting sender email password: {e}", exc_info=True)
            raise

    def send_email(self, recipient_emails: List[str], subject: str, body: str, attachments: List[str] = None) -> bool:
        """
        Sends an email to the specified recipients with optional attachments.
        
        Args:
            recipient_emails (List[str]): A list of recipient email addresses.
            subject (str): The subject of the email.
            body (str): The body content of the email.
            attachments (List[str], optional): Paths to files to attach. Defaults to None.
        
        Returns:
            bool: True if the email is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Preparing to send email to {recipient_emails}. Subject: {subject}")
            message = MIMEMultipart()
            message['From'] = self.sender_email
            message['To'] = ', '.join(recipient_emails)
            message['Subject'] = subject

            # Attach the body with MIMEText
            message.attach(MIMEText(body, 'plain'))

            # Attach files if any
            if attachments:
                for file_path in attachments:
                    try:
                        with open(file_path, 'rb') as f:
                            part = MIMEText(f.read(), 'base64', 'utf-8')
                            part.add_header('Content-Disposition', f'attachment; filename="{file_path.split("/")[-1]}"')
                            message.attach(part)
                        self.logger.debug(f"Attached file: {file_path}")
                    except Exception as e:
                        self.logger.error(f"Error attaching file '{file_path}': {e}", exc_info=True)
                        return False

            # Convert message to string
            text = message.as_string()

            # Send the email
            with self.lock:
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=self.context) as server:
                    server.login(self.sender_email, self.sender_password)
                    server.sendmail(self.sender_email, recipient_emails, text)
            self.logger.info(f"Email sent successfully to {recipient_emails}.")
            return True

        except Exception as e:
            self.logger.error(f"Error sending email to {recipient_emails}: {e}", exc_info=True)
            return False

    def send_email_async(self, recipient_emails: List[str], subject: str, body: str, attachments: List[str] = None) -> threading.Thread:
        """
        Sends an email asynchronously.
        
        Args:
            recipient_emails (List[str]): A list of recipient email addresses.
            subject (str): The subject of the email.
            body (str): The body content of the email.
            attachments (List[str], optional): Paths to files to attach. Defaults to None.
        
        Returns:
            threading.Thread: The thread handling the email sending.
        """
        def send():
            success = self.send_email(recipient_emails, subject, body, attachments)
            if success:
                self.logger.debug("Asynchronous email sent successfully.")
            else:
                self.logger.debug("Asynchronous email failed to send.")

        thread = threading.Thread(target=send, daemon=True)
        thread.start()
        self.logger.info(f"Scheduled asynchronous email to {recipient_emails}.")
        return thread

    def send_templated_email(self, recipient_emails: List[str], subject_template: str, body_template: str, context: Dict[str, Any], attachments: List[str] = None) -> bool:
        """
        Sends an email using templates for the subject and body, populated with context data.
        
        Args:
            recipient_emails (List[str]): A list of recipient email addresses.
            subject_template (str): The subject template with placeholders.
            body_template (str): The body template with placeholders.
            context (Dict[str, Any]): A dictionary of context data to populate the templates.
            attachments (List[str], optional): Paths to files to attach. Defaults to None.
        
        Returns:
            bool: True if the email is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Preparing to send templated email to {recipient_emails}.")
            subject = subject_template.format(**context)
            body = body_template.format(**context)
            return self.send_email(recipient_emails, subject, body, attachments)
        except Exception as e:
            self.logger.error(f"Error sending templated email to {recipient_emails}: {e}", exc_info=True)
            return False

    def fetch_emails(self, folder: str = 'INBOX', limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetches the latest emails from the specified folder.
        
        Args:
            folder (str, optional): The email folder to fetch from. Defaults to 'INBOX'.
            limit (int, optional): The number of emails to fetch. Defaults to 10.
        
        Returns:
            List[Dict[str, Any]]: A list of emails with their details.
        """
        try:
            self.logger.debug(f"Fetching {limit} emails from folder '{folder}'.")
            # Placeholder for fetching emails using IMAP or POP3
            # Implement secure fetching logic here
            # Example return structure
            emails = [
                {
                    'subject': 'Test Email',
                    'from': 'sender@example.com',
                    'body': 'This is a test email.',
                    'attachments': []
                }
                # Add more emails as fetched
            ]
            self.logger.info(f"Fetched {len(emails)} emails from folder '{folder}'.")
            return emails
        except Exception as e:
            self.logger.error(f"Error fetching emails from folder '{folder}': {e}", exc_info=True)
            return []
