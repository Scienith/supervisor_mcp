# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Scienith Supervisor MCP Service** - a Model Context Protocol (MCP) server that bridges AI IDEs with the Scienith Supervisor system for managing software development workflows.

## Common Development Commands

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test categories
pytest tests/unit/          # Unit tests (52 tests)
pytest tests/mcp/           # MCP functionality tests (14 tests)
pytest tests/api/           # API integration tests (4 tests)

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/unit/test_file_manager.py -v
```

### Running the Service
```bash
# Start MCP service (recommended)
./start_mcp.sh

# Alternative: Direct Python execution
python run.py

# With custom API URL
SUPERVISOR_API_URL=http://api.example.com:8000/api/v1 ./start_mcp.sh
```

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r test-requirements.txt

# Create virtual environment (if not using start_mcp.sh)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

## Architecture & Key Components

### Service Layer Architecture
The codebase follows a clean service layer pattern:

1. **MCP Server Layer** (`src/server.py`): 
   - Handles MCP protocol communication
   - Defines tool interfaces
   - Routes requests to service layer

2. **Business Logic Layer** (`src/service.py`):
   - Implements core workflow logic
   - Manages authentication and sessions
   - Coordinates with external API

3. **File Management Layer** (`src/file_manager.py`):
   - Handles local `.supervisor` directory
   - Manages project isolation
   - Stores project metadata

4. **Session Management** (`src/session.py`):
   - Tracks user authentication state
   - Manages API tokens
   - Handles session lifecycle

### MCP Tools Workflow

The service implements a structured development workflow:

1. **Quick Start (REQUIRED SETUP)**:
   - First, create a `.env` file in your project root:
     ```bash
     cp .env.example .env
     # Edit .env and fill in your credentials:
     # SUPERVISOR_USERNAME=your_username
     # SUPERVISOR_PASSWORD=your_password
     # SUPERVISOR_PROJECT_ID=your_project_id
     ```
   - Then use `login_with_project()` → One-step login and project initialization

   **IMPORTANT**:
   - `login_with_project` is the ONLY supported login method
   - It reads credentials from the `.env` file in the specified project directory
   - Requires `working_directory` parameter pointing to project root containing `.env` file
   - Example: `login_with_project("/path/to/your/project")`
   - Make sure `.env` is in `.gitignore` to protect your credentials

2. **Alternative Flow (Legacy - Deprecated)**:
   - `login` → authenticate with Scienith Supervisor (deprecated)
   - `setup_workspace` → initialize project workspace (deprecated)

3. **Project Creation**: `create_project` → creates new project and `.supervisor` directory

4. **Task Execution Loop**:
   - `next` → Get next task from server
   - Execute task (user/AI performs work)
   - `report` → Submit results back (supports `finish_task=True` to complete entire task group)
   - `finish_task` → Skip remaining phases and mark task as completed directly

5. **Task Group Management**: `add_task_group`, `suspend`, `continue_suspended`, `start`, `cancel_task`, `finish_task` for complex workflows

### API Communication Pattern

All API calls follow this pattern:
- Async HTTP using aiohttp
- Automatic session management via context managers
- Error handling with retries for network failures
- JSON request/response with proper content-type headers

#### Recent API Endpoint Updates

**Auth Validation Endpoint Added (2025-09-23)**:
- Added `auth/validate/` endpoint to backend for token validation
- MCP service uses this endpoint to verify token validity during session restoration
- Returns user info if token is valid, 401 if invalid
- Resolves previous 404 errors when MCP service attempted token validation

**Finish Task Endpoint Added (2025-09-23)**:
- Added `finish_task` MCP tool that calls `POST /api/v1/tasks/{task_id}/finish/`
- Allows directly marking a task as completed, skipping remaining phases
- Useful when users want to skip validation, fixing, or retrospective phases
- Requires task owner permission and all task phases to be completed or cancelled
- Idempotent operation - calling on already completed tasks returns info status

**Endpoint Consistency Verification**:
- All MCP service endpoints have been verified against backend implementation
- ViewSet actions (e.g., `projects/{id}/info/`, `projects/{id}/status/`) correctly map to Django REST Framework URLs
- Test scripts available: `test_api_endpoints.py` for basic endpoint existence verification

### Project Isolation

Each project maintains its own `.supervisor` directory:
```
working_directory/
└── .supervisor/
    ├── project.json         # Project metadata & API config
    ├── tasks/               # Task-specific files
    └── reports/             # Submitted reports
```

## Testing Guidelines

When modifying the service:

1. **Unit Tests**: Test individual functions in isolation
   - Use mocks for external dependencies
   - Test both success and error paths
   - Located in `tests/unit/`

2. **MCP Tests**: Test MCP protocol integration
   - Mock the FastMCP framework
   - Test tool registration and execution
   - Located in `tests/mcp/`

3. **API Tests**: Test external API communication
   - Mock HTTP responses
   - Test error handling and retries
   - Located in `tests/api/`

Always run tests before committing changes.

## Important Implementation Notes

### Async Programming
- All API operations are async - use `await` properly
- HTTP sessions are managed with async context managers
- Never block the event loop with synchronous I/O

### Error Handling
- The `@handle_error` decorator is used throughout for consistent error handling
- API errors should return structured error responses
- Network failures should be logged and retried where appropriate

### Environment Variables
- `SUPERVISOR_API_URL`: Backend API URL (required, set in .env file)
- `SUPERVISOR_PROJECT_PATH`: Base path for projects (default: current directory)
- Always respect environment variables for configuration

### File Operations
- All file operations go through `FileManager` class
- Project files are isolated in `.supervisor` directories
- Never write outside the project directory without explicit user permission