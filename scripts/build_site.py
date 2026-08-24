"""data/items.json と content/trends/*.md から docs/ に静的サイトを生成する."""

from __future__ import annotations

import json
import re
import shutil
from html import unescape
from pathlib import Path

import frontmatter
import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_TAG_RE = re.compile(r"<[^>]+>")
# 一部フィード（FASHIONSNAP等）はdescriptionが閉じ`>`の無いまま途中で切れた
# `<img src="...`のような不完全なタグを含むことがある。通常の_TAG_REは`>`を
# 要求するため除去できず、タグ風の文字列がそのまま読者に見えてしまう。
# 属性値（URL等）は空白を含まない前提で、`<タグ名 属性="値`の形だけを
# 狭く対象にして除去する（本文中の通常の"<"はこの形に一致しないため誤爆しない）。
_UNCLOSED_TAG_RE = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*\s+[a-zA-Z:-]+="[^"\s]*')

# WordPress系フィード（HOUYHNHNM等）のdescriptionの末尾に必ず付く
# 「The post <a>記事タイトル</a> first appeared on <a>サイト名</a>.」という定型フッターの
# 除去用。タグ除去後は記事タイトル・サイト名がリンクテキストとして地の文に残るため、
# 変動する部分（タイトル・サイト名）ではなく前後の固定の英語フレーズだけに一致させる。
# `.+?`は非貪欲マッチ: 通常このフッターは文字列の末尾に1つだけ出現するため、貪欲/非貪欲の
# 結果は変わらないが、万一本文中に同じ英語フレーズが偶然含まれる場合でも、最も手前の
# 一致から末尾までの最小範囲だけを削るようにするため非貪欲を選ぶ。
_WORDPRESS_BOILERPLATE_RE = re.compile(r"\s*The post .+? first appeared on .+?\.\s*$")


def excerpt(raw_html: str, limit: int = 200) -> str:
    """RSSのdescription（HTMLタグを含みうる）からタグを除去し、抜粋のプレーンテキストを返す.

    - HTMLタグを除去する（閉じ`>`の無い不完全なタグも狭い条件で除去する）
    - HTMLエンティティをアンエスケープする（Jinja2に渡す前のソーステキストをクリーンにするだけで、
      Jinja2の自動エスケープ自体はそのまま有効に働く）
    - WordPress系フィードの「The post ... first appeared on ....」という定型フッター
      （本文ではなくサイトのリンク案内文）を除去する
    - 空白・改行を1つのスペースに畳む
    - limit文字を超える場合は切り詰めて「…」を付与する
    """
    text = _TAG_RE.sub("", raw_html or "")
    text = _UNCLOSED_TAG_RE.sub("", text)
    text = unescape(text)
    text = " ".join(text.split())
    text = _WORDPRESS_BOILERPLATE_RE.sub("", text)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def load_items(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _extract_lead_markdown(markdown_text: str) -> str:
    """本文のうち、最初の見出し（#系記法）より前の部分だけを返す.

    トップページのフィーチャーカードは記事の導入部だけをリード文として見せたい。
    見出しが無い記事では全文がそのまま返るため、従来通り本文全体が使われる。
    """
    lead_lines = []
    for line in markdown_text.split("\n"):
        if line.lstrip().startswith("#"):
            break
        lead_lines.append(line)
    return "\n".join(lead_lines).strip()


def _resolve_trend_images(image_urls: list[str], items_by_url: dict[str, dict]) -> list[dict]:
    """トレンド記事のfrontmatterで指定されたURLを、data/items.jsonのアイテムに引き当てる.

    画像を著作権上の引用として成立させるため、新着カードと同じ「出典・元記事リンク付き」の
    形で表示する。該当アイテムが見つからない、または画像を持たない場合は静かにスキップする
    （記事の削除・データの入れ替わりでリンク切れになっても、ビルド自体は失敗させない）。
    """
    resolved = []
    for url in image_urls:
        item = items_by_url.get(url)
        if item and item.get("image_url"):
            resolved.append({
                "image_url": item["image_url"],
                "source": item.get("source", ""),
                "url": item["url"],
                "title": item.get("title", ""),
            })
    return resolved


def load_trend_posts(content_dir: Path, items: list[dict] = ()) -> list[dict]:
    if not content_dir.exists():
        return []
    items_by_url = {item["url"]: item for item in items}
    posts = []
    for p in sorted(content_dir.glob("*.md")):
        post = frontmatter.load(p)
        converter = md.Markdown(extensions=["toc"])
        html = converter.convert(post.content)
        lead_html = md.markdown(_extract_lead_markdown(post.content))
        posts.append({
            "title": post.get("title", p.stem),
            "date": str(post.get("date", "")),
            "slug": p.stem,
            "html": html,
            "lead_html": lead_html,
            "images": _resolve_trend_images(post.get("images", []), items_by_url),
            "toc": converter.toc if converter.toc_tokens else None,
        })
    posts.sort(key=lambda x: str(x["date"]), reverse=True)
    return posts


FEED_ITEM_LIMIT = 200
TOP_GRID_ITEM_LIMIT = 15
TOP_TREND_LIMIT = 5

# 海外メディア（Highsnobiety・Hypebeast）は1日あたりの投稿数が多く、公開日時降順の
# 単純な並びだとトップページの新着枠が海外メディアの記事で埋まってしまう
# （実データで新着グリッド15件中9件が海外メディアという偏りを確認した）。
# 日本人読者向けの露出を確保するため、国内メディアの記事が母集団の一定比率を
# 占めるよう優先的に選び出す。
JAPANESE_SOURCES = {"Fashionsnap", "HOUYHNHNM"}
TOP_GRID_JAPANESE_RATIO = 2 / 3


def _prioritize_japanese(items: list[dict], limit: int, jp_ratio: float = TOP_GRID_JAPANESE_RATIO) -> list[dict]:
    """itemsから、国内メディア（JAPANESE_SOURCES）がjp_ratio分を占めるようlimit件選び出す.

    itemsは公開日時降順にソート済みであることを前提とする。国内・海外それぞれの
    中では新しい順を維持したまま、国内メディアをjp_ratio分優先的に確保し、残り枠を
    海外メディアで埋める（海外メディアが不足する場合は国内メディアで埋め戻す）。
    最後に選び出した集合を公開日時降順で並べ直し、表示上は自然な新着順に見せる。
    """
    jp_target = round(limit * jp_ratio)
    jp_items = [i for i in items if i.get("source") in JAPANESE_SOURCES]
    other_items = [i for i in items if i.get("source") not in JAPANESE_SOURCES]

    selected_jp = jp_items[:jp_target]
    selected_other = other_items[: limit - len(selected_jp)]
    combined = selected_jp + selected_other
    if len(combined) < limit:
        remaining_jp = jp_items[len(selected_jp):]
        combined += remaining_jp[: limit - len(combined)]

    combined.sort(key=lambda i: i.get("published", ""), reverse=True)
    return combined


def _pick_hero(items: list[dict]) -> tuple[dict | None, list[dict]]:
    """画像のある最新アイテムをヒーローとして選ぶ。無ければ先頭にフォールバックする.

    itemsは公開日時降順にソート済みであることを前提とする。Highsnobietyのように
    フィードに画像データを一切含まないソースの記事がたまたま最新（先頭）になると、
    ヒーロー（トップページの大きな目立つ枠）が画像の無い黒い枠のまま表示され、
    壊れて見える問題があった。これを避けるため、先頭から順に見て画像URLを持つ
    最初のアイテムをヒーローとして選び、グリッド（それ以降のカード一覧）からは
    そのアイテムを除外して重複表示を防ぐ。
    どのアイテムにも画像が無い場合（空リストを含む）は、従来通りitems[0]に
    フォールバックする（空リストならヒーロー無し＝Noneを返す）。
    """
    for i, item in enumerate(items):
        if item.get("image_url"):
            return item, items[:i] + items[i + 1:]
    if items:
        return items[0], items[1:]
    return None, []


def _build_search_index(items: list[dict], trends: list[dict]) -> list[dict]:
    """サイト内検索用の軽量なインデックスをitems・trendsから生成する.

    静的サイトのためサーバーサイド検索は使えず、ブラウザ側のJavaScript
    （static/search.js）が単純な部分文字列一致でこのインデックスを絞り込む
    方式を取る。日本語の分かち書きは行わないため、タイトル・本文（トレンド
    記事はプレーンテキスト化した全文、新着アイテムは抜粋）の両方を検索対象
    として持たせ、部分一致でも見つけやすくする。
    """
    index = []
    for item in items[:FEED_ITEM_LIMIT]:
        index.append({
            "type": "item",
            "title": item.get("title", ""),
            "excerpt": excerpt(item.get("summary", "")),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "date": (item.get("published") or "")[:10],
            "image_url": item.get("image_url"),
        })
    for post in trends:
        first_image = post["images"][0]["image_url"] if post.get("images") else None
        index.append({
            "type": "trend",
            "title": post.get("title", ""),
            "excerpt": excerpt(post.get("html", ""), limit=100_000),
            "url": f"trends/{post['slug']}.html",
            "source": "トレンド分析",
            "date": post.get("date", ""),
            "image_url": first_image,
        })
    return index


def _group_by_source(items: list[dict]) -> list[dict]:
    """itemsを出典ソースごとにグループ化する。

    グループの並び順はitemsを先頭から走査して初めて出現したソースの順、
    各グループ内の並び順はitemsの既存順序（公開日時降順）をそのまま保つ。
    """
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for item in items:
        source = item.get("source", "")
        if source not in groups:
            groups[source] = []
            order.append(source)
        groups[source].append(item)
    return [{"source": s, "entries": groups[s]} for s in order]


def build(output_dir: Path, items: list[dict], trends: list[dict]) -> None:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["excerpt"] = excerpt
    output_dir.mkdir(parents=True, exist_ok=True)
    trends_dir = output_dir / "trends"
    trends_dir.mkdir(parents=True, exist_ok=True)

    # リネーム・削除済みトレンド記事の古い生成物を掃除する（index.htmlは常に再生成するため対象外）
    current_slugs = {post["slug"] for post in trends}
    for existing_html in trends_dir.glob("*.html"):
        if existing_html.stem != "index" and existing_html.stem not in current_slugs:
            existing_html.unlink()

    # GitHub PagesのJekyll処理を無効化する
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    # 静的アセット（CSS等）をdocs/配下にコピーする
    static_out = output_dir / "static"
    if STATIC_DIR.exists():
        static_out.mkdir(parents=True, exist_ok=True)
        for asset in STATIC_DIR.iterdir():
            if asset.is_file():
                shutil.copy2(asset, static_out / asset.name)

    grid_pool = _prioritize_japanese(items, TOP_GRID_ITEM_LIMIT + 1)
    hero, grid_items = _pick_hero(grid_pool)
    (output_dir / "index.html").write_text(
        env.get_template("index.html").render(
            hero=hero, items=grid_items[:TOP_GRID_ITEM_LIMIT], trends=trends[:TOP_TREND_LIMIT]
        ),
        encoding="utf-8",
    )
    (output_dir / "feed.html").write_text(
        env.get_template("feed.html").render(
            groups=_group_by_source(items[:FEED_ITEM_LIMIT])
        ),
        encoding="utf-8",
    )
    (trends_dir / "index.html").write_text(
        env.get_template("trends.html").render(trends=trends, asset_prefix="../"),
        encoding="utf-8",
    )
    (output_dir / "search.html").write_text(
        env.get_template("search.html").render(),
        encoding="utf-8",
    )
    (output_dir / "search-index.json").write_text(
        json.dumps(_build_search_index(items, trends), ensure_ascii=False),
        encoding="utf-8",
    )
    detail_tpl = env.get_template("trend_detail.html")
    for post in trends:
        (trends_dir / f"{post['slug']}.html").write_text(
            detail_tpl.render(post=post, asset_prefix="../"), encoding="utf-8"
        )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    items = load_items(root / "data" / "items.json")
    trends = load_trend_posts(root / "content" / "trends", items)
    build(root / "docs", items, trends)


if __name__ == "__main__":
    main()
