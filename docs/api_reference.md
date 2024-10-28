
---

# **3. `docs/api_reference.md`**

```markdown
# **Marvin Agent System API Reference**

## **Table of Contents**

1. [Introduction](#introduction)
2. [Authentication](#authentication)
3. [Error Handling](#error-handling)
4. [Endpoints](#endpoints)
   - [1. User Management](#1-user-management)
     - [Login](#login)
     - [Logout](#logout)
     - [Register](#register)
   - [2. Agent Management](#2-agent-management)
     - [Get Agents](#get-agents)
     - [Create Agent](#create-agent)
     - [Get Agent Details](#get-agent-details)
     - [Update Agent](#update-agent)
     - [Delete Agent](#delete-agent)
   - [3. Logs](#3-logs)
     - [Get Logs](#get-logs)
     - [Filter Logs](#filter-logs)
   - [4. Notifications](#4-notifications)
     - [Get Notifications](#get-notifications)
     - [Mark as Read](#mark-as-read)
4. [WebSocket Communication](#websocket-communication)
5. [Rate Limiting](#rate-limiting)
6. [Versioning](#versioning)
7. [Glossary](#glossary)

---

## **Introduction**

This document provides a comprehensive reference for the Marvin Agent System's RESTful API. It details the available endpoints, request and response formats, authentication methods, and error codes.

---

## **Authentication**

- **Method**: JWT (JSON Web Tokens)
- **Obtaining a Token**:
  - Send a `POST` request to `/api/login` with valid credentials.
  - Receive a JWT token in the response.
- **Using the Token**:
  - Include the token in the `Authorization` header of subsequent requests:
    ```
    Authorization: Bearer your_jwt_token
    ```

---

## **Error Handling**

- **Standard Error Response Format**:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Detailed error message."
  }
}
Common Error Codes:
AUTHENTICATION_FAILED
INVALID_REQUEST
NOT_FOUND
SERVER_ERROR
Endpoints
1. User Management
Login
Endpoint: POST /api/login
Description: Authenticates a user and returns a JWT token.
Request Body:
json
Copy code
{
  "username": "string",
  "password": "string"
}
Response:
json
Copy code
{
  "token": "your_jwt_token",
  "expires_in": 3600
}
Logout
Endpoint: POST /api/logout
Description: Invalidates the current JWT token.
Headers: Requires Authorization header.
Response:
json
Copy code
{
  "message": "Successfully logged out."
}
Register
Endpoint: POST /api/register
Description: Creates a new user account.
Request Body:
json
Copy code
{
  "username": "string",
  "email": "string",
  "password": "string"
}
Response:
json
Copy code
{
  "message": "Registration successful. Please verify your email."
}
2. Agent Management
Get Agents
Endpoint: GET /api/agents
Description: Retrieves a list of agents associated with the user.
Response:
json
Copy code
{
  "agents": [
    {
      "id": "string",
      "name": "string",
      "status": "active",
      "created_at": "datetime"
    }
    // More agents
  ]
}
Create Agent
Endpoint: POST /api/agents
Description: Creates a new agent.
Request Body:
json
Copy code
{
  "name": "string",
  "configuration": {
    // Agent-specific configuration
  }
}
Response:
json
Copy code
{
  "agent": {
    "id": "string",
    "name": "string",
    "status": "active",
    "created_at": "datetime"
  }
}
Get Agent Details
Endpoint: GET /api/agents/{agent_id}
Description: Retrieves details of a specific agent.
Response:
json
Copy code
{
  "agent": {
    "id": "string",
    "name": "string",
    "status": "active",
    "configuration": {
      // Agent-specific configuration
    },
    "created_at": "datetime",
    "updated_at": "datetime"
  }
}
Update Agent
Endpoint: PUT /api/agents/{agent_id}
Description: Updates an existing agent.
Request Body:
json
Copy code
{
  "name": "string",
  "configuration": {
    // Updated configuration
  }
}
Response:
json
Copy code
{
  "message": "Agent updated successfully."
}
Delete Agent
Endpoint: DELETE /api/agents/{agent_id}
Description: Deletes an agent.
Response:
json
Copy code
{
  "message": "Agent deleted successfully."
}
3. Logs
Get Logs
Endpoint: GET /api/logs
Description: Retrieves system logs.
Parameters:
page (optional): Page number for pagination.
limit (optional): Number of logs per page.
Response:
json
Copy code
{
  "logs": [
    {
      "id": "string",
      "level": "INFO",
      "message": "string",
      "timestamp": "datetime"
    }
    // More logs
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total_pages": 5
  }
}
Filter Logs
Endpoint: GET /api/logs
Description: Filters logs based on criteria.
Parameters:
level: Log level (INFO, WARNING, ERROR)
start_date: Start date for the log entries.
end_date: End date for the log entries.
Response: Same as Get Logs.
4. Notifications
Get Notifications
Endpoint: GET /api/notifications
Description: Retrieves user notifications.
Response:
json
Copy code
{
  "notifications": [
    {
      "id": "string",
      "title": "string",
      "message": "string",
      "read": false,
      "timestamp": "datetime"
    }
    // More notifications
  ]
}
Mark as Read
Endpoint: POST /api/notifications/mark_as_read
Description: Marks a notification as read.
Request Body:
json
Copy code
{
  "notification_id": "string"
}
Response:
json
Copy code
{
  "message": "Notification marked as read."
}
WebSocket Communication
Endpoint: ws://yourserver.com/ws/notifications
Description: Provides real-time updates for notifications.
Authentication: JWT token must be included in the connection parameters.
Rate Limiting
Policy: Maximum of 100 requests per minute per IP address.
Headers:
X-RateLimit-Limit: Maximum number of requests.
X-RateLimit-Remaining: Number of requests remaining.
Retry-After: Time in seconds to wait before retrying.
Versioning
Current API Version: v1
Base URL: /api/v1/
Deprecation Policy: Deprecated endpoints will be supported for 6 months after a new version is released.
Glossary
JWT: JSON Web Token, a compact URL-safe means of representing claims between two parties.
Endpoint: A specific URL where an API can be accessed by a client application.
Pagination: A process of dividing a document into discrete pages.
WebSocket: A computer communications protocol providing full-duplex communication channels over a single TCP connection.
Document Version: 1.0.0
Last Updated: YYYY-MM-DD