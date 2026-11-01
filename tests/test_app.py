"""Run with:  python -m unittest discover -s tests -v   (no extra packages needed)."""
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from app.flashcards.routes import schedule  # noqa: E402

PW = "Sup3rSecret!"


def utc_today():
    return datetime.now(timezone.utc).date()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "t.db")
        self.app = create_app({"DATABASE": self.db_path, "SECRET_KEY": "test-secret",
                               "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000"})
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers ---------------------------------------------------------------
    def token(self, client=None, path="/login"):
        html = (client or self.c).get(path).get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
        return m.group(1)

    def register(self, client=None, name="Ada", email="ada@example.com", pw=PW):
        client = client or self.c
        return client.post("/register", data={"csrf_token": self.token(client, "/register"), "name": name,
                                              "email": email, "password": pw, "confirm": pw})

    def new_user(self, name="Ada", email="ada@example.com"):
        client = self.app.test_client()
        self.register(client, name, email)
        return client

    def post(self, client, path, data=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = self.token(client, "/settings")
        return client.post(path, data=data, **kw)

    def post_json(self, client, path, payload):
        return client.post(path, json=payload, headers={"X-CSRF-Token": self.token(client, "/settings"),
                                                         "X-Requested-With": "fetch"})

    def q(self, sql, args=()):
        con = sqlite3.connect(self.db_path)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()


class AuthTests(Base):
    def test_register_login_logout_and_hashing(self):
        r = self.register()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)
        stored = self.q("SELECT password_hash FROM users")[0][0]
        self.assertTrue(stored.startswith("pbkdf2:sha256:"))
        self.assertNotIn(PW, stored)
        self.assertEqual(self.post(self.c, "/logout").status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 302)
        r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ADA@example.com", "password": PW})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_wrong_password_is_generic_and_rejected(self):
        self.register(); self.post(self.c, "/logout")
        r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ada@example.com", "password": "nope"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Invalid email or password.", r.get_data(as_text=True))
        r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ghost@example.com", "password": "nope"})
        self.assertIn("Invalid email or password.", r.get_data(as_text=True))

    def test_weak_and_duplicate_registration(self):
        self.assertEqual(self.register(pw="short").status_code, 400)
        self.assertEqual(self.register(pw="password123").status_code, 400)
        self.register(); self.post(self.c, "/logout")
        self.assertEqual(self.register(email="Ada@Example.com").status_code, 400)

    def test_protected_pages_require_login(self):
        for path in ["/", "/timer/", "/subjects/", "/tasks/", "/notes/", "/flashcards/", "/history/",
                     "/settings", "/profile", "/tasks/new", "/notes/new"]:
            r = self.c.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers["Location"], path)

    def test_csrf_enforced(self):
        self.register()
        self.assertEqual(self.c.post("/subjects/new", data={"name": "X"}).status_code, 400)
        self.assertEqual(self.c.post("/timer/complete", json={"session_key": "abcdefgh1", "duration": 25}).status_code, 400)
        self.assertEqual(self.c.post("/logout").status_code, 400)

    def test_login_rate_limit(self):
        self.register(); self.post(self.c, "/logout")
        for _ in range(5):
            r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ada@example.com", "password": "bad"})
            self.assertEqual(r.status_code, 401)
        r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ada@example.com", "password": PW})
        self.assertEqual(r.status_code, 429)  # locked even with the right password

    def test_open_redirect_blocked(self):
        self.register(); self.post(self.c, "/logout")
        for evil in ["//evil.com", "https://evil.com", "/\\evil.com"]:
            r = self.c.post("/login", data={"csrf_token": self.token(), "email": "ada@example.com",
                                            "password": PW, "next": evil})
            self.assertEqual(r.headers["Location"], "/", evil)
            self.post(self.c, "/logout")

    def test_headers_and_cookie_flags(self):
        r = self.c.get("/login")
        self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        cookie = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("studyos_session")][0]
        self.assertIn("HttpOnly", cookie); self.assertIn("SameSite=Lax", cookie)

    def test_password_change_and_account_delete(self):
        self.register()
        r = self.post(self.c, "/profile/password", {"current": "wrong", "new": "N3wPassword!", "confirm": "N3wPassword!"})
        self.assertEqual(self.q("SELECT COUNT(*) FROM users")[0][0], 1)
        old = self.q("SELECT password_hash FROM users")[0][0]
        self.post(self.c, "/profile/password", {"current": PW, "new": "N3wPassword!", "confirm": "N3wPassword!"})
        self.assertNotEqual(old, self.q("SELECT password_hash FROM users")[0][0])
        self.post(self.c, "/subjects/new", {"name": "Math"})
        self.post(self.c, "/profile/delete", {"password": "nope"})
        self.assertEqual(self.q("SELECT COUNT(*) FROM users")[0][0], 1)
        self.post(self.c, "/profile/delete", {"password": "N3wPassword!"})
        self.assertEqual(self.q("SELECT COUNT(*) FROM users")[0][0], 0)
        self.assertEqual(self.q("SELECT COUNT(*) FROM subjects")[0][0], 0)  # cascaded

    def test_no_traceback_leak(self):
        app = create_app({"DATABASE": os.path.join(self.tmp, "boom.db"), "SECRET_KEY": "k",
                          "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000", "PROPAGATE_EXCEPTIONS": False})

        @app.route("/boom")
        def boom():
            raise RuntimeError("secret internal detail")
        client = app.test_client()
        r = client.get("/boom")
        self.assertEqual(r.status_code, 500)
        text = r.get_data(as_text=True)
        self.assertNotIn("secret internal detail", text)
        self.assertNotIn("Traceback", text)
        self.assertIn("Something went wrong", text)
        self.assertEqual(client.get("/nope").status_code, 404)


class IsolationTests(Base):
    def setUp(self):
        super().setUp()
        self.a = self.new_user("Ann", "ann@example.com")
        self.b = self.new_user("Bob", "bob@example.com")
        # Ann creates one of everything
        self.post(self.a, "/subjects/new", {"name": "Physics", "color": "#34d399"})
        self.sid = self.q("SELECT id FROM subjects")[0][0]
        self.post(self.a, "/tasks/new", {"title": "Ann task", "subject_id": self.sid, "priority": "High"})
        self.post(self.a, "/notes/new", {"title": "Ann note", "content": "secret", "subject_id": self.sid})
        self.post(self.a, "/flashcards/new", {"question": "Q?", "answer": "A", "subject_id": self.sid})
        self.post_json(self.a, "/timer/complete", {"session_key": "ann-session-1", "duration": 25, "subject_id": self.sid})
        self.tid = self.q("SELECT id FROM tasks")[0][0]
        self.nid = self.q("SELECT id FROM notes")[0][0]
        self.cid = self.q("SELECT id FROM flashcards")[0][0]

    def test_other_user_gets_404_everywhere(self):
        for path in [f"/subjects/{self.sid}", f"/subjects/{self.sid}/edit", f"/tasks/{self.tid}/edit",
                     f"/notes/{self.nid}", f"/flashcards/{self.cid}/edit"]:
            self.assertEqual(self.b.get(path).status_code, 404, path)
        for path in [f"/subjects/{self.sid}/delete", f"/tasks/{self.tid}/toggle", f"/tasks/{self.tid}/delete",
                     f"/notes/{self.nid}/delete", f"/flashcards/{self.cid}/delete"]:
            self.assertEqual(self.post(self.b, path).status_code, 404, path)
        r = self.post_json(self.b, f"/flashcards/{self.cid}/review", {"result": "remembered"})
        self.assertEqual(r.status_code, 404)
        r = self.post_json(self.b, "/notes/autosave", {"id": self.nid, "title": "pwn", "content": "pwn"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.q("SELECT title FROM notes")[0][0], "Ann note")
        self.assertEqual(self.q("SELECT COUNT(*) FROM subjects")[0][0], 1)
        self.assertEqual(self.q("SELECT completed FROM tasks")[0][0], 0)

    def test_cannot_attach_records_to_foreign_subject(self):
        self.post(self.b, "/tasks/new", {"title": "Sneaky", "subject_id": self.sid})
        self.post(self.b, "/notes/new", {"title": "Sneaky", "subject_id": self.sid})
        self.post(self.b, "/flashcards/new", {"question": "q", "answer": "a", "subject_id": self.sid})
        self.assertEqual(self.q("SELECT COUNT(*) FROM tasks")[0][0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM notes")[0][0], 1)
        self.assertEqual(self.q("SELECT COUNT(*) FROM flashcards")[0][0], 1)
        r = self.post_json(self.b, "/timer/complete", {"session_key": "bob-session-1", "duration": 25, "subject_id": self.sid})
        self.assertEqual(r.status_code, 400)

    def test_lists_and_stats_are_private(self):
        for path in ["/subjects/", "/tasks/", "/notes/", "/flashcards/manage", "/history/", "/"]:
            body = self.b.get(path).get_data(as_text=True)
            for leak in ("Ann task", "Ann note", "Physics", "secret"):
                self.assertNotIn(leak, body, f"{leak} leaked on {path}")
        body = self.b.get(f"/history/?subject={self.sid}").get_data(as_text=True)
        self.assertNotIn("Physics", body)  # foreign subject id is ignored, not honoured
        self.assertNotIn("Ann note", self.b.get("/notes/?q=Ann").get_data(as_text=True))

    def test_settings_are_per_user(self):
        self.post(self.a, "/settings/timer", {"focus_min": "50", "short_min": "10", "long_min": "30",
                                              "sessions_before_long": "3", "ambient": "rain", "ambient_volume": "50"})
        rows = dict(self.q("SELECT user_id, focus_min FROM user_settings"))
        self.assertEqual(sorted(rows.values()), [25, 50])
        self.post(self.a, "/settings/appearance", {"bg_preset": "midnight-ocean", "bg_intensity": "40", "accent": "emerald"})
        html = self.a.get("/").get_data(as_text=True)
        self.assertIn('data-bg="midnight-ocean"', html)
        self.assertIn('data-bg="cosmic-night"', self.b.get("/").get_data(as_text=True))


class TimerTests(Base):
    def setUp(self):
        super().setUp(); self.register()

    def test_session_saved_exactly_once(self):
        payload = {"session_key": "key-abcdef-1", "duration": 25, "kind": "focus"}
        r1 = self.post_json(self.c, "/timer/complete", payload).get_json()
        r2 = self.post_json(self.c, "/timer/complete", payload).get_json()
        self.assertTrue(r1["saved"]); self.assertFalse(r1["duplicate"])
        self.assertFalse(r2["saved"]); self.assertTrue(r2["duplicate"])
        self.assertEqual(self.q("SELECT COUNT(*), SUM(duration) FROM study_sessions")[0], (1, 25))
        self.assertEqual(self.q("SELECT studied_on FROM study_sessions")[0][0], utc_today().isoformat())

    def test_breaks_and_bad_input_rejected(self):
        for payload in ({"session_key": "key-abcdef-2", "duration": 5, "kind": "short"},
                        {"session_key": "key-abcdef-3", "duration": 0}, {"session_key": "key-abcdef-3", "duration": 9999},
                        {"session_key": "bad key!", "duration": 25}, {"session_key": "key-abcdef-4", "duration": "x"},
                        {"duration": 25}):
            self.assertEqual(self.post_json(self.c, "/timer/complete", payload).status_code, 400, payload)
        self.assertEqual(self.q("SELECT COUNT(*) FROM study_sessions")[0][0], 0)

    def test_subject_association_and_stats(self):
        self.post(self.c, "/subjects/new", {"name": "Chem"})
        sid = self.q("SELECT id FROM subjects")[0][0]
        self.post_json(self.c, "/timer/complete", {"session_key": "key-abcdef-5", "duration": 30, "subject_id": sid})
        self.post_json(self.c, "/timer/complete", {"session_key": "key-abcdef-6", "duration": 45})
        self.assertEqual(self.q("SELECT subject_id, duration FROM study_sessions ORDER BY id"), [(sid, 30), (None, 45)])
        html = self.c.get("/").get_data(as_text=True)
        self.assertIn("<strong>1.2</strong><span>Study hours", html)   # 75 min -> 1.2 h
        self.assertIn("<strong>2</strong><span>Focus sessions", html)
        hist = self.c.get("/history/").get_data(as_text=True)
        self.assertIn("<strong>75</strong><span>Focused minutes", hist)
        only = self.c.get(f"/history/?subject={sid}").get_data(as_text=True)
        self.assertIn("<strong>30</strong><span>Focused minutes", only)

    def test_streak_counts_consecutive_days(self):
        uid = self.q("SELECT id FROM users")[0][0]
        con = sqlite3.connect(self.db_path)
        today = utc_today()
        for back in (0, 1, 2, 4):
            con.execute("INSERT INTO study_sessions (user_id,duration,studied_on,kind) VALUES (?,?,?,'focus')",
                        (uid, 20, (today - timedelta(days=back)).isoformat()))
        con.commit(); con.close()
        self.assertRegex(self.c.get("/").get_data(as_text=True), r"<strong>3</strong><span>days")


class FeatureTests(Base):
    def setUp(self):
        super().setUp(); self.register()

    def test_subject_crud(self):
        self.post(self.c, "/subjects/new", {"name": "Math", "description": "Calc", "color": "#123456"})
        sid = self.q("SELECT id FROM subjects")[0][0]
        self.assertEqual(self.post(self.c, "/subjects/new", {"name": "math"}).status_code, 200)  # duplicate name re-shows form
        self.assertEqual(self.q("SELECT COUNT(*) FROM subjects")[0][0], 1)
        self.post(self.c, f"/subjects/{sid}/edit", {"name": "Maths", "color": "not-a-color"})
        self.assertEqual(self.q("SELECT name, color FROM subjects")[0], ("Maths", "#8b5cf6"))  # bad color -> default
        self.post(self.c, "/tasks/new", {"title": "T", "subject_id": sid})
        self.post(self.c, f"/subjects/{sid}/delete")
        self.assertEqual(self.q("SELECT COUNT(*) FROM subjects")[0][0], 0)
        self.assertEqual(self.q("SELECT subject_id FROM tasks")[0][0], None)   # kept, unassigned

    def test_tasks_flow_filters_overdue(self):
        today = utc_today()
        self.post(self.c, "/tasks/new", {"title": "Past due", "due_date": (today - timedelta(days=2)).isoformat(), "priority": "High"})
        self.post(self.c, "/tasks/new", {"title": "Future", "due_date": (today + timedelta(days=3)).isoformat(), "priority": "Low"})
        self.post(self.c, "/tasks/new", {"title": "Bad date", "due_date": "2026-13-45"})
        self.post(self.c, "/tasks/new", {"title": "Bad prio", "priority": "Urgent"})
        self.assertEqual(self.q("SELECT COUNT(*) FROM tasks")[0][0], 2)
        html = self.c.get("/tasks/").get_data(as_text=True)
        self.assertIn("2 days overdue", html)
        self.assertLess(html.index("Past due"), html.index("Future"))     # deadline sort
        overdue = self.c.get("/tasks/?status=overdue").get_data(as_text=True)
        self.assertIn("Past due", overdue); self.assertNotIn("Future", overdue)
        tid = self.q("SELECT id FROM tasks WHERE title='Past due'")[0][0]
        self.post(self.c, f"/tasks/{tid}/toggle")
        self.assertEqual(self.q("SELECT completed, completed_at IS NOT NULL FROM tasks WHERE id=?", (tid,))[0], (1, 1))
        self.assertNotIn("Past due", self.c.get("/tasks/?status=pending").get_data(as_text=True))
        self.assertIn("Past due", self.c.get("/tasks/?status=completed").get_data(as_text=True))
        self.assertIn("Future", self.c.get("/tasks/?q=futu").get_data(as_text=True))
        self.post(self.c, f"/tasks/{tid}/edit", {"title": "Renamed", "priority": "Medium"})
        self.assertEqual(self.q("SELECT title FROM tasks WHERE id=?", (tid,))[0][0], "Renamed")
        self.post(self.c, f"/tasks/{tid}/delete")
        self.assertEqual(self.q("SELECT COUNT(*) FROM tasks")[0][0], 1)

    def test_notes_autosave_search_and_edit(self):
        r = self.post_json(self.c, "/notes/autosave", {"title": "", "content": "", "subject_id": ""}).get_json()
        self.assertTrue(r["skipped"])
        r = self.post_json(self.c, "/notes/autosave", {"title": "Cells", "content": "mitochondria 100% power_house"}).get_json()
        nid = r["id"]; self.assertTrue(r["ok"])
        r = self.post_json(self.c, "/notes/autosave", {"id": nid, "title": "Cells", "content": "mitochondria updated"}).get_json()
        self.assertEqual(self.q("SELECT COUNT(*), content FROM notes")[0], (1, "mitochondria updated"))
        self.post(self.c, "/notes/new", {"title": "Other", "content": "50% off_topic"})
        self.assertIn("Other", self.c.get("/notes/?q=50%25").get_data(as_text=True))
        self.assertNotIn("Cells", self.c.get("/notes/?q=50%25").get_data(as_text=True))   # % is literal, not a wildcard
        self.assertIn("Cells", self.c.get("/notes/?q=mito").get_data(as_text=True))
        self.post(self.c, f"/notes/{nid}", {"title": "Cells 2", "content": "x"})
        self.assertEqual(self.q("SELECT title FROM notes WHERE id=?", (nid,))[0][0], "Cells 2")
        self.post(self.c, f"/notes/{nid}/delete")
        self.assertEqual(self.q("SELECT COUNT(*) FROM notes")[0][0], 1)

    def test_flashcard_srs(self):
        today = utc_today()
        self.assertEqual(schedule(0, True, today), (1, (today + timedelta(days=1)).isoformat()))
        self.assertEqual(schedule(2, True, today), (3, (today + timedelta(days=7)).isoformat()))
        self.assertEqual(schedule(5, True, today), (5, (today + timedelta(days=30)).isoformat()))
        self.assertEqual(schedule(4, False, today), (1, today.isoformat()))
        self.post(self.c, "/flashcards/new", {"question": "Q1", "answer": "A1"})
        self.post(self.c, "/flashcards/new", {"question": "Q2", "answer": "A2"})
        ids = [r[0] for r in self.q("SELECT id FROM flashcards ORDER BY id")]
        self.assertIn("Q1", self.c.get("/flashcards/").get_data(as_text=True))
        self.post_json(self.c, f"/flashcards/{ids[0]}/review", {"result": "remembered"})
        self.post_json(self.c, f"/flashcards/{ids[1]}/review", {"result": "revise"})
        self.assertEqual(self.q("SELECT box, reviews, lapses FROM flashcards WHERE id=?", (ids[0],))[0], (1, 1, 0))
        self.assertEqual(self.q("SELECT box, lapses FROM flashcards WHERE id=?", (ids[1],))[0], (1, 1))
        due = self.c.get("/flashcards/").get_data(as_text=True)
        self.assertNotIn('"question": "Q1"', due)           # scheduled for tomorrow
        self.assertIn('"question": "Q2"', due)               # revise stays due
        self.assertIn('"question": "Q1"', self.c.get("/flashcards/?mode=all").get_data(as_text=True))
        self.assertEqual(self.post_json(self.c, f"/flashcards/{ids[0]}/review", {"result": "bogus"}).status_code, 400)
        self.post(self.c, f"/flashcards/{ids[0]}/edit", {"question": "Q1b", "answer": "A1b"})
        self.assertIn("Q1b", self.c.get("/flashcards/manage?q=1b").get_data(as_text=True))
        self.post(self.c, f"/flashcards/{ids[0]}/delete")
        self.assertEqual(self.q("SELECT COUNT(*) FROM flashcards")[0][0], 1)

    def test_settings_validation(self):
        bad = {"focus_min": "0", "short_min": "5", "long_min": "15", "sessions_before_long": "4"}
        self.post(self.c, "/settings/timer", bad)
        self.assertEqual(self.q("SELECT focus_min FROM user_settings")[0][0], 25)
        r = self.post(self.c, "/settings/timer", {"focus_min": "50", "short_min": "10", "long_min": "20", "sessions_before_long": "2",
                                                   "auto_start_breaks": "1", "ambient": "rain", "ambient_volume": "60"},
                      headers={"X-Requested-With": "fetch"})
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(self.q("SELECT focus_min, auto_start_breaks, auto_start_focus, ambient FROM user_settings")[0], (50, 1, 0, "rain"))
        self.post(self.c, "/settings/appearance", {"bg_preset": "../../etc", "bg_intensity": "70", "accent": "violet"})
        self.assertEqual(self.q("SELECT bg_preset FROM user_settings")[0][0], "cosmic-night")
        self.post(self.c, "/settings/appearance", {"bg_preset": "animated-stars", "bg_intensity": "55", "accent": "rose", "reduce_motion": "1"})
        self.assertEqual(self.q("SELECT bg_preset, bg_animated, bg_intensity, reduce_motion, accent FROM user_settings")[0],
                         ("animated-stars", 0, 55, 1, "rose"))

    def test_sql_injection_strings_are_inert(self):
        evil = "' OR 1=1; DROP TABLE users; --"
        self.post(self.c, "/notes/new", {"title": evil, "content": evil})
        for path in ("/tasks/", "/notes/", "/flashcards/manage"):
            self.assertEqual(self.c.get(path, query_string={"q": evil, "subject": evil, "status": evil, "sort": evil}).status_code, 200)
        self.assertEqual(self.q("SELECT COUNT(*) FROM users")[0][0], 1)
        self.assertEqual(self.q("SELECT title FROM notes")[0][0], evil)
        self.assertIn("&#39; OR 1=1", self.c.get("/notes/").get_data(as_text=True))   # escaped on output
        other = self.app.test_client()
        r = other.post("/login", data={"csrf_token": self.token(other), "email": evil, "password": evil})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.q("SELECT COUNT(*) FROM users")[0][0], 1)

    def test_dashboard_matches_database(self):
        self.post(self.c, "/subjects/new", {"name": "A"}); self.post(self.c, "/subjects/new", {"name": "B"})
        for i in range(3):
            self.post(self.c, "/tasks/new", {"title": f"t{i}"})
        tid = self.q("SELECT id FROM tasks")[0][0]
        self.post(self.c, f"/tasks/{tid}/toggle")
        self.post(self.c, "/notes/new", {"title": "n"})
        self.post(self.c, "/flashcards/new", {"question": "q", "answer": "a"})
        html = self.c.get("/").get_data(as_text=True)
        for value, label in ((2, "Subjects"), (3, "Assignments"), (1, "Completed"), (2, "Pending"), (1, "Notes"), (1, "Flashcards"), (0, "Focus sessions")):
            self.assertIn(f"<strong>{value}</strong><span>{label}</span>", html, label)
        self.assertIn("33%", html)    # 1 of 3 complete

    def test_empty_states_render(self):
        self.assertIn("No focus time yet this week", self.c.get("/").get_data(as_text=True))
        self.assertIn("Create your first subject", self.c.get("/subjects/").get_data(as_text=True))
        self.assertIn("No assignments yet", self.c.get("/tasks/").get_data(as_text=True))
        self.assertIn("No notes yet", self.c.get("/notes/").get_data(as_text=True))
        self.assertIn("No flashcards yet", self.c.get("/flashcards/").get_data(as_text=True))

    def test_active_navigation_comes_from_route(self):
        cases = {"/": "Dashboard", "/subjects/": "Subjects", "/tasks/": "Tasks & Assignments", "/notes/": "Notes",
                 "/flashcards/": "Flashcards", "/flashcards/manage": "Flashcards", "/history/": "Study History",
                 "/settings": "Settings", "/profile": "Profile", "/tasks/new": "Tasks & Assignments"}
        for path, label in cases.items():
            html = self.c.get(path).get_data(as_text=True)
            active = re.findall(r'class="side-link active"[^>]*>\s*<svg.*?</svg><span>([^<]+)</span>', html, re.S)
            self.assertEqual(active, [label.replace("&", "&amp;")] if "&" in label else [label], path)
        html = self.c.get("/timer/").get_data(as_text=True)
        self.assertEqual(re.findall(r'class="dock-item active"[^>]*>.*?<span>([^<]+)</span>', html, re.S), ["Focus Timer"])
        self.assertIn('class="dock-item active"', self.c.get("/").get_data(as_text=True))


class MigrationTests(unittest.TestCase):
    def test_legacy_database_upgrades_without_data_loss(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "legacy.db")
        con = sqlite3.connect(path)
        con.executescript("""
            CREATE TABLE subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, color TEXT DEFAULT '#9B7BFF', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, subject_id INTEGER, due_date TEXT, priority TEXT DEFAULT 'Medium', completed INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL);
            CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT DEFAULT '', subject_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL);
            CREATE TABLE study_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, duration INTEGER NOT NULL, studied_on TEXT NOT NULL, FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL);
            CREATE TABLE flashcards (id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, question TEXT NOT NULL, answer TEXT NOT NULL, FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE);
            INSERT INTO subjects (name) VALUES ('Old subject');
            INSERT INTO tasks (title, subject_id, completed) VALUES ('Old task', 1, 1);
            INSERT INTO notes (title, content, subject_id) VALUES ('Old note', 'body', 1);
            INSERT INTO study_sessions (subject_id, duration, studied_on) VALUES (1, 25, '2026-10-01');
            INSERT INTO flashcards (subject_id, question, answer) VALUES (1, 'old q', 'old a');
        """)
        con.commit(); con.close()
        app = create_app({"DATABASE": path, "SECRET_KEY": "k", "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000"})
        self.assertTrue([f for f in os.listdir(tmp) if ".backup-" in f], "pre-migration backup missing")
        create_app({"DATABASE": path, "SECRET_KEY": "k"})   # idempotent second start
        c = app.test_client()
        html = c.get("/register").get_data(as_text=True)
        tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        c.post("/register", data={"csrf_token": tok, "name": "First", "email": "f@example.com", "password": PW, "confirm": PW})
        con = sqlite3.connect(path)
        self.assertEqual(con.execute("SELECT name, user_id FROM subjects").fetchall(), [("Old subject", 1)])
        self.assertEqual(con.execute("SELECT title, user_id, completed FROM tasks").fetchall(), [("Old task", 1, 1)])
        self.assertEqual(con.execute("SELECT title, user_id FROM notes").fetchall(), [("Old note", 1)])
        self.assertEqual(con.execute("SELECT duration, user_id, kind FROM study_sessions").fetchall(), [(25, 1, "focus")])
        self.assertEqual(con.execute("SELECT question, user_id, box FROM flashcards").fetchall(), [("old q", 1, 0)])
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        con.close()
        # a second account must not see the adopted legacy data
        c2 = app.test_client()
        tok = re.search(r'name="csrf_token" value="([^"]+)"', c2.get("/register").get_data(as_text=True)).group(1)
        c2.post("/register", data={"csrf_token": tok, "name": "Second", "email": "s@example.com", "password": PW, "confirm": PW})
        self.assertNotIn("Old subject", c2.get("/subjects/").get_data(as_text=True))
        self.assertIn("Old subject", c.get("/subjects/").get_data(as_text=True))
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
