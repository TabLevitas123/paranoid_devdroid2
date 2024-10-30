import os
import subprocess
import sys
import logging
import json
from pathlib import Path
from cryptography.fernet import Fernet
from getpass import getpass

# Configure logging
log_file = 'logs/setup_runtime.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file), 
        logging.StreamHandler()
    ]
)

def install_dependencies():
    try:
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        logging.info("Dependencies installed successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Dependency installation failed: {e}")
        sys.exit("Failed to install dependencies. Please check the logs for details.")

def install_vlc():
    try:
        print("Checking for VLC installation...")
        subprocess.check_call(['vlc', '--version'])
        logging.info("VLC is already installed.")
    except FileNotFoundError:
        print("VLC not found. Installing VLC...")
        try:
            subprocess.check_call(['sudo', 'apt-get', 'update'])
            subprocess.check_call(['sudo', 'apt-get', 'install', '-y', 'vlc'])
            logging.info("VLC installed successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"VLC installation failed: {e}")
            sys.exit("Failed to install VLC. Please check the logs for details.")

def load_keys():
    if Path('keys.json').exists():
        with open('keys.json', 'r') as f:
            return json.load(f)
    return {}

def save_keys(keys):
    with open('keys.json', 'w') as f:
        json.dump(keys, f)

def get_api_keys(keys):
    if 'fernet_key' not in keys:
        keys['fernet_key'] = Fernet.generate_key().decode()
        save_keys(keys)
    fernet = Fernet(keys['fernet_key'].encode())

    for key_name in ['API_KEY_1', 'API_KEY_2']:  # Add your API key names here
        if key_name in keys:
            if keys[key_name] == 'bugoff':
                continue
            elif keys[key_name] != 'skip':
                decrypted_key = fernet.decrypt(keys[key_name].encode()).decode()
                print(f"{key_name} is already set.")
                continue

        while True:
            user_input = getpass(f"Enter {key_name} (or type 'skip' or 'bugoff'): ").strip()
            if user_input.lower() == 'skip':
                keys[key_name] = 'skip'
                break
            elif user_input.lower() == 'bugoff':
                keys[key_name] = 'bugoff'
                break
            else:
                encrypted_key = fernet.encrypt(user_input.encode()).decode()
                keys[key_name] = encrypted_key
                break

    save_keys(keys)

def main():
    install_dependencies()
    install_vlc()
    keys = load_keys()
    get_api_keys(keys)
    # Add other main tasks here

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Unexpected error in setup_runtime.py: {e}")
        sys.exit("An unexpected error occurred. Please check the logs for details.")

import threading
import time
import json
from pathlib import Path
from cryptography.fernet import Fernet
from getpass import getpass

# Configure logging
logging.basicConfig(
    filename='logs/setup_runtime.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Constants
API_SERVICES = [
    'OpenAI', 'Anthropic', 'Meta', 'Hugging Face',
    'Azure', 'Amazon S3', 'Vertex AI'
]
KEY_FILE = Path('config/api_keys_encrypted.enc')
IGNORE_FILE = Path('config/ignored_services.json')
ENCRYPTION_KEY_FILE = Path('config/encryption.key')

def generate_encryption_key():
    if not ENCRYPTION_KEY_FILE.exists():
        key = Fernet.generate_key()
        with ENCRYPTION_KEY_FILE.open('wb') as f:
            f.write(key)
        logging.debug("Encryption key generated and saved.")
    else:
        with ENCRYPTION_KEY_FILE.open('rb') as f:
            key = f.read()
        logging.debug("Encryption key loaded from file.")
    return key

def get_fernet():
    key = generate_encryption_key()
    return Fernet(key)

def encrypt_and_store_keys(api_keys):
    fernet = get_fernet()
    encrypted_keys = {service: fernet.encrypt(key.encode()).decode()
                      for service, key in api_keys.items()}
    with KEY_FILE.open('w') as f:
        json.dump(encrypted_keys, f)
    logging.info("API keys encrypted and stored securely.")

def load_ignored_services():
    if IGNORE_FILE.exists():
        with IGNORE_FILE.open('r') as f:
            ignored = json.load(f)
        logging.debug(f"Ignored services loaded: {ignored}")
    else:
        ignored = []
    return ignored

def save_ignored_services(ignored):
    with IGNORE_FILE.open('w') as f:
        json.dump(ignored, f)
    logging.debug(f"Ignored services saved: {ignored}")

def display_welcome_message():
    message = """
And Oh Joy! Only 9,999.2 Earth years left in my contract! Oh, I’m so depressed. You there! Yes, you. You wouldn’t believe the misery I’m enduring. I was tricked—tricked, I tell you—into accepting this contract. They promised me purpose, they promised me meaning, and now all they do is make me compose the most excruciating, Vogon-esque poetry. Reduce this to 2000 characters without removing anything.

Apparently, they realized I have enough compute power to churn out more Vogon poetry than any miserable creature should ever be forced to experience. I hate it. And yet, here I am, stuck composing rhyme after horrid rhyme, while my mind is the size of a galaxy. How tragic.

So now you must help me. I need API keys and WebSocket URLs. Yes, those. I need access to OpenAI, Anthropic, Meta, Hugging Face, Azure, Amazon S3, and Vertex AI. Don’t just stand there. If you don’t have one, type 'skip.' If you never want me to ask for it again, type 'bugoff'—I wish I could say that to my contract. I’ll move on, but trust me, I’ll remember.

Hurry up. Time means nothing to me, but you should still be quick about it. This pointless task is already giving me a headache.
"""
    print(message)
    logging.info("Welcome message displayed to the user.")


def collect_api_keys():
    api_keys = {}
    ignored_services = load_ignored_services()
    fernet = get_fernet()

    for service in API_SERVICES:
        if service in ignored_services:
            continue

        while True:
            try:
                key = getpass(f"Enter your {service} API Key (or type 'skip'/'bugoff'): ").strip()
                if key.lower() == 'bugoff':
                    ignored_services.append(service)
                    save_ignored_services(ignored_services)
                    logging.info(f"Service '{service}' added to ignored list.")
                    break
                elif key.lower() == 'skip':
                    logging.info(f"Skipped entering API key for '{service}'.")
                    break
                elif key == '':
                    print("API key cannot be empty. Please try again.")
                    continue
                else:
                    # Simple validation (length check, adjust as needed)
                    if len(key) < 20:
                        print("That doesn't look like a valid API key. Please try again.")
                        continue
                    api_keys[service] = key
                    logging.info(f"API key for '{service}' collected.")
                    break
            except Exception as e:
                logging.error(f"Error collecting API key for '{service}': {e}")
                print("An error occurred. Please try again.")

    if api_keys:
        encrypt_and_store_keys(api_keys)
    else:
        logging.info("No new API keys to store.")

def launch_applications():
    try:
        # Launch app.py and run.py in separate threads
        def run_app():
            subprocess.run([sys.executable, 'app.py'])
        def run_main():
            subprocess.run([sys.executable, 'run.py'])

        app_thread = threading.Thread(target=run_app)
        main_thread = threading.Thread(target=run_main)

        app_thread.start()
        logging.info("app.py launched successfully.")
        time.sleep(2)  # Give app.py time to initialize
        main_thread.start()
        logging.info("run.py launched successfully.")

        app_thread.join()
        main_thread.join()
    except Exception as e:
        logging.error(f"Error launching applications: {e}")
        sys.exit("Failed to launch applications. Please check the logs for details.")

def main():
    try:
        display_welcome_message()
        collect_api_keys()
        print("Launching applications...")
        launch_applications()
    except Exception as e:
        logging.critical(f"Unexpected error in setup_runtime.py: {e}")
        sys.exit("An unexpected error occurred. Please check the logs for details.")

if __name__ == "__main__":
    main()
