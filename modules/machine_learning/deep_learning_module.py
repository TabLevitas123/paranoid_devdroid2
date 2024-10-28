# deep_learning_module.py

import logging
import threading
import tempfile
import os
import tensorflow as tf
from tensorflow.python.keras.models import Sequential, Model, load_model
from tensorflow.python.keras.layers import Dense, Dropout, Conv2D, MaxPooling2D, Flatten, Input
from tensorflow.python.keras.callbacks import EarlyStopping, ModelCheckpoint
from tensorflow.python.keras.optimizers import Adam
from modules.utilities.logging_manager import setup_logging
from modules.security.encryption_manager import EncryptionManager
from modules.data.data_module import DataModule

class DeepLearningModule:
    """
    Provides deep learning functionalities using TensorFlow and Keras.
    """

    def __init__(self):
        self.logger = setup_logging('DeepLearningModule')
        self.encryption_manager = EncryptionManager()
        self.data_module = DataModule()
        self.lock = threading.Lock()
        self.logger.info("DeepLearningModule initialized successfully.")

    def define_model_architecture(self, input_shape, num_classes, architecture='MLP'):
        """
        Defines a neural network architecture.

        Args:
            input_shape (tuple): Shape of the input data.
            num_classes (int): Number of output classes.
            architecture (str): Type of architecture ('MLP', 'CNN').

        Returns:
            model: Uncompiled Keras model.
        """
        try:
            self.logger.info(f"Defining {architecture} model architecture.")
            if architecture == 'MLP':
                model = Sequential([
                    Dense(128, activation='relu', input_shape=input_shape),
                    Dropout(0.2),
                    Dense(64, activation='relu'),
                    Dropout(0.2),
                    Dense(num_classes, activation='softmax')
                ])
            elif architecture == 'CNN':
                model = Sequential([
                    Conv2D(32, kernel_size=(3, 3), activation='relu', input_shape=input_shape),
                    MaxPooling2D(pool_size=(2, 2)),
                    Conv2D(64, kernel_size=(3, 3), activation='relu'),
                    MaxPooling2D(pool_size=(2, 2)),
                    Flatten(),
                    Dense(128, activation='relu'),
                    Dropout(0.5),
                    Dense(num_classes, activation='softmax')
                ])
            else:
                self.logger.error(f"Unsupported architecture type: {architecture}")
                raise ValueError(f"Unsupported architecture type: {architecture}")
            self.logger.info(f"{architecture} model architecture defined successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error defining model architecture: {e}", exc_info=True)
            raise

    def train_model(self, model, X_train, y_train, X_val=None, y_val=None, epochs=50, batch_size=32, optimizer='adam', loss='categorical_crossentropy'):
        """
        Trains the deep learning model.

        Args:
            model: Uncompiled Keras model.
            X_train (array-like): Training feature data.
            y_train (array-like): Training labels.
            X_val (array-like): Validation feature data.
            y_val (array-like): Validation labels.
            epochs (int): Number of training epochs.
            batch_size (int): Batch size for training.
            optimizer (str): Optimizer to use.
            loss (str): Loss function to use.

        Returns:
            model: Trained Keras model.
            history: Training history object.
        """
        try:
            self.logger.info("Compiling the model.")
            model.compile(optimizer=optimizer, loss=loss, metrics=['accuracy'])
            callbacks = [
                EarlyStopping(monitor='val_loss', patience=5, verbose=1, restore_best_weights=True),
                ModelCheckpoint('best_model.h5', save_best_only=True, monitor='val_loss', verbose=1)
            ]
            self.logger.info("Starting model training.")
            with self.lock:
                history = model.fit(
                    X_train, y_train,
                    validation_data=(X_val, y_val) if X_val is not None and y_val is not None else None,
                    epochs=epochs,
                    batch_size=batch_size,
                    callbacks=callbacks,
                    verbose=1
                )
            self.logger.info("Model trained successfully.")
            return model, history
        except Exception as e:
            self.logger.error(f"Error training model: {e}", exc_info=True)
            raise

    def evaluate_model(self, model, X_test, y_test):
        """
        Evaluates the deep learning model.

        Args:
            model: Trained Keras model.
            X_test (array-like): Test feature data.
            y_test (array-like): Test labels.

        Returns:
            dict: Evaluation metrics including loss and accuracy.
        """
        try:
            self.logger.info("Evaluating the model.")
            results = model.evaluate(X_test, y_test, verbose=1)
            evaluation = {'loss': results[0], 'accuracy': results[1]}
            self.logger.info(f"Model evaluation completed with loss: {evaluation['loss']}, accuracy: {evaluation['accuracy']}")
            return evaluation
        except Exception as e:
            self.logger.error(f"Error evaluating model: {e}", exc_info=True)
            raise

    def run_inference(self, model, X_input):
        """
        Runs inference using the trained model.

        Args:
            model: Trained Keras model.
            X_input (array-like): Input data for inference.

        Returns:
            array: Inference results.
        """
        try:
            self.logger.info("Running inference.")
            predictions = model.predict(X_input)
            self.logger.debug(f"Inference results: {predictions}")
            return predictions
        except Exception as e:
            self.logger.error(f"Error during inference: {e}", exc_info=True)
            raise

    def optimize_model(self, model):
        """
        Optimizes the model for better performance.

        Args:
            model: Trained Keras model.

        Returns:
            model: Optimized Keras model.
        """
        try:
            self.logger.info("Optimizing the model.")
            converter = tf.lite.TFLiteConverter.from_keras_model(model)
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            tflite_model = converter.convert()
            self.logger.info("Model optimized successfully.")
            return tflite_model
        except Exception as e:
            self.logger.error(f"Error optimizing model: {e}", exc_info=True)
            raise

    def serialize_model(self, model):
        """
        Serializes the Keras model.

        Args:
            model: Keras model to serialize.

        Returns:
            bytes: Serialized model bytes.
        """
        try:
            self.logger.info("Serializing the model.")
            with self.lock:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.h5') as tmp_file:
                    model.save(tmp_file.name)
                    tmp_file.seek(0)
                    serialized_model = tmp_file.read()
                os.unlink(tmp_file.name)
            self.logger.info("Model serialized successfully.")
            return serialized_model
        except Exception as e:
            self.logger.error(f"Error serializing model: {e}", exc_info=True)
            raise

    def deserialize_model(self, serialized_model):
        """
        Deserializes the Keras model.

        Args:
            serialized_model (bytes): Serialized model bytes.

        Returns:
            model: Deserialized Keras model.
        """
        try:
            self.logger.info("Deserializing the model.")
            with self.lock:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.h5') as tmp_file:
                    tmp_file.write(serialized_model)
                    tmp_file.flush()
                    model = load_model(tmp_file.name)
                os.unlink(tmp_file.name)
            self.logger.info("Model deserialized successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error deserializing model: {e}", exc_info=True)
            raise

    def update_model(self, model, X_new, y_new, epochs=5, batch_size=32):
        """
        Updates the model with new data for continuous learning.

        Args:
            model: Trained Keras model.
            X_new (array-like): New feature data.
            y_new (array-like): New labels.
            epochs (int): Number of training epochs.
            batch_size (int): Batch size for training.

        Returns:
            model: Updated Keras model.
        """
        try:
            self.logger.info("Updating the model with new data.")
            with self.lock:
                model.fit(X_new, y_new, epochs=epochs, batch_size=batch_size, verbose=1)
            self.logger.info("Model updated successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error updating model: {e}", exc_info=True)
            raise

    def perform_transfer_learning(self, base_model, num_classes, freeze_layers=True):
        """
        Performs transfer learning using a pre-trained model.

        Args:
            base_model: Pre-trained Keras model.
            num_classes (int): Number of output classes.
            freeze_layers (bool): Whether to freeze base model layers.

        Returns:
            model: Modified Keras model ready for fine-tuning.
        """
        try:
            self.logger.info("Performing transfer learning.")
            if freeze_layers:
                for layer in base_model.layers:
                    layer.trainable = False
            x = base_model.output
            x = Flatten()(x) if len(x.shape) > 2 else x
            x = Dense(256, activation='relu')(x)
            x = Dropout(0.5)(x)
            predictions = Dense(num_classes, activation='softmax')(x)
            model = Model(inputs=base_model.input, outputs=predictions)
            self.logger.info("Transfer learning model prepared successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error performing transfer learning: {e}", exc_info=True)
            raise

    def save_model(self, model, file_path):
        """
        Saves the model to a specified file path.

        Args:
            model: Keras model to save.
            file_path (str): Path to save the model.

        Returns:
            bool: True if the model is saved successfully, False otherwise.
        """
        try:
            self.logger.info(f"Saving model to {file_path}.")
            model.save(file_path)
            self.logger.info("Model saved successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error saving model: {e}", exc_info=True)
            return False

    def load_model(self, file_path):
        """
        Loads a model from a specified file path.

        Args:
            file_path (str): Path to the model file.

        Returns:
            model: Loaded Keras model.
        """
        try:
            self.logger.info(f"Loading model from {file_path}.")
            model = load_model(file_path)
            self.logger.info("Model loaded successfully.")
            return model
        except Exception as e:
            self.logger.error(f"Error loading model: {e}", exc_info=True)
            raise
