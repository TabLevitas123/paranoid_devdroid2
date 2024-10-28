# services/virtual_assistant_service.py

import logging
import threading
from typing import Any, Dict, List, Optional, Union, Callable
import os

import requests
import speech_recognition_service as sr
import pyttsx3
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from transformers import pipeline
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class VirtualAssistantServiceError(Exception):
    """Custom exception for VirtualAssistantService-related errors."""
    pass


class VirtualAssistantService:
    """
    Provides virtual assistant capabilities, including speech recognition, natural language processing,
    task execution, and interactive responses. Utilizes libraries like SpeechRecognition, pyttsx3,
    NLTK, and transformers to ensure comprehensive assistant functionalities. Ensures secure handling
    of user data and interactions.
    """

    def __init__(self):
        """
        Initializes the VirtualAssistantService with necessary configurations and authentication.
        """
        self.logger = setup_logging('VirtualAssistantService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.engine = pyttsx3.init()
        self.nlp_pipeline = self._initialize_nlp_pipeline()
        self.lemmatizer = WordNetLemmatizer()
        nltk.download('punkt')
        nltk.download('stopwords')
        nltk.download('wordnet')
        self.logger.info("VirtualAssistantService initialized successfully.")

    def _initialize_nlp_pipeline(self) -> Any:
        """
        Initializes the NLP pipeline using transformers for natural language understanding.

        Returns:
            Any: The initialized NLP pipeline.
        """
        try:
            self.logger.debug("Initializing NLP pipeline using transformers.")
            nlp = pipeline('conversational', model='microsoft/DialoGPT-medium')
            self.logger.debug("NLP pipeline initialized successfully.")
            return nlp
        except Exception as e:
            self.logger.error(f"Error initializing NLP pipeline: {e}", exc_info=True)
            raise VirtualAssistantServiceError(f"Error initializing NLP pipeline: {e}")

    def listen(self) -> Optional[str]:
        """
        Listens to the user's speech input and converts it to text.

        Returns:
            Optional[str]: The transcribed text, or None if recognition fails.
        """
        try:
            self.logger.debug("Listening for user input.")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                audio = self.recognizer.listen(source, phrase_time_limit=5)
            self.logger.debug("Processing audio input.")
            text = self.recognizer.recognize_google(audio)
            self.logger.info(f"User said: {text}.")
            return text
        except sr.UnknownValueError:
            self.logger.warning("Speech recognition could not understand audio.")
            return None
        except sr.RequestError as e:
            self.logger.error(f"Could not request results from Speech Recognition service; {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error during speech recognition: {e}", exc_info=True)
            return None

    def respond(self, response_text: str) -> bool:
        """
        Converts text to speech and speaks it aloud.

        Args:
            response_text (str): The text to be spoken.

        Returns:
            bool: True if response is spoken successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Responding with text: {response_text}.")
            with self.lock:
                self.engine.say(response_text)
                self.engine.runAndWait()
            self.logger.info("Response spoken successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Error during text-to-speech conversion: {e}", exc_info=True)
            return False

    def process_command(self, command: str) -> bool:
        """
        Processes a user command by understanding intent and executing corresponding actions.

        Args:
            command (str): The user's command text.

        Returns:
            bool: True if command is processed successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Processing command: {command}.")
            tokens = word_tokenize(command.lower())
            tokens = [self.lemmatizer.lemmatize(word) for word in tokens if word.isalnum()]
            stop_words = set(stopwords.words('english'))
            filtered_tokens = [word for word in tokens if word not in stop_words]
            self.logger.debug(f"Filtered tokens: {filtered_tokens}.")

            if not filtered_tokens:
                self.logger.warning("No actionable words found in the command.")
                self.respond("I'm sorry, I didn't catch that. Could you please repeat?")
                return False

            intent = self._determine_intent(filtered_tokens)
            self.logger.debug(f"Determined intent: {intent}.")

            if intent == 'greeting':
                self.respond("Hello! How can I assist you today?")
            elif intent == 'goodbye':
                self.respond("Goodbye! Have a great day!")
            elif intent == 'time':
                from datetime import datetime
                current_time = datetime.now().strftime("%H:%M:%S")
                self.respond(f"The current time is {current_time}.")
            elif intent == 'weather':
                self._handle_weather_command(filtered_tokens)
            elif intent == 'joke':
                self._handle_joke_command()
            else:
                self.respond("I'm not sure how to help with that. Could you please elaborate?")
                return False

            return True
        except Exception as e:
            self.logger.error(f"Error processing command '{command}': {e}", exc_info=True)
            self.respond("Sorry, I encountered an error while processing your request.")
            return False

    def _determine_intent(self, tokens: List[str]) -> str:
        """
        Determines the user's intent based on the tokens extracted from the command.

        Args:
            tokens (List[str]): The list of tokens from the user's command.

        Returns:
            str: The determined intent.
        """
        greetings = {'hello', 'hi', 'hey', 'greetings'}
        farewells = {'bye', 'goodbye', 'see', 'later'}
        time_intents = {'time', 'clock', 'current'}
        weather_intents = {'weather', 'rain', 'sunny', 'forecast'}
        joke_intents = {'joke', 'funny'}

        if any(word in greetings for word in tokens):
            return 'greeting'
        elif any(word in farewells for word in tokens):
            return 'goodbye'
        elif any(word in time_intents for word in tokens):
            return 'time'
        elif any(word in weather_intents for word in tokens):
            return 'weather'
        elif any(word in joke_intents for word in tokens):
            return 'joke'
        else:
            return 'unknown'

    def _handle_weather_command(self, tokens: List[str]) -> bool:
        """
        Handles weather-related commands by fetching weather data from an API.

        Args:
            tokens (List[str]): The list of tokens from the user's command.

        Returns:
            bool: True if weather data is fetched and responded successfully, False otherwise.
        """
        try:
            self.logger.debug("Handling weather command.")
            # Extract location from tokens, assuming the last token is the location
            location = tokens[-1] if tokens else 'your location'
            api_config = self.config_loader.get('WEATHER_API_CONFIG', {})
            api_key_encrypted = api_config.get('api_key')
            if not api_key_encrypted:
                self.logger.error("Weather API key not found in configuration.")
                self.respond("Weather service is currently unavailable.")
                return False
            api_key = self.encryption_manager.decrypt_data(api_key_encrypted).decode('utf-8')
            base_url = api_config.get('base_url', 'http://api.openweathermap.org/data/2.5/weather')
            params = {
                'q': location,
                'appid': api_key,
                'units': 'metric'
            }
            response = requests.get(base_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                weather_desc = data['weather'][0]['description']
                temperature = data['main']['temp']
                self.respond(f"The current weather in {location} is {weather_desc} with a temperature of {temperature} degrees Celsius.")
                self.logger.info(f"Weather data for '{location}' retrieved successfully.")
                return True
            else:
                self.logger.error(f"Failed to fetch weather data: {response.text}")
                self.respond(f"Sorry, I couldn't retrieve the weather for {location}.")
                return False
        except Exception as e:
            self.logger.error(f"Error handling weather command: {e}", exc_info=True)
            self.respond("Sorry, I encountered an error while fetching the weather.")
            return False

    def _handle_joke_command(self) -> bool:
        """
        Handles joke-related commands by fetching a joke from an API.

        Returns:
            bool: True if a joke is fetched and responded successfully, False otherwise.
        """
        try:
            self.logger.debug("Handling joke command.")
            response = requests.get('https://official-joke-api.appspot.com/random_joke', timeout=10)
            if response.status_code == 200:
                joke = response.json()
                joke_text = f"Here's a joke for you: {joke['setup']} ... {joke['punchline']}"
                self.respond(joke_text)
                self.logger.info("Joke fetched and responded successfully.")
                return True
            else:
                self.logger.error(f"Failed to fetch joke: {response.text}")
                self.respond("Sorry, I couldn't fetch a joke at this time.")
                return False
        except Exception as e:
            self.logger.error(f"Error handling joke command: {e}", exc_info=True)
            self.respond("Sorry, I encountered an error while fetching a joke.")
            return False

    def run(self):
        """
        Runs the virtual assistant, continuously listening for user input and responding accordingly.
        """
        try:
            self.logger.debug("Virtual assistant is now running.")
            self.respond("Hello! I am your virtual assistant. How can I help you today?")
            while True:
                command = self.listen()
                if command:
                    self.process_command(command)
        except KeyboardInterrupt:
            self.logger.info("Virtual assistant has been stopped manually.")
        except Exception as e:
            self.logger.error(f"Error running virtual assistant: {e}", exc_info=True)
            self.respond("Sorry, I encountered an unexpected error.")
    
    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing VirtualAssistantService resources.")
            self.engine.stop()
            self.logger.info("VirtualAssistantService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing VirtualAssistantService: {e}", exc_info=True)
            raise VirtualAssistantServiceError(f"Error closing VirtualAssistantService: {e}")
