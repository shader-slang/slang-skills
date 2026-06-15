#!/usr/bin/env python3
"""Committer-signal ranking for the slang-pr-maintenance sweep.

Given a PR's changed files, rank candidate committers by how much "signal" they
have on those files. Used to pick a PR's assignee (top owner) and extra reviewer
(top dev-not-owner) — see pr_sweep.select_assignee_and_reviewers.

The ranking weights the PR's top changed files, runs a cheap commit-TOTAL-LOC
pass over their default-branch history (`_cheap_pass`), and only when the top
candidates are close pays for a per-file-LOC tiebreak over the finalists
(`_refine_finalists`); see `compute_committer_ranking`.

The pure helpers (classification, multipliers, weighting, attribution, ranking,
tiebreak bookkeeping) are unit-tested with no live `gh`.

This module is thin glue around the `gh` CLI and untyped JSON; strict type rules
are relaxed (see the directive below). It depends only on the stdlib and a
duck-typed `gh` client exposing .json(args), .api(path, jq=...), .graphql(q, v).
"""
from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownLambdaType=false, reportMissingParameterType=false, reportImplicitStringConcatenation=false

import fnmatch
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_SIGNAL_FINALISTS = 6        # top candidates re-scored by true per-file LOC
DEFAULT_SIGNAL_CLEAR_MARGIN = 1.5   # skip the tiebreak when #1 leads #2 by this factor


@dataclass
class SignalCache:
    """Run-scoped cache of raw, PR-independent source data from `gh`, so a file's
    history or a commit's per-file stats are fetched once per sweep no matter how
    many PRs touch them. Holds ONLY source data; per-PR weighting/attribution is
    always recomputed."""
    # (repo, path) -> cheap-pass commit rows [{oid, author, loc, last_approver}]
    file_history: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    # (repo, sha) -> {path: max(additions, deletions)} for that commit
    commit_files: dict[tuple[str, str], dict[str, float]] = field(default_factory=dict)


# --- Pure helpers ----------------------------------------------------------

def classify_is_bot(author: str, bot_authors: list[str]) -> bool:
    """True when an author should be treated as a bot (matches 'name',
    'name[bot]', or 'app/name' against the configured bot authors)."""
    a = author.lower()
    for b in bot_authors:
        b = b.strip().lower()
        if not b:
            continue
        base = a.replace("[bot]", "").replace("app/", "")
        if base == b or a == b:
            return True
    return False


def is_bot_login(login: str, bot_authors: list[str]) -> bool:
    """A login that should never be credited with committer signal: any GitHub
    App ([bot] suffix), an unmapped/empty login, or a configured bot author."""
    if not login:
        return True
    return login.lower().endswith("[bot]") or classify_is_bot(login, bot_authors)


def attribute_commit(author_login: str, last_approver: str | None,
                     pr_author: str, bot_authors: list[str]) -> str | None:
    """Who a past commit's signal counts for (pure). Prefer the commit author;
    but when the author is a bot, unmapped, OR the current PR's author, fall back
    to the last approver of the PR that introduced the commit — the author's own
    past commits instead credit whoever reviewed them. The PR author and bots are
    never credited, so the commit is dropped if no eligible approver remains."""
    if (author_login and not is_bot_login(author_login, bot_authors)
            and author_login.lower() != pr_author.lower()):
        return author_login
    if (not last_approver or last_approver.lower() == pr_author.lower()
            or is_bot_login(last_approver, bot_authors)):
        return None
    return last_approver


def match_file_multiplier(path: str, table: list[tuple[str, float]], default: float) -> float:
    """Multiplier for `path`: the longest (most specific) matching directory
    glob wins; `default` if none match."""
    best_len = -1
    best_mult = default
    for glob, mult in table:
        if fnmatch.fnmatch(path, glob) and len(glob) > best_len:
            best_len = len(glob)
            best_mult = mult
    return best_mult


def per_file_signals(loc_by_file: dict[str, float], table: list[tuple[str, float]],
                     default: float) -> dict[str, float]:
    """Per-file signal = LOC * file_multiplier, for every changed file."""
    return {
        path: loc * match_file_multiplier(path, table, default)
        for path, loc in loc_by_file.items()
    }


def top_k_weights(signals: dict[str, float], k: int) -> dict[str, float]:
    """Keep the top-`k` files by signal and normalize them into weights summing
    to 1 (relative ratio). Files with non-positive total contribute nothing."""
    ranked = sorted(signals.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:k]
    total = sum(s for _, s in ranked if s > 0)
    if total <= 0:
        return {}
    return {path: s / total for path, s in ranked if s > 0}


def overall_signal(file_weights: dict[str, float],
                   loc_by_file_login: dict[str, dict[str, float]]) -> dict[str, float]:
    """Per-committer overall signal = sum over files of weight * LOC-in-file."""
    out: dict[str, float] = {}
    for path, weight in file_weights.items():
        for login, loc in loc_by_file_login.get(path, {}).items():
            out[login] = out.get(login, 0.0) + weight * loc
    return out


def rank_logins(overall: dict[str, float]) -> list[str]:
    """Logins ordered by overall signal (largest first); tie-break by login."""
    return [
        login for login, _score in
        sorted(overall.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    ]


def needs_tiebreak(cheap_overall: dict[str, float], ranked: list[str],
                   clear_margin: float) -> bool:
    """Whether the cheap (total-LOC) top two are close enough to warrant the
    per-file-LOC tiebreak. False on a clear winner (or <2 candidates)."""
    if len(ranked) < 2:
        return False
    top = cheap_overall.get(ranked[0], 0.0)
    second = cheap_overall.get(ranked[1], 0.0)
    if second <= 0:
        return False
    return top < clear_margin * second


def merge_refined(ranked: list[str], n: int, refined_overall: dict[str, float]) -> list[str]:
    """Re-order the top-`n` finalists by their refined (per-file-LOC) score,
    keeping the remaining tail in cheap order."""
    finalists = ranked[:n]
    refined = sorted(finalists, key=lambda login: (refined_overall.get(login, 0.0), login),
                     reverse=True)
    return refined + ranked[n:]


# --- GraphQL: batched per-file history (cheap pass) ------------------------

_HISTORY_QUERY_HEAD = """
query($owner: String!, $name: String!, $since: GitTimestamp!, $n: Int!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef { target { ... on Commit {
"""
_HISTORY_QUERY_TAIL = """
    } } }
  }
}
"""
_HISTORY_FILE_FIELD = """
      f%(i)d: history(path: %(path)s, since: $since, first: $n) {
        nodes {
          oid
          additions
          deletions
          author { user { login } }
          associatedPullRequests(first: 1) { nodes {
            reviews(first: 20, states: [APPROVED]) { nodes {
              submittedAt
              author { login }
            } }
          } }
        }
      }
"""


def fetch_file_histories(gh: Any, repo: str, paths: list[str], since: str,
                         commits: int,
                         history_cache: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
                         ) -> dict[str, list[dict[str, Any]]]:
    """Per path, the last `commits` default-branch commits since `since`, as
    path -> [{oid, author, loc(total), last_approver}].

    A file's default-branch history is PR-independent, so results are cached by
    (repo, path) in `history_cache` (run-scoped). Only paths not already cached
    are fetched, in a single batched GraphQL query; if all are cached, no request
    is made."""
    if history_cache is None:
        history_cache = {}
    uncached = [p for p in paths if (repo, p) not in history_cache]
    if uncached:
        owner, name = repo.split("/", 1)
        fields = "".join(
            _HISTORY_FILE_FIELD % {"i": i, "path": json.dumps(path)}
            for i, path in enumerate(uncached)
        )
        query = _HISTORY_QUERY_HEAD + fields + _HISTORY_QUERY_TAIL
        data = gh.graphql(query, {"owner": owner, "name": name, "since": since, "n": commits})
        target = ((((data or {}).get("data") or {}).get("repository") or {})
                  .get("defaultBranchRef") or {}).get("target") or {}
        for i, path in enumerate(uncached):
            nodes = ((target.get(f"f{i}") or {}).get("nodes")) or []
            commit_list: list[dict[str, Any]] = []
            for node in nodes:
                author = (((node.get("author") or {}).get("user") or {}).get("login")) or ""
                loc = float(max(node.get("additions", 0) or 0, node.get("deletions", 0) or 0))
                commit_list.append({
                    "oid": node.get("oid") or "",
                    "author": author,
                    "loc": loc,
                    "last_approver": _last_approver(node),
                })
            history_cache[(repo, path)] = commit_list
    return {path: history_cache[(repo, path)] for path in paths}


def _last_approver(commit_node: dict[str, Any]) -> str | None:
    """Login of the latest APPROVED review on the commit's associated PR."""
    prs = ((commit_node.get("associatedPullRequests") or {}).get("nodes")) or []
    if not prs:
        return None
    reviews = ((prs[0].get("reviews") or {}).get("nodes")) or []
    dated = [r for r in reviews if r.get("submittedAt")]
    if not dated:
        return None
    dated.sort(key=lambda r: r["submittedAt"])
    return ((dated[-1].get("author") or {}).get("login")) or None


def commit_file_loc(gh: Any, repo: str, sha: str, path: str,
                    cache: dict[tuple[str, str], dict[str, float]]) -> float:
    """max(additions, deletions) that commit `sha` changed in `path`. Caches the
    whole commit's per-file stats by (repo, sha) so a commit touching several
    files — or shared across PRs — is fetched once (run-scoped dedup)."""
    detail = cache.get((repo, sha))
    if detail is None:
        detail = {}
        raw = gh.api(
            f"repos/{repo}/commits/{sha}",
            jq=".files[] | {filename: .filename, additions: .additions, deletions: .deletions}",
        )
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            filename = rec.get("filename")
            if filename:
                detail[filename] = float(max(rec.get("additions", 0) or 0,
                                             rec.get("deletions", 0) or 0))
        cache[(repo, sha)] = detail
    return detail.get(path, 0.0)


# --- Top-level ranking -----------------------------------------------------

def horizon_since(horizon_days: int, now: datetime | None = None) -> str:
    """The GraphQL `since` timestamp for the signal horizon. Computed once per
    sweep (and passed in) so cache keys are stable across PRs."""
    base = now or datetime.now(timezone.utc)
    return (base - timedelta(days=horizon_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cheap_pass(history: dict[str, list[dict[str, Any]]], pr_author: str,
                bot_authors: list[str],
                ) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, list[str]]]]:
    """Attribute each file's commit-TOTAL LOC to a login, returning per-file
    (login -> LOC) and (login -> [oid]). The oids let the tiebreak fetch true
    per-file LOC for only the commits that matter."""
    cheap_loc: dict[str, dict[str, float]] = {}
    oids_by_file_login: dict[str, dict[str, list[str]]] = {}
    for path, commit_list in history.items():
        per_login: dict[str, float] = {}
        per_oids: dict[str, list[str]] = {}
        for commit in commit_list:
            attributed = attribute_commit(
                commit["author"], commit["last_approver"], pr_author, bot_authors)
            if not attributed or commit["loc"] <= 0:
                continue
            per_login[attributed] = per_login.get(attributed, 0.0) + commit["loc"]
            if commit["oid"]:
                per_oids.setdefault(attributed, []).append(commit["oid"])
        if per_login:
            cheap_loc[path] = per_login
            oids_by_file_login[path] = per_oids
    return cheap_loc, oids_by_file_login


def _refine_finalists(gh: Any, repo: str, weights: dict[str, float],
                      oids_by_file_login: dict[str, dict[str, list[str]]],
                      finalist_set: set[str], cache: SignalCache,
                      ) -> dict[str, dict[str, float]]:
    """Re-score the finalists with TRUE per-file LOC, deduped via the run-scoped
    commit cache so shared commits are fetched once."""
    refined_loc: dict[str, dict[str, float]] = {}
    for path in weights:
        refined_per_login: dict[str, float] = {}
        for login, oids in oids_by_file_login.get(path, {}).items():
            if login not in finalist_set:
                continue
            total = sum(commit_file_loc(gh, repo, oid, path, cache.commit_files) for oid in oids)
            if total > 0:
                refined_per_login[login] = total
        if refined_per_login:
            refined_loc[path] = refined_per_login
    return refined_loc


def compute_committer_ranking(
    gh: Any, repo: str, pr_author: str, *,
    loc_by_file: dict[str, float],
    file_multipliers: list[tuple[str, float]], default_multiplier: float,
    top_files: int, commits: int, horizon_days: int, bot_authors: list[str],
    finalists: int = DEFAULT_SIGNAL_FINALISTS,
    clear_margin: float = DEFAULT_SIGNAL_CLEAR_MARGIN,
    since: str | None = None,
    cache: SignalCache | None = None,
) -> list[str]:
    """Ranked candidate committer logins for the PR (highest signal first),
    excluding the PR author and bots: a cheap total-LOC pass, then a per-file-LOC
    tiebreak over the top `finalists` only when they are close.

    `loc_by_file` is the PR's own changed-file LOC (path -> max(add, del)). The
    run-scoped `cache` dedups PR-independent source fetches across PRs; per-PR
    weighting/attribution is always recomputed. Pass `since` once per sweep for
    stable cache keys."""
    if cache is None:
        cache = SignalCache()
    if since is None:
        since = horizon_since(horizon_days)

    weights = top_k_weights(per_file_signals(loc_by_file, file_multipliers, default_multiplier),
                            top_files)
    if not weights:
        return []

    history = fetch_file_histories(gh, repo, list(weights), since, commits, history_cache=cache.file_history)
    cheap_loc, oids_by_file_login = _cheap_pass(history, pr_author, bot_authors)
    cheap_overall = overall_signal(weights, cheap_loc)
    cheap_ranked = rank_logins(cheap_overall)

    if not needs_tiebreak(cheap_overall, cheap_ranked, clear_margin):
        return cheap_ranked  # clear winner (or <2 candidates): cheap pass suffices

    finalist_set = set(cheap_ranked[:finalists])
    refined_loc = _refine_finalists(gh, repo, weights, oids_by_file_login, finalist_set, cache)
    refined_overall = overall_signal(weights, refined_loc)
    return merge_refined(cheap_ranked, finalists, refined_overall)
