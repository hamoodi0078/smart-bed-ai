# CS / SE Intern Contribution Guide: Danah AbuHalifa
## Designing, Building, and Scaling Our AI Smart Bed Software Stack

Welcome! As a Computer Science (CS) or Software Engineering (SE) intern at Danah AbuHalifa, you will work on a modern, high-performance tech stack. This guide maps out the core task areas, the skills you will need, their difficulty, and what we expect you to deliver.

---

## Role-Specific Tasks & Contributions

| Task Area | Description | Expected Skills | Difficulty | Expected Outcome (Deliverable) |
| :--- | :--- | :--- | :--- | :--- |
| **Refactoring Monolith Files** | Splitting our large [web_server.py](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/web_server.py) monolith (~397KB) into clean, modular FastAPI routers under [api/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/api/). | Python, FastAPI, API Routing, Git | **Medium** | A clean, modular backend directory structure where each feature (e.g., auth, settings, led controls) has its own standalone router file. |
| **Backend API Development** | Creating new REST endpoints and WebSocket channels for user profiles, device commands, sleep metrics, and custom alarms. | Python, FastAPI, Pydantic, REST API design principles | **Easy to Medium** | Well-documented, secure, and fast endpoints that validate input data using Pydantic models. |
| **Voice Pipeline Tuning** | Optimizing wake-word detection, speech-to-text (STT), and text-to-speech (TTS) streaming. Improving response latency and barge-in logic. | Python, AsyncIO, WebSockets, Audio processing libraries | **Hard** | Reduced voice loop latency (under 1.5 seconds) and reliable voice interruption when the user speaks while the bed is talking. |
| **Mobile App Support** | Building new screens, updating state managers, and implementing real-time widgets to sync with the backend. | Dart, Flutter, Riverpod (State Management), HTTP/JSON APIs | **Medium** | Responsive Flutter widgets on the dashboard showing live sensor stats, sleep scores, and Islamic prayer countdowns. |
| **Database Work** | Creating new migrations, writing optimized SQL/SQLAlchemy queries, and upgrading the `pgvector` conversation memory index. | PostgreSQL, SQLAlchemy, Alembic migrations, database index optimization | **Medium to Hard** | Fast database query execution times, clean schema migrations, and optimized semantic searches for AI memory. |
| **AI Integrations** | Refining prompt templates, managing LLM failovers (Claude $\rightarrow$ GPT), and improving emotion detection from speech text. | Prompt engineering, Python, JSON structured parsing | **Medium** | Emotionally intelligent responses where the bed transitions smoothly between Therapist, Coach, and Guide personalities. |
| **Automated Testing** | Writing unit tests, API integration tests, and edge-case property tests to expand our test coverage. | Pytest, Mocking libraries, Python, basic test-driven development (TDD) | **Easy** | Added test cases under [tests/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/tests/) that push the system's test coverage past our 80% benchmark. |
| **Bug Fixing** | Investigating runtime errors reported in Sentry (e.g., timezone bugs in prayer times, database locks, or websocket disconnects). | Debugging, log analysis, testing with Postman or Curl | **Easy to Medium** | Production hotfixes with corresponding unit tests to prevent regression, keeping our error dashboard green. |

---

## Onboarding Checklist for CS/SE Interns

Before starting your first coding task, complete these steps to set up your environment:

1.  **Clone the Repo and Set Up Virtual Environment:**
    ```powershell
    python -m venv .venv311
    .\.venv311\Scripts\Activate.ps1
    pip install -r requirements-dev.txt
    ```
2.  **Verify the Backend Runs Locally:**
    *   Copy the environment template: `Copy-Item .env.example .env`
    *   Edit `.env` and fill in necessary developer testing keys.
    *   Start the server: `python main.py` or run `python -m uvicorn web_server:app --reload`
3.  **Run the Test Suite:**
    *   Run all tests to make sure your local installation is correct:
        ```powershell
        python -m pytest tests/
        ```
4.  **Explore the API:**
    *   With the server running, open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your browser to view the interactive API documentation.

---

## Technical Standards to Follow

When writing code for Danah, we maintain high standards:
*   **Clean Code & Linting:** Run `ruff check .` before pushing. We do not accept code with unused imports, bad formatting, or standard lint errors.
*   **Async First:** Utilize Python `async` and `await` for all API-facing database calls and network requests to prevent blocking the FastAPI loop.
*   **Security Mindset:** Never hardcode secrets or API keys. Always read them from the environment via Pydantic settings.
*   **Document Your Changes:** If you add or edit an API route, update the docstrings so that Swagger documentation updates automatically.
