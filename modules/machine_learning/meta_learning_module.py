# meta_learning_module.py

import logging
import pickle
import threading
import numpy as np
import tensorflow as tf
from tensorflow.python.keras.models import Model
from tensorflow.python.keras.layers import Input, Dense
from tensorflow.python.keras.optimizers import Adam
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.data.data_module import DataModule
from modules.memory.shared_memory import SharedMemory
from tensorflow.python.keras.models import model_from_json
class MetaLearningModule:
    """
    Implements meta-learning algorithms to enable models to learn how to learn.
    """

    def __init__(self, input_shape, output_shape, agent_id):
        self.logger = setup_logging('MetaLearningModule')
        self.encryption_manager = EncryptionManager()
        self.data_module = DataModule()
        self.shared_memory = SharedMemory()
        self.input_shape = input_shape
        self.output_shape = output_shape
        self.agent_id = agent_id
        self.lock = threading.Lock()
        self.meta_model = self._build_meta_model()
        self.logger.info(f"MetaLearningModule initialized for agent {agent_id}.")

    def _build_meta_model(self):
        """
        Builds and compiles the meta-learning model.
        
        Returns:
            Model: A compiled Keras meta-learning model.
        """
        try:
            inputs = Input(shape=self.input_shape)
            x = Dense(64, activation='relu')(inputs)
            x = Dense(64, activation='relu')(x)
            outputs = Dense(self.output_shape, activation='softmax')(x)
            model = Model(inputs=inputs, outputs=outputs)
            model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy')
            self.logger.debug("Meta-learning model built and compiled successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error building meta-learning model: {e}", exc_info=True)
            raise

    def adapt_model(self, task_data):
        """
        Adapts the meta-model to a new task using few-shot learning.

        Args:
            task_data (tuple): A tuple containing (X_train, y_train).

        Returns:
            Model: The adapted model.
        """
        try:
            X_train, y_train = task_data
            adapted_model = self._clone_model(self.meta_model)
            adapted_model.compile(optimizer=Adam(learning_rate=0.01), loss='categorical_crossentropy')
            adapted_model.fit(X_train, y_train, epochs=1, verbose=0)
            self.logger.info("Meta-model adapted to new task successfully.")
            return adapted_model
        except Exception as e:
            self.logger.error(f"Error adapting model to new task: {e}", exc_info=True)
            raise

    def _clone_model(self, model):
        """
        Clones a Keras model including its weights.

        Args:
            model (Model): The model to clone.

        Returns:
            Model: The cloned model.
        """
        try:
            cloned_model = tf.keras.models.clone_model(model)
            cloned_model.set_weights(model.get_weights())
            self.logger.debug("Model cloned successfully.")
            return cloned_model
        except Exception as e:
            self.logger.error(f"Error cloning model: {e}", exc_info=True)
            raise

    def update_meta_model(self, task_adapted_model):
        """
        Updates the meta-model using the adapted model from a specific task.

        Args:
            task_adapted_model (Model): The model adapted to a specific task.
        """
        try:
            with self.lock:
                meta_weights = self.meta_model.get_weights()
                task_weights = task_adapted_model.get_weights()
                new_weights = [meta + 0.1 * (task - meta) for meta, task in zip(meta_weights, task_weights)]
                self.meta_model.set_weights(new_weights)
            self.logger.info("Meta-model updated successfully.")
        except Exception as e:
            self.logger.error(f"Error updating meta-model: {e}", exc_info=True)
            raise

    def perform_task(self, adapted_model, X_test):
        """
        Performs a task using the adapted model.

        Args:
            adapted_model (Model): The model adapted to the task.
            X_test (array): Test data.

        Returns:
            array: Predictions made by the adapted model.
        """
        try:
            predictions = adapted_model.predict(X_test)
            self.logger.info("Task performed successfully using adapted model.")
            return predictions
        except Exception as e:
            self.logger.error(f"Error performing task: {e}", exc_info=True)
            raise

    def serialize_meta_model(self):
        """
        Serializes the meta-model for storage or transmission.

        Returns:
            bytes: The serialized meta-model.
        """
        try:
            with self.lock:
                model_json = self.meta_model.to_json()
                model_weights = self.meta_model.get_weights()
                serialized_data = {
                    'model_json': model_json,
                    'model_weights': [w.tolist() for w in model_weights]
                }
                serialized_bytes = self.encryption_manager.encrypt_data(pickle.dumps(serialized_data))
            self.logger.debug("Meta-model serialized and encrypted successfully.")
            return serialized_bytes
        except Exception as e:
            self.logger.error(f"Error serializing meta-model: {e}", exc_info=True)
            raise

    def deserialize_meta_model(self, serialized_bytes):
        """
        Deserializes the meta-model from bytes.

        Args:
            serialized_bytes (bytes): The serialized meta-model bytes.
        """
        try:
            decrypted_data = self.encryption_manager.decrypt_data(serialized_bytes)
            serialized_data = pickle.loads(decrypted_data)
            with self.lock:
                model_json = serialized_data['model_json']
                model_weights = [np.array(w) for w in serialized_data['model_weights']]
                self.meta_model = model_from_json(model_json)
                self.meta_model.set_weights(model_weights)
                self.meta_model.compile(optimizer=Adam(learning_rate=0.001), loss='categorical_crossentropy')
            self.logger.debug("Meta-model deserialized and decrypted successfully.")
        except Exception as e:
            self.logger.error(f"Error deserializing meta-model: {e}", exc_info=True)
            raise

    def merge_meta_models(self, other_serialized_meta_model):
        """
        Merges another agent's meta-model with the current meta-model.

        Args:
            other_serialized_meta_model (bytes): Serialized meta-model from another agent.
        """
        try:
            decrypted_data = self.encryption_manager.decrypt_data(other_serialized_meta_model)
            serialized_data = pickle.loads(decrypted_data)
            other_model_json = serialized_data['model_json']
            other_model_weights = [np.array(w) for w in serialized_data['model_weights']]
            other_meta_model = model_from_json(other_model_json)
            other_meta_model.set_weights(other_model_weights)
            with self.lock:
                new_weights = []
                for self_w, other_w in zip(self.meta_model.get_weights(), other_meta_model.get_weights()):
                    new_weights.append((self_w + other_w) / 2)
                self.meta_model.set_weights(new_weights)
            self.logger.info("Meta-models merged successfully with another agent's meta-model.")
        except Exception as e:
            self.logger.error(f"Error merging meta-models: {e}", exc_info=True)
            raise

    def save_meta_model(self):
        """
        Saves the meta-model to shared memory securely.
        """
        try:
            meta_model_bytes = self.serialize_meta_model()
            key = f"meta_model_{self.agent_id}"
            self.shared_memory.write_data(key, meta_model_bytes, self.agent_id)
            self.logger.info(f"Meta-model saved to shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error saving meta-model: {e}", exc_info=True)
            raise

    def load_meta_model(self):
        """
        Loads the meta-model from shared memory securely.
        """
        try:
            key = f"meta_model_{self.agent_id}"
            meta_model_bytes = self.shared_memory.read_data(key, self.agent_id)
            if meta_model_bytes:
                self.deserialize_meta_model(meta_model_bytes)
                self.logger.info(f"Meta-model loaded from shared memory with key {key}.")
            else:
                self.logger.warning(f"No meta-model found in shared memory with key {key}.")
        except Exception as e:
            self.logger.error(f"Error loading meta-model: {e}", exc_info=True)
            raise
