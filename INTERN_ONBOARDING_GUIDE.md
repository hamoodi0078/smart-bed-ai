# Intern Onboarding Guide: Danah AbuHalifa
## Your First Days on the Smart Bed Engineering Team

Welcome to Danah AbuHalifa! This guide will walk you through everything you need to know during your first week. Read it carefully, bookmark it, and refer back to it whenever you feel lost.

---

## 1. Project Overview

Danah is an **AI-powered smart bed and bedside assistant** system. It combines:
*   A **Raspberry Pi 5** running at the bedside (sensors, LEDs, voice microphone)
*   A **Python backend** (FastAPI) handling AI logic, sleep analytics, and Islamic lifestyle features
*   A **Flutter mobile app** for controlling the bed from your phone
*   **PostgreSQL + Redis** for data storage and real-time messaging

Your job as an intern is to help build, test, fix, and improve parts of this system. You will not be doing busy work — you will be pushing real code into a real product.

For deeper context, read these documents in order:
1.  [INTERN_PROJECT_BRIEF.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/INTERN_PROJECT_BRIEF.md) — What Danah is and why it exists
2.  [PROBLEM_AND_VISION.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/PROBLEM_AND_VISION.md) — The problems we solve and our long-term vision
3.  [TECHNICAL_ARCHITECTURE.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/TECHNICAL_ARCHITECTURE.md) — How the system is built and how data flows
4.  [CS_SE_INTERN_GUIDE.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/CS_SE_INTERN_GUIDE.md) — Tasks for software interns
5.  [ECE_INTERN_GUIDE.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/ECE_INTERN_GUIDE.md) — Tasks for hardware/electronics interns

---

## 2. Who to Contact

| Person | Role | When to Contact |
| :--- | :--- | :--- |
| **Hamoud (Founder)** | Project Lead & Technical Architect | Architecture decisions, task assignment, weekly check-ins, and any blockers you cannot solve on your own. |
| **Your Assigned Mentor** | Senior Intern or Team Lead | Day-to-day code questions, pull request reviews, debugging help, and environment setup issues. |

**General Rules:**
*   Always try to solve a problem yourself for **30 minutes** before asking for help.
*   When you do ask, share what you already tried and what error messages you saw. Do not just say "it doesn't work."
*   Be respectful of everyone's time. Write clear, specific messages.

---

## 3. Repository Structure

The entire project lives in a single Git repository. Here is a simplified map of the most important directories:

```
smart-bed-by-me/
├── ai/                    ← AI modules (conversation, emotion, sleep, memory)
├── api/                   ← FastAPI routers (auth, devices, sleep, admin)
├── auth/                  ← Authentication logic (JWT, RBAC, OTP)
├── automations/           ← Automation rules (bedtime, wake, bathroom light)
├── config/                ← Application configuration and settings
├── core/                  ← Shared utilities (errors, logging, types)
├── database/              ← SQLAlchemy models and database connections
├── hardware/              ← Raspberry Pi drivers (LEDs, sensors, GPIO)
├── islamic_mode/          ← Prayer times, Ramadan, Tahajjud, Hadith
├── led/                   ← LED animation logic and scene rendering
├── mobile_app/            ← Flutter app (Dart code, screens, widgets)
├── notifications/         ← Push notifications (FCM, email, WhatsApp)
├── scenes/                ← Circadian lighting and weather-adaptive scenes
├── sleep_tracking/        ← Sleep score, debt tracker, nap optimizer
├── tests/                 ← All unit and integration tests (pytest)
├── docs/                  ← Setup guides and architecture decision records
├── scripts/               ← Utility scripts (start backend, run smoke tests)
├── web_server.py          ← Legacy monolith (being refactored into api/)
├── main.py                ← Backend entry point
├── requirements.txt       ← Python dependencies
├── requirements-dev.txt   ← Developer/test dependencies
├── docker-compose.yml     ← Docker setup for all services
└── .env.example           ← Template for environment variables
```

**Tip:** Do not feel overwhelmed. You will only work in 2–3 of these directories at a time. Your mentor will point you to the right folder on Day 1.

---

## 4. Hardware Setup Overview (ECE Interns)

If you are working on the physical hardware side, here is what your workbench needs:

*   **Raspberry Pi 5** with 8GB RAM and a 5V/5A USB-C power supply
*   **MicroSD card** (64GB+) flashed with Raspberry Pi OS 64-bit (Bookworm)
*   **AM2301A / DHT22** temperature and humidity sensor
*   **MAX30102** heart rate and SpO2 sensor module
*   **WS2812B NeoPixel LED strip** (start with a small 10-LED test strip)
*   **74AHCT125 logic level shifter** (converts Pi's 3.3V GPIO to 5V for LEDs)
*   **Breadboard, jumper wires, soldering iron, multimeter**

**First-day hardware task:** Assemble a basic circuit on a breadboard connecting the DHT22 sensor to the Pi via GPIO, and confirm you can read temperature values using the test scripts in [hardware/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/).

For full details, see [ECE_INTERN_GUIDE.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/ECE_INTERN_GUIDE.md).

---

## 5. Software Setup Overview (CS/SE Interns)

If you are working on backend, mobile, or AI code, follow these steps:

### Step 1: Clone the Repository
```powershell
git clone <repo-url>
cd smart-bed-by-me
```

### Step 2: Create a Python Virtual Environment
```powershell
python -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### Step 3: Configure Environment Variables
```powershell
Copy-Item .env.example .env
# Open .env in your editor and fill in the required API keys
```

### Step 4: Start the Backend Server
```powershell
python main.py
# Or use the helper script:
.\scripts\start_backend.ps1
```

### Step 5: Run the Tests
```powershell
python -m pytest tests/ -q
```
If all tests pass, your setup is correct.

### Step 6: Explore the API
*   Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your browser to see the live Swagger documentation.

### Flutter Mobile App (if assigned)
```powershell
cd mobile_app
flutter pub get
flutter analyze
flutter test
flutter run
```

For full details, see [CS_SE_INTERN_GUIDE.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/CS_SE_INTERN_GUIDE.md).

---

## 6. Coding Expectations

We maintain professional-grade standards. Here is what we expect from every intern:

*   **Write Clean Code:**
    *   Use meaningful variable and function names.
    *   Keep functions short (under 40 lines when possible).
    *   Add docstrings to every public function explaining what it does, its parameters, and its return value.
*   **Follow the Linter:**
    *   Run `ruff check .` before every commit. Fix all warnings.
    *   We use the configuration in [ruff.toml](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/ruff.toml).
*   **Write Tests:**
    *   Every new feature or bug fix should come with at least one corresponding test.
    *   Place test files in [tests/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/tests/) and name them `test_<module_name>.py`.
*   **Use Git Properly:**
    *   Create a new branch for every task (e.g., `feature/add-humidity-widget` or `fix/prayer-timezone-bug`).
    *   Write clear, descriptive commit messages (e.g., "Add moving average filter for MAX30102 heart rate readings").
    *   Never push directly to `main`. Always open a Pull Request (PR) for review.
*   **No Hardcoded Secrets:**
    *   API keys, passwords, and tokens go in the `.env` file, never in the source code.

---

## 7. Communication Rules

*   **Daily Updates:** Post a short message at the end of each working day summarizing:
    *   What you worked on today
    *   What you plan to work on tomorrow
    *   Any blockers or questions
*   **Ask Early, Ask Smart:** If you are stuck for more than 30 minutes, ask for help. Include:
    *   What you are trying to do
    *   What you tried
    *   The exact error message or unexpected behavior
*   **Be Responsive:** Reply to code review comments within 24 hours. If you disagree with feedback, explain your reasoning politely — do not just ignore it.
*   **Respect Working Hours:** We understand you are interns. You are not expected to work outside of agreed hours. Focus on quality during working hours, not overtime.

---

## 8. How Tasks Are Assigned

1.  **During onboarding**, your mentor will assign you a small "warm-up" task based on your skill level. This is intentionally easy — it is designed to help you learn the codebase and workflow.
2.  **After the warm-up**, Hamoud and your mentor will assign tasks from the project backlog based on:
    *   Your skill set (backend, mobile, hardware)
    *   Priority of the task
    *   Your interest (when possible, we try to match tasks to what excites you)
3.  **Task format:** Each task will have:
    *   A clear title and description
    *   Acceptance criteria (what "done" looks like)
    *   A difficulty estimate (Easy / Medium / Hard)
    *   A suggested deadline

---

## 9. How Progress Is Tracked

*   **Weekly Check-Ins:** A short meeting with Hamoud or your mentor each week to review what you accomplished, discuss blockers, and plan the next week.
*   **Pull Requests (PRs):** Your code contributions are tracked through Git. Every completed task results in a merged PR.
*   **Task Board:** We track active tasks, in-progress work, and completed items. Your mentor will show you where this board lives on Day 1.
*   **Self-Reflection:** At the end of each week, write 2–3 sentences about what you learned. This helps us improve the internship and helps you track your own growth.

---

## 10. What a Successful First Week Looks Like

By the end of your first seven days, you should have completed all of the following:

### Day 1–2: Environment & Orientation
- [ ] Read the onboarding documents listed in Section 1
- [ ] Set up your development environment (Python venv, Flutter SDK, or Raspberry Pi bench)
- [ ] Successfully run the backend server locally
- [ ] Successfully run the test suite with zero setup errors
- [ ] Explore the Swagger API docs at `/docs`

### Day 3–4: Codebase Exploration
- [ ] Understand the purpose of at least 5 key directories in the repo
- [ ] Read through one complete module related to your assigned area (e.g., `sleep_score.py`, `pi_sensors.py`, or a Flutter screen)
- [ ] Identify and write down 3 questions about the code to discuss with your mentor

### Day 5–7: First Contribution
- [ ] Complete your warm-up task (assigned by your mentor)
- [ ] Create a feature branch, commit your changes, and open your first Pull Request
- [ ] Respond to any code review feedback and get the PR merged
- [ ] Post your first daily update summarizing what you did and learned

---

**If you have completed all of these items by the end of Week 1, you are off to a great start. Welcome to the team!**
