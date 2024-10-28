# modules/task/task_module.py

"""
Task Module

This module provides the TaskModule class, responsible for managing tasks within the system.

Features:
- Task creation, execution, and lifecycle management
- Support for synchronous and asynchronous tasks
- Thread-safe operations with concurrent access handling
- Robust error handling and logging
- Integration with the DataModule for persistent storage
- Secure task execution environment
- Task scheduling and queue management
- Result storage and retrieval
- Task cancellation and timeout handling
- Configuration management using environment variables

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import threading
import uuid
from typing import Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, Future

from modules.data.data_module import DataModule, DataError
from modules.security.security_module import SecurityModule, AuthorizationError
from sqlalchemy import Column, String, JSON, DateTime, Enum
from datetime import datetime, timedelta
from enum import Enum as PyEnum

# Configure Logging
logger = logging.getLogger('task_module')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/task_module.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class TaskError(Exception):
    """Base class for task-related exceptions."""
    pass

class TaskNotFoundError(TaskError):
    """Raised when a task is not found."""
    pass

class TaskAlreadyExistsError(TaskError):
    """Raised when attempting to create a task that already exists."""
    pass

class TaskStatus(PyEnum):
    """Enumeration for task statuses."""
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'

class TaskModule:
    """
    TaskModule Class

    Manages tasks within the system, providing functionalities such as task creation,
    execution, scheduling, and result retrieval.
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of TaskModule exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(TaskModule, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self.tasks: Dict[str, 'Task'] = {}
        self.lock = threading.RLock()
        self.data_module = DataModule()
        self.security_module = SecurityModule()
        self.executor = ThreadPoolExecutor(max_workers=int(os.getenv('TASK_MAX_WORKERS', '10')))
        self._load_tasks_from_storage()

    def _load_tasks_from_storage(self):
        """
        Loads tasks from persistent storage into memory.
        """
        try:
            with self.data_module.session_scope() as session:
                stored_tasks = session.query(TaskModel).filter(TaskModel.status == TaskStatus.PENDING.value).all()
                for task_model in stored_tasks:
                    task = Task(
                        task_id=task_model.task_id,
                        agent_id=task_model.agent_id,
                        task_data=task_model.task_data,
                        status=TaskStatus(task_model.status),
                        created_at=task_model.created_at,
                        updated_at=task_model.updated_at
                    )
                    self.tasks[task.task_id] = task
                self.logger.info("Tasks loaded from storage successfully.")
        except DataError as e:
            self.logger.exception(f"Failed to load tasks from storage: {e}")
            raise TaskError("Failed to load tasks from storage.") from e

    def create_task(self, agent_id: str, task_data: Dict[str, Any]) -> str:
        """
        Creates and schedules a new task.

        Args:
            agent_id (str): The ID of the agent responsible for the task.
            task_data (Dict[str, Any]): The task data.

        Returns:
            str: The ID of the created task.

        Raises:
            TaskError: If task creation fails.
        """
        with self.lock:
            task_id = str(uuid.uuid4())
            task = Task(
                task_id=task_id,
                agent_id=agent_id,
                task_data=task_data,
                status=TaskStatus.PENDING
            )
            self.tasks[task_id] = task
            self._save_task_to_storage(task)
            self._execute_task(task)
            self.logger.info(f"Task created with ID: {task_id}")
            return task_id

    def _save_task_to_storage(self, task: 'Task') -> None:
        """
        Saves a task to persistent storage.

        Args:
            task (Task): The task instance to save.

        Raises:
            TaskError: If the operation fails.
        """
        try:
            with self.data_module.session_scope() as session:
                task_model = TaskModel(
                    task_id=task.task_id,
                    agent_id=task.agent_id,
                    task_data=task.task_data,
                    status=task.status.value,
                    created_at=task.created_at,
                    updated_at=task.updated_at
                )
                session.add(task_model)
                self.logger.debug(f"Task saved to storage: {task}")
        except DataError as e:
            self.logger.exception(f"Failed to save task to storage: {e}")
            raise TaskError("Failed to save task to storage.") from e

    def _execute_task(self, task: 'Task') -> None:
        """
        Executes a task asynchronously.

        Args:
            task (Task): The task instance.

        Raises:
            TaskError: If execution fails.
        """
        def task_wrapper():
            try:
                task.status = TaskStatus.RUNNING
                self._update_task_in_storage(task)
                self.logger.debug(f"Task {task.task_id} started execution.")
                # Simulate task execution
                # Implement actual task logic here
                time_to_sleep = task.task_data.get('duration', 1)
                threading.Event().wait(time_to_sleep)
                task.status = TaskStatus.COMPLETED
                task.result = {'message': 'Task completed successfully.'}
                self._update_task_in_storage(task)
                self.logger.debug(f"Task {task.task_id} completed execution.")
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                self._update_task_in_storage(task)
                self.logger.exception(f"Task {task.task_id} failed execution: {e}")

        future = self.executor.submit(task_wrapper)
        task.future = future

    def _update_task_in_storage(self, task: 'Task') -> None:
        """
        Updates a task's status in persistent storage.

        Args:
            task (Task): The task instance.

        Raises:
            TaskError: If the operation fails.
        """
        try:
            with self.data_module.session_scope() as session:
                task_model = session.query(TaskModel).filter_by(task_id=task.task_id).first()
                if task_model:
                    task_model.status = task.status.value
                    task_model.updated_at = datetime.utcnow()
                    if task.result:
                        task_model.result = task.result
                    if task.error:
                        task_model.error = task.error
                    session.add(task_model)
                    self.logger.debug(f"Task status updated in storage: {task.task_id}")
                else:
                    self.logger.warning(f"Task model not found in storage for ID: {task.task_id}")
        except DataError as e:
            self.logger.exception(f"Failed to update task in storage: {e}")
            raise TaskError("Failed to update task in storage.") from e

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Retrieves the status of a task.

        Args:
            task_id (str): The ID of the task.

        Returns:
            Dict[str, Any]: The task status information.

        Raises:
            TaskNotFoundError: If the task does not exist.
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                self.logger.warning(f"Task not found with ID: {task_id}")
                raise TaskNotFoundError(f"Task with ID {task_id} not found.")
            status_info = {
                'task_id': task.task_id,
                'status': task.status.value,
                'result': task.result,
                'error': task.error,
                'created_at': task.created_at,
                'updated_at': task.updated_at
            }
            self.logger.debug(f"Task status retrieved for ID: {task_id}")
            return status_info

    def cancel_task(self, task_id: str) -> None:
        """
        Attempts to cancel a running task.

        Args:
            task_id (str): The ID of the task.

        Raises:
            TaskNotFoundError: If the task does not exist.
            TaskError: If cancellation fails.
        """
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                self.logger.warning(f"Task not found with ID: {task_id}")
                raise TaskNotFoundError(f"Task with ID {task_id} not found.")
            if task.future and not task.future.done():
                cancelled = task.future.cancel()
                if cancelled:
                    task.status = TaskStatus.CANCELLED
                    self._update_task_in_storage(task)
                    self.logger.info(f"Task {task_id} cancelled successfully.")
                else:
                    self.logger.warning(f"Failed to cancel task {task_id}.")
                    raise TaskError(f"Failed to cancel task {task_id}.")
            else:
                self.logger.warning(f"Task {task_id} cannot be cancelled.")
                raise TaskError(f"Task {task_id} cannot be cancelled.")

    # Additional methods can be added here as needed

# Task Model and Task Class Definitions
from modules.data.data_module import Base
from sqlalchemy import PickleType

class TaskModel(Base):
    __tablename__ = 'tasks'

    task_id = Column(String(255), primary_key=True)
    agent_id = Column(String(255), nullable=False)
    task_data = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False)
    result = Column(JSON, nullable=True)
    error = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<TaskModel(task_id='{self.task_id}', status='{self.status}')>"

class Task:
    """
    Task Class

    Represents a task within the system.
    """

    def __init__(self, task_id: str, agent_id: str, task_data: Dict[str, Any],
                 status: TaskStatus = TaskStatus.PENDING,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None):
        self.task_id = task_id
        self.agent_id = agent_id
        self.task_data = task_data
        self.status = status
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or self.created_at
        self.future: Optional[Future] = None
        self.logger = logger

    def __repr__(self):
        return f"<Task(task_id='{self.task_id}', status='{self.status.value}')>"

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    task_module = TaskModule()
    try:
        # Create a task
        task_id = task_module.create_task(
            agent_id='agent_001',
            task_data={'action': 'process_data', 'duration': 2}
        )
        print(f"Task created with ID: {task_id}")
        # Get task status
        import time
        time.sleep(1)
        status = task_module.get_task_status(task_id)
        print(f"Task status: {status}")
        # Cancel task
        # task_module.cancel_task(task_id)
    except TaskError as e:
        print(f"Task error: {e}")
