# tests/test_agents.py

"""
Unit Tests for Agents Module

This module contains comprehensive unit tests for the Agents service,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
from unittest.mock import MagicMock, patch
from modules.agent.agent_manager import AgentManager, AgentError
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from data.databases.vector_db import VectorDatabase, VectorDatabaseError
from data.shared_memory.shared_data_structures import SharedMemoryManager
from data.databases.time_series_db import TimeSeriesDatabase

class TestAgentsService:
    """
    Test Suite for the Agents Service
    """

    @pytest.fixture(scope="class")
    def agents_service(self, config_loader, encryption_manager):
        """
        Fixture to initialize the Agents service with mocked dependencies.
        """
        with patch('modules.agents.agents.VectorDatabase') as mock_vector_db, \
             patch('modules.agents.agents.SharedMemoryManager') as mock_shared_memory, \
             patch('modules.agents.agents.TimeSeriesDatabase') as mock_time_series_db:
            
            # Mock database instances
            mock_vector_instance = MagicMock(spec=VectorDatabase)
            mock_shared_instance = MagicMock(spec=SharedMemoryManager)
            mock_time_series_instance = MagicMock(spec=TimeSeriesDatabase)
            mock_vector_db.return_value = mock_vector_instance
            mock_shared_memory.return_value = mock_shared_instance
            mock_time_series_db.return_value = mock_time_series_instance
            
            # Initialize Agents service
            agents = AgentManager()
            yield agents
            
            # Teardown if necessary
            agents.close()

    def test_initialization(self, agents_service):
        """
        Test that the Agents service initializes correctly with all dependencies.
        """
        assert agents_service.vector_db is not None
        assert agents_service.shared_memory is not None
        assert agents_service.time_series_db is not None
        assert len(agents_service.agents) == 0  # Initially, no agents

    def test_add_agent(self, agents_service):
        """
        Test adding a new agent to the Agents service.
        """
        agent_id = "agent_01"
        agent_role = "data_processing"
        agents_service.add_agent(agent_id, agent_role)
        
        assert agent_id in agents_service.agents
        assert isinstance(agents_service.agents[agent_id], AgentManager)
        assert agents_service.agents[agent_id].role == agent_role

    def test_remove_agent(self, agents_service):
        """
        Test removing an existing agent from the Agents service.
        """
        agent_id = "agent_02"
        agent_role = "model_training"
        agents_service.add_agent(agent_id, agent_role)
        assert agent_id in agents_service.agents
        
        agents_service.remove_agent(agent_id)
        assert agent_id not in agents_service.agents

    def test_assign_task_to_agent_success(self, agents_service):
        """
        Test assigning a task to an available agent successfully.
        """
        agent_id = "agent_03"
        agent_role = "user_interaction"
        task = {"task_id": "task_001", "type": "handle_user_query", "data": {"query": "What is AI?"}}
        
        agents_service.add_agent(agent_id, "user_interaction")
        agents_service.assign_task(agent_id, task)
        
        agents_service.agents[agent_id].execute_task.assert_called_with(task)

    def test_assign_task_to_nonexistent_agent(self, agents_service):
        """
        Test assigning a task to a non-existent agent raises an error.
        """
        agent_id = "agent_99"
        task = {"task_id": "task_002", "type": "unknown_task", "data": {}}
        
        with pytest.raises(AgentError) as exc_info:
            agents_service.assign_task(agent_id, task)
        
        assert f"Agent '{agent_id}' does not exist." in str(exc_info.value)

    def test_agent_task_execution_failure(self, agents_service):
        """
        Test that a failure in agent task execution is handled gracefully.
        """
        agent_id = "agent_04"
        agent_role = "model_training"
        task = {"task_id": "task_003", "type": "train_model", "data": {"model_type": "gpt-4"}}
        
        agents_service.add_agent(agent_id, "model_training")
        agents_service.agents[agent_id].execute_task.side_effect = AgentError("Training failed due to insufficient data.")
        
        with pytest.raises(AgentError) as exc_info:
            agents_service.assign_task(agent_id, task)
        
        assert f"Agent '{agent_id}' failed to execute task: Training failed due to insufficient data." in str(exc_info.value)

    def test_concurrent_task_assignments(self, agents_service):
        """
        Test assigning multiple tasks concurrently to ensure thread safety and proper handling.
        """
        agent_id_1 = "agent_05"
        agent_id_2 = "agent_06"
        task_1 = {"task_id": "task_004", "type": "data_cleanup", "data": {"dataset": "dataset_1"}}
        task_2 = {"task_id": "task_005", "type": "data_analysis", "data": {"dataset": "dataset_2"}}
        
        agents_service.add_agent(agent_id_1, "data_cleanup")
        agents_service.add_agent(agent_id_2, "data_analysis")
        
        agents_service.assign_task(agent_id_1, task_1)
        agents_service.assign_task(agent_id_2, task_2)
        
        agents_service.agents[agent_id_1].execute_task.assert_called_with(task_1)
        agents_service.agents[agent_id_2].execute_task.assert_called_with(task_2)

    def test_logging_of_agent_tasks(self, agents_service):
        """
        Test that agent task assignments and completions are logged correctly.
        """
        agent_id = "agent_07"
        agent_role = "content_generation"
        task = {"task_id": "task_006", "type": "generate_content", "data": {"topic": "Machine Learning"}}
        
        agents_service.add_agent(agent_id, "content_generation")
        agents_service.assign_task(agent_id, task)
        
        agents_service.time_series_db.log_event.assert_called_with(
            event_type='agent_task_assignment',
            details={
                'agent_id': agent_id,
                'task_id': task['task_id'],
                'task_type': task['type'],
                'status': 'assigned'
            }
        )
        
        agents_service.agents[agent_id].execute_task.return_value = {"status": "completed"}
        agents_service.agents[agent_id].execute_task(task)
        
        agents_service.time_series_db.log_event.assert_called_with(
            event_type='agent_task_completion',
            details={
                'agent_id': agent_id,
                'task_id': task['task_id'],
                'task_type': task['type'],
                'status': 'completed'
            }
        )

    def test_dispose_method(self, agents_service):
        """
        Test that the dispose method correctly closes all integrated services.
        """
        agents_service.vector_db.close = MagicMock()
        agents_service.shared_memory.close = MagicMock()
        agents_service.time_series_db.close = MagicMock()
        agents_service.agents.clear = MagicMock()
        
        # Call dispose
        agents_service.dispose()
        
        # Assert that dispose was called for all services
        agents_service.vector_db.close.assert_called_once()
        agents_service.shared_memory.close.assert_called_once()
        agents_service.time_series_db.close.assert_called_once()
        agents_service.agents.clear.assert_called_once()
