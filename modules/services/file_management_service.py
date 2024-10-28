# services/file_management_service.py

import logging
import threading
import time
from typing import Any, Dict, List, Optional
import os
import shutil
import hashlib
import json
from pathlib import Path
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class FileManagementServiceError(Exception):
    """Custom exception for FileManagementService-related errors."""
    pass

class FileManagementService:
    """
    Provides comprehensive file management capabilities, including uploading, downloading,
    organizing, searching, and securing files. Supports integration with local storage and
    cloud storage providers (e.g., AWS S3). Ensures secure handling of files and access control.
    """

    def __init__(self):
        """
        Initializes the FileManagementService with necessary configurations and authentication.
        """
        self.logger = setup_logging('FileManagementService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.storage_backend = self.config_loader.get('FILE_STORAGE_BACKEND', 'local')
        self.local_storage_path = self.config_loader.get('LOCAL_STORAGE_PATH', './file_storage')
        self.cloud_credentials = self._load_cloud_credentials()
        self.lock = threading.Lock()
        self._initialize_storage()
        self.logger.info("FileManagementService initialized successfully.")

    def _load_cloud_credentials(self) -> Optional[Dict[str, str]]:
        """
        Loads and decrypts cloud storage credentials from the configuration.

        Returns:
            Optional[Dict[str, str]]: A dictionary of cloud credentials, or None if not configured.
        """
        try:
            self.logger.debug("Loading cloud storage credentials from configuration.")
            encrypted_credentials = self.config_loader.get('CLOUD_STORAGE_CREDENTIALS_ENCRYPTED')
            if encrypted_credentials:
                decrypted_credentials = self.encryption_manager.decrypt_data(encrypted_credentials).decode('utf-8')
                credentials = json.loads(decrypted_credentials)
                self.logger.debug("Cloud storage credentials decrypted successfully.")
                return credentials
            else:
                self.logger.debug("No cloud storage credentials found in configuration.")
                return None
        except Exception as e:
            self.logger.error(f"Error loading cloud storage credentials: {e}", exc_info=True)
            return None

    def _initialize_storage(self):
        """
        Initializes the storage backend based on configuration.
        """
        try:
            self.logger.debug(f"Initializing storage backend: '{self.storage_backend}'.")
            if self.storage_backend == 'local':
                os.makedirs(self.local_storage_path, exist_ok=True)
                self.logger.debug(f"Local storage directory '{self.local_storage_path}' ensured.")
            elif self.storage_backend == 's3':
                if not self.cloud_credentials:
                    self.logger.error("Cloud storage credentials are not configured.")
                    raise FileManagementServiceError("Cloud storage credentials are not configured.")
                # Initialize AWS S3 client here if using AWS S3
                import boto3
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.cloud_credentials.get('aws_access_key_id'),
                    aws_secret_access_key=self.cloud_credentials.get('aws_secret_access_key'),
                    region_name=self.cloud_credentials.get('aws_region', 'us-east-1')
                )
                self.s3_bucket = self.cloud_credentials.get('s3_bucket')
                if not self.s3_bucket:
                    self.logger.error("S3 bucket name not configured.")
                    raise FileManagementServiceError("S3 bucket name not configured.")
                # Ensure the S3 bucket exists
                self._ensure_s3_bucket()
                self.logger.debug("AWS S3 storage initialized successfully.")
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                raise FileManagementServiceError(f"Unsupported storage backend '{self.storage_backend}'.")
        except Exception as e:
            self.logger.error(f"Error initializing storage backend: {e}", exc_info=True)
            raise FileManagementServiceError(f"Error initializing storage backend: {e}")

    def _ensure_s3_bucket(self):
        """
        Ensures that the specified S3 bucket exists; creates it if it does not.
        """
        try:
            self.logger.debug(f"Ensuring S3 bucket '{self.s3_bucket}' exists.")
            response = self.s3_client.list_buckets()
            buckets = [bucket['Name'] for bucket in response['Buckets']]
            if self.s3_bucket not in buckets:
                self.logger.debug(f"S3 bucket '{self.s3_bucket}' does not exist. Creating bucket.")
                self.s3_client.create_bucket(Bucket=self.s3_bucket)
                self.logger.info(f"S3 bucket '{self.s3_bucket}' created successfully.")
            else:
                self.logger.debug(f"S3 bucket '{self.s3_bucket}' already exists.")
        except Exception as e:
            self.logger.error(f"Error ensuring S3 bucket exists: {e}", exc_info=True)
            raise FileManagementServiceError(f"Error ensuring S3 bucket exists: {e}")

    def _get_file_hash(self, file_path: str) -> str:
        """
        Computes the MD5 hash of a file for deduplication and integrity checks.

        Args:
            file_path (str): The path to the file.

        Returns:
            str: The MD5 hash of the file.
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            file_hash = hash_md5.hexdigest()
            self.logger.debug(f"Computed MD5 hash for '{file_path}': {file_hash}")
            return file_hash
        except Exception as e:
            self.logger.error(f"Error computing hash for '{file_path}': {e}", exc_info=True)
            return ""

    def upload_file(self, source_path: str, destination_path: str) -> bool:
        """
        Uploads a file to the storage backend.

        Args:
            source_path (str): The local path to the source file.
            destination_path (str): The destination path in the storage backend.

        Returns:
            bool: True if the file is uploaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Uploading file from '{source_path}' to '{destination_path}'.")
            if self.storage_backend == 'local':
                full_destination = os.path.join(self.local_storage_path, destination_path)
                os.makedirs(os.path.dirname(full_destination), exist_ok=True)
                shutil.copy2(source_path, full_destination)
                self.logger.info(f"File uploaded successfully to '{full_destination}'.")
                return True
            elif self.storage_backend == 's3':
                self.s3_client.upload_file(source_path, self.s3_bucket, destination_path)
                self.logger.info(f"File uploaded successfully to S3 bucket '{self.s3_bucket}' at '{destination_path}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error uploading file '{source_path}' to '{destination_path}': {e}", exc_info=True)
            return False

    def download_file(self, destination_path: str, local_path: str) -> bool:
        """
        Downloads a file from the storage backend.

        Args:
            destination_path (str): The path in the storage backend.
            local_path (str): The local path where the file will be saved.

        Returns:
            bool: True if the file is downloaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Downloading file from '{destination_path}' to '{local_path}'.")
            if self.storage_backend == 'local':
                full_source = os.path.join(self.local_storage_path, destination_path)
                shutil.copy2(full_source, local_path)
                self.logger.info(f"File downloaded successfully from '{full_source}' to '{local_path}'.")
                return True
            elif self.storage_backend == 's3':
                self.s3_client.download_file(self.s3_bucket, destination_path, local_path)
                self.logger.info(f"File downloaded successfully from S3 bucket '{self.s3_bucket}' at '{destination_path}' to '{local_path}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error downloading file '{destination_path}' to '{local_path}': {e}", exc_info=True)
            return False

    def delete_file(self, destination_path: str) -> bool:
        """
        Deletes a file from the storage backend.

        Args:
            destination_path (str): The path in the storage backend.

        Returns:
            bool: True if the file is deleted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Deleting file at '{destination_path}'.")
            if self.storage_backend == 'local':
                full_path = os.path.join(self.local_storage_path, destination_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    self.logger.info(f"File '{full_path}' deleted successfully.")
                    return True
                else:
                    self.logger.warning(f"File '{full_path}' does not exist.")
                    return False
            elif self.storage_backend == 's3':
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=destination_path)
                self.logger.info(f"File '{destination_path}' deleted successfully from S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error deleting file '{destination_path}': {e}", exc_info=True)
            return False

    def organize_files(self, criteria: Dict[str, Any]) -> bool:
        """
        Organizes files based on specified criteria (e.g., file type, date).

        Args:
            criteria (Dict[str, Any]): The criteria for organizing files.

        Returns:
            bool: True if files are organized successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Organizing files with criteria: {criteria}")
            if self.storage_backend == 'local':
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_info = os.stat(file_path)
                        if 'file_type' in criteria:
                            _, ext = os.path.splitext(file)
                            if ext.lower() != criteria['file_type'].lower():
                                continue
                        if 'date' in criteria:
                            file_date = time.strftime('%Y-%m-%d', time.localtime(file_info.st_mtime))
                            if file_date != criteria['date']:
                                continue
                        # Define new directory based on criteria
                        new_dir = os.path.join(self.local_storage_path, criteria.get('organization_method', 'organized'), file_info.st_mtime.strftime('%Y-%m-%d'))
                        os.makedirs(new_dir, exist_ok=True)
                        new_path = os.path.join(new_dir, file)
                        shutil.move(file_path, new_path)
                        self.logger.debug(f"Moved '{file_path}' to '{new_path}'.")
                self.logger.info("Files organized successfully based on the specified criteria.")
                return True
            elif self.storage_backend == 's3':
                # Implement organization logic for S3, such as moving objects to different prefixes
                self.logger.error("File organization for S3 backend is not implemented.")
                return False
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error organizing files with criteria '{criteria}': {e}", exc_info=True)
            return False

    def search_files(self, query: str) -> List[str]:
        """
        Searches for files that match the query.

        Args:
            query (str): The search query (e.g., filename, extension).

        Returns:
            List[str]: A list of file paths that match the query.
        """
        try:
            self.logger.debug(f"Searching for files with query '{query}'.")
            matched_files = []
            if self.storage_backend == 'local':
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        if query.lower() in file.lower():
                            matched_files.append(os.path.join(root, file))
            elif self.storage_backend == 's3':
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.s3_bucket)
                for page in pages:
                    for obj in page.get('Contents', []):
                        if query.lower() in obj['Key'].lower():
                            matched_files.append(obj['Key'])
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
            self.logger.info(f"Found {len(matched_files)} files matching query '{query}'.")
            return matched_files
        except Exception as e:
            self.logger.error(f"Error searching files with query '{query}': {e}", exc_info=True)
            return []

    def download_all_files(self, destination_directory: str) -> bool:
        """
        Downloads all files from the storage backend to a specified local directory.

        Args:
            destination_directory (str): The local directory where files will be downloaded.

        Returns:
            bool: True if all files are downloaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Downloading all files to '{destination_directory}'.")
            os.makedirs(destination_directory, exist_ok=True)
            if self.storage_backend == 'local':
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        source_path = os.path.join(root, file)
                        relative_path = os.path.relpath(source_path, self.local_storage_path)
                        destination_path = os.path.join(destination_directory, relative_path)
                        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                        shutil.copy2(source_path, destination_path)
                        self.logger.debug(f"Copied '{source_path}' to '{destination_path}'.")
                self.logger.info(f"All files downloaded successfully to '{destination_directory}'.")
                return True
            elif self.storage_backend == 's3':
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.s3_bucket)
                for page in pages:
                    for obj in page.get('Contents', []):
                        key = obj['Key']
                        destination_path = os.path.join(destination_directory, key)
                        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                        self.s3_client.download_file(self.s3_bucket, key, destination_path)
                        self.logger.debug(f"Downloaded '{key}' to '{destination_path}'.")
                self.logger.info(f"All files downloaded successfully to '{destination_directory}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error downloading all files to '{destination_directory}': {e}", exc_info=True)
            return False

    def move_file(self, source_path: str, destination_path: str) -> bool:
        """
        Moves a file from one location to another within the storage backend.

        Args:
            source_path (str): The current path of the file.
            destination_path (str): The new path for the file.

        Returns:
            bool: True if the file is moved successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Moving file from '{source_path}' to '{destination_path}'.")
            if self.storage_backend == 'local':
                full_source = os.path.join(self.local_storage_path, source_path)
                full_destination = os.path.join(self.local_storage_path, destination_path)
                os.makedirs(os.path.dirname(full_destination), exist_ok=True)
                shutil.move(full_source, full_destination)
                self.logger.info(f"File moved successfully from '{full_source}' to '{full_destination}'.")
                return True
            elif self.storage_backend == 's3':
                copy_source = {'Bucket': self.s3_bucket, 'Key': source_path}
                self.s3_client.copy_object(CopySource=copy_source, Bucket=self.s3_bucket, Key=destination_path)
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=source_path)
                self.logger.info(f"File moved successfully from '{source_path}' to '{destination_path}' in S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error moving file from '{source_path}' to '{destination_path}': {e}", exc_info=True)
            return False

    def rename_file(self, old_path: str, new_name: str) -> bool:
        """
        Renames a file within the storage backend.

        Args:
            old_path (str): The current path of the file.
            new_name (str): The new name for the file.

        Returns:
            bool: True if the file is renamed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Renaming file from '{old_path}' to '{new_name}'.")
            if self.storage_backend == 'local':
                full_old_path = os.path.join(self.local_storage_path, old_path)
                directory = os.path.dirname(full_old_path)
                full_new_path = os.path.join(directory, new_name)
                os.rename(full_old_path, full_new_path)
                self.logger.info(f"File renamed successfully from '{full_old_path}' to '{full_new_path}'.")
                return True
            elif self.storage_backend == 's3':
                destination_path = os.path.join(os.path.dirname(old_path), new_name)
                copy_source = {'Bucket': self.s3_bucket, 'Key': old_path}
                self.s3_client.copy_object(CopySource=copy_source, Bucket=self.s3_bucket, Key=destination_path)
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=old_path)
                self.logger.info(f"File renamed successfully from '{old_path}' to '{destination_path}' in S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error renaming file from '{old_path}' to '{new_name}': {e}", exc_info=True)
            return False

    def get_file_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves metadata for a specified file.

        Args:
            file_path (str): The path to the file.

        Returns:
            Optional[Dict[str, Any]]: The file metadata, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving metadata for file '{file_path}'.")
            if self.storage_backend == 'local':
                full_path = os.path.join(self.local_storage_path, file_path)
                if not os.path.exists(full_path):
                    self.logger.warning(f"File '{full_path}' does not exist.")
                    return None
                stats = os.stat(full_path)
                metadata = {
                    'size_bytes': stats.st_size,
                    'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.st_ctime)),
                    'modified_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.st_mtime)),
                    'md5_hash': self._get_file_hash(full_path)
                }
                self.logger.info(f"Metadata retrieved for file '{full_path}': {metadata}")
                return metadata
            elif self.storage_backend == 's3':
                response = self.s3_client.head_object(Bucket=self.s3_bucket, Key=file_path)
                metadata = {
                    'size_bytes': response['ContentLength'],
                    'last_modified': response['LastModified'].strftime('%Y-%m-%d %H:%M:%S'),
                    'md5_hash': response.get('ETag', '').strip('"')
                }
                self.logger.info(f"Metadata retrieved for file '{file_path}' in S3 bucket '{self.s3_bucket}': {metadata}")
                return metadata
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error retrieving metadata for file '{file_path}': {e}", exc_info=True)
            return None

    def _get_file_hash(self, file_path: str) -> str:
        """
        Computes the MD5 hash of a file for deduplication and integrity checks.

        Args:
            file_path (str): The path to the file.

        Returns:
            str: The MD5 hash of the file.
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            file_hash = hash_md5.hexdigest()
            self.logger.debug(f"Computed MD5 hash for '{file_path}': {file_hash}")
            return file_hash
        except Exception as e:
            self.logger.error(f"Error computing hash for '{file_path}': {e}", exc_info=True)
            return ""

    def search_files_by_metadata(self, criteria: Dict[str, Any]) -> List[str]:
        """
        Searches for files based on metadata criteria (e.g., size, creation date).

        Args:
            criteria (Dict[str, Any]): The metadata criteria for searching files.

        Returns:
            List[str]: A list of file paths that match the criteria.
        """
        try:
            self.logger.debug(f"Searching for files with metadata criteria: {criteria}")
            matched_files = []
            if self.storage_backend == 'local':
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        metadata = self.get_file_metadata(os.path.relpath(file_path, self.local_storage_path))
                        if not metadata:
                            continue
                        match = True
                        for key, value in criteria.items():
                            if metadata.get(key) != value:
                                match = False
                                break
                        if match:
                            matched_files.append(os.path.relpath(file_path, self.local_storage_path))
            elif self.storage_backend == 's3':
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.s3_bucket)
                for page in pages:
                    for obj in page.get('Contents', []):
                        metadata = self.get_file_metadata(obj['Key'])
                        if not metadata:
                            continue
                        match = True
                        for key, value in criteria.items():
                            if metadata.get(key) != value:
                                match = False
                                break
                        if match:
                            matched_files.append(obj['Key'])
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return []
            self.logger.info(f"Found {len(matched_files)} files matching metadata criteria.")
            return matched_files
        except Exception as e:
            self.logger.error(f"Error searching files by metadata: {e}", exc_info=True)
            return []

    def list_all_files(self) -> List[str]:
        """
        Lists all files in the storage backend.

        Returns:
            List[str]: A list of all file paths.
        """
        try:
            self.logger.debug("Listing all files in the storage backend.")
            all_files = []
            if self.storage_backend == 'local':
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        all_files.append(os.path.relpath(file_path, self.local_storage_path))
            elif self.storage_backend == 's3':
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=self.s3_bucket)
                for page in pages:
                    for obj in page.get('Contents', []):
                        all_files.append(obj['Key'])
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
            self.logger.info(f"Total files found: {len(all_files)}.")
            return all_files
        except Exception as e:
            self.logger.error(f"Error listing all files: {e}", exc_info=True)
            return []

    def rename_file(self, old_path: str, new_name: str) -> bool:
        """
        Renames a file within the storage backend.

        Args:
            old_path (str): The current path of the file.
            new_name (str): The new name for the file.

        Returns:
            bool: True if the file is renamed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Renaming file from '{old_path}' to '{new_name}'.")
            if self.storage_backend == 'local':
                full_old_path = os.path.join(self.local_storage_path, old_path)
                directory = os.path.dirname(full_old_path)
                full_new_path = os.path.join(directory, new_name)
                os.rename(full_old_path, full_new_path)
                self.logger.info(f"File renamed successfully from '{full_old_path}' to '{full_new_path}'.")
                return True
            elif self.storage_backend == 's3':
                new_path = os.path.join(os.path.dirname(old_path), new_name)
                copy_source = {'Bucket': self.s3_bucket, 'Key': old_path}
                self.s3_client.copy_object(CopySource=copy_source, Bucket=self.s3_bucket, Key=new_path)
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=old_path)
                self.logger.info(f"File renamed successfully from '{old_path}' to '{new_path}' in S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error renaming file from '{old_path}' to '{new_name}': {e}", exc_info=True)
            return False

    def move_file(self, source_path: str, destination_path: str) -> bool:
        """
        Moves a file from one location to another within the storage backend.

        Args:
            source_path (str): The current path of the file.
            destination_path (str): The new path for the file.

        Returns:
            bool: True if the file is moved successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Moving file from '{source_path}' to '{destination_path}'.")
            if self.storage_backend == 'local':
                full_source = os.path.join(self.local_storage_path, source_path)
                full_destination = os.path.join(self.local_storage_path, destination_path)
                os.makedirs(os.path.dirname(full_destination), exist_ok=True)
                shutil.move(full_source, full_destination)
                self.logger.info(f"File moved successfully from '{full_source}' to '{full_destination}'.")
                return True
            elif self.storage_backend == 's3':
                copy_source = {'Bucket': self.s3_bucket, 'Key': source_path}
                self.s3_client.copy_object(CopySource=copy_source, Bucket=self.s3_bucket, Key=destination_path)
                self.s3_client.delete_object(Bucket=self.s3_bucket, Key=source_path)
                self.logger.info(f"File moved successfully from '{source_path}' to '{destination_path}' in S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error moving file from '{source_path}' to '{destination_path}': {e}", exc_info=True)
            return False

    def copy_file(self, source_path: str, destination_path: str) -> bool:
        """
        Copies a file from one location to another within the storage backend.

        Args:
            source_path (str): The current path of the file.
            destination_path (str): The destination path for the file.

        Returns:
            bool: True if the file is copied successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Copying file from '{source_path}' to '{destination_path}'.")
            if self.storage_backend == 'local':
                full_source = os.path.join(self.local_storage_path, source_path)
                full_destination = os.path.join(self.local_storage_path, destination_path)
                os.makedirs(os.path.dirname(full_destination), exist_ok=True)
                shutil.copy2(full_source, full_destination)
                self.logger.info(f"File copied successfully from '{full_source}' to '{full_destination}'.")
                return True
            elif self.storage_backend == 's3':
                copy_source = {'Bucket': self.s3_bucket, 'Key': source_path}
                self.s3_client.copy_object(CopySource=copy_source, Bucket=self.s3_bucket, Key=destination_path)
                self.logger.info(f"File copied successfully from '{source_path}' to '{destination_path}' in S3 bucket '{self.s3_bucket}'.")
                return True
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return False
        except Exception as e:
            self.logger.error(f"Error copying file from '{source_path}' to '{destination_path}': {e}", exc_info=True)
            return False

    def get_file_hash(self, file_path: str) -> Optional[str]:
        """
        Retrieves the MD5 hash of a file for integrity checks.

        Args:
            file_path (str): The path to the file.

        Returns:
            Optional[str]: The MD5 hash of the file, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Computing MD5 hash for file '{file_path}'.")
            if self.storage_backend == 'local':
                full_path = os.path.join(self.local_storage_path, file_path)
            elif self.storage_backend == 's3':
                import boto3
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=self.cloud_credentials.get('aws_access_key_id'),
                    aws_secret_access_key=self.cloud_credentials.get('aws_secret_access_key'),
                    region_name=self.cloud_credentials.get('aws_region', 'us-east-1')
                )
                response = s3_client.get_object(Bucket=self.s3_bucket, Key=file_path)
                data = response['Body'].read()
                hash_md5 = hashlib.md5(data).hexdigest()
                self.logger.debug(f"Computed MD5 hash for S3 file '{file_path}': {hash_md5}")
                return hash_md5
            else:
                self.logger.error(f"Unsupported storage backend '{self.storage_backend}'.")
                return None

            hash_md5 = hashlib.md5()
            with open(full_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            file_hash = hash_md5.hexdigest()
            self.logger.debug(f"Computed MD5 hash for file '{full_path}': {file_hash}")
            return file_hash
        except Exception as e:
            self.logger.error(f"Error computing hash for file '{file_path}': {e}", exc_info=True)
            return None

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing FileManagementService resources.")
            # Currently, no persistent resources to close
            self.logger.info("FileManagementService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing FileManagementService: {e}", exc_info=True)
            raise FileManagementServiceError(f"Error closing FileManagementService: {e}")
