# marvin_agent.py

import threading
import json
import os
import uuid
import time
from typing import Optional, Dict, Any, List

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

class MarvinAgentError(Exception):
    """Custom exception class for MarvinAgent-related errors."""
    pass

class MarvinAgent:
    """
    MarvinAgent is responsible for managing tasks, coordinating sub-agents, and ensuring secure and efficient
    processing of tasks using integrated language models and machine learning modules.
    """

    def __init__(self):
        """
        Initializes the MarvinAgent with necessary configurations, authentication, and integrations.
        """
        self.task_file = 'data/tasks.json'
        self.result_file = 'data/result.json'
        self.current_task: Optional[Dict[str, Any]] = None
        self.result: Optional[Any] = None
        self.logger = setup_logging('MarvinAgent')
        self.communication_module: Optional[CommunicationModule] = None
        self.shared_memory: Optional[SharedMemory] = None
        self.encryption_manager: Optional[EncryptionManager] = None
        self.ml_module = MachineLearningModule()
        self.lock = threading.Lock()

    def initialize(self, communication_module: CommunicationModule, shared_memory: SharedMemory, encryption_manager: EncryptionManager):
        """
        Initializes the MarvinAgent with communication, shared memory, and encryption modules.

        Args:
            communication_module (CommunicationModule): The communication module instance.
            shared_memory (SharedMemory): The shared memory manager instance.
            encryption_manager (EncryptionManager): The encryption manager instance.
        """
        self.communication_module = communication_module
        self.shared_memory = shared_memory
        self.encryption_manager = encryption_manager
        self.logger.info("MarvinAgent initialized with communication, shared memory, and encryption modules.")

    def save_task(self, task: Dict[str, Any]) -> None:
        """
        Saves the current task to a JSON file and updates the in-memory task.

        Args:
            task (Dict[str, Any]): The task data to be saved.
        """
        with self.lock:
            self.current_task = task
            try:
                with open(self.task_file, 'w', encoding='utf-8') as f:
                    json.dump({'task': task}, f, ensure_ascii=False, indent=4)
                self.logger.debug(f"Task saved successfully: {task}")
            except IOError as e:
                self.logger.error(f"Failed to save task to {self.task_file}: {e}")
                raise MarvinAgentError(f"Failed to save task: {e}")

    def get_current_task(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current task from memory or file.

        Returns:
            Optional[Dict[str, Any]]: The current task if available, else None.
        """
        with self.lock:
            if self.current_task:
                return self.current_task
            elif os.path.exists(self.task_file):
                try:
                    with open(self.task_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.current_task = data.get('task')
                        self.logger.debug(f"Task loaded from file: {self.current_task}")
                        return self.current_task
                except (IOError, json.JSONDecodeError) as e:
                    self.logger.error(f"Failed to load task from {self.task_file}: {e}")
                    raise MarvinAgentError(f"Failed to load task: {e}")
            else:
                self.logger.warning("No current task available.")
                return None

    def clear_current_task(self) -> None:
        """
        Clears the current task from memory and deletes the task file.
        """
        with self.lock:
            self.current_task = None
            try:
                if os.path.exists(self.task_file):
                    os.remove(self.task_file)
                    self.logger.debug(f"Task file {self.task_file} removed successfully.")
            except OSError as e:
                self.logger.error(f"Failed to remove task file {self.task_file}: {e}")
                raise MarvinAgentError(f"Failed to remove task file: {e}")

    def process_task(self) -> None:
        """
        Processes the current task by coordinating sub-agents to deliberate, perform tasks,
        verify results, make decisions, and monitor for hallucinations.
        """
        with self.lock:
            try:
                task = self.get_current_task()
                if not task:
                    self.logger.warning("No task to process.")
                    return

                self.logger.info(f"Processing task: {task}")

                # Initialize sub-agents
                hallucination_monitor = HallucinationMonitor()
                verifier = Verifier()
                decider = Decider()
                expert_panel = ExpertPanel()
                llm_service = LLMIntegrationService()

                # Expert panel deliberates on the task
                recommendations = expert_panel.deliberate(task)
                self.logger.debug(f"ExpertPanel recommendations: {recommendations}")

                # Create sub-agents based on recommendations
                sub_agents = self.create_sub_agents(recommendations)
                self.logger.debug(f"Sub-agents created: {sub_agents}")

                # Sub-agents perform their assigned tasks
                results = self.execute_sub_agents(sub_agents, task)
                self.logger.debug(f"Sub-agent results: {results}")

                # Verify the results
                verified_results = verifier.verify(results)
                self.logger.debug(f"Verified results: {verified_results}")

                # Make the final decision based on verified results
                final_decision = decider.decide(verified_results)
                self.logger.info(f"Final decision made: {final_decision}")

                # Monitor for hallucinations in the final decision
                if hallucination_monitor.detect(final_decision):
                    self.logger.warning("Hallucination detected in the final decision.")
                    final_decision = "Result may contain inaccuracies due to detected hallucinations."
                else:
                    self.logger.debug("No hallucinations detected in the final decision.")

                # Save the result
                self.save_result(final_decision)

                # Clear the current task
                self.clear_current_task()

            except MarvinAgentError as e:
                self.logger.error(f"MarvinAgent encountered an error: {e}", exc_info=True)
                self.result = "An error occurred while processing the task."
            except Exception as e:
                self.logger.critical(f"Unexpected error in MarvinAgent: {e}", exc_info=True)
                self.result = "A critical error occurred. Please contact support."

    def create_sub_agents(self, recommendations: List[str]) -> List[Any]:
        """
        Creates sub-agent instances based on the given recommendations.

        Args:
            recommendations (List[str]): List of recommendations from the expert panel.

        Returns:
            List[Any]: List of sub-agent instances.
        """
        sub_agents = []
        for rec in recommendations:
            agent = self.create_sub_agent(rec)
            sub_agents.append(agent)
            self.logger.debug(f"Sub-agent created for recommendation '{rec}': {agent}")
        return sub_agents

    def create_sub_agent(self, recommendation: str) -> Any:
        """
        Creates a single sub-agent instance based on the recommendation.

        Args:
            recommendation (str): The recommendation from the expert panel.

        Returns:
            Any: The created sub-agent instance.
        """
        agent = SubAgent(recommendation)
        return agent

    def execute_sub_agents(self, sub_agents: List[Any], task: Dict[str, Any]) -> List[Any]:
        """
        Executes tasks assigned to sub-agents concurrently.

        Args:
            sub_agents (List[Any]): List of sub-agent instances.
            task (Dict[str, Any]): The task data.

        Returns:
            List[Any]: List of results from sub-agents.
        """
        threads = []
        results = []

        def agent_task(agent, task, results_list):
            try:
                result = agent.perform_task(task)
                results_list.append(result)
                self.logger.debug(f"Agent {agent} completed task with result: {result}")
            except Exception as e:
                self.logger.error(f"Agent {agent} failed to perform task: {e}", exc_info=True)
                results_list.append({"agent": str(agent), "error": str(e)})

        for agent in sub_agents:
            thread = threading.Thread(target=agent_task, args=(agent, task, results))
            threads.append(thread)
            thread.start()
            self.logger.debug(f"Thread started for agent {agent}")

        for thread in threads:
            thread.join()
            self.logger.debug("Thread joined successfully.")

        return results

    def save_result(self, result: Any) -> None:
        """
        Saves the result to a JSON file.

        Args:
            result (Any): The result data to be saved.
        """
        try:
            self.result = result
            with open(self.result_file, 'w', encoding='utf-8') as f:
                json.dump({'result': result}, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Result saved successfully: {result}")
        except IOError as e:
            self.logger.error(f"Failed to save result to {self.result_file}: {e}")
            raise MarvinAgentError(f"Failed to save result: {e}")

    def get_result(self) -> Any:
        """
        Retrieves the result from memory or file.

        Returns:
            Any: The result data if available, else a default message.
        """
        with self.lock:
            if self.result:
                return self.result
            elif os.path.exists(self.result_file):
                try:
                    with open(self.result_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.result = data.get('result', "No result available.")
                        self.logger.debug(f"Result loaded from file: {self.result}")
                        return self.result
                except (IOError, json.JSONDecodeError) as e:
                    self.logger.error(f"Failed to load result from {self.result_file}: {e}")
                    raise MarvinAgentError(f"Failed to load result: {e}")
            else:
                self.logger.info("No result available.")
                return "No result available."

    def dispose(self) -> None:
        """
        Disposes of all resources and integrations gracefully.
        """
        try:
            self.close()
        except MarvinAgentError as e:
            self.logger.error(f"Error during disposal: {e}", exc_info=True)
            raise

    def close(self) -> None:
        """
        Closes all integrations and releases resources.
        """
        try:
            if self.shared_memory:
                self.shared_memory.close()
                self.logger.info("SharedMemoryManager closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close SharedMemoryManager: {e}", exc_info=True)
            raise MarvinAgentError(f"Failed to close SharedMemoryManager: {e}")

        try:
            if self.ml_module:
                self.ml_module.shutdown()
                self.logger.info("MachineLearningModule shutdown successfully.")
        except Exception as e:
            self.logger.error(f"Failed to shutdown MachineLearningModule: {e}", exc_info=True)
            raise MarvinAgentError(f"Failed to shutdown MachineLearningModule: {e}")

        try:
            if self.communication_module:
                self.communication_module.close()
                self.logger.info("CommunicationModule closed successfully.")
        except Exception as e:
            self.logger.error(f"Failed to close CommunicationModule: {e}", exc_info=True)
            raise MarvinAgentError(f"Failed to close CommunicationModule: {e}")

        self.logger.info("MarvinAgent disposed all resources successfully.")

class SubAgent:
    """
    SubAgent is responsible for performing specific tasks as recommended by the ExpertPanel.
    It interacts with language models and other services to execute its assigned tasks.
    """

    def __init__(self, recommendation: str):
        """
        Initializes the SubAgent with a specific recommendation.

        Args:
            recommendation (str): The recommendation guiding the sub-agent's task.
        """
        self.recommendation = recommendation
        self.logger = setup_logging('SubAgent')
        self.llm_service = LLMIntegrationService()

    def perform_task(self, task: Dict[str, Any]) -> Any:
        """
        Executes the task based on the sub-agent's recommendation.

        Args:
            task (Dict[str, Any]): The task data.

        Returns:
            Any: The result of the task execution.
        """
        self.logger.info(f"SubAgent performing task with recommendation: {self.recommendation}")
        try:
            if self.recommendation == "text_generation":
                prompt = task.get('prompt', '')
                model = task.get('model', 'gpt-3.5-turbo')
                response = self.llm_service.generate_text(prompt=prompt, model=model)
                self.logger.debug(f"Text generation response: {response}")
                return response
            elif self.recommendation == "data_analysis":
                data = task.get('data', {})
                analysis_result = self.analyze_data(data)
                self.logger.debug(f"Data analysis result: {analysis_result}")
                return analysis_result
            elif self.recommendation == "content_summarization":
                content = task.get('content', '')
                summary = self.summarize_content(content)
                self.logger.debug(f"Content summary: {summary}")
                return summary
            else:
                self.logger.error(f"Unknown recommendation: {self.recommendation}")
                raise MarvinAgentError(f"Unknown recommendation: {self.recommendation}")
        except Exception as e:
            self.logger.error(f"Error performing task with recommendation '{self.recommendation}': {e}", exc_info=True)
            raise

    def analyze_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes the provided data using the MachineLearningModule.

        Args:
            data (Dict[str, Any]): The data to be analyzed.

        Returns:
            Dict[str, Any]: The analysis results.
        """
        self.logger.info("Analyzing data.")
        try:
            analysis = self.llm_service.perform_analysis(data)
            self.logger.debug(f"Analysis complete: {analysis}")
            return analysis
        except Exception as e:
            self.logger.error(f"Data analysis failed: {e}", exc_info=True)
            raise MarvinAgentError(f"Data analysis failed: {e}")

    def summarize_content(self, content: str) -> str:
        """
        Summarizes the provided content using the Language Model Integration Service.

        Args:
            content (str): The content to be summarized.

        Returns:
            str: The summarized content.
        """
        self.logger.info("Summarizing content.")
        try:
            summary = self.llm_service.summarize_text(content)
            self.logger.debug(f"Summary: {summary}")
            return summary
        except Exception as e:
            self.logger.error(f"Content summarization failed: {e}", exc_info=True)
            raise MarvinAgentError(f"Content summarization failed: {e}")
