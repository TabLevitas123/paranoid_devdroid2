# tests/test_marvin_agent.py

"""
Unit Tests for MarvinAgent

This module contains comprehensive unit tests for the MarvinAgent class,
ensuring robust functionality, error handling, and security compliance.
"""

import pytest
import os
import json
from unittest.mock import MagicMock, patch
from marvin.marvin_agent import MarvinAgent, MarvinAgentError, SubAgent
from modules.communication.communication_module import CommunicationModule
from modules.memory.shared_memory import SharedMemory
from modules.security.encryption_manager import EncryptionManager
from modules.machine_learning.ml_module import MachineLearningModule
from marvin.sub_agents.expert_panel import ExpertPanel
from marvin.sub_agents.verifier import Verifier
from marvin.sub_agents.decider import Decider
from marvin.sub_agents.hallucination_monitor import HallucinationMonitor
from modules.services.llm_integration_service import LLMIntegrationService
from modules.utilities.logging_manager import setup_logging

@pytest.fixture
def mock_communication_module():
    with patch('modules.communication.communication_module.CommunicationModule') as mock_comm:
        instance = mock_comm.return_value
        instance.send_message = MagicMock()
        instance.receive_message = MagicMock(return_value={"status": "success"})
        yield instance

@pytest.fixture
def mock_shared_memory():
    with patch('modules.memory.shared_memory.SharedMemory') as mock_shared:
        instance = mock_shared.return_value
        instance.get_data = MagicMock(return_value=None)
        instance.cache_data = MagicMock()
        instance.close = MagicMock()
        yield instance

@pytest.fixture
def mock_encryption_manager():
    with patch('modules.security.encryption_manager.EncryptionManager') as mock_enc:
        instance = mock_enc.return_value
        instance.decrypt_data = MagicMock(return_value=b'secret_key')
        instance.encrypt_data = MagicMock(return_value=b'encrypted_data')
        yield instance

@pytest.fixture
def marvin_agent(mock_communication_module, mock_shared_memory, mock_encryption_manager):
    agent = MarvinAgent()
    agent.initialize(
        communication_module=mock_communication_module,
        shared_memory=mock_shared_memory,
        encryption_manager=mock_encryption_manager
    )
    return agent

@pytest.fixture
def sample_task():
    return {
        "task_id": "task_001",
        "type": "generate_text",
        "prompt": "Once upon a time",
        "model": "gpt-3.5-turbo"
    }

@pytest.fixture
def sample_result():
    return "Once upon a time, in a land far, far away..."

class TestMarvinAgent:
    """
    Test Suite for the MarvinAgent class
    """

    def test_initialization(self, marvin_agent, mock_communication_module, mock_shared_memory, mock_encryption_manager):
        """
        Test that the MarvinAgent initializes correctly with all dependencies.
        """
        assert marvin_agent.communication_module == mock_communication_module
        assert marvin_agent.shared_memory == mock_shared_memory
        assert marvin_agent.encryption_manager == mock_encryption_manager
        assert marvin_agent.ml_module is not None

    def test_save_task_success(self, marvin_agent, sample_task):
        """
        Test saving a task successfully.
        """
        marvin_agent.save_task(sample_task)
        assert marvin_agent.current_task == sample_task
        assert os.path.exists(marvin_agent.task_file)

        with open(marvin_agent.task_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data.get('task') == sample_task

    def test_save_task_failure(self, marvin_agent, sample_task):
        """
        Test handling failure when saving a task.
        """
        with patch('builtins.open', side_effect=IOError("Unable to write to file")):
            with pytest.raises(MarvinAgentError) as exc_info:
                marvin_agent.save_task(sample_task)
            assert "Failed to save task" in str(exc_info.value)

    def test_get_current_task_in_memory(self, marvin_agent, sample_task):
        """
        Test retrieving the current task from memory.
        """
        marvin_agent.current_task = sample_task
        task = marvin_agent.get_current_task()
        assert task == sample_task

    def test_get_current_task_from_file(self, marvin_agent, sample_task):
        """
        Test retrieving the current task from file when not in memory.
        """
        marvin_agent.current_task = None
        marvin_agent.save_task(sample_task)
        marvin_agent.current_task = None  # Clear in-memory task
        task = marvin_agent.get_current_task()
        assert task == sample_task

    def test_get_current_task_failure(self, marvin_agent):
        """
        Test handling failure when loading a task from file.
        """
        marvin_agent.current_task = None
        if os.path.exists(marvin_agent.task_file):
            os.remove(marvin_agent.task_file)
        with patch('builtins.open', side_effect=IOError("Unable to read file")):
            with pytest.raises(MarvinAgentError) as exc_info:
                marvin_agent.get_current_task()
            assert "Failed to load task" in str(exc_info.value)

    def test_clear_current_task(self, marvin_agent, sample_task):
        """
        Test clearing the current task.
        """
        marvin_agent.save_task(sample_task)
        marvin_agent.clear_current_task()
        assert marvin_agent.current_task is None
        assert not os.path.exists(marvin_agent.task_file)

    def test_process_task_no_task(self, marvin_agent):
        """
        Test processing when there is no task.
        """
        marvin_agent.current_task = None
        marvin_agent.clear_current_task()
        with patch.object(marvin_agent, 'logger') as mock_logger:
            marvin_agent.process_task()
            mock_logger.warning.assert_called_with("No task to process.")

    def test_process_task_success(self, marvin_agent, sample_task, sample_result):
        """
        Test successful processing of a task.
        """
        marvin_agent.save_task(sample_task)

        # Mock sub-agent creation and task execution
        with patch.object(SubAgent, 'perform_task', return_value=sample_result) as mock_perform_task, \
             patch.object(Verifier, 'verify', return_value=[sample_result]) as mock_verify, \
             patch.object(Decider, 'decide', return_value=sample_result) as mock_decide, \
             patch.object(HallucinationMonitor, 'detect', return_value=False) as mock_detect, \
             patch.object(LLMIntegrationService, 'generate_text', return_value=sample_result) as mock_generate_text, \
             patch.object(MarvinAgent, 'create_sub_agent', return_value=SubAgent("text_generation")) as mock_create_sub_agent:
            
            marvin_agent.process_task()

            # Assertions
            mock_create_sub_agent.assert_called_with("text_generation")
            mock_perform_task.assert_called_with(sample_task)
            mock_verify.assert_called_with([sample_result])
            mock_decide.assert_called_with([sample_result])
            mock_detect.assert_called_with(sample_result)

            assert marvin_agent.result == sample_result
            assert os.path.exists(marvin_agent.result_file)

            with open(marvin_agent.result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert data.get('result') == sample_result

    def test_process_task_hallucination_detected(self, marvin_agent, sample_task, sample_result):
        """
        Test processing a task where hallucination is detected.
        """
        marvin_agent.save_task(sample_task)

        # Mock sub-agent creation and task execution
        with patch.object(SubAgent, 'perform_task', return_value=sample_result) as mock_perform_task, \
             patch.object(Verifier, 'verify', return_value=[sample_result]) as mock_verify, \
             patch.object(Decider, 'decide', return_value=sample_result) as mock_decide, \
             patch.object(HallucinationMonitor, 'detect', return_value=True) as mock_detect, \
             patch.object(LLMIntegrationService, 'generate_text', return_value=sample_result) as mock_generate_text, \
             patch.object(MarvinAgent, 'create_sub_agent', return_value=SubAgent("text_generation")) as mock_create_sub_agent:
            
            marvin_agent.process_task()

            # Assertions
            mock_detect.assert_called_with(sample_result)
            assert marvin_agent.result == "Result may contain inaccuracies due to detected hallucinations."
            with open(marvin_agent.result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert data.get('result') == "Result may contain inaccuracies due to detected hallucinations."

    def test_process_task_exception(self, marvin_agent, sample_task):
        """
        Test processing a task where an exception occurs.
        """
        marvin_agent.save_task(sample_task)

        with patch.object(SubAgent, 'perform_task', side_effect=Exception("Sub-agent failure")), \
             patch.object(MarvinAgent, 'logger') as mock_logger:
            
            marvin_agent.process_task()

            mock_logger.error.assert_called()
            assert marvin_agent.result == "An error occurred while processing the task."

    def test_save_result_success(self, marvin_agent, sample_result):
        """
        Test saving a result successfully.
        """
        marvin_agent.save_result(sample_result)
        assert marvin_agent.result == sample_result
        assert os.path.exists(marvin_agent.result_file)

        with open(marvin_agent.result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data.get('result') == sample_result

    def test_save_result_failure(self, marvin_agent, sample_result):
        """
        Test handling failure when saving a result.
        """
        with patch('builtins.open', side_effect=IOError("Unable to write to file")):
            with pytest.raises(MarvinAgentError) as exc_info:
                marvin_agent.save_result(sample_result)
            assert "Failed to save result" in str(exc_info.value)

    def test_get_result_in_memory(self, marvin_agent, sample_result):
        """
        Test retrieving the result from memory.
        """
        marvin_agent.result = sample_result
        result = marvin_agent.get_result()
        assert result == sample_result

    def test_get_result_from_file(self, marvin_agent, sample_result):
        """
        Test retrieving the result from file when not in memory.
        """
        marvin_agent.result = None
        marvin_agent.save_result(sample_result)
        marvin_agent.result = None  # Clear in-memory result
        result = marvin_agent.get_result()
        assert result == sample_result

    def test_get_result_failure(self, marvin_agent):
        """
        Test handling failure when loading a result from file.
        """
        marvin_agent.result = None
        if os.path.exists(marvin_agent.result_file):
            os.remove(marvin_agent.result_file)
        with patch('builtins.open', side_effect=IOError("Unable to read file")):
            with pytest.raises(MarvinAgentError) as exc_info:
                marvin_agent.get_result()
            assert "Failed to load result" in str(exc_info.value)

    def test_dispose_success(self, marvin_agent, mock_shared_memory):
        """
        Test successful disposal of resources.
        """
        with patch.object(marvin_agent.ml_module, 'shutdown') as mock_shutdown, \
             patch.object(marvin_agent.communication_module, 'close') as mock_comm_close:
            
            marvin_agent.dispose()

            mock_shared_memory.close.assert_called_once()
            mock_shutdown.assert_called_once()
            mock_comm_close.assert_called_once()

    def test_dispose_failure_shared_memory(self, marvin_agent, mock_shared_memory):
        """
        Test handling failure when disposing shared memory.
        """
        mock_shared_memory.close.side_effect = Exception("SharedMemory closure failed")
        with patch.object(marvin_agent.logger, 'error') as mock_logger_error:
            with pytest.raises(MarvinAgentError):
                marvin_agent.dispose()
            mock_logger_error.assert_called_with("Failed to close SharedMemoryManager: SharedMemory closure failed", exc_info=True)

    def test_dispose_failure_ml_module(self, marvin_agent, mock_shared_memory):
        """
        Test handling failure when disposing machine learning module.
        """
        with patch.object(marvin_agent.ml_module, 'shutdown', side_effect=Exception("ML shutdown failed")), \
             patch.object(marvin_agent.logger, 'error') as mock_logger_error:
            
            with pytest.raises(MarvinAgentError):
                marvin_agent.dispose()
            
            mock_logger_error.assert_called_with("Failed to shutdown MachineLearningModule: ML shutdown failed", exc_info=True)

    def test_dispose_failure_communication_module(self, marvin_agent, mock_shared_memory):
        """
        Test handling failure when disposing communication module.
        """
        with patch.object(marvin_agent.communication_module, 'close', side_effect=Exception("Communication closure failed")), \
             patch.object(marvin_agent.logger, 'error') as mock_logger_error:
            
            with pytest.raises(MarvinAgentError):
                marvin_agent.dispose()
            
            mock_logger_error.assert_called_with("Failed to close CommunicationModule: Communication closure failed", exc_info=True)

class TestSubAgent:
    """
    Test Suite for the SubAgent class
    """

    @pytest.fixture
    def sub_agent(self):
        """
        Fixture to initialize a SubAgent instance.
        """
        return SubAgent("text_generation")

    def test_perform_task_text_generation_success(self, sub_agent):
        """
        Test performing a text generation task successfully.
        """
        task = {
            "prompt": "Once upon a time",
            "model": "gpt-3.5-turbo"
        }
        with patch.object(sub_agent.llm_service, 'generate_text', return_value="Once upon a time, there was a brave knight.") as mock_generate:
            result = sub_agent.perform_task(task)
            mock_generate.assert_called_with(prompt=task['prompt'], model=task['model'])
            assert result == "Once upon a time, there was a brave knight."

    def test_perform_task_data_analysis_success(self, sub_agent):
        """
        Test performing a data analysis task successfully.
        """
        sub_agent.recommendation = "data_analysis"
        task = {
            "data": {"values": [1, 2, 3, 4, 5]}
        }
        with patch.object(sub_agent.llm_service, 'perform_analysis', return_value={"mean": 3.0, "median": 3}) as mock_analyze:
            result = sub_agent.perform_task(task)
            mock_analyze.assert_called_with(task['data'])
            assert result == {"mean": 3.0, "median": 3}

    def test_perform_task_content_summarization_success(self, sub_agent):
        """
        Test performing a content summarization task successfully.
        """
        sub_agent.recommendation = "content_summarization"
        task = {
            "content": "Machine learning is a field of artificial intelligence that uses statistical techniques to give computer systems the ability to 'learn' from data."
        }
        with patch.object(sub_agent.llm_service, 'summarize_text', return_value="Machine learning enables computers to learn from data using statistical methods.") as mock_summarize:
            result = sub_agent.perform_task(task)
            mock_summarize.assert_called_with(task['content'])
            assert result == "Machine learning enables computers to learn from data using statistical methods."

    def test_perform_task_unknown_recommendation(self, sub_agent):
        """
        Test handling of an unknown recommendation.
        """
        sub_agent.recommendation = "unknown_task"
        task = {}
        with pytest.raises(MarvinAgentError) as exc_info:
            sub_agent.perform_task(task)
        assert "Unknown recommendation: unknown_task" in str(exc_info.value)

    def test_perform_task_exception(self, sub_agent):
        """
        Test handling an exception during task performance.
        """
        task = {
            "prompt": "Hello, world!",
            "model": "gpt-3.5-turbo"
        }
        with patch.object(sub_agent.llm_service, 'generate_text', side_effect=Exception("LLM service failure")) as mock_generate, \
             patch.object(sub_agent.logger, 'error') as mock_logger_error:
            with pytest.raises(MarvinAgentError) as exc_info:
                sub_agent.perform_task(task)
            mock_generate.assert_called_with(prompt=task['prompt'], model=task['model'])
            mock_logger_error.assert_called()
            assert "LLM service failure" in str(exc_info.value)
