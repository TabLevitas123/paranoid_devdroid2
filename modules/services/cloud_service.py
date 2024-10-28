# services/cloud_services.py

import logging
import threading
import boto3
import botocore
from typing import Any, Dict, List, Optional
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class CloudServiceError(Exception):
    """Custom exception for CloudService-related errors."""
    pass

class CloudServices:
    """
    Manages interactions with cloud service providers such as AWS, Azure, and Google Cloud.
    Handles tasks like resource provisioning, management, monitoring, and secure data storage.
    """

    def __init__(self):
        """
        Initializes the CloudServices with necessary configurations and authentication.
        """
        self.logger = setup_logging('CloudServices')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.aws_client = self._initialize_aws_client()
        self.lock = threading.Lock()
        self.logger.info("CloudServices initialized successfully.")

    def _initialize_aws_client(self) -> boto3.client:
        """
        Initializes the AWS client using encrypted credentials from the configuration.
        
        Returns:
            boto3.client: The initialized AWS client.
        
        Raises:
            CloudServiceError: If AWS credentials are missing or invalid.
        """
        try:
            self.logger.debug("Initializing AWS client.")
            encrypted_access_key = self.config_loader.get('AWS_ACCESS_KEY_ID_ENCRYPTED')
            encrypted_secret_key = self.config_loader.get('AWS_SECRET_ACCESS_KEY_ENCRYPTED')
            if not encrypted_access_key or not encrypted_secret_key:
                self.logger.error("AWS credentials not found in configuration.")
                raise CloudServiceError("AWS credentials not found in configuration.")
            access_key = self.encryption_manager.decrypt_data(encrypted_access_key).decode('utf-8')
            secret_key = self.encryption_manager.decrypt_data(encrypted_secret_key).decode('utf-8')
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=self.config_loader.get('AWS_REGION', 'us-east-1')
            )
            s3_client = session.client('s3')
            self.logger.debug("AWS client initialized successfully.")
            return s3_client
        except Exception as e:
            self.logger.error(f"Error initializing AWS client: {e}", exc_info=True)
            raise CloudServiceError(f"Error initializing AWS client: {e}")

    def create_s3_bucket(self, bucket_name: str, region: Optional[str] = None) -> bool:
        """
        Creates an S3 bucket in the specified region.
        
        Args:
            bucket_name (str): The name of the bucket to create.
            region (Optional[str], optional): The AWS region where the bucket will be created. Defaults to None.
        
        Returns:
            bool: True if the bucket is created successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Creating S3 bucket: {bucket_name} in region: {region}")
            with self.lock:
                if region:
                    self.aws_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={'LocationConstraint': region}
                    )
                else:
                    self.aws_client.create_bucket(Bucket=bucket_name)
            self.logger.info(f"S3 bucket '{bucket_name}' created successfully.")
            return True
        except self.aws_client.exceptions.BucketAlreadyOwnedByYou:
            self.logger.warning(f"S3 bucket '{bucket_name}' already exists and is owned by you.")
            return True
        except self.aws_client.exceptions.BucketAlreadyExists:
            self.logger.error(f"S3 bucket '{bucket_name}' already exists and is owned by someone else.")
            return False
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when creating S3 bucket '{bucket_name}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error when creating S3 bucket '{bucket_name}': {e}", exc_info=True)
            return False

    def list_s3_buckets(self) -> Optional[Dict[str, Any]]:
        """
        Lists all S3 buckets in the AWS account.
        
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing bucket information, or None if failed.
        """
        try:
            self.logger.debug("Listing all S3 buckets.")
            response = self.aws_client.list_buckets()
            buckets = response.get('Buckets', [])
            self.logger.info(f"Retrieved {len(buckets)} S3 buckets.")
            return {'Buckets': buckets}
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when listing S3 buckets: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when listing S3 buckets: {e}", exc_info=True)
            return None

    def upload_file_to_s3(self, file_path: str, bucket_name: str, object_name: Optional[str] = None) -> bool:
        """
        Uploads a file to a specified S3 bucket.
        
        Args:
            file_path (str): The local path to the file to upload.
            bucket_name (str): The name of the target S3 bucket.
            object_name (Optional[str], optional): The S3 object name. Defaults to None.
        
        Returns:
            bool: True if the file is uploaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Uploading file '{file_path}' to S3 bucket '{bucket_name}' as '{object_name}'.")
            if object_name is None:
                object_name = file_path.split('/')[-1]
            with self.lock:
                self.aws_client.upload_file(file_path, bucket_name, object_name)
            self.logger.info(f"File '{file_path}' uploaded to S3 bucket '{bucket_name}' as '{object_name}' successfully.")
            return True
        except botocore.exceptions.NoCredentialsError:
            self.logger.error("AWS credentials not available.")
            return False
        except botocore.exceptions.PartialCredentialsError:
            self.logger.error("Incomplete AWS credentials provided.")
            return False
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when uploading file to S3: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error when uploading file to S3: {e}", exc_info=True)
            return False

    def download_file_from_s3(self, bucket_name: str, object_name: str, download_path: str) -> bool:
        """
        Downloads a file from a specified S3 bucket.
        
        Args:
            bucket_name (str): The name of the S3 bucket.
            object_name (str): The S3 object name.
            download_path (str): The local path where the file will be saved.
        
        Returns:
            bool: True if the file is downloaded successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Downloading file '{object_name}' from S3 bucket '{bucket_name}' to '{download_path}'.")
            with self.lock:
                self.aws_client.download_file(bucket_name, object_name, download_path)
            self.logger.info(f"File '{object_name}' downloaded from S3 bucket '{bucket_name}' to '{download_path}' successfully.")
            return True
        except botocore.exceptions.NoCredentialsError:
            self.logger.error("AWS credentials not available.")
            return False
        except botocore.exceptions.PartialCredentialsError:
            self.logger.error("Incomplete AWS credentials provided.")
            return False
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when downloading file from S3: {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error when downloading file from S3: {e}", exc_info=True)
            return False

    def delete_s3_bucket(self, bucket_name: str) -> bool:
        """
        Deletes an S3 bucket. The bucket must be empty before deletion.
        
        Args:
            bucket_name (str): The name of the S3 bucket to delete.
        
        Returns:
            bool: True if the bucket is deleted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Deleting S3 bucket '{bucket_name}'.")
            # First, delete all objects in the bucket
            response = self.aws_client.list_objects_v2(Bucket=bucket_name)
            if 'Contents' in response:
                for obj in response['Contents']:
                    self.aws_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                self.logger.debug(f"All objects in bucket '{bucket_name}' deleted.")
            # Now, delete the bucket
            with self.lock:
                self.aws_client.delete_bucket(Bucket=bucket_name)
            self.logger.info(f"S3 bucket '{bucket_name}' deleted successfully.")
            return True
        except self.aws_client.exceptions.NoSuchBucket:
            self.logger.warning(f"S3 bucket '{bucket_name}' does not exist.")
            return True
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when deleting S3 bucket '{bucket_name}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error when deleting S3 bucket '{bucket_name}': {e}", exc_info=True)
            return False

    def list_objects_in_bucket(self, bucket_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all objects in a specified S3 bucket.
        
        Args:
            bucket_name (str): The name of the S3 bucket.
        
        Returns:
            Optional[List[Dict[str, Any]]]: A list of objects with their details, or None if failed.
        """
        try:
            self.logger.debug(f"Listing objects in S3 bucket '{bucket_name}'.")
            response = self.aws_client.list_objects_v2(Bucket=bucket_name)
            objects = response.get('Contents', [])
            self.logger.info(f"Retrieved {len(objects)} objects from S3 bucket '{bucket_name}'.")
            return objects
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when listing objects in S3 bucket '{bucket_name}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when listing objects in S3 bucket '{bucket_name}': {e}", exc_info=True)
            return None

    def create_ec2_instance(self, instance_type: str = 't2.micro', ami_id: Optional[str] = None, key_name: Optional[str] = None, security_group_ids: Optional[List[str]] = None, subnet_id: Optional[str] = None) -> Optional[str]:
        """
        Creates an EC2 instance with the specified parameters.
        
        Args:
            instance_type (str, optional): The type of instance to create. Defaults to 't2.micro'.
            ami_id (Optional[str], optional): The AMI ID to use for the instance. Defaults to None.
            key_name (Optional[str], optional): The name of the key pair for SSH access. Defaults to None.
            security_group_ids (Optional[List[str]], optional): List of security group IDs. Defaults to None.
            subnet_id (Optional[str], optional): The subnet ID to launch the instance in. Defaults to None.
        
        Returns:
            Optional[str]: The Instance ID of the created EC2 instance, or None if failed.
        """
        try:
            self.logger.debug(f"Creating EC2 instance with type '{instance_type}', AMI '{ami_id}', Key Name '{key_name}', Security Groups '{security_group_ids}', Subnet '{subnet_id}'.")
            ec2_client = self._initialize_ec2_client()
            response = ec2_client.run_instances(
                ImageId=ami_id,
                InstanceType=instance_type,
                KeyName=key_name,
                SecurityGroupIds=security_group_ids,
                SubnetId=subnet_id,
                MinCount=1,
                MaxCount=1
            )
            instance_id = response['Instances'][0]['InstanceId']
            self.logger.info(f"EC2 instance '{instance_id}' created successfully.")
            return instance_id
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when creating EC2 instance: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when creating EC2 instance: {e}", exc_info=True)
            return None

    def _initialize_ec2_client(self) -> boto3.client:
        """
        Initializes the EC2 client using the existing AWS session.
        
        Returns:
            boto3.client: The initialized EC2 client.
        """
        try:
            self.logger.debug("Initializing EC2 client.")
            ec2_client = self.aws_client.meta.client
            self.logger.debug("EC2 client initialized successfully.")
            return ec2_client
        except Exception as e:
            self.logger.error(f"Error initializing EC2 client: {e}", exc_info=True)
            raise CloudServiceError(f"Error initializing EC2 client: {e}")

    def terminate_ec2_instance(self, instance_id: str) -> bool:
        """
        Terminates an EC2 instance with the specified Instance ID.
        
        Args:
            instance_id (str): The Instance ID of the EC2 instance to terminate.
        
        Returns:
            bool: True if the instance is terminated successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Terminating EC2 instance '{instance_id}'.")
            ec2_client = self._initialize_ec2_client()
            ec2_client.terminate_instances(InstanceIds=[instance_id])
            self.logger.info(f"EC2 instance '{instance_id}' terminated successfully.")
            return True
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when terminating EC2 instance '{instance_id}': {e}", exc_info=True)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error when terminating EC2 instance '{instance_id}': {e}", exc_info=True)
            return False

    def monitor_ec2_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Monitors the status of an EC2 instance.
        
        Args:
            instance_id (str): The Instance ID of the EC2 instance to monitor.
        
        Returns:
            Optional[Dict[str, Any]]: A dictionary containing instance status details, or None if failed.
        """
        try:
            self.logger.debug(f"Monitoring EC2 instance '{instance_id}'.")
            ec2_client = self._initialize_ec2_client()
            response = ec2_client.describe_instance_status(InstanceIds=[instance_id])
            statuses = response.get('InstanceStatuses', [])
            if not statuses:
                self.logger.warning(f"No status information found for EC2 instance '{instance_id}'. It might be stopped or terminated.")
                return None
            status = statuses[0]
            self.logger.info(f"EC2 instance '{instance_id}' status: {status['InstanceState']['Name']}")
            return status
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when monitoring EC2 instance '{instance_id}': {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when monitoring EC2 instance '{instance_id}': {e}", exc_info=True)
            return None

    def list_ec2_instances(self) -> Optional[List[Dict[str, Any]]]:
        """
        Lists all EC2 instances in the AWS account.
        
        Returns:
            Optional[List[Dict[str, Any]]]: A list of EC2 instances with their details, or None if failed.
        """
        try:
            self.logger.debug("Listing all EC2 instances.")
            ec2_client = self._initialize_ec2_client()
            response = ec2_client.describe_instances()
            reservations = response.get('Reservations', [])
            instances = []
            for reservation in reservations:
                instances.extend(reservation.get('Instances', []))
            self.logger.info(f"Retrieved {len(instances)} EC2 instances.")
            return instances
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when listing EC2 instances: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when listing EC2 instances: {e}", exc_info=True)
            return None

    def list_available_regions(self) -> Optional[List[str]]:
        """
        Lists all available AWS regions.
        
        Returns:
            Optional[List[str]]: A list of AWS region names, or None if failed.
        """
        try:
            self.logger.debug("Listing all available AWS regions.")
            ec2_client = boto3.client('ec2')
            response = ec2_client.describe_regions(AllRegions=True)
            regions = [region['RegionName'] for region in response.get('Regions', [])]
            self.logger.info(f"Retrieved {len(regions)} AWS regions.")
            return regions
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"ClientError when listing AWS regions: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error when listing AWS regions: {e}", exc_info=True)
            return None

    def provision_resources(self, resource_type: str, configuration: Dict[str, Any]) -> Optional[str]:
        """
        Provisions a cloud resource based on the specified type and configuration.
        
        Args:
            resource_type (str): The type of resource to provision (e.g., 'ec2', 's3', 'rds').
            configuration (Dict[str, Any]): The configuration parameters for the resource.
        
        Returns:
            Optional[str]: The identifier of the provisioned resource, or None if failed.
        """
        try:
            self.logger.debug(f"Provisioning cloud resource of type '{resource_type}' with configuration {configuration}.")
            if resource_type.lower() == 'ec2':
                instance_id = self.create_ec2_instance(
                    instance_type=configuration.get('InstanceType', 't2.micro'),
                    ami_id=configuration.get('AmiId'),
                    key_name=configuration.get('KeyName'),
                    security_group_ids=configuration.get('SecurityGroupIds'),
                    subnet_id=configuration.get('SubnetId')
                )
                return instance_id
            elif resource_type.lower() == 's3':
                bucket_name = configuration.get('BucketName')
                region = configuration.get('Region')
                success = self.create_s3_bucket(bucket_name, region)
                return bucket_name if success else None
            # Add more resource types as needed
            else:
                self.logger.error(f"Unsupported resource type '{resource_type}'.")
                return None
        except Exception as e:
            self.logger.error(f"Error provisioning cloud resource '{resource_type}': {e}", exc_info=True)
            return None
