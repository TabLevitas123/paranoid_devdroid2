# q_learning_agent.py

import threading
import logging
import random
import numpy as np
from modules.machine_learning.rlhf_module import RLHFModule
from modules.environment.environment_module import EnvironmentModule
from modules.communication.communication_module import CommunicationModule
from modules.security.security_module import SecurityModule
from modules.utilities.logging_manager import setup_logging


class QLearningAgent:
    """
    Specializes in tasks requiring reinforcement learning using Q-learning.
    """

    def __init__(self, agent_id, communication_module, environment_module, security_module):
        self.agent_id = agent_id
        self.communication_module = communication_module
        self.environment_module = environment_module
        self.security_module = security_module
        self.rl_module = RLHFModule()
        self.logger = setup_logging(f'QLearningAgent_{agent_id}')
        self.lock = threading.Lock()
        self.q_table = {}
        self.learning_rate = 0.1
        self.discount_factor = 0.99
        self.exploration_rate = 1.0  # Initial exploration rate
        self.exploration_decay = 0.995
        self.min_exploration_rate = 0.01
        self.logger.info(f"QLearningAgent {self.agent_id} initialized successfully.")

    def perform_task(self, task_description):
        """
        Performs the given task using Q-learning.

        Args:
            task_description (str): Description of the task to perform.

        Returns:
            str: Result of the task execution.
        """
        try:
            self.logger.info(f"Agent {self.agent_id} performing task: {task_description}")
            environment = self.environment_module.create_environment(task_description)
            self.logger.debug(f"Environment created: {environment}")

            # Run Q-learning algorithm
            total_episodes = 1000
            max_steps_per_episode = 100

            for episode in range(total_episodes):
                state = environment.reset()
                self.logger.debug(f"Episode {episode+1}/{total_episodes} started.")
                for step in range(max_steps_per_episode):
                    action = self._choose_action(state)
                    new_state, reward, done, info = environment.step(action)
                    self._update_q_table(state, action, reward, new_state)
                    state = new_state
                    if done:
                        break
                self._decay_exploration_rate()
                self.logger.debug(f"Episode {episode+1} completed.")

            self.logger.info("Q-learning task completed successfully.")
            return "Q-learning task completed successfully."
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            return "An error occurred while performing the task."

    def _choose_action(self, state):
        """
        Chooses an action based on the current state and exploration rate.

        Args:
            state (tuple): The current state.

        Returns:
            int: The action to take.
        """
        try:
            if random.uniform(0, 1) < self.exploration_rate:
                # Explore: choose a random action
                action = self.environment_module.sample_action()
                self.logger.debug(f"Exploring: Chose random action {action}")
            else:
                # Exploit: choose the best known action
                state_actions = self.q_table.get(state, {})
                if not state_actions:
                    action = self.environment_module.sample_action()
                    self.logger.debug(f"No known actions for state {state}, choosing random action {action}")
                else:
                    action = max(state_actions, key=state_actions.get)
                    self.logger.debug(f"Exploiting: Chose best action {action} for state {state}")
            return action
        except Exception as e:
            self.logger.error(f"Error choosing action: {e}", exc_info=True)
            return self.environment_module.sample_action()

    def _update_q_table(self, state, action, reward, new_state):
        """
        Updates the Q-table based on the action taken and the reward received.

        Args:
            state (tuple): The previous state.
            action (int): The action taken.
            reward (float): The reward received.
            new_state (tuple): The new state after taking the action.
        """
        try:
            self.logger.debug(f"Updating Q-table for state {state}, action {action}")
            state_actions = self.q_table.setdefault(state, {})
            current_q = state_actions.get(action, 0.0)

            new_state_actions = self.q_table.get(new_state, {})
            max_future_q = max(new_state_actions.values()) if new_state_actions else 0.0

            # Q-learning formula
            updated_q = (1 - self.learning_rate) * current_q + self.learning_rate * (reward + self.discount_factor * max_future_q)
            state_actions[action] = updated_q
            self.logger.debug(f"Q-value updated to {updated_q}")

            # Save the updated Q-table securely
            self._save_q_table()
        except Exception as e:
            self.logger.error(f"Error updating Q-table: {e}", exc_info=True)

    def _decay_exploration_rate(self):
        """
        Decays the exploration rate after each episode.
        """
        try:
            self.exploration_rate = max(self.min_exploration_rate, self.exploration_rate * self.exploration_decay)
            self.logger.debug(f"Exploration rate decayed to {self.exploration_rate}")
        except Exception as e:
            self.logger.error(f"Error decaying exploration rate: {e}", exc_info=True)

    def _save_q_table(self):
        """
        Saves the Q-table securely using the security module.
        """
        try:
            serialized_q_table = self.rl_module.serialize_q_table(self.q_table)
            encrypted_q_table = self.security_module.encrypt_data(serialized_q_table)
            # Assuming we have a method to save the encrypted Q-table to persistent storage
            self.security_module.save_encrypted_data(f'q_table_{self.agent_id}.enc', encrypted_q_table)
            self.logger.debug("Q-table saved securely.")
        except Exception as e:
            self.logger.error(f"Error saving Q-table: {e}", exc_info=True)

    def _load_q_table(self):
        """
        Loads the Q-table securely using the security module.
        """
        try:
            encrypted_q_table = self.security_module.load_encrypted_data(f'q_table_{self.agent_id}.enc')
            serialized_q_table = self.security_module.decrypt_data(encrypted_q_table)
            self.q_table = self.rl_module.deserialize_q_table(serialized_q_table)
            self.logger.debug("Q-table loaded successfully.")
        except FileNotFoundError:
            self.logger.warning("No existing Q-table found; starting with an empty Q-table.")
            self.q_table = {}
        except Exception as e:
            self.logger.error(f"Error loading Q-table: {e}", exc_info=True)
            self.q_table = {}

    def receive_message(self, message):
        """
        Processes incoming messages related to Q-learning tasks.

        Args:
            message (dict): The message received.
        """
        try:
            self.logger.debug(f"Received message: {message}")
            message_type = message.get('message_type')
            sender_id = message.get('sender_id')
            content = message.get('content')

            if message_type == 'q_table_share':
                self._handle_q_table_share(sender_id, content)
            else:
                self.logger.warning(f"Unknown message type received: {message_type}")
        except Exception as e:
            self.logger.error(f"Error processing received message: {e}", exc_info=True)

    def _handle_q_table_share(self, sender_id, encrypted_content):
        """
        Handles receiving a shared Q-table from another agent.

        Args:
            sender_id (str): ID of the agent sharing the Q-table.
            encrypted_content (str): The encrypted serialized Q-table.
        """
        try:
            self.logger.info(f"Receiving Q-table from agent {sender_id}")
            serialized_q_table = self.security_module.decrypt_data(encrypted_content)
            q_table = self.rl_module.deserialize_q_table(serialized_q_table)
            # Merge the received Q-table with the current Q-table
            self._merge_q_tables(q_table)
            self.logger.info(f"Q-table received and merged from agent {sender_id}")
        except Exception as e:
            self.logger.error(f"Error handling Q-table share from agent {sender_id}: {e}", exc_info=True)

    def _merge_q_tables(self, other_q_table):
        """
        Merges another Q-table into the current Q-table.

        Args:
            other_q_table (dict): The Q-table to merge.
        """
        try:
            for state, actions in other_q_table.items():
                state_actions = self.q_table.setdefault(state, {})
                for action, q_value in actions.items():
                    existing_q = state_actions.get(action, 0.0)
                    # Simple averaging for merging
                    state_actions[action] = (existing_q + q_value) / 2
            self.logger.debug("Q-tables merged successfully.")
        except Exception as e:
            self.logger.error(f"Error merging Q-tables: {e}", exc_info=True)

    def share_q_table(self, agent_id):
        """
        Shares the current Q-table with another agent.

        Args:
            agent_id (str): The ID of the agent to share the Q-table with.

        Returns:
            bool: True if Q-table shared successfully, False otherwise.
        """
        try:
            self.logger.info(f"Sharing Q-table with agent {agent_id}.")
            serialized_q_table = self.rl_module.serialize_q_table(self.q_table)
            encrypted_q_table = self.security_module.encrypt_data(serialized_q_table)
            message = {
                'sender_id': self.agent_id,
                'receiver_id': agent_id,
                'message_type': 'q_table_share',
                'content': encrypted_q_table
            }
            self.communication_module.send_message(message)
            self.logger.debug(f"Q-table sent to agent {agent_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error sharing Q-table with agent {agent_id}: {e}", exc_info=True)
            return False
