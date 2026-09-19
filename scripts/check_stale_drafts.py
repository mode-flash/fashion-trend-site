"""滞留しているトレンド記事の下書きPRを検知し、ラベルとコメントで知らせるスクリプト.

トレンド記事のroutineは、`trend-draft-`で始まるブランチのオープンPRが残っている間は
新しい下書きを作らない。PRが放置されると記事の更新が止まるため、作成から一定日数が
経った下書きPRにコメントとラベルを付けて、GitHubの通知でオーナーに知らせる。
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from datetime import datetime, timezone
from typing import Callable, NamedTuple

logger = logging.getLogger(__name__)

DRAFT_BRANCH_PREFIX = "trend-draft-"
STALE_LABEL = "stale-draft"
STALE_LABEL_COLOR = "d93f0b"
STALE_LABEL_DESCRIPTION = "マージ待ちで滞留しているトレンド記事の下書きPR"
DEFAULT_THRESHOLD_DAYS = 5


class StaleDraft(NamedTuple):
    number: int
    days: int


def _parse_time(value: str) -> datetime:
    # Python 3.9のfromisoformatは末尾の"Z"を解釈できないため置き換える
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def select_stale_drafts(prs: list[dict], now: datetime, threshold_days: int) -> list[StaleDraft]:
    """下書きPRのうち、作成からthreshold_days日以上経ち、まだ通知していないものを返す."""
    stale = []
    for pr in prs:
        if not pr["headRefName"].startswith(DRAFT_BRANCH_PREFIX):
            continue
        if any(label["name"] == STALE_LABEL for label in pr["labels"]):
            continue
        days = (now - _parse_time(pr["createdAt"])).days
        if days >= threshold_days:
            stale.append(StaleDraft(pr["number"], days))
    return stale


def build_comment(days: int) -> str:
    return (
        f"このトレンド記事の下書きPRは、作成から{days}日間マージもクローズもされていません。\n\n"
        f"トレンド記事のroutineは、`{DRAFT_BRANCH_PREFIX}`で始まるブランチのオープンPRが残っている間は"
        "新しい下書きを作りません。記事の更新を続けるには、このPRをマージするかクローズしてください。"
    )


def notify_stale_drafts(
    prs: list[dict],
    now: datetime,
    threshold_days: int,
    run_gh: Callable[[list[str]], str],
    dry_run: bool = False,
) -> list[StaleDraft]:
    """滞留した下書きPRにコメントとラベルを付ける.

    ラベルを通知済みの目印にする。コメントを先に投稿するのは、途中で失敗したときに
    通知されないまま終わるより、翌日に重複して通知されるほうがましなため。
    """
    stale = select_stale_drafts(prs, now, threshold_days)
    if stale and not dry_run:
        run_gh([
            "label", "create", STALE_LABEL,
            "--color", STALE_LABEL_COLOR,
            "--description", STALE_LABEL_DESCRIPTION,
            "--force",
        ])
    for draft in stale:
        logger.info("PR #%d: 作成から%d日経過", draft.number, draft.days)
        if dry_run:
            continue
        run_gh(["pr", "comment", str(draft.number), "--body", build_comment(draft.days)])
        run_gh(["pr", "edit", str(draft.number), "--add-label", STALE_LABEL])
    return stale


def _run_gh(args: list[str]) -> str:
    # stderrは取り込まず、ghのエラーメッセージをそのままログに出す
    result = subprocess.run(
        ["gh", *args], check=True, stdout=subprocess.PIPE, text=True, encoding="utf-8"
    )
    return result.stdout


def list_open_prs(run_gh: Callable[[list[str]], str]) -> list[dict]:
    output = run_gh([
        "pr", "list", "--state", "open", "--limit", "100",
        "--json", "number,headRefName,createdAt,labels",
    ])
    return json.loads(output)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=DEFAULT_THRESHOLD_DAYS,
        help="作成からこの日数以上経った下書きPRを通知する（既定: %(default)s）",
    )
    parser.add_argument("--dry-run", action="store_true", help="通知せず、対象だけを表示する")
    args = parser.parse_args()
    stale = notify_stale_drafts(
        list_open_prs(_run_gh), datetime.now(timezone.utc), args.days, _run_gh, dry_run=args.dry_run
    )
    if not stale:
        logger.info("通知対象の下書きPRはありません")


if __name__ == "__main__":
    main()
