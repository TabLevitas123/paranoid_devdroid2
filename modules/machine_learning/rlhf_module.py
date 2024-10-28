# rlhf_module.py

import logging
import pickle
import threading
import numpy as np
import tensorflow as tf
from tensorflow.python.keras.models import model_from_json
from tensorflow.python.keras.models import Model
from tensorflow.python.keras.layers import Input, Dense
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.memory.shared_memory import SharedMemory
from modules.services.feedback_service import FeedbackService

class RLHFModule:
    """
    Implements Reinforcement Learning from Human Feedback (RLHF) algorithms.
    """

    def __init__(self, input_shape, output_shape, agent_id):
        self.logger = setup_logging('RLHFModule')
        self.encryption_manager = EncryptionManager()
        self.shared_memory = SharedMemory()
        self.feedback_module = FeedbackService()
        self.input_shape = input_shape
        self.output_shape = output_shape
        self.agent_id = agent_id
        self.lock = threading.Lock()
        self.policy_model = self._build_policy_model()
        self.reward_model = self._build_reward_model()
        self.logger.info(f"RLHFModule initialized for agent {agent_id}.")

    def _build_policy_model(self):
        """
        Builds and compiles the policy model.

        Returns:
            Model: A compiled Keras policy model.
        """
        try:
            inputs = Input(shape=self.input_shape)
            x = Dense(128, activation='relu')(inputs)
            x = Dense(64, activation='relu')(x)
            outputs = Dense(self.output_shape, activation='softmax')(x)
            model = Model(inputs=inputs, outputs=outputs)
            model.compile(optimizer='adam', loss='categorical_crossentropy')
            self.logger.debug("Policy model built and compiled successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error building policy model: {e}", exc_info=True)
            raise

    def _build_reward_model(self):
        """
        Builds and compiles the reward model.

        Returns:
            Model: A compiled Keras reward model.
        """
        try:
            inputs = Input(shape=self.input_shape)
            x = Dense(128, activation='relu')(inputs)
            x = Dense(64, activation='relu')(x)
            outputs = Dense(1, activation='linear')(x)
            model = Model(inputs=inputs, outputs=outputs)
            model.compile(optimizer='adam', loss='mean_squared_error')
            self.logger.debug("Reward model built and compiled successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error building reward model: {e}", exc_info=True)
            raise

    def generate_action(self, state):
        """
        Generates an action based on the current policy.

        Args:
            state (array): The current state.

        Returns:
            int: The action selected.
        """
        try:
            state = np.array([state])
            action_probs = self.policy_model.predict(state)
            action = np.argmax(action_probs[0])
            self.logger.debug(f"Generated action {action} with probabilities {action_probs[0]}")
            return action
        except Exception as e:
            self.logger.error(f"Error generating action: {e}", exc_info=True)
            raise

    def update_models(self, states, actions, rewards):
        """
        Updates the policy and reward models based on human feedback.

        Args:
            states (array): Array of states.
            actions (array): Array of actions taken.
            rewards (array): Array of rewards received from human feedback.
        """
        try:
            with self.lock:
                # Update reward model
                self.reward_model.fit(states, rewards, epochs=1, verbose=0)
                # Update policy model using policy gradient method
                action_one_hot = tf.keras.utils.to_categorical(actions, num_classes=self.output_shape)
                advantages = rewards - self.reward_model.predict(states)
                self.policy_model.fit(states, action_one_hot, sample_weight=advantages.flatten(), epochs=1, verbose=0)
            self.logger.info("Policy and reward models updated based on human feedback.")
        except Exception as e:
            self.logger.error(f"Error updating models: {e}", exc_info=True)
            raise

    def collect_human_feedback(self, state, action):
        """
        Collects human feedback for a given state and action.

        Args:
            state (array): The state presented to the human.
            action (int): The action taken.

        Returns:
            float: The reward provided by the human.
        """
        try:
            feedback = self.feedback_module.request_feedback(state, action)
            self.logger.debug(f"Received human feedback: {feedback}")
            return feedback
        except Exception as e:
            self.logger.error(f"Error collecting human feedback: {e}", exc_info=True)
            raise

    def serialize_policy(self):
        """
        Serializes the policy model for storage or transmission.

        Returns:
            bytes: The serialized policy model.
        """
        try:
            with self.lock:
                model_json = self.policy_model.to_json()
                model_weights = self.policy_model.get_weights()
                serialized_data = {
                    'model_json': model_json,
                    'model_weights': [w.tolist() for w in model_weights]
                }
                serialized_bytes = self.encryption_manager.encrypt_data(pickle.dumps(serialized_data))
            self.logger.debug("Policy model serialized and encrypted successfully.")
            return serialized_bytes
        except Exception as e:
            self.logger.error(f"Error serializing policy model: {e}", exc_info=True)
            raise

    def deserialize_policy(self, serialized_bytes):
        """
        Deserializes the policy model from bytes.

        Args:
            serialized_bytes (bytes): The serialized policy model bytes.
        """
        try:
            decrypted_data = self.encryption_manager.decrypt_data(serialized_bytes)
            serialized_data = pickle.loads(decrypted_data)
            with self.lock:
                model_json = serialized_data['model_json']
                model_weights = [np.array(w) for w in serialized_data['model_weights']]
                self.policy_model = model_from_json(model_json)
                self.policy_model.set_weights(model_weights)
            self.logger.debug("Policy model deserialized and decrypted successfully.")
        except Exception as e:
            self.logger.error(f"Error deserializing policy model: {e}", exc_info=True)
            raise

    def save_policy(self):
        """
        Saves the policy model to shared memory securely.
        """
        try:
            policy_bytes = self.serialize_policy()
            key = f"policy_model_{self.agent_id}"
            self.shared_memory.write_data(key, policy_bytes, self.agent_id)
            self.logger.info(f"Policy model saved to shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error saving policy model: {e}", exc_info=True)
            raise

    def load_policy(self):
        """
        Loads the policy model from shared memory securely.
        """
        try:
            key = f"policy_model_{self.agent_id}"
            policy_bytes = self.shared_memory.read_data(key, self.agent_id)
            if policy_bytes:
                self.deserialize_policy(policy_bytes)
                self.logger.info(f"Policy model loaded from shared memory with key {key}.")
            else:
                self.logger.warning(f"No policy model found in shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error loading policy model: {e}", exc_info=True)
            raise

    def merge_policies(self, other_policy_bytes):
        """
        Merges another agent's policy model with the current policy.

        Args:
            other_policy_bytes (bytes): Serialized policy model from another agent.
        """
        try:
            decrypted_data = self.encryption_manager.decrypt_data(other_policy_bytes)
            serialized_data = pickle.loads(decrypted_data)
            other_model_json = serialized_data['model_json']
            other_model_weights = [np.array(w) for w in serialized_data['model_weights']]
            other_policy_model = model_from_json(other_model_json)
            other_policy_model.set_weights(other_model_weights)

            # Average the weights
            with self.lock:
                new_weights = []
                for weights_self, weights_other in zip(self.policy_model.get_weights(), other_policy_model.get_weights()):
                    new_weights.append((weights_self + weights_other) / 2)
                self.policy_model.set_weights(new_weights)
            self.logger.info("Policy models merged successfully with another agent's policy.")
        except Exception as e:
            self.logger.error(f"Error merging policy models: {e}", exc_info=True)
            raise
