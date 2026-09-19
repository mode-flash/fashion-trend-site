import os
import stat
import subprocess
from datetime import datetime, timezone

import pytest

from scripts.check_stale_drafts import (
    STALE_LABEL,
    _run_gh,
    build_comment,
    notify_stale_drafts,
    select_stale_drafts,
)

NOW = datetime(2026, 9, 19, 0, 30, tzinfo=timezone.utc)


def _pr(number, branch="trend-draft-2026-09-03", created="2026-09-03T00:15:03Z", labels=()):
    return {
        "number": number,
        "headRefName": branch,
        "createdAt": created,
        "labels": [{"name": name} for name in labels],
    }


def test_select_returns_draft_pr_older_than_threshold():
    stale = select_stale_drafts([_pr(3)], NOW, 5)
    assert [(d.number, d.days) for d in stale] == [(3, 16)]


def test_select_includes_pr_exactly_at_threshold():
    stale = select_stale_drafts([_pr(4, created="2026-09-14T00:30:00Z")], NOW, 5)
    assert [d.number for d in stale] == [4]


def test_select_excludes_pr_just_under_threshold():
    stale = select_stale_drafts([_pr(4, created="2026-09-14T00:30:01Z")], NOW, 5)
    assert stale == []


def test_select_ignores_branches_without_draft_prefix():
    stale = select_stale_drafts([_pr(5, branch="feature/alert")], NOW, 5)
    assert stale == []


def test_select_skips_pr_that_already_has_stale_label():
    stale = select_stale_drafts([_pr(3, labels=[STALE_LABEL])], NOW, 5)
    assert stale == []


def test_select_with_zero_threshold_picks_fresh_draft():
    stale = select_stale_drafts([_pr(6, created="2026-09-19T00:30:00Z")], NOW, 0)
    assert [(d.number, d.days) for d in stale] == [(6, 0)]


def test_build_comment_states_elapsed_days_and_routine_effect():
    comment = build_comment(15)
    assert "15日" in comment
    assert "trend-draft-" in comment


def test_notify_creates_label_then_comments_then_labels_pr():
    calls = []
    notify_stale_drafts([_pr(3)], NOW, 5, calls.append)
    assert calls == [
        ["label", "create", STALE_LABEL, "--color", "d93f0b",
         "--description", "マージ待ちで滞留しているトレンド記事の下書きPR", "--force"],
        ["pr", "comment", "3", "--body", build_comment(16)],
        ["pr", "edit", "3", "--add-label", STALE_LABEL],
    ]


def test_notify_makes_no_gh_calls_when_nothing_is_stale():
    calls = []
    stale = notify_stale_drafts([_pr(3, created="2026-09-18T00:00:00Z")], NOW, 5, calls.append)
    assert stale == []
    assert calls == []


def test_notify_dry_run_reports_but_makes_no_gh_calls():
    calls = []
    stale = notify_stale_drafts([_pr(3)], NOW, 5, calls.append, dry_run=True)
    assert [d.number for d in stale] == [3]
    assert calls == []


def _install_fake_gh(tmp_path, monkeypatch, script):
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])


def test_run_gh_returns_stdout(tmp_path, monkeypatch):
    _install_fake_gh(tmp_path, monkeypatch, "echo '[1]'\n")
    assert _run_gh(["pr", "list"]).strip() == "[1]"


def test_run_gh_failure_raises_and_shows_gh_error_message(tmp_path, monkeypatch, capfd):
    _install_fake_gh(tmp_path, monkeypatch, "echo 'label create: permission denied' >&2\nexit 1\n")
    with pytest.raises(subprocess.CalledProcessError):
        _run_gh(["label", "create", STALE_LABEL])
    assert "permission denied" in capfd.readouterr().err
