# ファッショントレンドサイト

ストリート・カジュアル系ブランドの新着情報とトレンド分析を専門メディアのRSSから自動収集して公開する静的サイト。

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 手動実行

```bash
python -m scripts.fetch_feeds
python -m scripts.build_site
```

## テスト

```bash
pytest
```

## 運用メモ

- GitHub Actionsが1日3回（1時・9時・17時 UTC）走り、`main`ブランチに直接コミット・pushする。
  ローカルで変更をpushする前には、必ず`git pull`してから作業すること（そうしないとpushが
  リジェクトされることがある）。
- 公開URL: https://mode-flash.github.io/fashion-trend-site/
- `docs/`はビルドの生成物。手で編集しないこと（`build_site.py`を実行するたびに上書きされる）。

## 下書きPRの滞留通知

claude.aiのroutineが、3日おきに`content/trends/`へ記事の下書きを追加するPRを作る
（ブランチ名は`trend-draft-`で始まる）。
routineは、このブランチのオープンPRが残っている間は新しい下書きを作らないため、
PRを放置すると記事の更新が止まる。

`stale-draft-alert.yml`が毎日（0:30 UTC）走り、作成から5日以上経った`trend-draft-`のPRに
コメントと`stale-draft`ラベルを付ける。日数はUTCの暦日で数える。
通知はPRの作者（現在はオーナー本人）にGitHubの通知として届く。
コメントはActionsのbotが付けるので、作者本人の操作にはならない。

- 通知は1つのPRにつき1回。ラベルを通知済みの目印にしているので、もう一度通知したいときは
  `stale-draft`ラベルを外す。
- 日数を変えて手で走らせるときは、ActionsのRun workflowで`days`を指定する。
- ローカルで確認するときは`python3 -m scripts.check_stale_drafts --dry-run`を実行する
  （`gh`にログイン済みであること）。通知はせず、対象のPRだけを表示する。
