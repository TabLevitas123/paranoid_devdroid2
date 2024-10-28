# q_learning_module.py

import logging
import threading
import numpy as np
import random
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.memory.shared_memory import SharedMemory
from modules.environment.environment_module import EnvironmentModule

class QLearningModule:
    """
    Provides functionalities for the Q-learning algorithm.
    """

    def __init__(self, state_space_size, action_space_size, agent_id):
        self.logger = setup_logging('QLearningModule')
        self.encryption_manager = EncryptionManager()
        self.shared_memory = SharedMemory()
        self.environment_module = EnvironmentModule()
        self.state_space_size = state_space_size
        self.action_space_size = action_space_size
        self.agent_id = agent_id
        self.lock = threading.Lock()
        self.q_table = np.zeros((state_space_size, action_space_size))
        self.learning_rate = 0.1
        self.discount_factor = 0.99
        self.exploration_rate = 1.0
        self.min_exploration_rate = 0.01
        self.exploration_decay_rate = 0.001
        self.logger.info(f"QLearningModule initialized for agent {agent_id}.")

    def choose_action(self, state):
        """
        Chooses an action based on the current state and exploration rate.

        Args:
            state (int): The current state.

        Returns:
            int: The action to take.
        """
        try:
            if random.uniform(0, 1) < self.exploration_rate:
                action = self.environment_module.sample_action()
                self.logger.debug(f"Agent {self.agent_id} exploring: chose random action {action}.")
            else:
                action = np.argmax(self.q_table[state, :])
                self.logger.debug(f"Agent {self.agent_id} exploiting: chose best action {action}.")
            return action
        except Exception as e:
            self.logger.error(f"Error choosing action: {e}", exc_info=True)
            raise

    def update_q_value(self, state, action, reward, next_state):
        """
        Updates the Q-value for the given state and action.

        Args:
            state (int): The current state.
            action (int): The action taken.
            reward (float): The reward received.
            next_state (int): The next state after taking the action.
        """
        try:
            max_future_q = np.max(self.q_table[next_state, :])
            current_q = self.q_table[state, action]
            new_q = (1 - self.learning_rate) * current_q + \
                    self.learning_rate * (reward + self.discount_factor * max_future_q)
            with self.lock:
                self.q_table[state, action] = new_q
            self.logger.debug(f"Updated Q-value for state {state}, action {action}: {new_q}.")
        except Exception as e:
            self.logger.error(f"Error updating Q-value: {e}", exc_info=True)
            raise

    def decay_exploration_rate(self):
        """
        Decays the exploration rate over time.
        """
        try:
            self.exploration_rate = max(
                self.min_exploration_rate,
                self.exploration_rate * np.exp(-self.exploration_decay_rate)
            )
            self.logger.debug(f"Exploration rate decayed to {self.exploration_rate}.")
        except Exception as e:
            self.logger.error(f"Error decaying exploration rate: {e}", exc_info=True)
            raise

    def serialize_q_table(self):
        """
        Serializes the Q-table for storage or transmission.

        Returns:
            bytes: The serialized Q-table.
        """
        try:
            with self.lock:
                q_table_bytes = self.q_table.tobytes()
            encrypted_q_table = self.encryption_manager.encrypt_data(q_table_bytes)
            self.logger.debug("Q-table serialized and encrypted successfully.")
            return encrypted_q_table
        except Exception as e:
            self.logger.error(f"Error serializing Q-table: {e}", exc_info=True)
            raise

    def deserialize_q_table(self, encrypted_q_table):
        """
        Deserializes the Q-table from encrypted bytes.

        Args:
            encrypted_q_table (bytes): The encrypted serialized Q-table bytes.
        """
        try:
            decrypted_bytes = self.encryption_manager.decrypt_data(encrypted_q_table)
            with self.lock:
                self.q_table = np.frombuffer(decrypted_bytes).reshape(self.state_space_size, self.action_space_size)
            self.logger.debug("Q-table deserialized and decrypted successfully.")
        except Exception as e:
            self.logger.error(f"Error deserializing Q-table: {e}", exc_info=True)
            raise

    def save_q_table(self):
        """
        Saves the Q-table to shared memory securely.
        """
        try:
            encrypted_q_table = self.serialize_q_table()
            key = f"q_table_{self.agent_id}"
            self.shared_memory.write_data(key, encrypted_q_table, self.agent_id)
            self.logger.info(f"Q-table saved to shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error saving Q-table: {e}", exc_info=True)
            raise

    def load_q_table(self):
        """
        Loads the Q-table from shared memory securely.
        """
        try:
            key = f"q_table_{self.agent_id}"
            encrypted_q_table = self.shared_memory.read_data(key, self.agent_id)
            if encrypted_q_table:
                self.deserialize_q_table(encrypted_q_table)
                self.logger.info(f"Q-table loaded from shared memory with key {key}.")
            else:
                self.logger.warning(f"No Q-table found in shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error loading Q-table: {e}", exc_info=True)
            raise

    def merge_q_tables(self, other_encrypted_q_table):
        """
        Merges another agent's Q-table with the current Q-table.

        Args:
            other_encrypted_q_table (bytes): Encrypted serialized Q-table from another agent.
        """
        try:
            decrypted_bytes = self.encryption_manager.decrypt_data(other_encrypted_q_table)
            other_q_table = np.frombuffer(decrypted_bytes).reshape(self.state_space_size, self.action_space_size)
            with self.lock:
                self.q_table = (self.q_table + other_q_table) / 2
            self.logger.info("Q-table merged successfully with another agent's Q-table.")
        except Exception as e:
            self.logger.error(f"Error merging Q-tables: {e}", exc_info=True)
            raise

    def sample_action(self):
        """
        Samples a random action from the action space.

        Returns:
            int: A random action.
        """
        try:
            action = random.randint(0, self.action_space_size - 1)
            self.logger.debug(f"Sampled random action: {action}")
            return action
        except Exception as e:
            self.logger.error(f"Error sampling action: {e}", exc_info=True)
            raise
