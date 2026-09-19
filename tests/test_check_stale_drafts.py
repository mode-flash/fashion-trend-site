import json
import os
import stat
import subprocess
from datetime import datetime, timezone

import pytest

from scripts.check_stale_drafts import (
    STALE_LABEL,
    _run_gh,
    build_comment,
    list_open_prs,
    main,
    notify_stale_drafts,
    select_stale_drafts,
)

NOW = datetime(2026, 9, 19, 0, 30, tzinfo=timezone.utc)
LABEL_CREATE = [
    "label", "create", STALE_LABEL, "--color", "d93f0b",
    "--description", "マージ待ちで滞留しているトレンド記事の下書きPR", "--force",
]


def _pr(number, branch="trend-draft-2026-09-03", created="2026-09-03T00:15:03Z", labels=(), cross=False):
    return {
        "number": number,
        "headRefName": branch,
        "createdAt": created,
        "labels": [{"name": name} for name in labels],
        "isCrossRepository": cross,
    }


def _install_fake_gh(tmp_path, monkeypatch, script):
    fake_gh = tmp_path / "gh"
    fake_gh.write_text("#!/bin/sh\n" + script, encoding="utf-8")
    fake_gh.chmod(fake_gh.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])


def _install_recording_gh(tmp_path, monkeypatch, prs):
    """`gh pr list`にprsを返し、全呼び出しの先頭3引数をログに残す偽のgh."""
    log = tmp_path / "gh.log"
    prs_file = tmp_path / "prs.json"
    prs_file.write_text(json.dumps(prs), encoding="utf-8")
    script = (
        "printf '%s\\n' \"$1 $2 $3\" >> \"" + str(log) + "\"\n"
        "if [ \"$1 $2\" = \"pr list\" ]; then cat \"" + str(prs_file) + "\"; fi\n"
    )
    _install_fake_gh(tmp_path, monkeypatch, script)
    return log


def _gh_log(log):
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


# --- select_stale_drafts ---

def test_select_returns_draft_pr_older_than_threshold():
    stale = select_stale_drafts([_pr(3)], NOW, 5)
    assert [(d.number, d.days) for d in stale] == [(3, 16)]


def test_select_counts_calendar_days_in_utc():
    # 実際の経過は4日と30分ほどだが、暦日では5日前にあたる
    stale = select_stale_drafts([_pr(4, created="2026-09-14T23:59:59Z")], NOW, 5)
    assert [(d.number, d.days) for d in stale] == [(4, 5)]


def test_select_excludes_pr_created_fewer_calendar_days_ago():
    stale = select_stale_drafts([_pr(4, created="2026-09-15T00:00:00Z")], NOW, 5)
    assert stale == []


def test_select_ignores_branches_without_draft_prefix():
    stale = select_stale_drafts([_pr(5, branch="feature/alert")], NOW, 5)
    assert stale == []


def test_select_ignores_pr_from_a_fork():
    stale = select_stale_drafts([_pr(5, cross=True)], NOW, 5)
    assert stale == []


def test_select_skips_pr_that_already_has_stale_label():
    stale = select_stale_drafts([_pr(3, labels=[STALE_LABEL])], NOW, 5)
    assert stale == []


def test_select_with_zero_threshold_picks_fresh_draft():
    stale = select_stale_drafts([_pr(6, created="2026-09-19T00:30:00Z")], NOW, 0)
    assert [(d.number, d.days) for d in stale] == [(6, 0)]


# --- build_comment ---

def test_build_comment_states_elapsed_days_and_routine_effect():
    comment = build_comment(15)
    assert "15日" in comment
    assert "trend-draft-" in comment


# --- notify_stale_drafts ---

def test_notify_comments_then_creates_label_then_labels_pr():
    calls = []
    notify_stale_drafts([_pr(3)], NOW, 5, calls.append)
    assert calls == [
        ["pr", "comment", "3", "--body", build_comment(16)],
        LABEL_CREATE,
        ["pr", "edit", "3", "--add-label", STALE_LABEL],
    ]


def test_notify_creates_label_only_once_for_several_drafts():
    calls = []
    notify_stale_drafts([_pr(3), _pr(4)], NOW, 5, calls.append)
    assert calls.count(LABEL_CREATE) == 1
    assert [c[:3] for c in calls] == [
        ["pr", "comment", "3"], ["label", "create", STALE_LABEL], ["pr", "edit", "3"],
        ["pr", "comment", "4"], ["pr", "edit", "4"],
    ]


def test_notify_still_comments_when_label_creation_fails():
    calls = []

    def run_gh(args):
        calls.append(args)
        if args[:2] == ["label", "create"]:
            raise subprocess.CalledProcessError(1, ["gh"])
        return ""

    with pytest.raises(subprocess.CalledProcessError):
        notify_stale_drafts([_pr(3)], NOW, 5, run_gh)
    assert ["pr", "comment", "3", "--body", build_comment(16)] in calls


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


# --- gh の呼び出し ---

def test_run_gh_returns_stdout(tmp_path, monkeypatch):
    _install_fake_gh(tmp_path, monkeypatch, "echo '[1]'\n")
    assert _run_gh(["pr", "list"]).strip() == "[1]"


def test_run_gh_failure_raises_and_shows_gh_error_message(tmp_path, monkeypatch, capfd):
    _install_fake_gh(tmp_path, monkeypatch, "echo 'label create: permission denied' >&2\nexit 1\n")
    with pytest.raises(subprocess.CalledProcessError):
        _run_gh(["label", "create", STALE_LABEL])
    assert "permission denied" in capfd.readouterr().err


def test_list_open_prs_parses_json_and_requests_every_field_used_for_selection():
    seen = []

    def run_gh(args):
        seen.append(args)
        return json.dumps([_pr(3)])

    assert list_open_prs(run_gh) == [_pr(3)]
    args = seen[0]
    fields = set(args[args.index("--json") + 1].split(","))
    assert {"number", "headRefName", "createdAt", "labels", "isCrossRepository"} <= fields
    assert int(args[args.index("--limit") + 1]) >= 1000


# --- main（偽のghを使った通し） ---

def test_main_notifies_stale_draft_with_default_threshold(tmp_path, monkeypatch):
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3)])
    main([])
    assert _gh_log(log) == ["pr list --state", "pr comment 3", "label create stale-draft", "pr edit 3"]


def test_main_does_nothing_when_no_draft_is_stale(tmp_path, monkeypatch):
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3, created="2999-01-01T00:00:00Z")])
    main([])
    assert _gh_log(log) == ["pr list --state"]


def test_main_dry_run_only_lists_prs(tmp_path, monkeypatch):
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3)])
    main(["--dry-run"])
    assert _gh_log(log) == ["pr list --state"]


def test_main_days_option_lowers_the_threshold(tmp_path, monkeypatch):
    just_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3, created=just_now)])
    main([])
    assert _gh_log(log) == ["pr list --state"]
    main(["--days", "0"])
    assert "pr comment 3" in _gh_log(log)


def test_main_rejects_non_integer_days_with_a_readable_message(tmp_path, monkeypatch, capsys):
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3)])
    with pytest.raises(SystemExit) as exc_info:
        main(["--days", "abc"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "整数" in err
    assert "_non_negative_int" not in err
    assert _gh_log(log) == []


def test_main_rejects_negative_days(tmp_path, monkeypatch):
    log = _install_recording_gh(tmp_path, monkeypatch, [_pr(3)])
    with pytest.raises(SystemExit) as exc_info:
        main(["--days", "-1"])
    assert exc_info.value.code == 2
    assert _gh_log(log) == []
