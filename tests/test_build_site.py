from pathlib import Path

import json

from scripts.build_site import build, excerpt, load_items, load_trend_posts, _pick_hero, _group_by_source, _prioritize_japanese, _build_search_index


def test_excerpt_strips_html_tags_and_entities_and_truncates():
    raw = (
        '<div><img src="https://example.com/a.jpg" /><p>' +
        "とても&amp;素敵な新作スニーカーが登場しました。" * 10 +
        "</p></div>"
    )
    result = excerpt(raw)
    assert "<img" not in result
    assert "<p>" not in result
    assert "&amp;" not in result
    assert "&" in result  # アンエスケープされて素の文字になっている
    assert len(result) == 201  # 200文字 + "…"
    assert result.endswith("…")


def test_excerpt_short_plain_text_passes_through_unchanged():
    assert excerpt("短い紹介文です") == "短い紹介文です"


def test_excerpt_strips_unclosed_img_tag_missing_closing_bracket():
    # FASHIONSNAPのフィードで実際に観測された、閉じ`>`の無い不完全なimgタグ
    raw = '<img src="https://example.com/photo.jpg 東京で撮影しました。'
    result = excerpt(raw)
    assert "<img" not in result
    assert "src=" not in result
    assert "東京で撮影しました。" in result


def test_excerpt_strips_wordpress_the_post_first_appeared_on_boilerplate():
    # HOUYHNHNMの実データ（WordPress由来）は、descriptionの末尾に必ず
    # 「The post <a>記事タイトル</a> first appeared on <a>サイト名</a>.」という
    # 英語の定型フッターが付く。タグ除去後はリンクテキスト（記事タイトル・サイト名）が
    # 地の文として残るため、周辺の英語の定型句だけを狙って除去する。
    raw = (
        '<p>こう暑いと服のことを考えるのもなんだか億劫になりますよね。'
        '少しでも涼しげに、ということで、白とか爽やかな色を身に纏いたいところ。'
        'なのですが、あえて「真夏のブラック」をテーマにしたコレクションが'
        '〈ブラブラブラ（BbbLl）〉から発売 […]</p>\n'
        '<p>The post <a href="https://www.houyhnhnm.jp/news/1162887/">'
        '真夏のブラック。ブラブラブラから軽やかなコットンウェアの新作コレクションが。'
        '夏に黒もオツなものです。</a> first appeared on '
        '<a href="https://www.houyhnhnm.jp">HOUYHNHNM（フイナム）</a>.</p>'
    )
    result = excerpt(raw)
    assert "The post" not in result
    assert "first appeared on" not in result
    assert "HOUYHNHNM" not in result
    assert result.startswith("こう暑いと服のことを考えるのもなんだか億劫になりますよね。")
    assert result.endswith("から発売 […]")


def test_excerpt_normal_summary_without_wordpress_boilerplate_is_unaffected():
    # Fashionsnap/Hypebeast等、WordPressの定型フッターを持たない通常の抜粋文は
    # 一切変化しない（"post"や"first"を含む正当な本文を誤って削らないことの確認）。
    raw = "<p>新作スニーカーが発売された。This is the first drop of the post-summer collection.</p>"
    result = excerpt(raw)
    assert result == "新作スニーカーが発売された。This is the first drop of the post-summer collection."


def test_load_items_returns_empty_list_when_missing(tmp_path):
    assert load_items(tmp_path / "items.json") == []


def test_load_items_reads_json(tmp_path):
    path = tmp_path / "items.json"
    path.write_text('[{"title": "a", "url": "https://example.com/a"}]', encoding="utf-8")
    assert load_items(path) == [{"title": "a", "url": "https://example.com/a"}]


def test_load_trend_posts_parses_frontmatter_and_sorts_desc(tmp_path):
    (tmp_path / "old.md").write_text(
        "---\ntitle: 古い記事\ndate: 2026-08-01\n---\n本文A\n", encoding="utf-8"
    )
    (tmp_path / "new.md").write_text(
        "---\ntitle: 新しい記事\ndate: 2026-08-15\n---\n本文B\n", encoding="utf-8"
    )
    posts = load_trend_posts(tmp_path)
    assert [p["title"] for p in posts] == ["新しい記事", "古い記事"]
    assert posts[0]["slug"] == "new"
    assert "本文B" in posts[0]["html"]
    assert posts[0]["date"] == "2026-08-15"
    assert posts[1]["date"] == "2026-08-01"


def test_load_trend_posts_empty_dir_returns_empty_list(tmp_path):
    assert load_trend_posts(tmp_path / "does-not-exist") == []


def test_load_trend_posts_builds_toc_from_h2_headings(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 見出しのある記事\ndate: 2026-08-21\n---\n"
        "## 色のトレンド\n本文A\n\n## 素材のトレンド\n本文B\n",
        encoding="utf-8",
    )
    posts = load_trend_posts(tmp_path)
    assert 'href="#' in posts[0]["toc"]
    assert "色のトレンド" in posts[0]["toc"]
    assert "素材のトレンド" in posts[0]["toc"]
    assert 'id="' in posts[0]["html"]


def test_load_trend_posts_toc_is_none_when_no_headings(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 見出しのない記事\ndate: 2026-08-21\n---\n本文のみで見出しは無い。\n",
        encoding="utf-8",
    )
    posts = load_trend_posts(tmp_path)
    assert posts[0]["toc"] is None


def test_load_trend_posts_lead_html_excludes_text_after_first_heading(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 見出しのある記事\ndate: 2026-08-21\n---\n"
        "導入の段落です。\n\n## 最初の見出し\n見出し以降の本文A\n\n## 次の見出し\n見出し以降の本文B\n",
        encoding="utf-8",
    )
    posts = load_trend_posts(tmp_path)
    assert "導入の段落です" in posts[0]["lead_html"]
    assert "最初の見出し" not in posts[0]["lead_html"]
    assert "見出し以降の本文A" not in posts[0]["lead_html"]


def test_load_trend_posts_lead_html_equals_full_body_when_no_headings(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 見出しのない記事\ndate: 2026-08-21\n---\n本文のみで見出しは無い。\n",
        encoding="utf-8",
    )
    posts = load_trend_posts(tmp_path)
    assert "本文のみで見出しは無い。" in posts[0]["lead_html"]


def test_load_trend_posts_resolves_images_from_frontmatter_urls(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 画像付き記事\ndate: 2026-08-21\n"
        "images:\n  - https://example.com/a\n  - https://example.com/b\n"
        "---\n本文\n",
        encoding="utf-8",
    )
    items = [
        {"url": "https://example.com/a", "image_url": "https://example.com/a.jpg", "source": "Hypebeast", "title": "記事A"},
        {"url": "https://example.com/b", "image_url": "https://example.com/b.jpg", "source": "Fashionsnap", "title": "記事B"},
    ]
    posts = load_trend_posts(tmp_path, items)
    assert [img["image_url"] for img in posts[0]["images"]] == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    assert posts[0]["images"][0]["source"] == "Hypebeast"
    assert posts[0]["images"][0]["url"] == "https://example.com/a"
    assert posts[0]["images"][0]["title"] == "記事A"


def test_load_trend_posts_skips_urls_not_found_or_without_image(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 画像付き記事\ndate: 2026-08-21\n"
        "images:\n  - https://example.com/missing\n  - https://example.com/no-image\n"
        "---\n本文\n",
        encoding="utf-8",
    )
    items = [
        {"url": "https://example.com/no-image", "image_url": None, "source": "Hypebeast", "title": "画像なし記事"},
    ]
    posts = load_trend_posts(tmp_path, items)
    assert posts[0]["images"] == []


def test_load_trend_posts_images_empty_when_no_images_field(tmp_path):
    (tmp_path / "post.md").write_text(
        "---\ntitle: 画像指定なし記事\ndate: 2026-08-21\n---\n本文\n",
        encoding="utf-8",
    )
    posts = load_trend_posts(tmp_path)
    assert posts[0]["images"] == []


def test_build_writes_expected_files(tmp_path):
    items = [{
        "title": "新作スニーカー登場",
        "url": "https://example.com/a",
        "source": "Hypebeast",
        "published": "2026-08-20T00:00:00+00:00",
        "summary": "新作の紹介文",
        "image_url": None,
    }]
    trends = [{"title": "今週のトレンド", "date": "2026-08-20", "slug": "week-1", "html": "<p>本文</p>"}]

    build(tmp_path, items, trends)

    assert (tmp_path / "index.html").exists()
    assert "新作スニーカー登場" in (tmp_path / "index.html").read_text(encoding="utf-8")

    feed_html = (tmp_path / "feed.html").read_text(encoding="utf-8")
    assert "新作スニーカー登場" in feed_html
    assert "Hypebeast" in feed_html

    trends_index = (tmp_path / "trends" / "index.html").read_text(encoding="utf-8")
    assert "今週のトレンド" in trends_index

    detail = (tmp_path / "trends" / "week-1.html").read_text(encoding="utf-8")
    assert "本文" in detail


def test_build_caps_feed_html_at_200_items(tmp_path):
    items = [
        {
            "title": f"記事{i}",
            "url": f"https://example.com/{i}",
            "source": "Hypebeast",
            "published": f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00",
            "summary": "紹介文",
            "image_url": None,
        }
        for i in range(250)
    ]

    build(tmp_path, items, [])

    feed_html = (tmp_path / "feed.html").read_text(encoding="utf-8")
    assert feed_html.count('class="feed-item"') == 200
    assert "記事0" in feed_html
    assert "記事199" in feed_html
    assert "記事200" not in feed_html
    assert "記事249" not in feed_html


def test_build_removes_stale_trend_detail_pages(tmp_path):
    trends_dir = tmp_path / "trends"
    trends_dir.mkdir(parents=True)
    # リネーム・削除済みの古い生成物を模擬する
    (trends_dir / "old-slug.html").write_text("<p>古い記事</p>", encoding="utf-8")
    (trends_dir / "index.html").write_text("stale index", encoding="utf-8")

    trends = [{"title": "現行記事", "date": "2026-08-20", "slug": "current-slug", "html": "<p>本文</p>"}]

    build(tmp_path, [], trends)

    assert not (trends_dir / "old-slug.html").exists()
    assert (trends_dir / "current-slug.html").exists()
    assert (trends_dir / "index.html").exists()


def test_build_creates_nojekyll_file(tmp_path):
    build(tmp_path, [], [])
    nojekyll = tmp_path / ".nojekyll"
    assert nojekyll.exists()
    assert nojekyll.read_text(encoding="utf-8") == ""


def test_build_copies_static_assets(tmp_path):
    build(tmp_path, [], [])
    style_css = tmp_path / "static" / "style.css"
    assert style_css.exists()
    assert len(style_css.read_text(encoding="utf-8")) > 0


def test_pick_hero_selects_first_item_with_image_when_first_item_has_none():
    # Highsnobietyのように画像を一切持たないソースの記事が最新であっても、
    # 画像のある最初のアイテムがヒーローとして選ばれることを確認する。
    items = [
        {"title": "画像なし記事", "url": "https://example.com/a", "image_url": None},
        {"title": "画像あり記事", "url": "https://example.com/b", "image_url": "https://example.com/b.jpg"},
        {"title": "その次の記事", "url": "https://example.com/c", "image_url": None},
    ]
    hero, grid = _pick_hero(items)
    assert hero["title"] == "画像あり記事"
    assert [item["title"] for item in grid] == ["画像なし記事", "その次の記事"]


def test_pick_hero_grid_does_not_duplicate_hero_item():
    items = [
        {"title": "A", "url": "https://example.com/a", "image_url": None},
        {"title": "B", "url": "https://example.com/b", "image_url": "https://example.com/b.jpg"},
    ]
    hero, grid = _pick_hero(items)
    assert hero["title"] == "B"
    assert len(grid) == 1
    assert grid[0]["title"] == "A"


def test_pick_hero_falls_back_to_first_item_when_no_item_has_image():
    items = [
        {"title": "A", "url": "https://example.com/a", "image_url": None},
        {"title": "B", "url": "https://example.com/b", "image_url": None},
    ]
    hero, grid = _pick_hero(items)
    assert hero["title"] == "A"
    assert [item["title"] for item in grid] == ["B"]


def test_pick_hero_empty_list_returns_none_hero_and_empty_grid():
    hero, grid = _pick_hero([])
    assert hero is None
    assert grid == []


def test_build_index_hero_prefers_item_with_image_over_more_recent_imageless_item(tmp_path):
    # 公開日時降順で最新（先頭）のHighsnobiety記事に画像が無く、2番目の記事に
    # 画像がある場合、ヒーローには画像のある2番目の記事が使われ、実際に
    # <img>タグが出力されることを確認する（画像なしの黒い枠がヒーローになる不具合の回帰確認）。
    items = [
        {
            "title": "Highsnobietyの画像なし記事",
            "url": "https://example.com/no-image",
            "source": "Highsnobiety",
            "published": "2026-08-20T00:00:00+00:00",
            "summary": "画像の無い記事",
            "image_url": None,
        },
        {
            "title": "画像ありの記事",
            "url": "https://example.com/with-image",
            "source": "Fashionsnap",
            "published": "2026-08-19T00:00:00+00:00",
            "summary": "画像のある記事",
            "image_url": "https://example.com/photo.jpg",
        },
    ]
    build(tmp_path, items, [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'src="https://example.com/photo.jpg"' in index_html
    # 画像ありの記事がヒーロー（<h1>）になり、画像なしの記事はグリッドに1回だけ
    # 出現する（どちらも重複表示されない）。ヒーローのタイトルはimgのalt属性と
    # <h1>の両方に出るのが仕様なので、alt分の重複はここでは数えない。
    assert "<h1>画像ありの記事</h1>" in index_html
    assert index_html.count("Highsnobietyの画像なし記事") == 1
    assert index_html.count("<h1>") == 1


def test_group_by_source_groups_items_preserving_first_appearance_order():
    items = [
        {"title": "A", "source": "Hypebeast"},
        {"title": "B", "source": "Fashionsnap"},
        {"title": "C", "source": "Hypebeast"},
        {"title": "D", "source": "Fashionsnap"},
    ]
    groups = _group_by_source(items)
    assert [g["source"] for g in groups] == ["Hypebeast", "Fashionsnap"]
    assert [item["title"] for item in groups[0]["entries"]] == ["A", "C"]
    assert [item["title"] for item in groups[1]["entries"]] == ["B", "D"]


def test_group_by_source_empty_list_returns_empty_list():
    assert _group_by_source([]) == []


def test_build_feed_html_groups_items_by_source_with_toc(tmp_path):
    items = [
        {
            "title": "記事A",
            "url": "https://example.com/a",
            "source": "Hypebeast",
            "published": "2026-08-20T00:00:00+00:00",
            "summary": "紹介文A",
            "image_url": None,
        },
        {
            "title": "記事B",
            "url": "https://example.com/b",
            "source": "Fashionsnap",
            "published": "2026-08-19T00:00:00+00:00",
            "summary": "紹介文B",
            "image_url": None,
        },
    ]
    build(tmp_path, items, [])
    feed_html = (tmp_path / "feed.html").read_text(encoding="utf-8")
    assert 'href="#source-Hypebeast"' in feed_html
    assert 'href="#source-Fashionsnap"' in feed_html
    assert 'id="source-Hypebeast"' in feed_html
    assert 'id="source-Fashionsnap"' in feed_html
    assert feed_html.index("記事A") < feed_html.index("記事B")


def test_build_index_trend_section_appears_before_new_arrivals_section(tmp_path):
    items = [{
        "title": "新作スニーカー登場",
        "url": "https://example.com/a",
        "source": "Hypebeast",
        "published": "2026-08-20T00:00:00+00:00",
        "summary": "新作の紹介文",
        "image_url": None,
    }]
    trends = [{"title": "今週のトレンド", "date": "2026-08-20", "slug": "week-1", "html": "<p>本文</p>"}]

    build(tmp_path, items, trends)
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert index_html.index('class="trend-feature"') < index_html.index('class="card-grid"')


def test_build_index_latest_trend_rendered_as_feature_card(tmp_path):
    trends = [
        {"title": "今週のトレンド", "date": "2026-08-20", "slug": "week-1", "html": "<p>本文リード</p>", "lead_html": "<p>本文リード</p>"},
        {"title": "先週のトレンド", "date": "2026-08-13", "slug": "week-0", "html": "<p>先週の本文</p>", "lead_html": "<p>先週の本文</p>"},
    ]
    build(tmp_path, [], trends)
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'class="trend-feature"' in index_html
    assert "今週のトレンド" in index_html
    assert "本文リード" in index_html
    # 2件目は引き続きtrend-cardとして小さく表示される
    assert 'class="trend-card"' in index_html
    assert "先週のトレンド" in index_html


def test_build_index_new_arrival_card_shows_source_badge(tmp_path):
    items = [
        {
            "title": "ヒーロー用記事",
            "url": "https://example.com/hero",
            "source": "Fashionsnap",
            "published": "2026-08-20T00:00:00+00:00",
            "summary": "ヒーローの紹介文",
            "image_url": "https://example.com/hero.jpg",
        },
        {
            "title": "新作スニーカー登場",
            "url": "https://example.com/a",
            "source": "Hypebeast",
            "published": "2026-08-19T00:00:00+00:00",
            "summary": "新作の紹介文",
            "image_url": None,
        },
    ]
    build(tmp_path, items, [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'class="source-badge"' in index_html
    assert "Hypebeast" in index_html


def test_build_index_grid_shows_up_to_15_items(tmp_path):
    items = [
        {
            "title": f"記事{i}",
            "url": f"https://example.com/{i}",
            "source": "Fashionsnap",
            "published": f"2026-08-{(i % 28) + 1:02d}T00:00:00+00:00",
            "summary": "紹介文",
            "image_url": "https://example.com/photo.jpg" if i == 0 else None,
        }
        for i in range(20)
    ]
    build(tmp_path, items, [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # 記事0はヒーローに使われるため、グリッドには記事1〜15の15件が表示される
    assert index_html.count('class="card"') == 15
    assert "記事1" in index_html
    assert "記事15" in index_html
    assert "記事16" not in index_html


def test_prioritize_japanese_selects_target_ratio_of_japanese_sources():
    en_items = [
        {"title": f"en{i}", "url": f"u-en-{i}", "source": "Highsnobiety", "published": f"2026-08-{20 - i:02d}"}
        for i in range(10)
    ]
    jp_items = [
        {"title": f"jp{i}", "url": f"u-jp-{i}", "source": "Fashionsnap", "published": f"2026-08-{15 - i:02d}"}
        for i in range(10)
    ]
    items = sorted(en_items + jp_items, key=lambda i: i["published"], reverse=True)
    result = _prioritize_japanese(items, 16)
    assert len(result) == 16
    jp_count = sum(1 for i in result if i["source"] == "Fashionsnap")
    assert jp_count == 10  # 目標11件だが国内メディアの実在数(10件)が上限になる


def test_prioritize_japanese_backfills_with_japanese_when_other_sources_scarce():
    en_items = [
        {"title": f"en{i}", "url": f"u-en-{i}", "source": "Highsnobiety", "published": f"2026-08-{20 - i:02d}"}
        for i in range(2)
    ]
    jp_items = [
        {"title": f"jp{i}", "url": f"u-jp-{i}", "source": "Fashionsnap", "published": f"2026-08-{15 - i:02d}"}
        for i in range(20)
    ]
    items = sorted(en_items + jp_items, key=lambda i: i["published"], reverse=True)
    result = _prioritize_japanese(items, 16)
    assert len(result) == 16
    en_count = sum(1 for i in result if i["source"] == "Highsnobiety")
    jp_count = sum(1 for i in result if i["source"] == "Fashionsnap")
    assert en_count == 2  # 海外メディアは実在する2件を全て採用
    assert jp_count == 14  # 不足分は国内メディアで埋め戻す


def test_build_index_grid_prioritizes_japanese_sources(tmp_path):
    en_items = [
        {
            "title": f"海外記事{i}",
            "url": f"https://example.com/en/{i}",
            "source": "Highsnobiety",
            "published": f"2026-08-{20 - i:02d}T00:00:00+00:00",
            "summary": "",
            "image_url": None,
        }
        for i in range(10)
    ]
    jp_items = [
        {
            "title": f"国内記事{i}",
            "url": f"https://example.com/jp/{i}",
            "source": "Fashionsnap",
            "published": f"2026-08-{15 - i:02d}T00:00:00+00:00",
            "summary": "",
            "image_url": None,
        }
        for i in range(10)
    ]
    items = sorted(en_items + jp_items, key=lambda i: i["published"], reverse=True)
    build(tmp_path, items, [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    jp_count = sum(1 for i in range(10) if f"国内記事{i}" in index_html)
    en_count = sum(1 for i in range(10) if f"海外記事{i}" in index_html)
    # 海外メディア（Highsnobiety）の方が新しい記事が多くても、
    # トップページの表示は国内メディアが優勢になる
    assert jp_count > en_count
    assert jp_count >= 9


def test_build_index_trends_shows_up_to_5_posts(tmp_path):
    trends = [
        {"title": f"トレンド記事{i}", "date": f"2026-08-{20 - i:02d}", "slug": f"post-{i}", "html": "<p>本文</p>", "lead_html": "<p>本文</p>"}
        for i in range(7)
    ]
    build(tmp_path, [], trends)
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # トレンド記事0はフィーチャーカード、1〜4がサブカード（計5件）
    assert "トレンド記事0" in index_html
    assert "トレンド記事4" in index_html
    assert "トレンド記事5" not in index_html


def test_build_index_empty_items_renders_without_hero_and_without_crashing(tmp_path):
    build(tmp_path, [], [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert (tmp_path / "index.html").exists()
    assert 'class="hero"' not in index_html


def test_build_trends_pages_link_assets_one_level_up(tmp_path):
    trends = [{"title": "現行記事", "date": "2026-08-20", "slug": "current-slug", "html": "<p>本文</p>"}]
    build(tmp_path, [], trends)

    trends_index = (tmp_path / "trends" / "index.html").read_text(encoding="utf-8")
    assert 'href="../static/style.css"' in trends_index

    detail = (tmp_path / "trends" / "current-slug.html").read_text(encoding="utf-8")
    assert 'href="../static/style.css"' in detail


def test_build_search_index_includes_items_and_trends():
    items = [
        {
            "title": "アディダス新作サンバ",
            "url": "https://example.com/samba",
            "source": "Highsnobiety",
            "published": "2026-08-22T07:10:03+00:00",
            "summary": "<p>新作のサンバが登場しました。</p>",
            "image_url": "https://example.com/samba.jpg",
        },
    ]
    trends = [
        {
            "title": "定番に一手だけ加えた一週間",
            "date": "2026-08-21",
            "slug": "standard-revisited",
            "html": "<h2>見出し</h2><p>本文のテキストです。</p>",
            "images": [{"image_url": "https://example.com/trend.jpg", "source": "Fashionsnap", "url": "https://example.com/a", "title": "紹介アイテム"}],
        },
    ]
    index = _build_search_index(items, trends)
    assert len(index) == 2

    item_entry = next(e for e in index if e["type"] == "item")
    assert item_entry["title"] == "アディダス新作サンバ"
    assert "新作のサンバが登場しました。" in item_entry["excerpt"]
    assert item_entry["url"] == "https://example.com/samba"
    assert item_entry["source"] == "Highsnobiety"
    assert item_entry["date"] == "2026-08-22"
    assert item_entry["image_url"] == "https://example.com/samba.jpg"

    trend_entry = next(e for e in index if e["type"] == "trend")
    assert trend_entry["title"] == "定番に一手だけ加えた一週間"
    assert "本文のテキストです。" in trend_entry["excerpt"]
    assert "<h2>" not in trend_entry["excerpt"]
    assert trend_entry["url"] == "trends/standard-revisited.html"
    assert trend_entry["source"] == "トレンド分析"
    assert trend_entry["image_url"] == "https://example.com/trend.jpg"


def test_build_search_index_trend_without_images_has_none_image_url():
    trends = [{"title": "画像なし記事", "date": "2026-08-20", "slug": "no-image-post", "html": "<p>本文</p>", "images": []}]
    index = _build_search_index([], trends)
    assert index[0]["image_url"] is None


def test_build_writes_search_page_and_index_json(tmp_path):
    items = [
        {
            "title": "記事タイトル",
            "url": "https://example.com/1",
            "source": "Fashionsnap",
            "published": "2026-08-22T00:00:00+00:00",
            "summary": "紹介文です",
            "image_url": None,
        },
    ]
    trends = [{"title": "トレンド記事", "date": "2026-08-21", "slug": "post-a", "html": "<p>内容</p>", "images": []}]
    build(tmp_path, items, trends)

    assert (tmp_path / "search.html").exists()
    search_html = (tmp_path / "search.html").read_text(encoding="utf-8")
    assert "search-input" in search_html
    assert 'static/search.js' in search_html

    index_path = tmp_path / "search-index.json"
    assert index_path.exists()
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(data) == 2
    titles = {e["title"] for e in data}
    assert titles == {"記事タイトル", "トレンド記事"}


def test_base_nav_includes_search_link(tmp_path):
    build(tmp_path, [], [])
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="search.html">検索</a>' in index_html
