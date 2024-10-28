# services/iot_control_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Callable
import os
import json
import paho.mqtt.client as mqtt
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class IoTControlServiceError(Exception):
    """Custom exception for IoTControlService-related errors."""
    pass


class IoTControlService:
    """
    Provides IoT device control capabilities, including sending commands to IoT devices,
    subscribing to device topics for status updates, managing device states, and handling
    real-time communication using MQTT. Utilizes the paho-mqtt library for MQTT interactions
    to ensure reliable and secure IoT device management.
    """

    def __init__(self):
        """
        Initializes the IoTControlService with necessary configurations and authentication.
        """
        self.logger = setup_logging('IoTControlService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.devices: Dict[str, Dict[str, Any]] = {}  # Mapping of device IDs to their configurations
        self.callbacks: Dict[str, Callable[[str, Any], None]] = {}  # Device ID to callback function
        self._initialize_mqtt()
        self.logger.info("IoTControlService initialized successfully.")

    def _initialize_mqtt(self):
        """
        Initializes the MQTT client and connects to the MQTT broker.
        """
        try:
            self.logger.debug("Initializing MQTT client.")
            mqtt_config = self.config_loader.get('MQTT_CONFIG', {})
            broker_address_encrypted = mqtt_config.get('broker_address')
            broker_port = mqtt_config.get('broker_port', 1883)
            username_encrypted = mqtt_config.get('username')
            password_encrypted = mqtt_config.get('password')

            if not broker_address_encrypted:
                self.logger.error("MQTT broker address not provided in configuration.")
                raise IoTControlServiceError("MQTT broker address not provided in configuration.")

            broker_address = self.encryption_manager.decrypt_data(broker_address_encrypted).decode('utf-8')
            username = self.encryption_manager.decrypt_data(username_encrypted).decode('utf-8') if username_encrypted else None
            password = self.encryption_manager.decrypt_data(password_encrypted).decode('utf-8') if password_encrypted else None

            self.client = mqtt.Client()
            if username and password:
                self.client.username_pw_set(username, password)

            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect

            self.client.connect(broker_address, broker_port, keepalive=60)
            self.client.loop_start()
            self.logger.debug("MQTT client initialized and connected.")
        except Exception as e:
            self.logger.error(f"Error initializing MQTT client: {e}", exc_info=True)
            raise IoTControlServiceError(f"Error initializing MQTT client: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        """
        Callback when the MQTT client connects to the broker.
        """
        if rc == 0:
            self.logger.info("Connected to MQTT broker successfully.")
            # Subscribe to all device status topics
            for device_id, device_info in self.devices.items():
                topic = device_info.get('status_topic')
                if topic:
                    self.client.subscribe(topic)
                    self.logger.debug(f"Subscribed to topic '{topic}' for device '{device_id}'.")
        else:
            self.logger.error(f"Failed to connect to MQTT broker. Return code: {rc}")

    def _on_message(self, client, userdata, msg):
        """
        Callback when a message is received from the MQTT broker.
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            self.logger.debug(f"Received message on topic '{topic}': {payload}")
            # Identify the device based on the topic
            for device_id, device_info in self.devices.items():
                if topic == device_info.get('status_topic'):
                    callback = self.callbacks.get(device_id)
                    if callback:
                        data = json.loads(payload)
                        callback(device_id, data)
                        self.logger.debug(f"Executed callback for device '{device_id}'.")
                    else:
                        self.logger.warning(f"No callback registered for device '{device_id}'.")
        except Exception as e:
            self.logger.error(f"Error processing incoming MQTT message: {e}", exc_info=True)

    def _on_disconnect(self, client, userdata, rc):
        """
        Callback when the MQTT client disconnects from the broker.
        """
        self.logger.warning(f"Disconnected from MQTT broker with return code {rc}. Attempting to reconnect.")
        try:
            self.client.reconnect()
        except Exception as e:
            self.logger.error(f"Reconnection attempt failed: {e}", exc_info=True)

    def register_device(self, device_id: str, control_topic: str, status_topic: str, callback: Callable[[str, Any], None]) -> bool:
        """
        Registers an IoT device for control and status monitoring.

        Args:
            device_id (str): The unique identifier of the device.
            control_topic (str): The MQTT topic to send control commands to the device.
            status_topic (str): The MQTT topic to subscribe for status updates from the device.
            callback (Callable[[str, Any], None]): The callback function to handle status updates.

        Returns:
            bool: True if the device is registered successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Registering device '{device_id}' with control topic '{control_topic}' and status topic '{status_topic}'.")
            with self.lock:
                if device_id in self.devices:
                    self.logger.error(f"Device '{device_id}' is already registered.")
                    return False
                self.devices[device_id] = {
                    'control_topic': control_topic,
                    'status_topic': status_topic
                }
                self.callbacks[device_id] = callback
                # Subscribe to the status topic
                self.client.subscribe(status_topic)
                self.logger.info(f"Device '{device_id}' registered and subscribed to status topic '{status_topic}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error registering device '{device_id}': {e}", exc_info=True)
            return False

    def unregister_device(self, device_id: str) -> bool:
        """
        Unregisters an IoT device, stopping control and status monitoring.

        Args:
            device_id (str): The unique identifier of the device.

        Returns:
            bool: True if the device is unregistered successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Unregistering device '{device_id}'.")
            with self.lock:
                device_info = self.devices.pop(device_id, None)
                callback = self.callbacks.pop(device_id, None)
                if device_info:
                    self.client.unsubscribe(device_info.get('status_topic'))
                    self.logger.info(f"Device '{device_id}' unregistered and unsubscribed from status topic '{device_info.get('status_topic')}'.")
                    return True
                else:
                    self.logger.warning(f"Device '{device_id}' is not registered.")
                    return False
        except Exception as e:
            self.logger.error(f"Error unregistering device '{device_id}': {e}", exc_info=True)
            return False

    def send_command(self, device_id: str, command: Dict[str, Any]) -> bool:
        """
        Sends a control command to a specified IoT device.

        Args:
            device_id (str): The unique identifier of the device.
            command (Dict[str, Any]): The command data to send to the device.

        Returns:
            bool: True if the command is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Sending command to device '{device_id}': {command}.")
            with self.lock:
                device_info = self.devices.get(device_id)
                if not device_info:
                    self.logger.error(f"Device '{device_id}' is not registered.")
                    return False
                control_topic = device_info.get('control_topic')
                if not control_topic:
                    self.logger.error(f"Control topic for device '{device_id}' is not defined.")
                    return False
                payload = json.dumps(command)
                self.client.publish(control_topic, payload)
                self.logger.info(f"Command sent to device '{device_id}' on topic '{control_topic}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error sending command to device '{device_id}': {e}", exc_info=True)
            return False

    def list_registered_devices(self) -> List[str]:
        """
        Retrieves a list of all registered IoT devices.

        Returns:
            List[str]: A list of device IDs.
        """
        try:
            with self.lock:
                device_list = list(self.devices.keys())
            self.logger.debug(f"Registered devices: {device_list}.")
            return device_list
        except Exception as e:
            self.logger.error(f"Error listing registered devices: {e}", exc_info=True)
            return []

    def subscribe_to_device_status(self, device_id: str, callback: Callable[[str, Any], None]) -> bool:
        """
        Subscribes to a device's status updates with a specific callback.

        Args:
            device_id (str): The unique identifier of the device.
            callback (Callable[[str, Any], None]): The callback function to handle status updates.

        Returns:
            bool: True if subscription is successful, False otherwise.
        """
        try:
            self.logger.debug(f"Subscribing to status updates for device '{device_id}'.")
            with self.lock:
                if device_id not in self.devices:
                    self.logger.error(f"Device '{device_id}' is not registered.")
                    return False
                self.callbacks[device_id] = callback
                status_topic = self.devices[device_id].get('status_topic')
                self.client.subscribe(status_topic)
                self.logger.info(f"Subscribed to status topic '{status_topic}' for device '{device_id}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error subscribing to device '{device_id}' status: {e}", exc_info=True)
            return False

    def publish_broadcast_command(self, command: Dict[str, Any], topic: str = 'iot/control/broadcast') -> bool:
        """
        Publishes a broadcast command to all IoT devices.

        Args:
            command (Dict[str, Any]): The command data to broadcast.
            topic (str, optional): The MQTT topic to publish the broadcast. Defaults to 'iot/control/broadcast'.

        Returns:
            bool: True if the broadcast command is sent successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Publishing broadcast command: {command} on topic '{topic}'.")
            payload = json.dumps(command)
            self.client.publish(topic, payload)
            self.logger.info(f"Broadcast command published on topic '{topic}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error publishing broadcast command: {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing IoTControlService resources.")
            with self.lock:
                for device_id in list(self.devices.keys()):
                    self.unregister_device(device_id)
                self.client.disconnect()
                self.client.loop_stop()
            self.logger.info("IoTControlService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing IoTControlService: {e}", exc_info=True)
            raise IoTControlServiceError(f"Error closing IoTControlService: {e}")
