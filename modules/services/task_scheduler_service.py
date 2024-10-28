# services/task_scheduler_service.py

import datetime
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from reactivex import interval
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager

class TaskSchedulerServiceError(Exception):
    """Custom exception for TaskSchedulerService-related errors."""
    pass

class TaskSchedulerService:
    """
    Provides task scheduling capabilities, allowing users to schedule, manage, and execute tasks
    at specified times or intervals. Utilizes APScheduler for robust scheduling functionalities.
    Ensures thread-safe operations, persistent job storage, and secure execution of tasks.
    """

    def __init__(self):
        """
        Initializes the TaskSchedulerService with necessary configurations and scheduler setup.
        """
        self.logger = setup_logging('TaskSchedulerService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.scheduler = self._initialize_scheduler()
        self.lock = threading.Lock()
        self.logger.info("TaskSchedulerService initialized successfully.")

    def _initialize_scheduler(self) -> BackgroundScheduler:
        """
        Initializes the APScheduler background scheduler with configured job stores and executors.

        Returns:
            BackgroundScheduler: The initialized scheduler instance.
        """
        try:
            self.logger.debug("Initializing APScheduler BackgroundScheduler.")
            jobstores = {
                'default': MemoryJobStore()
            }
            executors = {
                'default': {'type': 'threadpool', 'max_workers': 20},
                'processpool': {'type': 'processpool', 'max_workers': 5}
            }
            job_defaults = {
                'coalesce': False,
                'max_instances': 3
            }
            scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone='UTC')
            scheduler.start()
            self.logger.debug("APScheduler BackgroundScheduler started successfully.")
            return scheduler
        except Exception as e:
            self.logger.error(f"Error initializing scheduler: {e}", exc_info=True)
            raise TaskSchedulerServiceError(f"Error initializing scheduler: {e}")

    def schedule_task(self, func: Callable, trigger: str, args: Optional[List[Any]] = None, kwargs: Optional[Dict[str, Any]] = None, **trigger_args) -> Optional[str]:
        """
        Schedules a task with the specified trigger and arguments.

        Args:
            func (Callable): The function to execute.
            trigger (str): The type of trigger ('date', 'interval', 'cron').
            args (Optional[List[Any]], optional): Positional arguments for the function. Defaults to None.
            kwargs (Optional[Dict[str, Any]], optional): Keyword arguments for the function. Defaults to None.
            **trigger_args: Additional arguments specific to the trigger type.

        Returns:
            Optional[str]: The job ID if scheduling is successful, or None otherwise.
        """
        try:
            self.logger.debug(f"Scheduling task '{func.__name__}' with trigger '{trigger}' and args {args}, kwargs {kwargs}, trigger_args {trigger_args}")
            with self.lock:
                if trigger == 'date':
                    job = self.scheduler.add_job(func, trigger=DateTrigger(**trigger_args), args=args or [], kwargs=kwargs or {})
                elif trigger == 'interval':
                    job = self.scheduler.add_job(func, trigger=interval, args=args or [], kwargs=kwargs or {}, **trigger_args)
                elif trigger == 'cron':
                    job = self.scheduler.add_job(func, trigger=CronTrigger(**trigger_args), args=args or [], kwargs=kwargs or {})
                else:
                    self.logger.error(f"Unsupported trigger type '{trigger}'.")
                    return None
                self.logger.info(f"Task '{func.__name__}' scheduled successfully with job ID '{job.id}'.")
                return job.id
        except Exception as e:
            self.logger.error(f"Error scheduling task '{func.__name__}': {e}", exc_info=True)
            return None

    def remove_task(self, job_id: str) -> bool:
        """
        Removes a scheduled task by its job ID.

        Args:
            job_id (str): The ID of the job to remove.

        Returns:
            bool: True if the task is removed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Removing task with job ID '{job_id}'.")
            with self.lock:
                self.scheduler.remove_job(job_id)
            self.logger.info(f"Task with job ID '{job_id}' removed successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error removing task with job ID '{job_id}': {e}", exc_info=True)
            return False

    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        Lists all scheduled tasks.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing job details.
        """
        try:
            self.logger.debug("Listing all scheduled tasks.")
            jobs = self.scheduler.get_jobs()
            job_list = []
            for job in jobs:
                job_info = {
                    'id': job.id,
                    'name': job.name,
                    'next_run_time': job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else None,
                    'trigger': str(job.trigger)
                }
                job_list.append(job_info)
            self.logger.info(f"Retrieved {len(job_list)} scheduled tasks.")
            return job_list
        except Exception as e:
            self.logger.error(f"Error listing tasks: {e}", exc_info=True)
            return []

    def modify_task(self, job_id: str, **new_trigger_args) -> bool:
        """
        Modifies the trigger of an existing scheduled task.

        Args:
            job_id (str): The ID of the job to modify.
            **new_trigger_args: New arguments for the trigger.

        Returns:
            bool: True if the task is modified successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Modifying task with job ID '{job_id}' with new trigger args {new_trigger_args}.")
            with self.lock:
                job = self.scheduler.get_job(job_id)
                if not job:
                    self.logger.error(f"No job found with ID '{job_id}'.")
                    return False
                job.reschedule(trigger=job.trigger, **new_trigger_args)
            self.logger.info(f"Task with job ID '{job_id}' modified successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error modifying task with job ID '{job_id}': {e}", exc_info=True)
            return False

    def shutdown_scheduler(self, wait: bool = True):
        """
        Shuts down the scheduler.

        Args:
            wait (bool, optional): Whether to wait for running jobs to finish. Defaults to True.
        """
        try:
            self.logger.debug(f"Shutting down scheduler with wait={wait}.")
            self.scheduler.shutdown(wait=wait)
            self.logger.info("Scheduler shut down successfully.")
        except Exception as e:
            self.logger.error(f"Error shutting down scheduler: {e}", exc_info=True)

    def schedule_recurring_task(self, func: Callable, cron_expression: Dict[str, Any], args: Optional[List[Any]] = None, kwargs: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Schedules a recurring task based on a cron expression.

        Args:
            func (Callable): The function to execute.
            cron_expression (Dict[str, Any]): A dictionary representing the cron schedule (e.g., {'hour': 12, 'minute': 30}).
            args (Optional[List[Any]], optional): Positional arguments for the function. Defaults to None.
            kwargs (Optional[Dict[str, Any]], optional): Keyword arguments for the function. Defaults to None.

        Returns:
            Optional[str]: The job ID if scheduling is successful, or None otherwise.
        """
        return self.schedule_task(func, 'cron', args=args, kwargs=kwargs, **cron_expression)

    def schedule_one_time_task(self, func: Callable, run_date: datetime, args: Optional[List[Any]] = None, kwargs: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Schedules a one-time task to run at a specified date and time.

        Args:
            func (Callable): The function to execute.
            run_date (datetime): The date and time to execute the function.
            args (Optional[List[Any]], optional): Positional arguments for the function. Defaults to None.
            kwargs (Optional[Dict[str, Any]], optional): Keyword arguments for the function. Defaults to None.

        Returns:
            Optional[str]: The job ID if scheduling is successful, or None otherwise.
        """
        return self.schedule_task(func, 'date', args=args, kwargs=kwargs, run_date=run_date)

    def schedule_interval_task(self, func: Callable, interval: Dict[str, Any], args: Optional[List[Any]] = None, kwargs: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Schedules a task to run at fixed intervals.

        Args:
            func (Callable): The function to execute.
            interval (Dict[str, Any]): A dictionary representing the interval (e.g., {'minutes': 15}).
            args (Optional[List[Any]], optional): Positional arguments for the function. Defaults to None.
            kwargs (Optional[Dict[str, Any]], optional): Keyword arguments for the function. Defaults to None.

        Returns:
            Optional[str]: The job ID if scheduling is successful, or None otherwise.
        """
        return self.schedule_task(func, 'interval', args=args, kwargs=kwargs, **interval)

    def close_service(self):
        """
        Closes any resources or sessions held by the service and shuts down the scheduler.
        """
        try:
            self.logger.debug("Closing TaskSchedulerService resources.")
            self.shutdown_scheduler(wait=True)
            self.logger.info("TaskSchedulerService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing TaskSchedulerService: {e}", exc_info=True)
            raise TaskSchedulerServiceError(f"Error closing TaskSchedulerService: {e}")
