# __init__.py

import os
from typing import Any, Dict
from flask import Flask, render_template, Request, redirect, url_for, jsonify
from flask_wtf import CSRFProtect
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from modules.communication.communication_module import CommunicationModule, CommunicationModuleError
from modules.security.encryption_manager import EncryptionManager
from modules.utilities.logging_manager import setup_logging

# Initialize Logging
logger = setup_logging('FlaskApp')

# Initialize Flask App
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'Replace_With_A_Strong_Secret_Key'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI') or 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
csrf = CSRFProtect(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize Communication Module
communication_module = CommunicationModule()

# User Model for Authentication
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password) -> bool:
        return check_password_hash(self.password_hash, password)

# Load User Callback
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes

@app.route('/')
def index():
    """
    Landing page route.
    """
    try:
        logger.info("Rendering index.html")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index.html: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred while loading the page."), 500

@app.route('/dashboard')
@login_required
def dashboard():
    """
    Dashboard page route, accessible only to authenticated users.
    """
    try:
        logger.info(f"User {current_user.username} accessing dashboard.")
        # Fetch relevant data for dashboard
        metrics = get_system_metrics()
        return render_template('dashboard.html', metrics=metrics)
    except Exception as e:
        logger.error(f"Error rendering dashboard.html: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred while loading the dashboard."), 500

@app.route('/metrics')
@login_required
def metrics():
    """
    Metrics page route, displays system metrics.
    """
    try:
        logger.info(f"User {current_user.username} accessing metrics.")
        metrics = get_system_metrics()
        return render_template('metrics.html', metrics=metrics)
    except Exception as e:
        logger.error(f"Error rendering metrics.html: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred while loading the metrics."), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    User login route.
    """
    if Request.method == 'POST':
        try:
            username = Request.form['username']
            password = Request.form['password']
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                logger.info(f"User {username} logged in successfully.")
                return redirect(url_for('dashboard'))
            else:
                logger.warning(f"Failed login attempt for username: {username}")
                return render_template('login.html', error="Invalid username or password.")
        except Exception as e:
            logger.error(f"Error during login: {e}", exc_info=True)
            return render_template('error.html', message="An error occurred during login."), 500
    else:
        return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """
    User logout route.
    """
    try:
        logger.info(f"User {current_user.username} logging out.")
        logout_user()
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error during logout: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred during logout."), 500

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    """
    API endpoint to send messages between agents.
    """
    try:
        data = Request.get_json()
        sender_id = current_user.id
        receiver_id = data.get('receiver_id')
        message_type = data.get('message_type')
        content = data.get('content')
        
        if not receiver_id or not message_type or not content:
            logger.warning("Missing fields in send_message API request.")
            return jsonify({"error": "Missing required fields."}), 400
        
        communication_module.send_message(
            sender_id=str(sender_id),
            receiver_id=str(receiver_id),
            message_type=message_type,
            content=content
        )
        logger.info(f"Message sent from {sender_id} to {receiver_id} of type {message_type}.")
        return jsonify({"status": "Message sent successfully."}), 200
    except CommunicationModuleError as e:
        logger.error(f"Communication error: {e}", exc_info=True)
        return jsonify({"error": "Failed to send message."}), 500
    except Exception as e:
        logger.error(f"Error in send_message API: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500

@app.route('/api/receive_message', methods=['GET'])
@login_required
def receive_message():
    """
    API endpoint to receive messages for the current user.
    """
    try:
        receiver_id = current_user.id
        message_type_filter = Request.args.get('message_type')
        timeout = float(Request.args.get('timeout', 5))
        
        message = communication_module.receive_message(
            receiver_id=str(receiver_id),
            message_type_filter=message_type_filter,
            timeout=timeout
        )
        
        if message:
            logger.info(f"Message {message['message_id']} received by {receiver_id}.")
            return jsonify({"message": message}), 200
        else:
            logger.info(f"No message received for {receiver_id} within timeout.")
            return jsonify({"message": None}), 200
    except CommunicationModuleError as e:
        logger.error(f"Communication error: {e}", exc_info=True)
        return jsonify({"error": "Failed to receive message."}), 500
    except Exception as e:
        logger.error(f"Error in receive_message API: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred."}), 500

# Helper Functions

def get_system_metrics() -> Dict[str, Any]:
    """
    Retrieves system metrics for dashboard display.
    
    Returns:
        Dict[str, Any]: A dictionary containing system metrics.
    """
    try:
        # Placeholder for actual metric retrieval logic
        metrics = {
            "cpu_usage": "15%",
            "memory_usage": "45%",
            "disk_space": "70%",
            "active_agents": 5,
            "tasks_processed": 120
        }
        logger.debug(f"System metrics retrieved: {metrics}")
        return metrics
    except Exception as e:
        logger.error(f"Failed to retrieve system metrics: {e}", exc_info=True)
        return {}

# Error Handlers

@app.errorhandler(404)
def page_not_found(e):
    """
    Handler for 404 Not Found errors.
    """
    logger.warning(f"404 error encountered: {e}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    """
    Handler for 500 Internal Server errors.
    """
    logger.error(f"500 error encountered: {e}", exc_info=True)
    return render_template('500.html'), 500

# Run the App
if __name__ == '__main__':
    try:
        # Ensure database tables are created
        with app.app_context():
            db.create_all()
        # Run the Flask development server
        app.run(host='0.0.0.0', port=5000, debug=False, ssl_context='adhoc')
    except Exception as e:
        logger.critical(f"Failed to start the Flask application: {e}", exc_info=True)
