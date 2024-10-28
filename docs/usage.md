# **Marvin Agent System Usage Guide**

## **Table of Contents**

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Running the Application](#running-the-application)
6. [User Interface Overview](#user-interface-overview)
   - [Dashboard](#dashboard)
   - [Agents](#agents)
   - [Logs](#logs)
   - [Notifications](#notifications)
   - [Settings](#settings)
7. [Using the API](#using-the-api)
8. [Troubleshooting](#troubleshooting)
9. [Support](#support)

---

## **Introduction**

This guide provides comprehensive instructions on how to install, configure, and use the Marvin Agent System. Whether you're a new user or an experienced developer, this document will help you navigate through the system's features effectively.

---

## **Prerequisites**

- **Operating System**: Linux (Ubuntu 20.04 LTS recommended), macOS, or Windows 10+
- **Python Version**: Python 3.9 or higher
- **Hardware Requirements**:
  - Minimum 8 GB RAM
  - Minimum 20 GB free disk space
- **Database**: PostgreSQL 13+
- **Additional Tools**:
  - Git
  - Docker and Docker Compose (for containerized deployment)

---

## **Installation**

### **1. Clone the Repository**

```bash
git clone https://github.com/yourusername/marvin-agent-system.git
cd marvin-agent-system
2. Create a Virtual Environment
bash
Copy code
python3 -m venv venv
source venv/bin/activate  # On Windows use venv\Scripts\activate
3. Install Dependencies
bash
Copy code
pip install -r requirements.txt
4. Install Frontend Assets
bash
Copy code
# Assuming Node.js and npm are installed
cd frontend
npm install
npm run build
cd ..
Configuration
1. Environment Variables
Create a .env file in the project root directory:

bash
Copy code
cp .env.example .env
Update the .env file with your specific configurations:

dotenv
Copy code
# .env
SECRET_KEY=your_secret_key
DATABASE_URL=postgresql://user:password@localhost:5432/marvin_db
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
2. Database Setup
bash
Copy code
# Create the PostgreSQL database
psql -U postgres
CREATE DATABASE marvin_db;
CREATE USER marvin_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE marvin_db TO marvin_user;
\q

# Run database migrations
flask db upgrade
3. SSL Configuration
For production environments, configure SSL certificates:

Option 1: Use Let's Encrypt for free SSL certificates.
Option 2: Use a self-signed certificate for testing purposes.
Running the Application
1. Start the Redis and RabbitMQ Services
bash
Copy code
# Using Docker Compose
docker-compose up -d redis rabbitmq
2. Start the Celery Worker
bash
Copy code
celery -A app.celery worker --loglevel=info
3. Run the Flask Application
bash
Copy code
flask run --host=0.0.0.0 --port=5000
User Interface Overview
Dashboard
Overview: Provides a summary of system status, agent performance, and recent activities.
Widgets: Customize widgets to display metrics relevant to your use case.
Agents
Manage Agents: Add, remove, or configure agents.
Agent Details: View performance metrics and logs specific to each agent.
Logs
System Logs: Monitor system-wide events and errors.
Filter and Search: Use filters to search logs by date, level, or agent.
Notifications
View Notifications: Access unread and read notifications.
Manage Preferences: Set notification preferences in settings.
Settings
Profile Settings: Update your user profile, including email and password.
System Settings: Configure application-wide settings (admin users only).
Using the API
Authentication
JWT Tokens: Obtain a JWT token by logging in via the /login endpoint.
Headers: Include the token in the Authorization header for subsequent requests.
Endpoints
GET /api/agents: Retrieve a list of agents.
POST /api/agents: Create a new agent.
GET /api/agents/{id}: Get details of a specific agent.
PUT /api/agents/{id}: Update an agent.
DELETE /api/agents/{id}: Delete an agent.
Refer to the API Reference for a complete list of endpoints and their usage.

Troubleshooting
Application Fails to Start:

Check Logs: Review the logs in logs/ directory for error messages.
Dependencies: Ensure all dependencies are installed correctly.
Database Connection Errors:

Configuration: Verify the DATABASE_URL in your .env file.
Database Service: Ensure PostgreSQL is running and accessible.
Unable to Authenticate:

JWT Tokens: Check the validity of your JWT token.
User Credentials: Verify your username and password.
Static Files Not Loading:

Asset Compilation: Ensure frontend assets are built using npm run build.
Flask Configuration: Confirm static_folder and static_url_path are set correctly.
Support
For further assistance:

Documentation: Refer to the Architecture and API Reference documents.
Issue Tracker: Submit issues on the project's GitHub repository.
Community Forum: Join the discussion on our community forum at forum.marvinagentsystem.com.
Contact: Email support at support@marvinagentsystem.com.
Document Version: 1.0.0
Last Updated: YYYY-MM-DD