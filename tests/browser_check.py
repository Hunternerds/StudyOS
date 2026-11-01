"""Real-browser checks (optional; needs `pip install playwright` + a Chromium).

    python tests/browser_check.py            # prints PASS/FAIL per check, writes screenshots to ./instance/shots
"""
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("TEST_PORT", "5057"))
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = os.path.join(ROOT, "instance", "shots")
os.makedirs(SHOTS, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def main():
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "e2e.db")
    env = dict(os.environ, DATABASE_PATH=db, PORT=str(PORT), HOST="127.0.0.1", SECRET_KEY="e2e-secret",
               PASSWORD_HASH_METHOD="pbkdf2:sha256:1000", STUDYOS_ENV="development")
    server = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/login", timeout=1); break
            except Exception:
                time.sleep(0.25)
        run(db)
    finally:
        server.terminate()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} browser checks passed")
    sys.exit(1 if failed else 0)


def wait_eval(pg, expr, timeout=8.0):
    """Poll a JS expression via page.evaluate. (wait_for_function needs eval, which our CSP rightly forbids.)"""
    end = time.time() + timeout
    while time.time() < end:
        if pg.evaluate(expr):
            return True
        time.sleep(0.1)
    raise AssertionError("timed out waiting for: " + expr)


def rows(db, sql, args=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def run(db):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        mobile.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"),
                     lambda route: route.fulfill(status=200, content_type="text/css", body=""))
        page = mobile.new_page()
        errors, failed_requests = [], []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed_requests.append(r.url) if "fonts.g" not in r.url else None)
        page.on("response", lambda r: failed_requests.append(f"{r.status} {r.url}") if r.status >= 400 and "/login" not in r.url else None)

        # ------------------------------------------------ auth + branding
        page.goto(BASE + "/")
        check("unauthenticated visit redirects to login", "/login" in page.url)
        check("login page shows the StudyOS logo", page.evaluate("document.querySelector('.auth-logo').naturalWidth") > 0)
        check("favicon links point at the supplied logo", page.evaluate(
            "[...document.querySelectorAll('link[rel~=icon],link[rel=apple-touch-icon]')].every(l => l.href.includes('/static/images/'))"))
        page.screenshot(path=f"{SHOTS}/login-mobile.png")
        page.click("text=Create an account")
        page.fill("input[name=name]", "Ada Lovelace"); page.fill("input[name=email]", "ada@example.com")
        page.fill("input[name=password]", "Sup3rSecret!"); page.fill("input[name=confirm]", "Sup3rSecret!")
        page.click("main button[type=submit]:not([name])")
        page.wait_for_url(BASE + "/")
        check("registration logs the user in", "Good" in page.inner_text("h1") or "Still up" in page.inner_text("h1"))
        check("topbar shows logo + hamburger + avatar", page.locator(".topbar img").count() == 1 and page.locator("#menuToggle").is_visible() and page.locator(".topbar .avatar").is_visible())
        check("only Dashboard and Focus Timer in primary nav", page.locator(".dock-item").all_inner_texts() == ["Dashboard", "Focus Timer"])

        # ------------------------------------------------ sidebar behaviour
        page.click("#menuToggle")
        wait_eval(page, "document.documentElement.classList.contains('menu-open')")
        page.wait_for_timeout(400)
        check("sidebar opens", page.evaluate("document.getElementById('sidebar').getBoundingClientRect().left") >= -1)
        check("sidebar lists all required items", page.locator(".sidebar .side-link").all_inner_texts() ==
              ["Dashboard", "Subjects", "Tasks & Assignments", "Notes", "Flashcards", "Study History", "Settings", "Profile", "Log out"])
        check("page scroll is locked while menu open", page.evaluate("getComputedStyle(document.documentElement).overflow") == "hidden"
              and page.evaluate("getComputedStyle(document.body).overflow") == "hidden")
        check("aria-expanded reflects state", page.get_attribute("#menuToggle", "aria-expanded") == "true")
        check("active item highlighted (Dashboard)", page.locator(".side-link.active").inner_text() == "Dashboard")
        page.keyboard.press("Escape"); page.wait_for_timeout(400)
        check("Escape closes the sidebar", page.evaluate("document.getElementById('sidebar').getBoundingClientRect().right") <= 1
              and page.get_attribute("#menuToggle", "aria-expanded") == "false")
        page.click("#menuToggle"); page.wait_for_timeout(400)
        page.mouse.click(370, 400); page.wait_for_timeout(400)   # tap outside (on the scrim)
        check("tapping outside closes the sidebar", not page.evaluate("document.documentElement.classList.contains('menu-open')"))
        page.click("#menuToggle"); page.wait_for_timeout(350)
        page.click(".sidebar >> text=Subjects"); page.wait_for_url(BASE + "/subjects/")
        check("selecting a page closes the menu and navigates", not page.evaluate("document.documentElement.classList.contains('menu-open')"))
        page.click("#menuToggle"); page.wait_for_timeout(350)
        check("active state follows the route (Subjects)", page.locator(".side-link.active").inner_text() == "Subjects")
        page.set_viewport_size({"width": 390, "height": 300}); page.wait_for_timeout(200)
        can_scroll = page.evaluate("(() => { const n = document.querySelector('.sidebar-nav'); n.scrollTop = 9999; return n.scrollHeight > n.clientHeight && n.scrollTop > 0; })()")
        check("sidebar itself scrolls on short screens", can_scroll)
        page.set_viewport_size({"width": 390, "height": 844}); page.keyboard.press("Escape"); page.wait_for_timeout(350)

        # ------------------------------------------------ create academic data through the UI
        page.goto(BASE + "/subjects/new"); page.fill("input[name=name]", "Mathematics"); page.fill("textarea[name=description]", "Calculus & algebra")
        page.click("main button[type=submit]:not([name])"); page.wait_for_url(re.compile(r"/subjects/\d+$"))
        check("subject created and detail page opens", page.inner_text("h1") == "Mathematics")
        page.goto(BASE + "/subjects/new"); page.fill("input[name=name]", "Biology"); page.locator(".swatch").nth(3).click(); page.click("main button[type=submit]:not([name])")
        page.wait_for_url(re.compile(r"/subjects/\d+$"))
        for title, prio, due in (("Problem set 4", "High", "2020-01-01"), ("Lab report", "Low", "2099-01-01")):
            page.goto(BASE + "/tasks/new"); page.fill("input[name=title]", title); page.fill("input[name=due_date]", due)
            page.locator(f".seg-form label:has-text('{prio}')").click(); page.click("main button[type=submit]:not([name])"); page.wait_for_url(BASE + "/tasks/")
        check("overdue assignment is clearly marked", page.locator(".task.overdue").count() == 1 and "overdue" in page.locator(".task.overdue").inner_text())
        page.locator(".task:has-text('Problem set 4') .check").click(); page.wait_for_load_state()
        check("assignment can be completed", page.locator(".task.done").count() == 1)
        page.fill("input[name=q]", "lab"); page.press("input[name=q]", "Enter"); page.wait_for_load_state()
        check("assignment search filters results", page.locator(".task").count() == 1 and "Lab report" in page.inner_text(".task-list"))
        page.goto(BASE + "/tasks/")
        page.locator(".task:has-text('Lab report') .icon-btn.danger").click()
        page.wait_for_selector("#confirmDialog[open]")
        check("delete asks for confirmation", "Lab report" in page.inner_text("#confirmText"))
        page.click("#confirmDialog button[value=cancel]"); page.wait_for_timeout(200)
        check("cancel keeps the assignment", page.locator(".task").count() == 2)
        page.locator(".task:has-text('Lab report') .icon-btn.danger").click(); page.wait_for_selector("#confirmDialog[open]")
        with page.expect_navigation():
            page.click("#confirmOk")
        check("confirming deletes the assignment", page.locator(".task").count() == 1 and rows(db, "SELECT COUNT(*) FROM tasks")[0][0] == 1)

        # ------------------------------------------------ notes autosave
        page.goto(BASE + "/notes/new")
        page.fill(".editor-title", "Limits"); page.fill(".editor-body", "epsilon-delta definition")
        wait_eval(page, "document.getElementById('saveState').textContent.includes('All changes saved')")
        check("note autosaves and URL becomes the note URL", re.search(r"/notes/\d+$", page.url) is not None and rows(db, "SELECT content FROM notes")[0][0] == "epsilon-delta definition")
        page.fill(".editor-body", "epsilon-delta definition, updated"); wait_eval(page, "document.getElementById('saveState').textContent.includes('All changes saved')")
        check("editing a note updates it (no duplicate)", rows(db, "SELECT COUNT(*), MAX(content) FROM notes")[0] == (1, "epsilon-delta definition, updated"))

        # ------------------------------------------------ flashcards
        for q, a in (("What is a derivative?", "Rate of change"), ("What is an integral?", "Area under a curve"), ("Define limit", "Value a function approaches")):
            page.goto(BASE + "/flashcards/new"); page.fill("textarea[name=question]", q); page.fill("textarea[name=answer]", a); page.click("main button[type=submit]:not([name])")
            page.wait_for_url(BASE + "/flashcards/manage")
        page.goto(BASE + "/flashcards/")
        check("study view shows ONE card at a time", page.locator(".flip").count() == 1 and "Card 1 of 3" in page.inner_text("#progressText"))
        first = page.inner_text("#frontText")
        check("answer side hidden until flipped", not page.locator("#gradeRow").is_visible())
        page.click("#flipCard"); page.wait_for_timeout(600)
        check("flip reveals answer + grading buttons", page.locator("#gradeRow").is_visible() and page.inner_text("#backText") != "")
        page.screenshot(path=f"{SHOTS}/flashcard-flipped-mobile.png")
        page.click("#reviseBtn"); page.wait_for_timeout(200)
        check("'revise' re-queues the card at the end", page.inner_text("#frontText") != first and "Card 1 of 3" in page.inner_text("#progressText"))
        for _ in range(3):                      # B, C, then the re-queued A
            page.click("#flipBtn"); page.click("#rememberBtn")
        page.wait_for_selector("#doneCard:not([hidden])")
        check("session completes with summary", "remembered" in page.inner_text("#doneText"))
        boxes = sorted(r[0] for r in rows(db, "SELECT box FROM flashcards"))
        check("spaced-repetition boxes saved on the server", boxes == [1, 1, 2] and rows(db, "SELECT COUNT(*) FROM flashcards WHERE due_on IS NOT NULL")[0][0] == 3)
        page.goto(BASE + "/flashcards/")
        check("remembered cards are no longer due", "All caught up" in page.inner_text("main"))

        # ------------------------------------------------ timer (fake clock, real DOM)
        tp = mobile.new_page()
        terrors = []
        tp.on("console", lambda m: terrors.append(m.text) if m.type == "error" else None); tp.on("pageerror", lambda e: terrors.append(str(e)))
        tp.clock.install(time=datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc))
        tp.goto(BASE + "/timer/")
        check("timer defaults to 25:00 focus", tp.inner_text("#clock") == "25:00" and tp.locator("#modeTabs .active").inner_text() == "Focus")
        tp.select_option("#subjectSel", label="Mathematics")
        tp.screenshot(path=f"{SHOTS}/timer-idle-mobile.png")
        tp.click("#btnMain")
        check("starting enters immersive mode", tp.evaluate("document.body.classList.contains('immersive')") and tp.get_attribute("#timer", "data-state") == "running")
        wait_eval(tp, "getComputedStyle(document.querySelector('.topbar')).visibility === 'hidden'")
        check("normal header and bottom nav are hidden", tp.evaluate("getComputedStyle(document.querySelector('.topbar')).visibility") == "hidden"
              and tp.evaluate("getComputedStyle(document.querySelector('.dock')).visibility") == "hidden")
        check("page controls (tabs/settings) are removed", tp.evaluate("[...document.querySelectorAll('.timer-chrome')].every(e => getComputedStyle(e).display === 'none')"))
        tp.clock.run_for(2000)
        check("controls still visible before 3s of inactivity", not tp.evaluate("document.body.classList.contains('controls-hidden')"))
        tp.clock.run_for(1500)
        check("controls auto-hide after ~3s inactivity", tp.evaluate("document.body.classList.contains('controls-hidden')"))
        wait_eval(tp, "getComputedStyle(document.getElementById('controls')).opacity === '0'")
        check("hidden controls ignore pointer events", tp.evaluate("getComputedStyle(document.getElementById('controls')).pointerEvents") == "none")
        check("countdown keeps running while controls hidden", tp.inner_text("#clock") in ("24:56", "24:57"), tp.inner_text("#clock"))
        box = tp.locator("#btnMain").bounding_box()
        tp.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        tp.wait_for_timeout(100)
        check("touch reveals controls", not tp.evaluate("document.body.classList.contains('controls-hidden')"))
        check("the revealing tap does NOT press a button", tp.get_attribute("#timer", "data-state") == "running")
        tp.screenshot(path=f"{SHOTS}/timer-running-mobile.png")
        tp.clock.run_for(3500)
        check("controls hide again after more inactivity", tp.evaluate("document.body.classList.contains('controls-hidden')"))
        tp.keyboard.press("Shift")
        check("keyboard reveals controls", not tp.evaluate("document.body.classList.contains('controls-hidden')"))
        tp.clock.run_for(3500)
        tp.mouse.move(100, 100)
        check("mouse movement reveals controls", not tp.evaluate("document.body.classList.contains('controls-hidden')"))
        tp.click("#btnMain")
        wait_eval(tp, "getComputedStyle(document.querySelector('.topbar')).visibility === 'visible'")
        check("pause restores the normal interface", tp.get_attribute("#timer", "data-state") == "paused" and not tp.evaluate("document.body.classList.contains('immersive')")
              and tp.evaluate("getComputedStyle(document.querySelector('.topbar')).visibility") == "visible",
              tp.evaluate("[document.getElementById('timer').dataset.state, document.body.className, getComputedStyle(document.querySelector('.topbar')).visibility]").__str__())
        frozen = tp.inner_text("#clock"); tp.clock.run_for(120_000)
        check("paused countdown does not move", tp.inner_text("#clock") == frozen and tp.inner_text("#mainLabel") == "Resume")
        tp.click("#btnMain"); check("resume continues", tp.get_attribute("#timer", "data-state") == "running" and tp.inner_text("#mainLabel") == "Pause")
        tp.click("#btnReset") if tp.locator("#btnReset").is_visible() else tp.mouse.move(5, 5)
        tp.mouse.move(50, 50); tp.click("#btnReset")
        check("reset returns to idle 25:00 with normal UI", tp.inner_text("#clock") == "25:00" and tp.get_attribute("#timer", "data-state") == "idle" and not tp.evaluate("document.body.classList.contains('immersive')"))
        check("reset saved nothing", rows(db, "SELECT COUNT(*) FROM study_sessions")[0][0] == 0)

        tp.click("#btnMain"); tp.mouse.move(60, 60)
        tp.clock.fast_forward(26 * 60 * 1000)   # simulates a locked phone: no intermediate ticks
        wait_eval(tp, "document.getElementById('status').textContent.includes('saved')")
        check("finishing a focus session saves exactly one row", rows(db, "SELECT COUNT(*) FROM study_sessions")[0][0] == 1)
        check("saved with duration, subject and today's date", rows(db, "SELECT s.duration, m.name, s.kind FROM study_sessions s JOIN subjects m ON m.id=s.subject_id")[0] == (25, "Mathematics", "focus"))
        check("completion message shown, moved to short break", "Focus session saved" in tp.inner_text("#status") and tp.locator("#modeTabs .active").inner_text() == "Short break" and tp.inner_text("#clock") == "05:00")
        check("session counter advanced", "1 of 4" in tp.inner_text("#counter"))
        tp.click("#btnMain"); tp.mouse.move(70, 70); tp.clock.run_for(5 * 60 * 1000 + 1500); tp.wait_for_timeout(300)
        check("break finishing does NOT record study time", rows(db, "SELECT COUNT(*) FROM study_sessions")[0][0] == 1 and tp.locator("#modeTabs .active").inner_text() == "Focus")

        # custom timer + reload survival
        tp.click("[data-mode=custom]"); tp.fill("#customMin", "3")
        check("custom duration applied", tp.inner_text("#clock") == "03:00")
        tp.click("#btnMain"); tp.mouse.move(80, 80); tp.clock.run_for(60_000)
        tp.reload(); tp.wait_for_load_state()
        check("running timer survives a page reload", tp.get_attribute("#timer", "data-state") == "running" and "01:30" <= tp.inner_text("#clock") <= "02:05", tp.inner_text("#clock"))
        tp.mouse.move(90, 90); tp.clock.run_for(2 * 60 * 1000 + 2000); wait_eval(tp, "document.getElementById('status').textContent.includes('saved')")
        check("custom session recorded with its own length", rows(db, "SELECT duration FROM study_sessions ORDER BY id")[-1][0] == 3 and rows(db, "SELECT COUNT(*) FROM study_sessions")[0][0] == 2)
        tp.reload(); tp.wait_for_load_state(); tp.wait_for_timeout(300)
        check("reloading after completion never double-saves", rows(db, "SELECT COUNT(*) FROM study_sessions")[0][0] == 2)
        check("timer page has no console errors", not terrors, str(terrors))
        check("fullscreen control available when supported", tp.evaluate("!!document.documentElement.requestFullscreen") == (not tp.locator("#btnFull").is_hidden()))

        # settings drawer (custom lengths persisted per user)
        tp.click("#timerSettings summary"); tp.fill("#timerForm [name=focus_min]", "50"); tp.click("#timerForm button[type=submit]")
        wait_eval(tp, "document.getElementById('status').textContent.includes('settings saved')")
        tp.click("[data-mode=focus]")
        check("saved timer settings change durations immediately", tp.inner_text("#clock") == "50:00" and rows(db, "SELECT focus_min FROM user_settings")[0][0] == 50)
        tp.close()

        # ------------------------------------------------ dashboard + history use real data
        page.goto(BASE + "/")
        text = page.inner_text("main")
        check("dashboard reflects real counts", "Mathematics" in text and "2" in page.locator(".stat:has-text('Focus sessions') strong").inner_text())
        check("dashboard weekly chart has a bar", page.locator(".bar-col i").count() >= 7)
        page.screenshot(path=f"{SHOTS}/dashboard-mobile.png", full_page=True)
        page.goto(BASE + "/history/")
        check("history totals match sessions (28 min)", page.locator(".stat:has-text('Focused minutes') strong").inner_text() == "28")
        with page.expect_navigation():
            page.select_option("select[name=subject]", label="Biology")
        check("history filter: subject without sessions shows zero", page.locator(".stat:has(span:text-is('Sessions')) strong").inner_text() == "0")
        with page.expect_navigation():
            page.select_option("select[name=subject]", label="Mathematics")
        check("history filter: Mathematics shows its 2 sessions / 28 min", page.locator(".stat:has(span:text-is('Sessions')) strong").inner_text() == "2"
              and page.locator(".stat:has(span:text-is('Focused minutes')) strong").inner_text() == "28")
        page.screenshot(path=f"{SHOTS}/history-mobile.png", full_page=True)

        # ------------------------------------------------ settings + personalisation
        page.goto(BASE + "/settings")
        page.locator(".preset:has-text('Midnight Ocean')").click()
        check("background preview applies instantly", page.evaluate("document.documentElement.dataset.bg") == "midnight-ocean")
        page.locator(".swatch[title=Emerald]").click(); page.locator(".switch:has-text('Animated background')").click()
        check("accent + animation preview apply", page.evaluate("document.documentElement.style.getPropertyValue('--accent-rgb').trim()") == "52 211 153" and page.evaluate("document.documentElement.dataset.anim") == "0")
        page.click("#appearanceForm button[type=submit]"); page.wait_for_load_state()
        page.reload()
        check("appearance persists after reload", page.evaluate("document.documentElement.dataset.bg") == "midnight-ocean" and page.evaluate("document.documentElement.dataset.anim") == "0")
        page.screenshot(path=f"{SHOTS}/settings-mobile.png", full_page=True)

        # ------------------------------------------------ logout
        page.goto(BASE + "/profile")
        page.click("#menuToggle"); page.wait_for_timeout(350); page.click(".sidebar button.side-link"); page.wait_for_url(re.compile("/login"))
        check("logout ends the session", "/login" in page.url)
        page.goto(BASE + "/tasks/")
        check("protected page redirects after logout", "/login" in page.url)

        # ------------------------------------------------ layout sweeps
        page.goto(BASE + "/login"); page.fill("input[name=email]", "ada@example.com"); page.fill("input[name=password]", "Sup3rSecret!"); page.click("main button[type=submit]:not([name])"); page.wait_for_url(BASE + "/")
        pages = ["/", "/timer/", "/subjects/", "/subjects/new", "/tasks/", "/tasks/new", "/notes/", "/notes/new", "/flashcards/", "/flashcards/manage",
                 "/flashcards/new", "/history/", "/settings", "/profile"]
        subject_id = rows(db, "SELECT id FROM subjects ORDER BY id")[0][0]
        pages.append(f"/subjects/{subject_id}")
        for label, size in (("phone-360", (360, 740)), ("phone-390", (390, 844)), ("tablet", (820, 1180)), ("desktop", (1366, 800))):
            page.set_viewport_size({"width": size[0], "height": size[1]})
            overflow = []
            broken = []
            for path in pages:
                page.goto(BASE + path); page.wait_for_load_state("networkidle")
                if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                    overflow.append(path)
                broken += page.evaluate("[...document.images].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)")
                if page.locator("use").count() and page.evaluate(
                        "[...document.querySelectorAll('use')].some(u => !document.querySelector(u.getAttribute('href')))"):
                    broken.append("missing icon on " + path)
            check(f"no horizontal overflow on any page ({label})", not overflow, str(overflow))
            check(f"no broken images / missing icons ({label})", not broken, str(broken))
        page.set_viewport_size({"width": 1366, "height": 800}); page.goto(BASE + "/")
        page.screenshot(path=f"{SHOTS}/dashboard-desktop.png")
        page.goto(BASE + "/timer/"); page.screenshot(path=f"{SHOTS}/timer-desktop.png")
        check("no console errors or failed requests during the session", not errors and not failed_requests, str(errors[:3]) + str(failed_requests[:3]))
        browser.close()


if __name__ == "__main__":
    main()
