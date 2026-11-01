# 🎓 StudyOS — Your Personal Academic Workspace

<p align="center">
  <strong>Study smarter. Stay organized. Achieve more.</strong>
</p>

<p align="center">
  A modern, privacy-focused academic workspace designed to help college and university students manage their entire study life in one place.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Flask-Web%20Framework-000000?style=for-the-badge&logo=flask&logoColor=white">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white">
  <img src="https://img.shields.io/badge/Frontend-Vanilla%20JS-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black">
</p>

---

## ✨ Overview

**StudyOS** is an all-in-one academic productivity platform that brings your subjects, assignments, notes, flashcards, focus sessions, and study analytics together in a single, beautifully designed workspace.

Instead of switching between multiple apps to organize your academic life, StudyOS gives you everything you need in one private, personalized environment.

Built with Python and Flask, it is lightweight, fast, mobile-friendly, and designed to run even on Android through Termux.

## 🚀 Features

### 📊 1. Intelligent Dashboard

Get a complete overview of your academic progress.

- Personalized greeting and current date.
- Total subjects, assignments, notes, and study time.
- Assignment completion progress ring.
- Seven-day study activity chart.
- Study time breakdown by subject.
- Daily study streak tracking.
- Upcoming assignment deadlines.
- Recent study sessions and completed tasks.

### 📚 2. Subject Management

- Create, edit, and delete subjects.
- Custom subject colours.
- Individual subject statistics.
- View assignments, notes, and sessions associated with each subject.
- Dedicated subject overview.

### 📝 3. Assignment Manager

- Create, edit, and delete assignments.
- Assign subjects and priorities.
- Set deadlines.
- Mark assignments as completed or pending.
- Search and filter assignments.
- Sort by deadline, priority, or status.
- Automatic overdue highlighting.

### 📖 4. Smart Notes

- Create and edit notes.
- Automatic debounced saving.
- Search through your notes.
- Filter notes by subject.
- Track creation and modification dates.
- Simple, distraction-free writing experience.

### 🧠 5. Spaced-Repetition Flashcards

Make revision more effective with the Leitner learning system.

- Create, edit, and delete flashcards.
- Interactive card-flipping animation.
- One-card-at-a-time learning experience.
- Shuffle and navigation controls.
- Track learning progress.
- Separate Due and All collections.
- Remembered and Revise Again actions.
- Five-level Leitner spaced repetition.

**Leitner scheduling:**

| Box | Next Review |
|---|---|
| Box 1 | 1 day |
| Box 2 | 3 days |
| Box 3 | 7 days |
| Box 4 | 14 days |
| Box 5 | 30 days |

Remembered cards advance to the next box. Cards marked for revision return to Box 1 and become due again.

### ⏱️ 6. Immersive Focus Timer

A distraction-free study timer with advanced controls.

- Focus sessions, short breaks, and long breaks.
- Custom timer durations.
- Pause, resume, reset, and skip.
- Automatic session counting.
- Optional automatic break and focus starts.
- Completion chime.
- Browser-generated ambient sounds.
- Fullscreen mode.
- Screen Wake Lock support.
- Immersive interface with auto-hiding controls.
- Persistent timer state across page reloads.
- Accurate absolute-end-timestamp timing.
- Exactly-once saving of completed focus sessions.

### 📈 7. Study Analytics & History

- Total study time.
- Subject-wise study breakdown.
- Daily activity charts.
- Weekly analytics covering eight weeks.
- Monthly analytics covering six months.
- Recent study session history.
- Date-range filtering.
- Subject-based filtering.

### 🎨 8. Personalization & Settings

- Six background themes.
- Custom accent colours.
- Animations on/off.
- Adjustable animation intensity.
- Reduced-motion support.
- Configurable focus and break durations.
- Timer automation preferences.
- Optional sound settings.
- User-specific preferences.

### 🔐 9. Private User Accounts

- User registration and login.
- Secure logout.
- Profile management.
- Name and email updates.
- Password changes.
- Account deletion.
- Private subjects, assignments, notes, and flashcards.
- Per-user settings and study history.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Flask | Web application framework |
| SQLite | Database |
| Jinja2 | Server-side templates |
| HTML5 | Application structure |
| CSS3 | Styling and responsive layouts |
| Vanilla JavaScript | Interactive functionality |
| Werkzeug | Password hashing and security |

**Dependency philosophy:** Flask is the only required Python dependency. Werkzeug and Jinja2 are included with Flask.

Gunicorn is used for production deployment.

## 📂 Project Structure

```text
StudyOS/
├── app/
│   ├── __init__.py
│   ├── db.py
│   ├── security.py
│   ├── helpers.py
│   ├── ownership.py
│   ├── auth/
│   ├── dashboard/
│   ├── subjects/
│   ├── tasks/
│   ├── notes/
│   ├── flashcards/
│   ├── timer/
│   ├── analytics/
│   ├── settings/
│   ├── templates/
│   │   └── partials/
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
├── tests/
│   ├── backend tests
│   ├── timer-core.test.js
│   └── browser_check.py
├── config.py
├── run.py
├── requirements.txt
├── .env.example
└── .gitignore
```

## ⚡ Installation & Setup

### Requirements

- Python 3.10 or newer.
- Git (optional).
- A modern web browser.

### 1. Clone the Repository

```bash
git clone https://github.com/Hunternerds/StudyOS.git
cd StudyOS
```

### 2. Create a Virtual Environment

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Generate a secure secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Add the generated key to your `.env` file as `SECRET_KEY`.

### 5. Start StudyOS

```bash
python run.py
```

Open your browser:

```text
http://localhost:5000
```

Create your account and start organizing your academic life!

## 📱 Android / Termux Support

StudyOS is designed to run on Android without requiring native compilation.

Install the required packages:

```bash
pkg update && pkg install python git
```

Install Flask:

```bash
pip install flask
```

Clone the repository:

```bash
git clone https://github.com/Hunternerds/StudyOS.git
cd StudyOS
```

Start the application:

```bash
python run.py
```

Visit:

```text
http://127.0.0.1:5000
```

You can now use StudyOS directly from Chrome or another browser on your phone.

## 🧪 Testing

StudyOS includes automated tests covering backend functionality, timer logic, and browser interactions.

### Backend Tests

```bash
python -m unittest discover -s tests -v
```

**28 backend tests** covering authentication, data isolation, timer APIs, application features, and database migrations.

### Timer Engine Tests

```bash
node --test tests/timer-core.test.js
```

**14 timer tests** using a fake clock to validate timer behaviour.

### Browser Tests

Install Playwright:

```bash
pip install playwright
```

Install Chromium:

```bash
playwright install chromium
```

Run browser checks:

```bash
python tests/browser_check.py
```

**81 browser checks** covering real browser interactions. Screenshots are saved in `instance/shots/`.

## 🔒 Security & Privacy

Privacy and security are fundamental parts of StudyOS.

| Security Feature | Implementation |
|---|---|
| Password security | PBKDF2-SHA256 with 600,000 iterations |
| Session security | Signed, HttpOnly cookies |
| CSRF protection | Per-session tokens |
| Login protection | Database-backed rate limiting |
| Data isolation | User-specific database queries |
| SQL injection protection | Parameterized SQL queries |
| Output protection | Jinja2 autoescaping |
| Content security | Strict Content Security Policy |
| Clickjacking protection | X-Frame-Options |
| Secret management | Environment variables |
| Error handling | Generic user-facing error pages |

Additional protections include secure cookie settings in production, ownership checks for private resources, open-redirect protection, and constant-time CSRF token comparison.

**Your academic data stays separated between accounts.**

## 🌐 Production Deployment

StudyOS supports deployment using a production WSGI server.

### Install Gunicorn

```bash
pip install gunicorn
```

### Configure Production Environment

```bash
export STUDYOS_ENV=production
export SECRET_KEY=your-long-random-secret
export DATABASE_PATH=/var/data/studyos.db
```

### Start the Application

```bash
gunicorn -w 2 -b 0.0.0.0:8000 run:app
```

For Windows, you can use Waitress:

```bash
pip install waitress
waitress-serve --port 8000 run:app
```

### Hosting Platforms

- [Render](https://render.com/)
- [Railway](https://railway.com/)
- [Fly.io](https://fly.io/)
- [PythonAnywhere](https://www.pythonanywhere.com/)

**Important:** SQLite requires persistent storage. If your hosting provider uses an ephemeral filesystem, configure a persistent volume or your database may be lost during redeployment.

For production, always use HTTPS and a persistent database location.

## 🔄 Database Migration

Upgrading from the previous single-user StudyOS version is supported.

On the first upgraded startup:

1. An automatic timestamped database backup is created.
2. Existing database tables are upgraded using versioned migrations.
3. Existing records are preserved.
4. The first registered account adopts the existing single-user data.
5. Subsequent accounts receive independent, empty workspaces.

Flashcards are also preserved when their associated subjects are deleted.

## 🗄️ Future Database Migration

The application currently uses SQLite for simplicity and portability.

A future PostgreSQL migration can be implemented by replacing the database connection layer and adapting SQLite-specific SQL constructs.

The current architecture keeps most database operations concentrated in:

- `app/db.py`
- `app/analytics/service.py`
- Blueprint route modules.

## 🤝 Contributing

Contributions, suggestions, bug reports, and improvements are welcome!

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run the existing tests.
5. Submit a pull request.

For major changes, consider opening an issue first to discuss your proposal.

## 📜 License

This project is distributed under the **MIT License**.

See the `LICENSE` file for details.

## ⭐ Support the Project

If you find StudyOS useful:

- ⭐ Star this repository.
- 🍴 Fork it and make your own improvements.
- 🐛 Report bugs and suggest features.
- 📢 Share it with other students.

Your support helps the project grow!

---

<p align="center">
  <strong>StudyOS</strong>
  <br>
  Your academics. Your workspace. Your progress.
  <br><br>
  Made with ❤️ for students.
</p>