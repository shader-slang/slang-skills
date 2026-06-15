#!/usr/bin/env python3
"""Unit tests for the pure decision functions in pr_sweep.py and pr_signal.py.

No live `gh` calls — every test constructs plain data and checks the synthesis
logic (classification, the state machine, working-hours/idle gates, CI
summarization, backoff windowing, committer-signal weighting, and the hybrid
tiebreak bookkeeping).

Run:  python3 scripts/test_pr_sweep.py
"""
from __future__ import annotations

# Tests use unittest's setUp pattern, which confuses strict type inference.
# Relax the strict rules for this test module.
# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportImplicitOverride=false, reportUninitializedInstanceVariable=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportUnusedCallResult=false, reportImplicitRelativeImport=false, reportUnusedParameter=false, reportPrivateUsage=false

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from typing import final

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import pr_sweep as sweep      # noqa: E402  (path inserted above)
import pr_signal as signal    # noqa: E402


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def make_cfg(**kw):
    base = dict(repos=["shader-slang/slang"], project_id="P",
                bot_authors=["nv-slang-bot", "slang-coworker-nanoclaw", "Copilot", "copilot-swe-agent"])
    base.update(kw)
    return sweep.Config(**base)


def make_pr(**kw):
    # On the board by default (project_item_id set) so lifecycle tests don't trip
    # the off-board rule; Community source by default (the bot-overseen human
    # flow). Pass project_item_id=None / source=... to test other paths.
    defaults = dict(repo="shader-slang/slang", number=1, project_item_id="PVTI_x",
                    source="Community")
    defaults.update(kw)
    return sweep.PR(**defaults)


@final
class TestClassification(unittest.TestCase):
    def test_bot_author_variants(self):
        bots = ["nv-slang-bot", "slang-coworker-nanoclaw"]
        self.assertTrue(signal.classify_is_bot("nv-slang-bot", bots))
        self.assertTrue(signal.classify_is_bot("nv-slang-bot[bot]", bots))
        self.assertTrue(signal.classify_is_bot("app/nv-slang-bot", bots))
        self.assertTrue(signal.classify_is_bot("slang-coworker-nanoclaw[bot]", bots))
        self.assertFalse(signal.classify_is_bot("some-human", bots))


@final
class TestWorkingHours(unittest.TestCase):
    def setUp(self):
        self.tz = timezone.utc

    def test_weekday_span(self):
        # Mon 09:00 -> Tue 09:00 = 24 working hours
        start = utc(2026, 6, 8, 9)   # Monday
        end = utc(2026, 6, 9, 9)     # Tuesday
        self.assertAlmostEqual(sweep.working_hours_between(start, end, self.tz), 24.0, places=3)

    def test_weekend_skipped(self):
        # Fri 12:00 -> Mon 12:00 spans a full weekend; only Fri 12:00->Sat 00:00
        # (12h) + Mon 00:00->Mon 12:00 (12h) = 24 working hours.
        start = utc(2026, 6, 12, 12)  # Friday
        end = utc(2026, 6, 15, 12)    # Monday
        self.assertAlmostEqual(sweep.working_hours_between(start, end, self.tz), 24.0, places=3)

    def test_zero_when_reversed(self):
        self.assertEqual(sweep.working_hours_between(utc(2026, 6, 9), utc(2026, 6, 8), self.tz), 0.0)


@final
class TestCiSummary(unittest.TestCase):
    def test_action_required_wins(self):
        runs = [{"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "action_required"}]
        self.assertEqual(sweep.summarize_ci(runs), sweep.CI_ACTION_REQUIRED)

    def test_pending(self):
        runs = [{"status": "in_progress", "conclusion": None}]
        self.assertEqual(sweep.summarize_ci(runs), sweep.CI_PENDING)

    def test_failed(self):
        runs = [{"status": "completed", "conclusion": "failure"}]
        self.assertEqual(sweep.summarize_ci(runs), sweep.CI_FAILED)

    def test_passed(self):
        runs = [{"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "skipped"}]
        self.assertEqual(sweep.summarize_ci(runs), sweep.CI_PASSED)

    def test_none(self):
        self.assertEqual(sweep.summarize_ci([]), sweep.CI_NONE)


@final
class TestReconcile(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def test_human_draft_is_noop(self):
        pr = make_pr(is_draft=True, is_bot=False, author="alice")
        self.assertTrue(sweep.reconcile(pr, self.cfg).is_noop())

    def test_merged_goes_done(self):
        pr = make_pr(state="MERGED", board_status="Todo")
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Done")

    def test_merged_already_done_noop(self):
        pr = make_pr(state="MERGED", board_status="Done")
        self.assertTrue(sweep.reconcile(pr, self.cfg).is_noop())

    def test_unassigned_human_gets_assignee_and_reviewers(self):
        pr = make_pr(author="alice", assignee_pick="bob", review_requests=["bob", "carol"],
                     ci_state=sweep.CI_PENDING, board_status="Revising")
        d = sweep.reconcile(pr, self.cfg)
        self.assertEqual(d.set_assignee, "bob")
        self.assertEqual(d.request_reviewers, ["bob", "carol"])

    def test_bot_pr_assigned_at_promotion(self):
        pr = make_pr(author="nv-slang-bot", is_bot=True, is_draft=True,
                     coverage_passed=True, board_status="Revising",
                     assignee_pick="bob", review_requests=["bob"])
        d = sweep.reconcile(pr, self.cfg)
        self.assertEqual(d.set_status, "Todo")
        self.assertEqual(d.set_assignee, "bob")

    def test_change_requested_returns_to_revising(self):
        pr = make_pr(author="alice", assignees=["bob"], change_requested=True,
                     board_status="Todo", ci_state=sweep.CI_PASSED)
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_human_ci_clean_promotes_to_todo(self):
        pr = make_pr(author="alice", assignees=["bob"], ci_state=sweep.CI_PASSED,
                     board_status="Revising")
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Todo")

    def test_human_ci_pending_no_status_set_revising(self):
        pr = make_pr(author="alice", assignees=["bob"], ci_state=sweep.CI_PENDING,
                     board_status=None)
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_bot_draft_goes_to_todo_without_coverage_gate(self):
        # No coverage check configured (default cfg): a bot draft is shepherded
        # by a human owner, so it promotes to Todo + assignee regardless of draft.
        pr = make_pr(author="nv-slang-bot", is_bot=True, is_draft=True, source="Bot",
                     coverage_passed=False, board_status="Revising", assignee_pick="bob")
        d = sweep.reconcile(pr, self.cfg)
        self.assertEqual(d.set_status, "Todo")
        self.assertEqual(d.set_assignee, "bob")
        self.assertIsNone(d.comment_kind)  # draft is not "ready for review" yet

    def test_bot_draft_coverage_gated_when_check_configured(self):
        cfg = make_cfg(coverage_check="draft-coverage")
        not_ready = make_pr(author="nv-slang-bot", is_bot=True, is_draft=True, source="Bot",
                            coverage_passed=False, board_status="Revising")
        self.assertTrue(sweep.reconcile(not_ready, cfg).is_noop())
        ready = make_pr(author="nv-slang-bot", is_bot=True, is_draft=True, source="Bot",
                        coverage_passed=True, board_status="Revising", assignee_pick="bob")
        self.assertEqual(sweep.reconcile(ready, cfg).set_status, "Todo")

    def test_bot_failing_ci_in_todo_not_bounced(self):
        # Bot PRs are owner-shepherded; a failing-CI bot PR in Todo stays put
        # (only human PRs bounce on failing CI).
        pr = make_pr(author="nv-slang-bot", is_bot=True, assignees=["bob"], source="Bot",
                     ci_state=sweep.CI_FAILED, board_status="Todo")
        self.assertTrue(sweep.reconcile(pr, self.cfg).is_noop())

    def test_in_progress_never_overwritten_on_promotion(self):
        pr = make_pr(author="alice", assignees=["bob"], ci_state=sweep.CI_PASSED,
                     board_status="In Progress")
        self.assertTrue(sweep.reconcile(pr, self.cfg).is_noop())

    # --- auto-corrections -------------------------------------------------
    def test_off_board_pr_added(self):
        pr = make_pr(author="alice", project_item_id=None)
        d = sweep.reconcile(pr, self.cfg)
        self.assertTrue(d.add_to_project)
        self.assertFalse(d.is_noop())

    def test_human_draft_in_todo_moves_to_revising(self):
        pr = make_pr(author="alice", is_draft=True, board_status="Todo")
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_human_draft_in_done_moves_to_revising(self):
        pr = make_pr(author="alice", is_draft=True, board_status="Done")
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_open_done_in_merge_queue_left_alone(self):
        pr = make_pr(author="alice", assignees=["bob"], board_status="Done",
                     in_merge_queue=True, review_decision="APPROVED")
        self.assertTrue(sweep.reconcile(pr, self.cfg).is_noop())

    def test_open_done_not_queued_approved_back_to_todo(self):
        pr = make_pr(author="alice", board_status="Done", in_merge_queue=False,
                     review_decision="APPROVED", assignee_pick="bob")
        d = sweep.reconcile(pr, self.cfg)
        self.assertEqual(d.set_status, "Todo")
        self.assertEqual(d.set_assignee, "bob")

    def test_open_done_changes_requested_back_to_revising(self):
        pr = make_pr(author="alice", board_status="Done", in_merge_queue=False,
                     review_decision="CHANGES_REQUESTED")
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_todo_failing_ci_back_to_revising(self):
        pr = make_pr(author="alice", assignees=["bob"], board_status="Todo",
                     ci_state=sweep.CI_FAILED)
        self.assertEqual(sweep.reconcile(pr, self.cfg).set_status, "Revising")

    def test_in_progress_no_assignee_demoted_and_assigned(self):
        pr = make_pr(author="alice", board_status="In Progress", assignees=[],
                     assignee_pick="bob")
        d = sweep.reconcile(pr, self.cfg)
        self.assertEqual(d.set_status, "Todo")
        self.assertEqual(d.set_assignee, "bob")


@final
class TestPredicates(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def _match(self, pr):
        return next((p for p in sweep.ladder_for(pr, self.cfg) if p.applies(pr, self.cfg)), None)

    def test_needs_ci_approval(self):
        pr = make_pr(source="Community", ci_state=sweep.CI_ACTION_REQUIRED)
        p = self._match(pr)
        self.assertEqual(p.key, "needs_ci_approval")
        self.assertEqual(p.render(pr, self.cfg, 0), "needs CI approval")

    def test_changes_requested(self):
        pr = make_pr(source="Community", change_requested=True)
        p = self._match(pr)
        self.assertEqual(p.key, "changes_requested")
        self.assertIn("changes requested", p.render(pr, self.cfg, 0))

    def test_awaiting_review(self):
        pr = make_pr(source="Community", board_status="Todo",
                     existing_reviewers=["dan"], review_decision="REVIEW_REQUIRED")
        p = self._match(pr)
        self.assertEqual(p.key, "awaiting_review")
        self.assertEqual(p.render(pr, self.cfg, 0), "awaiting review from: `dan`")

    def test_ci_failing(self):
        pr = make_pr(source="Community", board_status="Revising", ci_state=sweep.CI_FAILED)
        self.assertEqual(self._match(pr).key, "ci_failing")

    def test_idle_catchall_and_render(self):
        pr = make_pr(source="Community", board_status="Revising", ci_state=sweep.CI_PENDING)
        p = self._match(pr)
        self.assertEqual(p.key, "idle")
        self.assertEqual(p.render(pr, self.cfg, 3), "idle for 3 days")

    def test_first_match_precedence(self):
        pr = make_pr(source="Community", ci_state=sweep.CI_ACTION_REQUIRED, change_requested=True)
        self.assertEqual(self._match(pr).key, "needs_ci_approval")  # earliest applicable wins

    def test_bot_ladder_omits_ci_approval_and_changes(self):
        keys = [p.key for p in sweep.BOT_LADDER]
        self.assertNotIn("needs_ci_approval", keys)
        self.assertNotIn("changes_requested", keys)

    def test_internal_has_no_ladder(self):
        self.assertEqual(sweep.ladder_for(make_pr(source="Internal"), self.cfg), [])


@final
class TestComputeStall(unittest.TestCase):
    def setUp(self):
        self.now = utc(2026, 6, 10, 12)
        self.tz = timezone.utc

    def test_first_sight_anchors_to_activity(self):
        pr = make_pr(board_status="Todo", head_sha="abc", last_activity_at=utc(2026, 6, 9, 12))
        state, _wh, days = sweep.compute_stall(pr, {}, self.now, self.tz)
        self.assertEqual(sweep.parse_iso(state["last_moved_at"]), utc(2026, 6, 9, 12))
        self.assertEqual(days, 1)

    def test_unchanged_keeps_prior(self):
        pr = make_pr(board_status="Todo", head_sha="abc")
        prior = {"move_fingerprint": ["Todo", "abc", None],
                 "last_moved_at": utc(2026, 6, 8).isoformat()}
        state, _wh, _days = sweep.compute_stall(pr, prior, self.now, self.tz)
        self.assertEqual(state["last_moved_at"], prior["last_moved_at"])

    def test_movement_resets_to_now(self):
        pr = make_pr(board_status="Todo", head_sha="NEW")
        prior = {"move_fingerprint": ["Revising", "abc", None],
                 "last_moved_at": utc(2026, 6, 1).isoformat()}
        state, _wh, days = sweep.compute_stall(pr, prior, self.now, self.tz)
        self.assertEqual(sweep.parse_iso(state["last_moved_at"]), self.now)
        self.assertEqual(days, 0)


@final
class TestBuildReport(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg(maintainer="maint")

    def _awaiting(self, **kw):
        base = dict(board_status="Todo", existing_reviewers=["dan"],
                    review_decision="REVIEW_REQUIRED")
        base.update(kw)
        return make_pr(**base)

    def test_assignee_only_below_maintainer_rung(self):
        pr = self._awaiting(number=10, source="Community", assignees=["bob"])
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (30.0, 2)})  # 24 <= 30 < 48
        self.assertIn("bob", rec)
        self.assertNotIn("maint", rec)
        self.assertFalse(rec["bob"][0].escalated)

    def test_escalates_in_place_no_maintainer_section(self):
        # Past the maintainer rung: the item gains the up-arrow but stays under
        # the assignee; there is no separate maintainer section.
        pr = self._awaiting(number=11, source="Community", assignees=["bob"])
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 3)})  # >= 48
        self.assertEqual(list(rec.keys()), ["bob"])
        self.assertNotIn("maint", rec)
        self.assertTrue(rec["bob"][0].escalated)
        self.assertEqual(rec["bob"][0].assignee, "bob")

    def test_community_changes_requested_timings(self):
        # changes_requested escalates slowly: assignee @1wk (168 wh), maintainer @2wk (336 wh).
        pr = self._awaiting(number=17, source="Community", assignees=["bob"],
                            change_requested=True)
        self.assertEqual(sweep.build_report([pr], self.cfg, {pr.key(): (120.0, 5)}), {})  # < 168
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (200.0, 9)})  # 168 <= 200 < 336
        self.assertIn("changes requested", rec["bob"][0].reason)
        self.assertFalse(rec["bob"][0].escalated)
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (340.0, 15)})  # >= 336
        self.assertTrue(rec["bob"][0].escalated)

    def test_below_first_rung_nobody(self):
        pr = self._awaiting(number=12, source="Community", assignees=["bob"])
        self.assertEqual(sweep.build_report([pr], self.cfg, {pr.key(): (10.0, 0)}), {})

    def test_bot_thresholds_higher(self):
        pr = self._awaiting(number=13, source="Bot", is_bot=True, assignees=["carol"])
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 2)})  # community would escalate; bot maint=168
        self.assertIn("carol", rec)
        self.assertNotIn("maint", rec)

    def test_internal_and_human_draft_excluded(self):
        internal = self._awaiting(number=14, source="Internal", assignees=["x"])
        draft = self._awaiting(number=15, source="Community", is_draft=True, assignees=["y"])
        rec = sweep.build_report([internal, draft], self.cfg,
                                 {internal.key(): (99.0, 9), draft.key(): (99.0, 9)})
        self.assertEqual(rec, {})

    def test_maintainer_own_pr_still_escalated(self):
        # The arrow fires on the maintainer's own escalated item too — a public
        # signal others can use to keep them honest.
        pr = self._awaiting(number=16, source="Community", assignees=["maint"])
        rec = sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 3)})  # >= 48
        self.assertEqual(len(rec["maint"]), 1)         # not double-listed
        self.assertTrue(rec["maint"][0].escalated)     # own PR: still arrowed
        # ...but below the maintainer rung it is not escalated.
        rec2 = sweep.build_report([pr], self.cfg, {pr.key(): (30.0, 2)})  # 24 <= 30 < 48
        self.assertFalse(rec2["maint"][0].escalated)

    def test_render_links_icons_escalation(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"],
                            url="https://github.com/shader-slang/slang/pull/99")
        out = sweep.render_report(sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
        self.assertIn("**`bob`**:", out)                # grouped under the assignee (inert by default)
        self.assertNotIn("**`maint`**:", out)           # no separate maintainer section
        self.assertIn("[slang#99](https://github.com/shader-slang/slang/pull/99)", out)
        self.assertIn(sweep.ESCALATED_ICON, out)        # in-place up-arrow
        self.assertNotIn("(@bob)", out)                 # redundant once grouped by assignee
        self.assertIn(sweep.COMMUNITY_ICON, out)

    def test_recipient_map_remaps_mentions(self):
        # With a map, the assignee header and the reviewer in the reason become
        # <@id> mentions; an unmapped login stays inert backticks.
        cfg = make_cfg(maintainer="maint",
                       recipient_map={"bob": "111", "dan": "222"})
        pr = self._awaiting(number=98, source="Community", assignees=["bob"],
                            existing_reviewers=["dan", "eve"])
        out = sweep.render_report(sweep.build_report([pr], cfg, {pr.key(): (50.0, 3)}), cfg)
        self.assertIn("**<@111>**:", out)               # mapped assignee header pings
        self.assertIn("<@222>", out)                    # mapped reviewer pings
        self.assertNotIn("`bob`", out)                  # bob is mapped -> no backticks
        self.assertNotIn("@bob", out)                   # never bare @login

    def test_recipient_map_unmapped_stays_inert(self):
        cfg = make_cfg(maintainer="maint", recipient_map={"someone-else": "999"})
        pr = self._awaiting(number=97, source="Community", assignees=["bob"])
        out = sweep.render_report(sweep.build_report([pr], cfg, {pr.key(): (50.0, 3)}), cfg)
        self.assertIn("**`bob`**:", out)                # unmapped -> inert
        self.assertNotIn("<@", out)

    def test_render_includes_legend(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"])
        out = sweep.render_report(sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
        self.assertIn(f"{sweep.BOT_ICON} agent PR", out)
        self.assertIn(f"{sweep.COMMUNITY_ICON} community PR", out)
        self.assertIn(f"{sweep.ESCALATED_ICON} escalated to maintainer", out)

    def test_report_title(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"])
        out = sweep.render_report(sweep.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
        self.assertIn("## Slang PR Escalation Report", out)

    def test_within_group_sort_community_then_escalated(self):
        # One assignee, four PRs: community/bot x escalated/not. Expect order
        # community-escalated, community-plain, bot-escalated, bot-plain.
        ce = self._awaiting(number=1, source="Community", assignees=["bob"])
        cp = self._awaiting(number=2, source="Community", assignees=["bob"])
        be = self._awaiting(number=3, source="Bot", is_bot=True, assignees=["bob"])
        bp = self._awaiting(number=4, source="Bot", is_bot=True, assignees=["bob"])
        stalls = {
            ce.key(): (50.0, 3),    # community: >=48 -> escalated
            cp.key(): (30.0, 2),    # community: 24<=.<48 -> not escalated
            be.key(): (200.0, 9),   # bot: >=168 -> escalated
            bp.key(): (50.0, 3),    # bot: 48<=.<168 -> not escalated
        }
        # Feed in a deliberately jumbled order to prove sorting, not insertion.
        out = sweep.render_report(sweep.build_report([bp, be, cp, ce], self.cfg, stalls), self.cfg)
        order = [out.index(f"slang#{n}]") for n in (1, 2, 3, 4)]
        self.assertEqual(order, sorted(order))  # #1 < #2 < #3 < #4 in the text


@final
class TestRecipientMap(unittest.TestCase):
    def test_format_mention_default_is_backticks(self):
        cfg = make_cfg()  # empty recipient_map
        self.assertEqual(sweep.format_mention("bob", cfg), "`bob`")

    def test_format_mention_mapped_pings(self):
        cfg = make_cfg(recipient_map={"bob": "123"})
        self.assertEqual(sweep.format_mention("bob", cfg), "<@123>")

    def test_format_mention_unmapped_in_nonempty_map(self):
        cfg = make_cfg(recipient_map={"alice": "123"})
        self.assertEqual(sweep.format_mention("bob", cfg), "`bob`")

    def test_format_mention_case_insensitive(self):
        cfg = make_cfg(recipient_map={"bob": "123"})  # keys are lowercased on load
        self.assertEqual(sweep.format_mention("BoB", cfg), "<@123>")

    def test_load_recipient_map_flat_and_lowercased(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "map.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"Jhelferty-NV": "111", "bob": 222}, f)
            m = sweep.load_recipient_map(p)
        self.assertEqual(m, {"jhelferty-nv": "111", "bob": "222"})  # keys lowered, values str

    def test_load_recipient_map_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(["bob", "dan"], f)
            with self.assertRaises(SystemExit):
                sweep.load_recipient_map(p)

    def test_load_recipient_map_missing_file(self):
        with self.assertRaises(SystemExit):
            sweep.load_recipient_map("/no/such/recipient-map.json")


@final
class TestWeightedSignal(unittest.TestCase):
    TABLE = [("source/slang/**", 3.0), ("source/**", 2.0), ("tests/**", 1.0)]

    def test_multiplier_most_specific_wins(self):
        self.assertEqual(signal.match_file_multiplier("source/slang/x.cpp", self.TABLE, 1.0), 3.0)
        self.assertEqual(signal.match_file_multiplier("source/core/x.cpp", self.TABLE, 1.0), 2.0)
        self.assertEqual(signal.match_file_multiplier("tests/x.slang", self.TABLE, 1.0), 1.0)
        self.assertEqual(signal.match_file_multiplier("README.md", self.TABLE, 1.0), 1.0)  # default

    def test_per_file_signals(self):
        loc = {"source/slang/a.cpp": 10.0, "tests/b.slang": 10.0}
        sig = signal.per_file_signals(loc, self.TABLE, 1.0)
        self.assertEqual(sig, {"source/slang/a.cpp": 30.0, "tests/b.slang": 10.0})

    def test_top_k_weights_normalizes(self):
        weights = signal.top_k_weights({"a": 30.0, "b": 10.0}, k=10)
        self.assertAlmostEqual(weights["a"], 0.75)
        self.assertAlmostEqual(weights["b"], 0.25)

    def test_top_k_limits(self):
        weights = signal.top_k_weights({"a": 3.0, "b": 2.0, "c": 1.0}, k=2)
        self.assertEqual(set(weights), {"a", "b"})  # c dropped

    def test_top_k_empty_when_no_signal(self):
        self.assertEqual(signal.top_k_weights({"a": 0.0}, k=5), {})

    def test_overall_signal_sums_weight_times_loc(self):
        weights = {"f1": 0.75, "f2": 0.25}
        loc = {"f1": {"alice": 40.0, "bob": 10.0}, "f2": {"bob": 20.0}}
        overall = signal.overall_signal(weights, loc)
        self.assertAlmostEqual(overall["alice"], 30.0)          # 0.75*40
        self.assertAlmostEqual(overall["bob"], 0.75 * 10 + 0.25 * 20)  # 12.5

    def test_rank_logins_descending(self):
        self.assertEqual(signal.rank_logins({"alice": 30.0, "bob": 12.5}), ["alice", "bob"])

    def test_is_bot_login(self):
        bots = ["nv-slang-bot"]
        self.assertTrue(signal.is_bot_login("github-actions[bot]", bots))
        self.assertTrue(signal.is_bot_login("nv-slang-bot", bots))
        self.assertTrue(signal.is_bot_login("", bots))
        self.assertFalse(signal.is_bot_login("alice", bots))


@final
class TestAttributeCommit(unittest.TestCase):
    BOTS = ["nv-slang-bot"]

    def test_human_author_credited(self):
        self.assertEqual(
            signal.attribute_commit("alice", None, "author", self.BOTS), "alice")

    def test_author_self_uses_approver(self):
        # the PR author's own past commit credits whoever reviewed it
        self.assertEqual(
            signal.attribute_commit("author", "carol", "author", self.BOTS), "carol")

    def test_author_self_no_approver_dropped(self):
        self.assertIsNone(
            signal.attribute_commit("author", None, "author", self.BOTS))

    def test_author_self_approver_is_author_dropped(self):
        self.assertIsNone(
            signal.attribute_commit("author", "author", "author", self.BOTS))

    def test_bot_author_uses_approver(self):
        self.assertEqual(
            signal.attribute_commit("nv-slang-bot", "carol", "author", self.BOTS), "carol")

    def test_unmapped_author_uses_approver(self):
        self.assertEqual(
            signal.attribute_commit("", "carol", "author", self.BOTS), "carol")

    def test_bot_author_no_approver_dropped(self):
        self.assertIsNone(
            signal.attribute_commit("nv-slang-bot", None, "author", self.BOTS))

    def test_bot_author_approver_is_pr_author_dropped(self):
        self.assertIsNone(
            signal.attribute_commit("nv-slang-bot", "author", "author", self.BOTS))

    def test_bot_author_approver_is_bot_dropped(self):
        self.assertIsNone(
            signal.attribute_commit("nv-slang-bot", "nv-slang-bot", "author", self.BOTS))


@final
class TestSelectAssigneeAndReviewers(unittest.TestCase):
    OWNERS = {"owner1", "owner2"}
    COLLAB = {"owner1", "owner2", "dev1", "dev2"}  # owners are also collaborators
    MAINT = "maintainer"

    def select(self, issue, committers, author="author"):
        return sweep.select_assignee_and_reviewers(
            issue, committers, self.OWNERS, self.COLLAB, author, self.MAINT)

    def test_issue_assignee_wins(self):
        # issue assigned to owner2; commit signal favors owner1 -> issue wins
        assignee, reviewers = self.select(["owner2"], ["owner1", "dev1"])
        self.assertEqual(assignee, "owner2")
        self.assertIn("owner2", reviewers)

    def test_commit_signal_owner_when_no_issue(self):
        assignee, _reviewers = self.select([], ["owner1", "owner2"])
        self.assertEqual(assignee, "owner1")  # most recent owner committer

    def test_maintainer_fallback(self):
        assignee, reviewers = self.select([], ["dev1"])  # no owner committed
        self.assertEqual(assignee, "maintainer")
        self.assertEqual(reviewers, ["maintainer", "dev1"])  # top collaborator-not-owner added

    def test_extra_reviewer_is_top_collaborator_not_owner(self):
        # committers newest-first: dev2, owner1, dev1 -> assignee owner1, extra dev2
        assignee, reviewers = self.select([], ["dev2", "owner1", "dev1"])
        self.assertEqual(assignee, "owner1")
        self.assertEqual(reviewers, ["owner1", "dev2"])

    def test_no_collaborator_committer_means_only_assignee(self):
        _assignee, reviewers = self.select([], ["owner1", "owner2"])
        self.assertEqual(reviewers, ["owner1"])

    def test_author_never_requested_as_reviewer(self):
        # maintainer happens to equal author -> dropped from reviewers
        assignee, reviewers = sweep.select_assignee_and_reviewers(
            [], ["dev1"], self.OWNERS, self.COLLAB, author="maintainer", maintainer="maintainer")
        self.assertEqual(assignee, "maintainer")
        self.assertEqual(reviewers, ["dev1"])  # author(maintainer) excluded from reviewers

    def test_real_existing_reviewer_blocks_adding(self):
        # A real (approve-capable) reviewer already requested -> add no reviewers.
        assignee, reviewers = sweep.select_assignee_and_reviewers(
            [], ["dev2", "owner1"], self.OWNERS, self.COLLAB, "author", self.MAINT,
            existing_reviewers=["dave"], ignored_reviewers={"bmillsNV"})
        self.assertEqual(assignee, "owner1")
        self.assertEqual(reviewers, [])

    def test_ignored_and_bot_reviewers_do_not_count_as_existing(self):
        # bmillsNV (ignored, can't approve) + a [bot] don't block adding reviewers.
        assignee, reviewers = sweep.select_assignee_and_reviewers(
            [], ["dev2", "owner1"], self.OWNERS, self.COLLAB, "author", self.MAINT,
            existing_reviewers=["bmillsNV", "copilot[bot]"],
            bot_authors=["nv-slang-bot"], ignored_reviewers={"bmillsNV"})
        self.assertEqual(assignee, "owner1")
        self.assertEqual(reviewers, ["owner1", "dev2"])


@final
class TestSourceClassify(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def test_bot(self):
        self.assertEqual(sweep.source_for(True, False, self.cfg), "Bot")

    def test_internal_when_can_commit(self):
        self.assertEqual(sweep.source_for(False, True, self.cfg), "Internal")

    def test_community_when_cannot_commit(self):
        self.assertEqual(sweep.source_for(False, False, self.cfg), "Community")


@final
class TestHybridTiebreak(unittest.TestCase):
    def test_needs_tiebreak_close(self):
        self.assertTrue(signal.needs_tiebreak({"a": 10.0, "b": 8.0}, ["a", "b"], 1.5))

    def test_no_tiebreak_clear_winner(self):
        self.assertFalse(signal.needs_tiebreak({"a": 20.0, "b": 8.0}, ["a", "b"], 1.5))

    def test_no_tiebreak_single_candidate(self):
        self.assertFalse(signal.needs_tiebreak({"a": 5.0}, ["a"], 1.5))

    def test_no_tiebreak_second_zero(self):
        self.assertFalse(signal.needs_tiebreak({"a": 5.0, "b": 0.0}, ["a", "b"], 1.5))

    def test_merge_refined_reorders_top_n_keeps_tail(self):
        # refined per-file score flips a and b within the top-2 finalists
        self.assertEqual(
            signal.merge_refined(["a", "b", "c", "d"], 2, {"a": 1.0, "b": 5.0}),
            ["b", "a", "c", "d"])

    def test_merge_refined_all_finalists(self):
        self.assertEqual(
            signal.merge_refined(["a", "b"], 2, {"a": 1.0, "b": 2.0}), ["b", "a"])


@final
class _CountingGh:
    """Minimal fake gh that records graphql/api call counts for cache tests."""
    def __init__(self):
        self.graphql_calls = 0
        self.api_calls = 0

    def graphql(self, query, variables=None):
        self.graphql_calls += 1
        # One history node for whichever file aliases the query requested.
        target = {}
        i = 0
        while ("f%d:" % i) in query or ("f%d :" % i) in query:
            i += 1
        for j in range(max(i, 1)):
            target["f%d" % j] = {"nodes": [{
                "oid": "sha%d" % j, "additions": 10, "deletions": 2,
                "author": {"user": {"login": "alice"}},
                "associatedPullRequests": {"nodes": []},
            }]}
        return {"data": {"repository": {"defaultBranchRef": {"target": target}}}}

    def api(self, path, jq=None, paginate=False):
        self.api_calls += 1
        return '{"filename": "a.cpp", "additions": 5, "deletions": 1}'


@final
class TestSignalCache(unittest.TestCase):
    def test_file_history_cached_across_calls(self):
        gh = _CountingGh()
        cache = {}
        signal.fetch_file_histories(gh, "o/r", ["a.cpp", "b.cpp"], "S", 5, cache)
        self.assertEqual(gh.graphql_calls, 1)
        # Same paths again -> fully cached -> no new query.
        signal.fetch_file_histories(gh, "o/r", ["a.cpp", "b.cpp"], "S", 5, cache)
        self.assertEqual(gh.graphql_calls, 1)
        # A new path -> one more query (only the uncached path).
        signal.fetch_file_histories(gh, "o/r", ["a.cpp", "c.cpp"], "S", 5, cache)
        self.assertEqual(gh.graphql_calls, 2)

    def test_file_history_keyed_by_repo(self):
        gh = _CountingGh()
        cache = {}
        signal.fetch_file_histories(gh, "o/r1", ["a.cpp"], "S", 5, cache)
        signal.fetch_file_histories(gh, "o/r2", ["a.cpp"], "S", 5, cache)
        self.assertEqual(gh.graphql_calls, 2)  # same path, different repo -> not shared

    def test_commit_file_loc_cached_by_repo_sha(self):
        gh = _CountingGh()
        cache = {}
        signal.commit_file_loc(gh, "o/r", "deadbeef", "a.cpp", cache)
        signal.commit_file_loc(gh, "o/r", "deadbeef", "a.cpp", cache)  # cached
        self.assertEqual(gh.api_calls, 1)
        signal.commit_file_loc(gh, "o/r", "cafef00d", "a.cpp", cache)  # new sha
        self.assertEqual(gh.api_calls, 2)


@final
class _ApplyGh:
    """No-op fake gh for the apply path: records the writes attempted."""
    def __init__(self):
        self.run_calls = 0
        self.graphql_calls = 0

    def run(self, args, check=True):
        self.run_calls += 1
        return ""

    def graphql(self, query, variables=None):
        self.graphql_calls += 1
        return {}

    def api(self, path, jq=None, paginate=False):
        return ""


@final
class TestApplyDecisions(unittest.TestCase):
    def test_plan_roundtrips_state(self):
        summary = {"plan": [{"repo": "o/r", "number": 1, "set_status": "Todo"}],
                   "digest": "d", "state": {"prs": {"o/r#1": {"notified": {"idle": "T"}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "plan.json")
            sweep.save_plan(path, summary)
            doc = sweep.load_plan(path)
        assert doc is not None
        self.assertEqual(doc["state"], summary["state"])
        self.assertEqual(doc["plan"], summary["plan"])

    def test_apply_decisions_persists_state_and_replays(self):
        doc = {"plan": [{"repo": "o/r", "number": 1, "item_id": "I", "set_status": "Todo"},
                        {"repo": "o/r", "number": 2, "item_id": "J", "set_assignee": "bob",
                         "request_reviewers": [], "remove_reviewers": ["bmillsNV"]}],
               "state": {"prs": {"o/r#1": {"notified": {"idle": "T"}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            cfg = make_cfg(state_file=state_path)
            gh = _ApplyGh()
            n = sweep.apply_decisions(gh, cfg, doc)
            self.assertEqual(n, 2)  # both plan items executed
            self.assertTrue(gh.run_calls > 0)
            with open(state_path) as f:
                self.assertEqual(json.load(f), doc["state"])  # state persisted

    def test_apply_decisions_no_state_writes_no_file(self):
        doc = {"plan": [{"repo": "o/r", "number": 1, "item_id": "I", "set_status": "Todo"}]}
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            cfg = make_cfg(state_file=state_path)
            sweep.apply_decisions(_ApplyGh(), cfg, doc)
            self.assertFalse(os.path.exists(state_path))  # nothing to persist


@final
class TestSummarizeReviews(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(sweep.summarize_reviews([]), (None, False))

    def test_last_review_and_change_requested(self):
        reviews = [
            {"state": "APPROVED", "submittedAt": "2026-06-01T00:00:00Z"},
            {"state": "CHANGES_REQUESTED", "submittedAt": "2026-06-02T00:00:00Z"},
            {"state": "COMMENTED", "submittedAt": "2026-06-03T00:00:00Z"},  # non-decisive
        ]
        last, changed = sweep.summarize_reviews(reviews)
        self.assertEqual(last, utc(2026, 6, 3))            # latest submitted
        self.assertTrue(changed)                            # last decisive = CHANGES_REQUESTED

    def test_approved_last_decisive(self):
        reviews = [
            {"state": "CHANGES_REQUESTED", "submittedAt": "2026-06-01T00:00:00Z"},
            {"state": "approved", "submittedAt": "2026-06-02T00:00:00Z"},  # case-insensitive
        ]
        _last, changed = sweep.summarize_reviews(reviews)
        self.assertFalse(changed)


@final
class TestCIFromRollup(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def test_null_rollup(self):
        self.assertEqual(sweep.ci_state_from_rollup(None, self.cfg), (sweep.CI_NONE, False))

    def test_action_required(self):
        rollup = {"contexts": {"nodes": [
            {"__typename": "CheckRun", "name": "x", "status": "COMPLETED", "conclusion": "ACTION_REQUIRED"}]}}
        self.assertEqual(sweep.ci_state_from_rollup(rollup, self.cfg)[0], sweep.CI_ACTION_REQUIRED)

    def test_pending_failed_passed(self):
        pend = {"contexts": {"nodes": [{"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": None}]}}
        self.assertEqual(sweep.ci_state_from_rollup(pend, self.cfg)[0], sweep.CI_PENDING)
        fail = {"contexts": {"nodes": [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}]}}
        self.assertEqual(sweep.ci_state_from_rollup(fail, self.cfg)[0], sweep.CI_FAILED)
        ok = {"contexts": {"nodes": [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]}}
        self.assertEqual(sweep.ci_state_from_rollup(ok, self.cfg)[0], sweep.CI_PASSED)

    def test_legacy_status_context(self):
        rollup = {"contexts": {"nodes": [{"__typename": "StatusContext", "context": "ci", "state": "FAILURE"}]}}
        self.assertEqual(sweep.ci_state_from_rollup(rollup, self.cfg)[0], sweep.CI_FAILED)

    def test_coverage_passed_by_name(self):
        cfg = make_cfg(coverage_check="cov")
        rollup = {"contexts": {"nodes": [
            {"__typename": "CheckRun", "name": "cov", "status": "COMPLETED", "conclusion": "SUCCESS"}]}}
        self.assertEqual(sweep.ci_state_from_rollup(rollup, cfg), (sweep.CI_PASSED, True))


@final
class TestParsePrNode(unittest.TestCase):
    def _node(self, **over):
        node = {
            "number": 42, "title": "t", "url": "u", "id": "PR_x", "isDraft": False,
            "headRefOid": "abc123", "createdAt": "2026-06-01T00:00:00Z",
            "updatedAt": "2026-06-10T00:00:00Z", "reviewDecision": "REVIEW_REQUIRED",
            "author": {"login": "alice", "__typename": "User"},
            "assignees": {"nodes": [{"login": "bob"}]},
            "reviewRequests": {"nodes": [{"requestedReviewer": {"__typename": "User", "login": "bmillsNV"}},
                                         {"requestedReviewer": {"__typename": "Team"}}]},
            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"contexts": {"nodes": [
                {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]}}}}]},
            "reviews": {"nodes": [{"state": "CHANGES_REQUESTED", "submittedAt": "2026-06-09T00:00:00Z"}]},
            "mergeQueueEntry": None,
            "closingIssuesReferences": {"nodes": [{"assignees": {"nodes": [{"login": "carol"}]}}]},
            "files": {"nodes": [{"path": "a.cpp", "additions": 10, "deletions": 2}]},
        }
        node.update(over)
        return node

    def test_full_node(self):
        pr = sweep.parse_pr_node(self._node(), "shader-slang/slang", make_cfg())
        self.assertEqual(pr.number, 42)
        self.assertEqual(pr.author, "alice")
        self.assertFalse(pr.is_bot)
        self.assertEqual(pr.assignees, ["bob"])
        self.assertEqual(pr.existing_reviewers, ["bmillsNV"])  # team entry skipped
        self.assertEqual(pr.ci_state, sweep.CI_PASSED)
        self.assertTrue(pr.change_requested)
        self.assertEqual(pr.last_review_at, utc(2026, 6, 9))
        self.assertFalse(pr.in_merge_queue)
        self.assertEqual(pr.issue_assignees, ["carol"])
        self.assertEqual(pr.changed_files, {"a.cpp": 10.0})

    def test_bot_author(self):
        pr = sweep.parse_pr_node(
            self._node(author={"login": "nv-slang-bot", "__typename": "Bot"}),
            "shader-slang/slang", make_cfg())
        self.assertTrue(pr.is_bot)

    def test_merge_queue_present(self):
        pr = sweep.parse_pr_node(self._node(mergeQueueEntry={"id": "MQ_1"}),
                                 "shader-slang/slang", make_cfg())
        self.assertTrue(pr.in_merge_queue)


@final
class TestRealReviewersAndEffective(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()  # ignored_reviewers default ["bmillsNV"]

    def test_real_reviewers_filters_ignored_and_bots(self):
        pr = make_pr(existing_reviewers=["bmillsNV", "copilot[bot]", "dan"])
        self.assertEqual(sweep._real_reviewers(pr, self.cfg), ["dan"])

    def test_reviewers_text(self):
        # Default (no recipient map): reviewers render as inert backticks.
        self.assertEqual(sweep._reviewers_text(make_pr(existing_reviewers=["bmillsNV", "dan"]),
                                               self.cfg), "`dan`")
        self.assertEqual(sweep._reviewers_text(make_pr(existing_reviewers=["bmillsNV"]),
                                               self.cfg), "(no reviewers requested)")

    def test_awaiting_review_needs_real_reviewer(self):
        # Only bmillsNV requested -> not "awaiting review"; falls through to idle.
        pr = make_pr(source="Community", board_status="Todo",
                     existing_reviewers=["bmillsNV"], review_decision="REVIEW_REQUIRED")
        match = next((p for p in sweep.ladder_for(pr, self.cfg) if p.applies(pr, self.cfg)), None)
        self.assertEqual(match.key, "idle")

    def test_effective_pr_applies_actions(self):
        pr = make_pr(board_status="Todo", assignees=[], existing_reviewers=["bmillsNV", "dan"])
        d = sweep.Decision(pr=pr, set_status="Revising", set_assignee="bob",
                           request_reviewers=["erin"], remove_reviewers=["bmillsNV"])
        sweep.effective_pr(pr, d)
        self.assertEqual(pr.board_status, "Revising")
        self.assertEqual(pr.assignees, ["bob"])
        self.assertEqual(pr.existing_reviewers, ["dan", "erin"])  # bmills removed, erin added

    def test_report_reflects_post_plan_status(self):
        # A Todo PR with failing CI that the plan bounces to Revising should show
        # "CI failing", not "awaiting review", in the post-plan report.
        pr = make_pr(number=20, source="Community", board_status="Todo", assignees=["bob"],
                     existing_reviewers=["dan"], review_decision="REVIEW_REQUIRED",
                     ci_state=sweep.CI_FAILED)
        sweep.effective_pr(pr, sweep.Decision(pr=pr, set_status="Revising"))
        rec = sweep.build_report([pr], make_cfg(maintainer="maint"), {pr.key(): (50.0, 3)})
        self.assertIn("CI failing", rec["bob"][0].reason)

    def test_copilot_is_recognized_as_bot(self):
        self.assertTrue(signal.classify_is_bot("Copilot", self.cfg.bot_authors))
        self.assertTrue(signal.classify_is_bot("copilot-swe-agent", self.cfg.bot_authors))

    def test_effective_assignee_skips_bot(self):
        # [bmillsNV, Copilot] -> bmillsNV (first non-bot)
        pr = make_pr(assignees=["bmillsNV", "Copilot"])
        self.assertEqual(sweep.effective_assignee(pr, self.cfg), "bmillsNV")

    def test_effective_assignee_bot_only_falls_back(self):
        cfg = make_cfg(maintainer="maint")
        pr = make_pr(assignees=["Copilot"], assignee_pick=None)
        self.assertEqual(sweep.effective_assignee(pr, cfg), "maint")  # no human -> maintainer
        pr2 = make_pr(assignees=["Copilot"], assignee_pick="owner1")
        self.assertEqual(sweep.effective_assignee(pr2, cfg), "owner1")  # signal owner if known

    def test_no_copilot_recipient_section(self):
        # A Copilot-only-assigned bot PR is routed to the maintainer, not @Copilot.
        pr = make_pr(number=21, source="Bot", is_bot=True, board_status="Todo",
                     assignees=["Copilot"], existing_reviewers=["dan"],
                     review_decision="REVIEW_REQUIRED")
        rec = sweep.build_report([pr], make_cfg(maintainer="maint"), {pr.key(): (200.0, 9)})
        self.assertNotIn("Copilot", rec)
        self.assertIn("maint", rec)


if __name__ == "__main__":
    unittest.main()
