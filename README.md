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
- 公開URL: https://kosaku0801-a11y.github.io/fashion-trend-site/
- `docs/`はビルドの生成物。手で編集しないこと（`build_site.py`を実行するたびに上書きされる）。
- `stale-draft-alert.yml`が毎日走り、作成から5日以上マージされていない`trend-draft-`ブランチのPRにコメントと`stale-draft`ラベルを付ける。トレンド記事のroutineはオープンな下書きPRが残っている間は新しい下書きを作らないため、PRを放置すると記事の更新が止まる。
