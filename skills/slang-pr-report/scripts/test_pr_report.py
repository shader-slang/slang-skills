#!/usr/bin/env python3
"""Unit tests for the escalation report (pr_report.py).

No live `gh` calls — every test constructs plain data and checks the synthesis
logic: the per-source lifecycle-stage derivation (derive_stage), the predicate
ladders, the movement/stall clock, the assignee-grouped report
routing/rendering, and the recipient map.

Run:  python3 scripts/test_pr_report.py
"""
from __future__ import annotations

# Tests use unittest's setUp pattern, which confuses strict type inference.
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
import pr_report as report  # noqa: E402  (path inserted above)


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def make_cfg(**kw):
    base = dict(repos=["shader-slang/slang"],
                bot_authors=["nv-slang-bot", "slang-coworker-nanoclaw", "Copilot", "copilot-swe-agent"])
    base.update(kw)
    return report.Config(**base)


def make_pr(**kw):
    # Community source by default. The human-ready ("Todo") stage is derived
    # from CI: a Community PR needs ci_state=CI_PASSED (and not draft) to derive
    # Todo.
    defaults = dict(repo="shader-slang/slang", number=1, source="Community")
    defaults.update(kw)
    return report.PR(**defaults)


@final
class TestDeriveStage(unittest.TestCase):
    """derive_stage maps live signals to a lifecycle stage, per source."""
    def setUp(self):
        self.cfg = make_cfg()

    def test_merge_queue_is_done(self):
        pr = make_pr(in_merge_queue=True, ci_state=report.CI_PASSED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Done")

    def test_terminal_state_is_done(self):
        pr = make_pr(state="MERGED")
        self.assertEqual(report.derive_stage(pr, self.cfg), "Done")

    # --- contributor fingerprint --------------------------------------------
    def test_contributor_ci_passed_is_todo(self):
        pr = make_pr(source="Community", ci_state=report.CI_PASSED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Todo")

    def test_contributor_ci_pending_is_revising(self):
        pr = make_pr(source="Community", ci_state=report.CI_PENDING)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Revising")

    def test_contributor_ci_failed_is_revising(self):
        pr = make_pr(source="Community", ci_state=report.CI_FAILED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Revising")

    def test_contributor_draft_is_revising(self):
        pr = make_pr(source="Community", is_draft=True, ci_state=report.CI_PASSED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Revising")

    def test_contributor_changes_requested_is_revising(self):
        pr = make_pr(source="Community", change_requested=True, ci_state=report.CI_PASSED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Revising")

    # --- bot fingerprint ----------------------------------------------------
    def test_bot_promotes_regardless_of_ci_and_draft(self):
        pr = make_pr(source="Bot", is_bot=True, is_draft=True, ci_state=report.CI_FAILED)
        self.assertEqual(report.derive_stage(pr, self.cfg), "Todo")  # no coverage gate

    def test_bot_coverage_gated_when_configured(self):
        cfg = make_cfg(coverage_check="cov")
        not_ready = make_pr(source="Bot", is_bot=True, coverage_passed=False)
        self.assertEqual(report.derive_stage(not_ready, cfg), "Revising")
        ready = make_pr(source="Bot", is_bot=True, coverage_passed=True)
        self.assertEqual(report.derive_stage(ready, cfg), "Todo")


@final
class TestPredicates(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def _match(self, pr):
        return next((p for p in report.ladder_for(pr, self.cfg) if p.applies(pr, self.cfg)), None)

    def test_needs_ci_approval(self):
        pr = make_pr(source="Community", ci_state=report.CI_ACTION_REQUIRED)
        p = self._match(pr)
        self.assertEqual(p.key, "needs_ci_approval")
        self.assertEqual(p.render(pr, self.cfg, 0), "needs CI approval")

    def test_changes_requested(self):
        pr = make_pr(source="Community", change_requested=True)
        p = self._match(pr)
        self.assertEqual(p.key, "changes_requested")
        self.assertIn("changes requested", p.render(pr, self.cfg, 0))

    def test_awaiting_review(self):
        # A Community PR reaches the human-ready stage via CI passed.
        pr = make_pr(source="Community", ci_state=report.CI_PASSED,
                     existing_reviewers=["dan"], review_decision="REVIEW_REQUIRED")
        p = self._match(pr)
        self.assertEqual(p.key, "awaiting_review")
        self.assertEqual(p.render(pr, self.cfg, 0), "awaiting review from: `dan`")

    def test_ci_failing(self):
        pr = make_pr(source="Community", ci_state=report.CI_FAILED)
        self.assertEqual(self._match(pr).key, "ci_failing")

    def test_idle_catchall_and_render(self):
        pr = make_pr(source="Community", ci_state=report.CI_PENDING)
        p = self._match(pr)
        self.assertEqual(p.key, "idle")
        self.assertEqual(p.render(pr, self.cfg, 3), "idle for 3 days")

    def test_first_match_precedence(self):
        pr = make_pr(source="Community", ci_state=report.CI_ACTION_REQUIRED, change_requested=True)
        self.assertEqual(self._match(pr).key, "needs_ci_approval")  # earliest applicable wins

    def test_bot_ladder_omits_ci_approval_and_changes(self):
        keys = [p.key for p in report.BOT_LADDER]
        self.assertNotIn("needs_ci_approval", keys)
        self.assertNotIn("changes_requested", keys)

    def test_internal_has_no_ladder(self):
        self.assertEqual(report.ladder_for(make_pr(source="Internal"), self.cfg), [])


@final
class TestComputeStall(unittest.TestCase):
    def setUp(self):
        self.now = utc(2026, 6, 10, 12)
        self.tz = timezone.utc
        self.cfg = make_cfg()

    def test_first_sight_anchors_to_activity(self):
        pr = make_pr(ci_state=report.CI_PASSED, head_sha="abc",
                     last_activity_at=utc(2026, 6, 9, 12))
        state, _wh, days = report.compute_stall(pr, self.cfg, {}, self.now, self.tz)
        self.assertEqual(report.parse_iso(state["last_moved_at"]), utc(2026, 6, 9, 12))
        self.assertEqual(days, 1)

    def test_unchanged_keeps_prior(self):
        # Derived stage Todo (CI passed); fingerprint matches prior -> no movement.
        pr = make_pr(ci_state=report.CI_PASSED, head_sha="abc")
        prior = {"move_fingerprint": ["Todo", "abc", None],
                 "last_moved_at": utc(2026, 6, 8).isoformat()}
        state, _wh, _days = report.compute_stall(pr, self.cfg, prior, self.now, self.tz)
        self.assertEqual(state["last_moved_at"], prior["last_moved_at"])

    def test_movement_resets_to_now(self):
        # New head SHA -> fingerprint changes -> last_moved resets to now.
        pr = make_pr(ci_state=report.CI_PASSED, head_sha="NEW")
        prior = {"move_fingerprint": ["Todo", "abc", None],
                 "last_moved_at": utc(2026, 6, 1).isoformat()}
        state, _wh, days = report.compute_stall(pr, self.cfg, prior, self.now, self.tz)
        self.assertEqual(report.parse_iso(state["last_moved_at"]), self.now)
        self.assertEqual(days, 0)

    def test_stage_change_counts_as_movement(self):
        # CI flips pending -> passed: derived stage Revising -> Todo is movement.
        pr = make_pr(ci_state=report.CI_PASSED, head_sha="abc")
        prior = {"move_fingerprint": ["Revising", "abc", None],
                 "last_moved_at": utc(2026, 6, 1).isoformat()}
        state, _wh, days = report.compute_stall(pr, self.cfg, prior, self.now, self.tz)
        self.assertEqual(report.parse_iso(state["last_moved_at"]), self.now)
        self.assertEqual(days, 0)


@final
class TestBuildReport(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def _awaiting(self, **kw):
        # A Community PR that derives to Todo (CI passed) with a real reviewer.
        base = dict(ci_state=report.CI_PASSED, existing_reviewers=["dan"],
                    review_decision="REVIEW_REQUIRED")
        base.update(kw)
        return make_pr(**base)

    def test_assignee_only_below_escalate_rung(self):
        pr = self._awaiting(number=10, source="Community", assignees=["bob"])
        rec = report.build_report([pr], self.cfg, {pr.key(): (30.0, 2)})  # 24 <= 30 < 48
        self.assertIn("bob", rec)
        self.assertNotIn(report.UNASSIGNED, rec)
        self.assertFalse(rec["bob"][0].escalated)

    def test_escalates_in_place(self):
        # Past the escalate rung: the item gains the up-arrow but stays under its
        # assignee (no separate section).
        pr = self._awaiting(number=11, source="Community", assignees=["bob"])
        rec = report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)})  # >= 48
        self.assertEqual(list(rec.keys()), ["bob"])
        self.assertTrue(rec["bob"][0].escalated)
        self.assertEqual(rec["bob"][0].assignee, "bob")

    def test_community_changes_requested_timings(self):
        # changes_requested escalates slowly: assignee @1wk (168 wh), escalate @2wk (336 wh).
        pr = self._awaiting(number=17, source="Community", assignees=["bob"],
                            change_requested=True)
        self.assertEqual(report.build_report([pr], self.cfg, {pr.key(): (120.0, 5)}), {})  # < 168
        rec = report.build_report([pr], self.cfg, {pr.key(): (200.0, 9)})  # 168 <= 200 < 336
        self.assertIn("changes requested", rec["bob"][0].reason)
        self.assertFalse(rec["bob"][0].escalated)
        rec = report.build_report([pr], self.cfg, {pr.key(): (340.0, 15)})  # >= 336
        self.assertTrue(rec["bob"][0].escalated)

    def test_below_first_rung_nobody(self):
        pr = self._awaiting(number=12, source="Community", assignees=["bob"])
        self.assertEqual(report.build_report([pr], self.cfg, {pr.key(): (10.0, 0)}), {})

    def test_bot_thresholds_higher(self):
        pr = self._awaiting(number=13, source="Bot", is_bot=True, assignees=["carol"])
        rec = report.build_report([pr], self.cfg, {pr.key(): (50.0, 2)})  # community would escalate; bot escalate=168
        self.assertIn("carol", rec)
        self.assertFalse(rec["carol"][0].escalated)

    def test_internal_and_human_draft_excluded(self):
        internal = self._awaiting(number=14, source="Internal", assignees=["x"])
        draft = self._awaiting(number=15, source="Community", is_draft=True, assignees=["y"])
        rec = report.build_report([internal, draft], self.cfg,
                                  {internal.key(): (99.0, 9), draft.key(): (99.0, 9)})
        self.assertEqual(rec, {})

    def test_owned_pr_escalates_in_place(self):
        # An owned item gains the arrow past the escalate rung and stays in place.
        pr = self._awaiting(number=16, source="Community", assignees=["alice"])
        rec = report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)})  # >= 48
        self.assertEqual(len(rec["alice"]), 1)          # not double-listed
        self.assertTrue(rec["alice"][0].escalated)
        # ...but below the escalate rung it is not escalated.
        rec2 = report.build_report([pr], self.cfg, {pr.key(): (30.0, 2)})  # 24 <= 30 < 48
        self.assertFalse(rec2["alice"][0].escalated)

    def test_render_links_icons_escalation(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"],
                            url="https://github.com/shader-slang/slang/pull/99")
        out = report.render_report(report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
        self.assertIn("**`bob`**:", out)                # grouped under the assignee (inert by default)
        self.assertIn("[slang#99](https://github.com/shader-slang/slang/pull/99)", out)
        self.assertIn(report.ESCALATED_ICON, out)       # in-place up-arrow
        self.assertNotIn("(@bob)", out)                 # redundant once grouped by assignee
        self.assertIn(report.COMMUNITY_ICON, out)

    def test_recipient_map_remaps_mentions(self):
        # With a map, the assignee header and the reviewer in the reason become
        # <@id> mentions; an unmapped login stays inert backticks.
        cfg = make_cfg(recipient_map={"bob": "111", "dan": "222"})
        pr = self._awaiting(number=98, source="Community", assignees=["bob"],
                            existing_reviewers=["dan", "eve"])
        out = report.render_report(report.build_report([pr], cfg, {pr.key(): (50.0, 3)}), cfg)
        self.assertIn("**<@111>**:", out)               # mapped assignee header pings
        self.assertIn("<@222>", out)                    # mapped reviewer pings
        self.assertNotIn("`bob`", out)                  # bob is mapped -> no backticks
        self.assertNotIn("@bob", out)                   # never bare @login

    def test_recipient_map_unmapped_stays_inert(self):
        cfg = make_cfg(recipient_map={"someone-else": "999"})
        pr = self._awaiting(number=97, source="Community", assignees=["bob"])
        out = report.render_report(report.build_report([pr], cfg, {pr.key(): (50.0, 3)}), cfg)
        self.assertIn("**`bob`**:", out)                # unmapped -> inert
        self.assertNotIn("<@", out)

    def test_render_includes_legend(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"])
        out = report.render_report(report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
        self.assertIn(f"{report.BOT_ICON} agent PR", out)
        self.assertIn(f"{report.COMMUNITY_ICON} community PR", out)
        self.assertIn(f"{report.ESCALATED_ICON} escalated/overdue", out)

    def test_report_title(self):
        pr = self._awaiting(number=99, source="Community", assignees=["bob"])
        out = report.render_report(report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)}), self.cfg)
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
        out = report.render_report(report.build_report([bp, be, cp, ce], self.cfg, stalls), self.cfg)
        order = [out.index(f"slang#{n}]") for n in (1, 2, 3, 4)]
        self.assertEqual(order, sorted(order))  # #1 < #2 < #3 < #4 in the text


@final
class TestUnassignedGroup(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()

    def _awaiting(self, **kw):
        base = dict(ci_state=report.CI_PASSED, existing_reviewers=["dan"],
                    review_decision="REVIEW_REQUIRED")
        base.update(kw)
        return make_pr(**base)

    def test_unassigned_pr_grouped_under_sentinel(self):
        pr = self._awaiting(number=30, source="Community", assignees=[])
        rec = report.build_report([pr], self.cfg, {pr.key(): (30.0, 2)})
        self.assertIn(report.UNASSIGNED, rec)
        self.assertEqual(rec[report.UNASSIGNED][0].assignee, report.UNASSIGNED)

    def test_unassigned_escalates_like_owned(self):
        pr = self._awaiting(number=31, source="Community", assignees=[])
        rec = report.build_report([pr], self.cfg, {pr.key(): (50.0, 3)})  # >= 48
        self.assertTrue(rec[report.UNASSIGNED][0].escalated)

    def test_unassigned_renders_first_with_header(self):
        unassigned = self._awaiting(number=32, source="Community", assignees=[])
        owned = self._awaiting(number=33, source="Community", assignees=["bob"])
        out = report.render_report(
            report.build_report([owned, unassigned], self.cfg,
                                 {unassigned.key(): (30.0, 2), owned.key(): (30.0, 2)}),
            self.cfg)
        self.assertIn("- **Unassigned**:", out)                 # literal header, not a mention
        self.assertNotIn("(unassigned)", out)                   # sentinel never leaks into text
        self.assertLess(out.index("**Unassigned**"), out.index("**`bob`**"))  # listed first


@final
class TestPruneState(unittest.TestCase):
    def _state(self):
        return {"prs": {
            "shader-slang/slang#1": {"stall": {"a": 1}},   # still open this run
            "shader-slang/slang#2": {"stall": {"b": 2}},   # closed -> should drop
            "shader-slang/other#9": {"stall": {"c": 3}},   # repo not scanned -> keep
        }}

    def test_open_kept_closed_dropped(self):
        state = self._state()
        report.prune_state(state, {"shader-slang/slang#1"}, {"shader-slang/slang"})
        self.assertIn("shader-slang/slang#1", state["prs"])      # open -> kept
        self.assertNotIn("shader-slang/slang#2", state["prs"])   # closed -> dropped

    def test_unscanned_repo_kept(self):
        # A subset run (only shader-slang/slang scanned) must not wipe clocks for
        # repos it didn't look at.
        state = self._state()
        report.prune_state(state, {"shader-slang/slang#1"}, {"shader-slang/slang"})
        self.assertIn("shader-slang/other#9", state["prs"])

    def test_empty_state_is_safe(self):
        state = {"prs": {}}
        report.prune_state(state, set(), {"shader-slang/slang"})
        self.assertEqual(state["prs"], {})


@final
class TestRecipientMap(unittest.TestCase):
    def test_format_mention_default_is_backticks(self):
        cfg = make_cfg()  # empty recipient_map
        self.assertEqual(report.format_mention("bob", cfg), "`bob`")

    def test_format_mention_mapped_pings(self):
        cfg = make_cfg(recipient_map={"bob": "123"})
        self.assertEqual(report.format_mention("bob", cfg), "<@123>")

    def test_format_mention_unmapped_in_nonempty_map(self):
        cfg = make_cfg(recipient_map={"alice": "123"})
        self.assertEqual(report.format_mention("bob", cfg), "`bob`")

    def test_format_mention_case_insensitive(self):
        cfg = make_cfg(recipient_map={"bob": "123"})  # keys are lowercased on load
        self.assertEqual(report.format_mention("BoB", cfg), "<@123>")

    def test_load_recipient_map_flat_and_lowercased(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "map.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"Jhelferty-NV": "111", "bob": 222}, f)
            m = report.load_recipient_map(p)
        self.assertEqual(m, {"jhelferty-nv": "111", "bob": "222"})  # keys lowered, values str

    def test_load_recipient_map_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(["bob", "dan"], f)
            with self.assertRaises(SystemExit):
                report.load_recipient_map(p)

    def test_load_recipient_map_missing_file(self):
        with self.assertRaises(SystemExit):
            report.load_recipient_map("/no/such/recipient-map.json")


@final
class TestRealReviewersAndEffective(unittest.TestCase):
    def setUp(self):
        self.cfg = make_cfg()  # ignored_reviewers default ["bmillsNV"]

    def test_real_reviewers_filters_ignored_and_bots(self):
        pr = make_pr(existing_reviewers=["bmillsNV", "copilot[bot]", "dan"])
        self.assertEqual(report._real_reviewers(pr, self.cfg), ["dan"])

    def test_reviewers_text(self):
        # Default (no recipient map): reviewers render as inert backticks.
        self.assertEqual(report._reviewers_text(make_pr(existing_reviewers=["bmillsNV", "dan"]),
                                                self.cfg), "`dan`")
        self.assertEqual(report._reviewers_text(make_pr(existing_reviewers=["bmillsNV"]),
                                                self.cfg), "(no reviewers requested)")

    def test_awaiting_review_needs_real_reviewer(self):
        # Only bmillsNV requested -> not "awaiting review"; falls through to idle.
        pr = make_pr(source="Community", ci_state=report.CI_PASSED,
                     existing_reviewers=["bmillsNV"], review_decision="REVIEW_REQUIRED")
        match = next((p for p in report.ladder_for(pr, self.cfg) if p.applies(pr, self.cfg)), None)
        self.assertEqual(match.key, "idle")

    def test_failing_ci_shows_ci_failing_not_awaiting(self):
        # A Community PR with failing CI derives to Revising, so it shows
        # "CI failing", not "awaiting review" (derived directly from live state).
        pr = make_pr(number=20, source="Community", assignees=["bob"],
                     existing_reviewers=["dan"], review_decision="REVIEW_REQUIRED",
                     ci_state=report.CI_FAILED)
        rec = report.build_report([pr], make_cfg(), {pr.key(): (50.0, 3)})
        self.assertIn("CI failing", rec["bob"][0].reason)

    def test_copilot_is_recognized_as_bot(self):
        self.assertTrue(report.classify_is_bot("Copilot", self.cfg.bot_authors))
        self.assertTrue(report.classify_is_bot("copilot-swe-agent", self.cfg.bot_authors))

    def test_effective_assignee_skips_bot(self):
        # [bmillsNV, Copilot] -> bmillsNV (first non-bot)
        pr = make_pr(assignees=["bmillsNV", "Copilot"])
        self.assertEqual(report.effective_assignee(pr, self.cfg), "bmillsNV")

    def test_effective_assignee_bot_only_is_unassigned(self):
        # No human assignee -> the sentinel; the report does not predict an owner.
        pr = make_pr(assignees=["Copilot"])
        self.assertEqual(report.effective_assignee(pr, self.cfg), report.UNASSIGNED)
        pr2 = make_pr(assignees=[])
        self.assertEqual(report.effective_assignee(pr2, self.cfg), report.UNASSIGNED)

    def test_copilot_only_goes_to_unassigned(self):
        # A Copilot-only-assigned bot PR has no human owner -> Unassigned group.
        pr = make_pr(number=21, source="Bot", is_bot=True,
                     assignees=["Copilot"], existing_reviewers=["dan"],
                     review_decision="REVIEW_REQUIRED")
        rec = report.build_report([pr], make_cfg(), {pr.key(): (200.0, 9)})
        self.assertNotIn("Copilot", rec)
        self.assertIn(report.UNASSIGNED, rec)


if __name__ == "__main__":
    unittest.main()
