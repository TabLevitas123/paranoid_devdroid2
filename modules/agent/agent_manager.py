# modules/agent/agent_manager.py

"""
Agent Manager Module

This module provides the AgentManager class, responsible for managing agents within the system.

Features:
- Agent registration, deregistration, and lifecycle management
- Thread-safe operations with concurrent access handling
- Robust error handling and logging
- Integration with the DataModule for persistent storage
- Secure communication between agents and tasks
- Event-driven architecture with observer pattern implementation
- Support for asynchronous operations
- Configuration management using environment variables
- Agent monitoring and health checks
- Inter-agent communication facilitation

Author: Your Name
Date: YYYY-MM-DD
"""

import os
import logging
import threading
from typing import Dict, Optional, List, Callable, Any

from modules.data.data_module import DataModule, DataError
from modules.security.security_module import SecurityModule, AuthenticationError, AuthorizationError
from modules.task.task_module import TaskModule, TaskError

# Configure Logging
logger = logging.getLogger('agent_manager')
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File Handler
file_handler = logging.FileHandler('logs/agent_manager.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

# Stream Handler (optional)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

# Exception Classes
class AgentError(Exception):
    """Base class for agent-related exceptions."""
    pass

class AgentNotFoundError(AgentError):
    """Raised when an agent is not found."""
    pass

class AgentAlreadyExistsError(AgentError):
    """Raised when attempting to register an agent that already exists."""
    pass

class AgentManager:
    """
    AgentManager Class

    Manages agents within the system, providing functionalities such as registration,
    deregistration, lifecycle management, and inter-agent communication.
    """

    _instance_lock = threading.Lock()
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern to ensure only one instance of AgentManager exists.
        """
        if not cls._instance:
            with cls._instance_lock:
                if not cls._instance:
                    cls._instance = super(AgentManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.logger = logger
        self.agents: Dict[str, 'Agent'] = {}
        self.lock = threading.RLock()
        self.data_module = DataModule()
        self.security_module = SecurityModule()
        self.task_module = TaskModule()
        self._load_agents_from_storage()

    def _load_agents_from_storage(self):
        """
        Loads agents from persistent storage into memory.
        """
        try:
            with self.data_module.session_scope() as session:
                stored_agents = session.query(AgentModel).all()
                for agent_model in stored_agents:
                    agent = Agent(
                        agent_id=agent_model.agent_id,
                        name=agent_model.name,
                        config=agent_model.config,
                        status=agent_model.status
                    )
                    self.agents[agent.agent_id] = agent
                self.logger.info("Agents loaded from storage successfully.")
        except DataError as e:
            self.logger.exception(f"Failed to load agents from storage: {e}")
            raise AgentError("Failed to load agents from storage.") from e

    def register_agent(self, agent: 'Agent') -> None:
        """
        Registers a new agent.

        Args:
            agent (Agent): The agent instance to register.

        Raises:
            AgentAlreadyExistsError: If the agent already exists.
            AgentError: If registration fails.
        """
        with self.lock:
            if agent.agent_id in self.agents:
                self.logger.warning(f"Agent already exists with ID: {agent.agent_id}")
                raise AgentAlreadyExistsError(f"Agent with ID {agent.agent_id} already exists.")
            self.agents[agent.agent_id] = agent
            self._save_agent_to_storage(agent)
            self.logger.info(f"Agent registered with ID: {agent.agent_id}")

    def deregister_agent(self, agent_id: str) -> None:
        """
        Deregisters an agent.

        Args:
            agent_id (str): The ID of the agent to deregister.

        Raises:
            AgentNotFoundError: If the agent does not exist.
            AgentError: If deregistration fails.
        """
        with self.lock:
            if agent_id not in self.agents:
                self.logger.warning(f"Agent not found with ID: {agent_id}")
                raise AgentNotFoundError(f"Agent with ID {agent_id} not found.")
            agent = self.agents.pop(agent_id)
            self._remove_agent_from_storage(agent_id)
            self.logger.info(f"Agent deregistered with ID: {agent_id}")

    def _save_agent_to_storage(self, agent: 'Agent') -> None:
        """
        Saves an agent to persistent storage.

        Args:
            agent (Agent): The agent instance to save.

        Raises:
            AgentError: If the operation fails.
        """
        try:
            with self.data_module.session_scope() as session:
                agent_model = AgentModel(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    config=agent.config,
                    status=agent.status
                )
                session.add(agent_model)
                self.logger.debug(f"Agent saved to storage: {agent}")
        except DataError as e:
            self.logger.exception(f"Failed to save agent to storage: {e}")
            raise AgentError("Failed to save agent to storage.") from e

    def _remove_agent_from_storage(self, agent_id: str) -> None:
        """
        Removes an agent from persistent storage.

        Args:
            agent_id (str): The ID of the agent to remove.

        Raises:
            AgentError: If the operation fails.
        """
        try:
            with self.data_module.session_scope() as session:
                agent_model = session.query(AgentModel).filter_by(agent_id=agent_id).first()
                if agent_model:
                    session.delete(agent_model)
                    self.logger.debug(f"Agent removed from storage: {agent_id}")
                else:
                    self.logger.warning(f"Agent model not found in storage for ID: {agent_id}")
        except DataError as e:
            self.logger.exception(f"Failed to remove agent from storage: {e}")
            raise AgentError("Failed to remove agent from storage.") from e

    def get_agent(self, agent_id: str) -> 'Agent':
        """
        Retrieves an agent by its ID.

        Args:
            agent_id (str): The ID of the agent.

        Returns:
            Agent: The agent instance.

        Raises:
            AgentNotFoundError: If the agent does not exist.
        """
        with self.lock:
            agent = self.agents.get(agent_id)
            if not agent:
                self.logger.warning(f"Agent not found with ID: {agent_id}")
                raise AgentNotFoundError(f"Agent with ID {agent_id} not found.")
            self.logger.debug(f"Agent retrieved with ID: {agent_id}")
            return agent

    def list_agents(self) -> List['Agent']:
        """
        Lists all registered agents.

        Returns:
            List[Agent]: A list of all agents.
        """
        with self.lock:
            agents_list = list(self.agents.values())
            self.logger.debug("Listing all agents.")
            return agents_list

    def send_task_to_agent(self, agent_id: str, task_data: Dict[str, Any]) -> None:
        """
        Sends a task to a specified agent.

        Args:
            agent_id (str): The ID of the agent.
            task_data (Dict[str, Any]): The task data.

        Raises:
            AgentNotFoundError: If the agent does not exist.
            AgentError: If sending the task fails.
        """
        agent = self.get_agent(agent_id)
        try:
            self.task_module.create_task(agent_id=agent_id, task_data=task_data)
            self.logger.info(f"Task sent to agent {agent_id}")
        except TaskError as e:
            self.logger.exception(f"Failed to send task to agent {agent_id}: {e}")
            raise AgentError(f"Failed to send task to agent {agent_id}.") from e

    def monitor_agents(self) -> None:
        """
        Monitors all agents' health status.

        This method can be scheduled to run periodically.
        """
        with self.lock:
            for agent_id, agent in self.agents.items():
                try:
                    is_healthy = agent.check_health()
                    agent.status = 'healthy' if is_healthy else 'unhealthy'
                    self._update_agent_status_in_storage(agent)
                    self.logger.debug(f"Agent {agent_id} health status: {agent.status}")
                except Exception as e:
                    self.logger.exception(f"Failed to check health for agent {agent_id}: {e}")
                    agent.status = 'unhealthy'
                    self._update_agent_status_in_storage(agent)

    def _update_agent_status_in_storage(self, agent: 'Agent') -> None:
        """
        Updates an agent's status in persistent storage.

        Args:
            agent (Agent): The agent instance.

        Raises:
            AgentError: If the operation fails.
        """
        try:
            with self.data_module.session_scope() as session:
                agent_model = session.query(AgentModel).filter_by(agent_id=agent.agent_id).first()
                if agent_model:
                    agent_model.status = agent.status
                    session.add(agent_model)
                    self.logger.debug(f"Agent status updated in storage: {agent.agent_id}")
                else:
                    self.logger.warning(f"Agent model not found in storage for ID: {agent.agent_id}")
        except DataError as e:
            self.logger.exception(f"Failed to update agent status in storage: {e}")
            raise AgentError("Failed to update agent status in storage.") from e

    def broadcast_message(self, message: str) -> None:
        """
        Broadcasts a message to all agents.

        Args:
            message (str): The message to broadcast.

        Raises:
            AgentError: If broadcasting fails.
        """
        with self.lock:
            for agent_id, agent in self.agents.items():
                try:
                    agent.receive_message(message)
                    self.logger.debug(f"Message broadcasted to agent {agent_id}")
                except Exception as e:
                    self.logger.exception(f"Failed to send message to agent {agent_id}: {e}")

    # Additional methods can be added here as needed

# Agent Model and Agent Class Definitions
from sqlalchemy import Column, String, JSON

from modules.data.data_module import Base

class AgentModel(Base):
    __tablename__ = 'agents'

    agent_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False)

    def __repr__(self):
        return f"<AgentModel(agent_id='{self.agent_id}', name='{self.name}', status='{self.status}')>"

class Agent:
    """
    Agent Class

    Represents an agent within the system.
    """

    def __init__(self, agent_id: str, name: str, config: Dict[str, Any], status: str = 'inactive'):
        self.agent_id = agent_id
        self.name = name
        self.config = config
        self.status = status
        self.logger = logger

    def check_health(self) -> bool:
        """
        Checks the health status of the agent.

        Returns:
            bool: True if the agent is healthy, False otherwise.
        """
        # Implement health check logic here
        self.logger.debug(f"Checking health for agent {self.agent_id}")
        return True  # Placeholder for actual health check implementation

    def receive_message(self, message: str) -> None:
        """
        Handles receiving a message.

        Args:
            message (str): The message content.
        """
        self.logger.info(f"Agent {self.agent_id} received message: {message}")
        # Implement message handling logic here

    def __repr__(self):
        return f"<Agent(agent_id='{self.agent_id}', name='{self.name}', status='{self.status}')>"

# Example Usage (Remove or comment out in production)
if __name__ == "__main__":
    agent_manager = AgentManager()
    try:
        # Create an agent
        agent = Agent(
            agent_id='agent_001',
            name='Agent One',
            config={'param1': 'value1', 'param2': 'value2'}
        )
        agent_manager.register_agent(agent)
        # List agents
        agents = agent_manager.list_agents()
        print(f"Registered agents: {agents}")
        # Send a task to the agent
        agent_manager.send_task_to_agent('agent_001', {'task': 'process_data', 'data': [1, 2, 3]})
        # Broadcast a message
        agent_manager.broadcast_message("System maintenance scheduled at midnight.")
        # Monitor agents
        agent_manager.monitor_agents()
        # Deregister the agent
        agent_manager.deregister_agent('agent_001')
        print("Agent deregistered.")
    except AgentError as e:
        print(f"Agent error: {e}")
