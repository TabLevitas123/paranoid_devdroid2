# security/authorization.py

import logging
from functools import wraps
import threading
from modules.utilities.logging_manager import setup_logging
from modules.security.authentication import AuthenticationManager
from modules.security.encryption_manager import EncryptionManager

class AuthorizationError(Exception):
    """Custom exception for authorization failures."""
    pass

class AuthorizationManager:
    """
    Manages user and agent authorization, including role-based access control (RBAC).
    """

    def __init__(self):
        """
        Initializes the AuthorizationManager with necessary configurations.
        """
        self.logger = setup_logging('AuthorizationManager')
        self.auth_manager = AuthenticationManager()
        self.encryption_manager = EncryptionManager()
        self.roles_permissions = self._load_roles_permissions()
        self.lock = threading.Lock()
        self.logger.info("AuthorizationManager initialized successfully.")

    def _load_roles_permissions(self):
        """
        Loads roles and their corresponding permissions from a secure source.
        This example uses a hardcoded dictionary, but in production, it should be
        loaded from a secure database or configuration file.

        Returns:
            dict: A dictionary mapping roles to their permissions.
        """
        try:
            self.logger.debug("Loading roles and permissions.")
            # Example roles and permissions
            roles_permissions = {
                'admin': {
                    'create_user',
                    'delete_user',
                    'modify_user',
                    'view_metrics',
                    'send_notifications',
                    'access_sensitive_data',
                    'rotate_keys',
                    'manage_roles',
                    'view_logs',
                    'configure_system'
                },
                'user': {
                    'view_metrics',
                    'send_notifications',
                    'access_data'
                },
                'guest': {
                    'view_metrics'
                }
            }
            self.logger.debug("Roles and permissions loaded successfully.")
            return roles_permissions
        except Exception as e:
            self.logger.error(f"Error loading roles and permissions: {e}", exc_info=True)
            raise

    def assign_role(self, username, role):
        """
        Assigns a role to a user.

        Args:
            username (str): The username of the user.
            role (str): The role to assign.

        Returns:
            bool: True if role assignment is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Assigning role '{role}' to user '{username}'.")
            with self.lock:
                if role not in self.roles_permissions:
                    self.logger.error(f"Role '{role}' does not exist.")
                    return False
                # In a production environment, update the user's role in the database
                # Here, we assume the AuthenticationManager can handle user roles
                self.auth_manager.user_db[username]['role'] = role
            self.logger.info(f"Role '{role}' assigned to user '{username}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error assigning role '{role}' to user '{username}': {e}", exc_info=True)
            return False

    def check_permission(self, username, permission):
        """
        Checks if a user has a specific permission.

        Args:
            username (str): The username of the user.
            permission (str): The permission to check.

        Returns:
            bool: True if the user has the permission, False otherwise.
        """
        try:
            self.logger.debug(f"Checking if user '{username}' has permission '{permission}'.")
            user = self.auth_manager.user_db.get(username)
            if not user:
                self.logger.warning(f"User '{username}' not found.")
                return False
            role = user.get('role')
            if not role:
                self.logger.warning(f"User '{username}' has no role assigned.")
                return False
            permissions = self.roles_permissions.get(role, set())
            has_permission = permission in permissions
            self.logger.debug(f"User '{username}' has permission '{permission}': {has_permission}")
            return has_permission
        except Exception as e:
            self.logger.error(f"Error checking permission '{permission}' for user '{username}': {e}", exc_info=True)
            return False

    def require_permission(self, permission):
        """
        Decorator to enforce that a user has a specific permission to execute a function.

        Args:
            permission (str): The required permission.

        Returns:
            function: The decorated function.
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    # Assume that the first argument is 'self' and the second is 'username'
                    username = args[1]
                    if not self.check_permission(username, permission):
                        self.logger.warning(f"User '{username}' lacks permission '{permission}' to execute '{func.__name__}'.")
                        raise AuthorizationError(f"User '{username}' does not have permission '{permission}'.")
                    return func(*args, **kwargs)
                except AuthorizationError as ae:
                    self.logger.error(ae)
                    raise
                except Exception as e:
                    self.logger.error(f"Error in authorization decorator: {e}", exc_info=True)
                    raise
            return wrapper
        return decorator

    def add_permission_to_role(self, role, permission):
        """
        Adds a permission to a specific role.

        Args:
            role (str): The role to update.
            permission (str): The permission to add.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.logger.debug(f"Adding permission '{permission}' to role '{role}'.")
            with self.lock:
                if role not in self.roles_permissions:
                    self.logger.error(f"Role '{role}' does not exist.")
                    return False
                self.roles_permissions[role].add(permission)
            self.logger.info(f"Permission '{permission}' added to role '{role}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding permission '{permission}' to role '{role}': {e}", exc_info=True)
            return False

    def remove_permission_from_role(self, role, permission):
        """
        Removes a permission from a specific role.

        Args:
            role (str): The role to update.
            permission (str): The permission to remove.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.logger.debug(f"Removing permission '{permission}' from role '{role}'.")
            with self.lock:
                if role not in self.roles_permissions:
                    self.logger.error(f"Role '{role}' does not exist.")
                    return False
                self.roles_permissions[role].discard(permission)
            self.logger.info(f"Permission '{permission}' removed from role '{role}' successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error removing permission '{permission}' from role '{role}': {e}", exc_info=True)
            return False

    def define_role(self, role, permissions):
        """
        Defines a new role with a set of permissions.

        Args:
            role (str): The name of the role.
            permissions (set): A set of permissions.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.logger.debug(f"Defining new role '{role}' with permissions {permissions}.")
            with self.lock:
                if role in self.roles_permissions:
                    self.logger.error(f"Role '{role}' already exists.")
                    return False
                self.roles_permissions[role] = set(permissions)
            self.logger.info(f"Role '{role}' defined successfully with permissions {permissions}.")
            return True
        except Exception as e:
            self.logger.error(f"Error defining role '{role}': {e}", exc_info=True)
            return False

    def remove_role(self, role):
        """
        Removes an existing role.

        Args:
            role (str): The name of the role to remove.

        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            self.logger.debug(f"Removing role '{role}'.")
            with self.lock:
                if role not in self.roles_permissions:
                    self.logger.error(f"Role '{role}' does not exist.")
                    return False
                del self.roles_permissions[role]
            self.logger.info(f"Role '{role}' removed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error removing role '{role}': {e}", exc_info=True)
            return False

    def list_roles(self):
        """
        Lists all defined roles and their permissions.

        Returns:
            dict: A dictionary of roles and their permissions.
        """
        try:
            self.logger.debug("Listing all roles and permissions.")
            with self.lock:
                roles_copy = {role: perms.copy() for role, perms in self.roles_permissions.items()}
            self.logger.info("Roles and permissions listed successfully.")
            return roles_copy
        except Exception as e:
            self.logger.error(f"Error listing roles and permissions: {e}", exc_info=True)
            return {}
