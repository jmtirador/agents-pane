"""The session reader: states, names, search and day counts, from hand-made transcript records."""

import os
import time
import unittest

from cockpit import sessions as ap

NOW = int(time.time() * 1000)


def assistant(text="", tools=(), at="2026-10-07T02:00:00.000Z", error=False):
    content = [{"type": "text", "text": text}] if text else []
    content += [{"type": "tool_use", "id": f"t{i}", "name": n, "input": inp} for i, (n, inp) in enumerate(tools)]
    rec = {"type": "assistant", "timestamp": at, "message": {"content": content}}
    if error:
        rec["isApiErrorMessage"] = True
    return rec


def user(text, at="2026-10-07T01:59:00.000Z"):
    return {"type": "user", "timestamp": at, "message": {"content": text}}


class RuleA(unittest.TestCase):
    def test_real_question_at_the_end(self):
        self.assertEqual(ap.asks_question("I compared both.\n\nWhich one should ship first?"), "Which one should ship first?")

    def test_offers_are_not_questions(self):
        for offer in ("Want me to patch the query?", "Should I push it?", "Would you like the long version?", "Good to send?"):
            self.assertIsNone(ap.asks_question(f"Done.\n\n{offer}"), offer)

    def test_question_before_the_last_paragraph_does_not_count(self):
        self.assertIsNone(ap.asks_question("Is this right?\n\nIt is, and it shipped."))

    def test_code_and_shortcut_hack_are_ignored(self):
        text = "Pick one.\n\nTea or coffee?\n\n```\nx = 1?\n```\n\nShortcut hack: press ctrl+r?"
        self.assertEqual(ap.asks_question(text), "Tea or coffee?")


class Words(unittest.TestCase):
    def test_a_one_word_first_sentence_takes_the_next_one_too(self):  # G5: "Done." says nothing
        self.assertEqual(ap.first_sentence("Done. The fix is in and the tests pass. Then more."), "Done. The fix is in and the tests pass.")
        self.assertEqual(ap.first_sentence("All the tests pass now. Then more."), "All the tests pass now.")

    def test_server_names_stay_whole(self):  # G4: "using ccd_sessio: dismiss_task"
        self.assertEqual(ap.tool_step({"name": "mcp__finch-browser__take_screenshot", "input": {}})[0], "finch-browser")
        self.assertEqual(ap.tool_step({"name": "mcp__plugin_posthog_posthog__query", "input": {}})[0], "posthog")
        self.assertEqual(ap.tool_step({"name": "mcp__fb5c1d77-2ac5-42bb-a8e0-0698ad75eec7__send", "input": {}})[0], "send")


class Tail(unittest.TestCase):
    def test_the_last_tool_call_with_no_result_is_pending(self):  # G2
        call = assistant(tools=[("Bash", {"description": "Read the log"})])
        self.assertEqual(ap.parse_tail([call])["pendingTool"], ("Bash", "Read the log"))
        answered = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0"}]}}
        self.assertIsNone(ap.parse_tail([call, answered])["pendingTool"])

    def test_unanswered_ask_is_pending_and_an_answer_clears_it(self):
        ask = assistant(tools=[("AskUserQuestion", {"questions": [{"question": "Tea or coffee?", "options": [{"label": "Tea"}, {"label": "Coffee"}]}]})])
        pending = ap.parse_tail([ask])["pendingAsk"]
        self.assertEqual(pending["question"], "Tea or coffee?")
        self.assertEqual(pending["options"], ["Tea", "Coffee"])
        answered = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t0", "content": "Coffee"}]}}
        self.assertIsNone(ap.parse_tail([ask, answered])["pendingAsk"])

    def test_steps_reset_on_a_typed_prompt_and_name_their_tools(self):
        recs = [
            assistant(tools=[("Read", {"file_path": "/a/b/c/old.py"})]),
            user("now fix it"),
            assistant(tools=[("Bash", {"command": "npm test", "description": "Run the tests"}), ("mcp__supabase__execute_sql", {})]),
        ]
        steps = ap.parse_tail(recs)["steps"]
        self.assertEqual([(s["tool"], s["what"]) for s in steps], [("Bash", "Run the tests"), ("supabase", "execute_sql")])

    def test_harness_noise_is_not_a_prompt(self):
        self.assertFalse(ap.is_typed_prompt(user("<command-name>/pane</command-name>")))
        self.assertFalse(ap.is_typed_prompt(user("This session is being continued from a previous conversation")))
        self.assertTrue(ap.is_typed_prompt(user("add pagination")))

    def test_permission_mode_is_read(self):
        self.assertEqual(ap.parse_tail([{"type": "permission-mode", "permissionMode": "bypassPermissions"}])["mode"], "bypassPermissions")

    def test_a_mode_is_read_from_the_newest_prompt_when_no_record_says_it(self):  # third review: the Claude app writes
        recs = [{**user("plan it"), "permissionMode": "plan"}, {**user("now build it"), "permissionMode": "bypassPermissions"}]
        self.assertEqual(ap.parse_tail(recs)["mode"], "bypassPermissions")  # no permission-mode records at all
        record = {"type": "permission-mode", "permissionMode": "bypassPermissions"}
        self.assertEqual(ap.parse_tail([record, {**user("go"), "permissionMode": "auto"}])["mode"], "bypassPermissions")  # a record wins

    def test_an_sdk_session_mode_is_read_from_its_first_prompt(self):  # second review: 25 of his newest 400 read as yolo
        import json
        import tempfile
        first = {"type": "user", "entrypoint": "sdk-cli", "permissionMode": "dontAsk", "message": {"content": "triage the inbox"}}
        filler = assistant("x" * 2000)
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(first) + "\n" + "".join(json.dumps(filler) + "\n" for _ in range(100)))  # past the tail
        self.assertEqual(ap.mode_of(f.name), "dontAsk")
        self.assertEqual(ap.read_head(f.name)["mode"], "dontAsk")
        os.remove(f.name)


class States(unittest.TestCase):
    """make_row's state rules, fed fake registry, job and transcript data."""

    def row(self, reg=None, job=None, recs=()):
        w = ap.Watcher()
        w.transcript_info = lambda sid, hint=None: (None, ap.parse_tail(list(recs)), "/no/such/path.jsonl")
        w.heads["s1"] = (0, {"firstPrompt": "fix the ledger", "firstTitle": "Ledger fix", "customTitle": "", "cwd": "", "mode": ""})
        return w.make_row("s1", reg or {}, job or {}, NOW)

    def reg(self, status, **extra):
        return {"sessionId": "s1", "pid": 1, "kind": "bg", "status": status, "statusUpdatedAt": NOW - 60_000, "startedAt": NOW - 600_000, **extra}

    def test_waiting_status_needs_you(self):
        self.assertEqual(self.row(self.reg("waiting"))["state"], "needs")

    def test_blocked_tempo_needs_you_with_its_detail_as_the_question(self):
        row = self.row(self.reg("idle"), {"state": "working", "tempo": "blocked", "detail": "Tea or coffee?"})
        self.assertEqual((row["state"], row["question"]), ("needs", "Tea or coffee?"))
        # the same tempo while busy is a stale flag, not a question
        self.assertNotEqual(self.row(self.reg("busy"), {"state": "working", "tempo": "blocked"})["state"], "needs")

    def test_a_stale_blocked_state_while_busy_is_working(self):
        row = self.row(self.reg("busy"), {"state": "blocked", "tempo": "active", "detail": "old question", "updatedAt": "2026-10-07T02:00:00Z"})
        self.assertIn(row["state"], ("working", "quiet"))

    def test_busy_is_working_and_ages_from_going_busy(self):
        row = self.row(self.reg("busy"))
        self.assertEqual(row["turnStart"], NOW - 60_000)

    def test_idle_after_a_real_question_asks(self):
        recs = [assistant("Both work.\n\nWhich one should ship first?", at=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()))]
        self.assertEqual(self.row(self.reg("idle"), recs=recs)["state"], "asks")

    def test_the_name_is_his_title_then_the_auto_title(self):
        self.assertEqual(self.row(self.reg("idle"))["name"], "Ledger fix")

    def test_a_permission_prompt_says_what_it_wants_to_do(self):  # G2: "waiting 44h" over a blank line
        recs = [assistant(tools=[("Bash", {"command": "ssh box tail deploy.log", "description": "Read the deploy log on the server"})])]
        row = self.row(self.reg("waiting", waitingFor="permission prompt"), recs=recs)
        self.assertEqual((row["state"], row["question"]), ("needs", "wants to run: Read the deploy log on the server"))

    def test_a_waiting_chat_with_no_tool_call_shows_the_question_it_ended_on(self):  # G2
        recs = [assistant("The draft is ready.\n\nShould I send it to the whole list now?")]
        self.assertEqual(self.row(self.reg("waiting"), recs=recs)["question"], "Should I send it to the whole list now?")

    def test_a_chat_in_the_claude_app_is_marked_as_one(self):  # G3
        self.assertTrue(self.row(self.reg("idle", entrypoint="claude-desktop"))["desktop"])
        self.assertFalse(self.row(self.reg("idle", entrypoint="cli"))["desktop"])

    def test_the_name_is_claude_codes_own_unless_he_renamed_it(self):  # G6: two names for one session
        self.assertEqual(self.row(self.reg("idle", name="ledger cleanup"))["name"], "ledger cleanup")
        self.assertEqual(self.row(self.reg("idle"), {"state": "done", "name": "ledger v2"})["name"], "ledger v2")
        renamed = [{"type": "custom-title", "customTitle": "my ledger"}]
        self.assertEqual(self.row(self.reg("idle", name="ledger cleanup"), recs=renamed)["name"], "my ledger")
        self.assertEqual(self.row(self.reg("idle", name="s1", jobId="s1"))["name"], "Ledger fix")  # an id is not a name

    def test_spare_workers_are_hidden(self):
        self.assertIsNone(self.row(self.reg("idle", spare=True)))

    def test_a_job_whose_process_died_mid_turn_is_stopped_not_working(self):
        self.assertEqual(self.row(None, {"state": "working", "tempo": "active"})["state"], "stopped")

    def test_a_dead_job_left_blocked_is_not_lime(self):
        self.assertNotEqual(self.row(None, {"state": "working", "tempo": "blocked", "detail": "old"})["state"], "needs")

    def test_an_error_followed_by_a_recovery_is_not_failed(self):
        recs = [assistant("API Error: overloaded", error=True), assistant("Recovered and finished.")]
        self.assertNotEqual(self.row(self.reg("idle"), recs=recs)["state"], "failed")
        self.assertEqual(self.row(self.reg("idle"), recs=recs[:1])["state"], "failed")

    def test_a_turn_starts_at_the_message_that_started_it(self):
        notice = {"type": "user", "timestamp": "2026-10-07T01:30:00.000Z", "message": {"content": "<task-notification>done</task-notification>"}}
        recs = [user("go", at="2026-10-07T01:00:00.000Z"), notice]
        self.assertEqual(self.row(self.reg("busy"), recs=recs)["turnStart"], ap.iso_ms("2026-10-07T01:30:00.000Z"))


class Paths(unittest.TestCase):
    def test_short_cwd(self):
        home = ap.HOME
        self.assertEqual(ap.short_cwd(home), "")
        self.assertEqual(ap.short_cwd(f"{home}/Projects/finch/backend/.claude/worktrees/x"), "finch/backend")
        self.assertEqual(ap.short_cwd(f"{home}/Projects/finch"), "finch")

    def test_snippet_keeps_the_match_near_the_start(self):
        text = "word " * 40 + "Invoice export " + "more " * 40
        self.assertLess(ap.snippet(text, "invoice").lower().find("invoice"), 20)

    def test_iso_times_are_utc(self):
        self.assertEqual(ap.iso_ms("2026-10-07T01:47:33.467Z"), 1791337653467)


class Days(unittest.TestCase):
    def test_a_utc_hour_becomes_his_local_day(self):
        os.environ["TZ"] = "America/Chicago"
        time.tzset()
        try:
            self.assertEqual(ap.local_day("2026-10-07T03"), "2026-10-06")
            self.assertEqual(ap.local_day("2026-10-07T15"), "2026-10-07")
        finally:
            del os.environ["TZ"]
            time.tzset()


if __name__ == "__main__":
    unittest.main()
