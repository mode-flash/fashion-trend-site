import json
from unittest.mock import MagicMock, patch

from scripts.fetch_feeds import (
    _backfill_og_images,
    _is_excluded,
    fetch_og_image,
    fetch_source,
    parse_feed,
    load_existing_items,
    merge_items,
    save_items,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事1</title>
<link>https://example.com/item1</link>
<description>サンプルの説明文です</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""


def test_parse_feed_extracts_fields():
    items = parse_feed(SAMPLE_RSS, "SampleMedia")
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "サンプル記事1"
    assert item["url"] == "https://example.com/item1"
    assert item["source"] == "SampleMedia"
    assert item["summary"] == "サンプルの説明文です"
    assert item["published"] == "2026-08-20T03:00:00+00:00"
    assert item["image_url"] is None


def test_parse_feed_empty_feed_returns_empty_list():
    empty_rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>"""
    assert parse_feed(empty_rss, "SampleMedia") == []


def test_parse_feed_rejects_javascript_url_scheme():
    malicious_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Malicious Feed</title>
<item>
<title>危険なリンク</title>
<link>javascript:alert(1)</link>
<description>説明文</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(malicious_rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["url"] == ""


def test_parse_feed_rejects_javascript_image_url_scheme():
    malicious_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>Malicious Feed</title>
<item>
<title>危険な画像リンク</title>
<link>https://example.com/a</link>
<description>説明文</description>
<media:thumbnail url="javascript:alert(1)" />
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(malicious_rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["image_url"] is None


def test_parse_feed_extracts_image_from_description_img_tag():
    # Fashionsnap/Hypebeast両方の実データはmedia:thumbnail/media:content拡張要素を使わず、
    # descriptionの先頭に<img src="...">を埋め込み、その後ろに本文が続く形式で画像を提供する。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事</title>
<link>https://example.com/item-with-image</link>
<description>&lt;img src="https://example.com/photo.jpg" /&gt; お笑いトリオの記事本文がここに続きます。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert len(items) == 1
    assert items[0]["image_url"] == "https://example.com/photo.jpg"


def test_parse_feed_unescapes_query_string_ampersands_in_description_image():
    # Hypebeastの実データはクエリ文字列付きの画像URLを持ち、XML上は`&amp;amp;`と
    # 二重エスケープされているため、feedparserが1段階デコードした後のsummaryには
    # `&amp;`が残る。html.unescape()でさらに1段階デコードして実URLに戻す必要がある。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>サンプル記事2</title>
<link>https://example.com/item-with-query-image</link>
<description>&lt;img src="https://example.com/photo.jpg?w=800&amp;amp;q=90" /&gt; 本文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] == "https://example.com/photo.jpg?w=800&q=90"


def test_parse_feed_rejects_unsafe_scheme_in_description_image():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>危険な画像リンク（description内）</title>
<link>https://example.com/item-unsafe-image</link>
<description>&lt;img src="javascript:alert(1)" /&gt; 本文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] is None


def test_parse_feed_still_prefers_media_thumbnail_when_present():
    # media:thumbnail/media:content経由の既存の抽出パスが、description内img
    # フォールバックの追加によって壊れていないことを確認する回帰テスト。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>Sample Feed</title>
<item>
<title>media:thumbnail付き記事</title>
<link>https://example.com/item-media-thumbnail</link>
<description>&lt;img src="https://example.com/should-not-be-used.jpg" /&gt; 本文です。</description>
<media:thumbnail url="https://example.com/thumbnail.jpg" />
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] == "https://example.com/thumbnail.jpg"


def test_parse_feed_extracts_image_from_content_encoded_when_summary_has_none():
    # HOUYHNHNMの実データはFashionsnap/Hypebeastと異なり、画像はdescription(summary)には
    # 一切含まれず、content:encoded（entry.content[0].value）にのみ<img>タグとして
    # 埋め込まれている（実際のフィードをfeedparserで確認済み）。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>Sample Feed</title>
<item>
<title>真夏のブラック。ブラブラブラから軽やかなコットンウェアの新作コレクションが。</title>
<link>https://example.com/houyhnhnm-item</link>
<description>&lt;p&gt;こう暑いと服のことを考えるのもなんだか億劫になりますよね。&lt;/p&gt;
&lt;p&gt;The post &lt;a href="https://example.com/houyhnhnm-item"&gt;記事タイトル&lt;/a&gt; first appeared on &lt;a href="https://example.com"&gt;HOUYHNHNM（フイナム）&lt;/a&gt;.&lt;/p&gt;</description>
<content:encoded><![CDATA[<div class="tate-img">
<img alt="" class="alignnone size-full wp-image-1162896 image" height="1000" src="https://www.houyhnhnm.jp/wp-content/uploads/2026/08/BBB_CRSPBLK_01-1.jpg" width="800" />
</div>]]></content:encoded>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "HOUYHNHNM")
    assert len(items) == 1
    assert items[0]["image_url"] == "https://www.houyhnhnm.jp/wp-content/uploads/2026/08/BBB_CRSPBLK_01-1.jpg"


def test_parse_feed_prefers_summary_image_over_content_encoded_when_both_present():
    # summary内にimgがあればcontent:encodedより優先する（Fashionsnap/Hypebeastの既存挙動を
    # 変えないための優先順位）。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>Sample Feed</title>
<item>
<title>両方に画像がある記事</title>
<link>https://example.com/item-both-images</link>
<description>&lt;img src="https://example.com/summary-photo.jpg" /&gt; 本文の抜粋です。</description>
<content:encoded><![CDATA[<img src="https://example.com/content-photo.jpg" />]]></content:encoded>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] == "https://example.com/summary-photo.jpg"


def test_parse_feed_no_image_in_summary_or_content_encoded_returns_none():
    # summary・content:encodedのいずれにも画像が無い場合はNoneを返し、クラッシュしない
    # （content:encoded自体が存在するフィードでの回帰確認）。
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>Sample Feed</title>
<item>
<title>画像の無い記事（content:encodedあり）</title>
<link>https://example.com/item-no-image-with-content</link>
<description>画像を含まない普通の説明文です。</description>
<content:encoded><![CDATA[<p>本文にも画像はありません。</p>]]></content:encoded>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] is None


def test_parse_feed_no_image_anywhere_returns_none_without_crashing():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Sample Feed</title>
<item>
<title>画像の無い記事</title>
<link>https://example.com/item-no-image</link>
<description>画像を含まない普通の説明文です。</description>
<pubDate>Thu, 20 Aug 2026 03:00:00 GMT</pubDate>
</item>
</channel>
</rss>"""
    items = parse_feed(rss, "SampleMedia")
    assert items[0]["image_url"] is None


def test_merge_items_removes_duplicates_by_url():
    existing = [{"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [
        {"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"},
        {"url": "https://example.com/b", "published": "2026-08-20T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    assert [item["url"] for item in merged] == [
        "https://example.com/b",
        "https://example.com/a",
    ]


def test_merge_items_ignores_missing_url_without_raising():
    existing = [{"url": "https://example.com/a", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [
        {"title": "urlが無いアイテム", "published": "2026-08-20T00:00:00+00:00"},
        {"url": "https://example.com/b", "published": "2026-08-18T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    # urlの無いアイテムも消えずに残る（重複判定の対象外として扱われる）
    assert len(merged) == 3
    urls = [item.get("url") for item in merged]
    assert "https://example.com/a" in urls
    assert "https://example.com/b" in urls


def test_merge_items_sorts_missing_published_last():
    existing = []
    new_items = [
        {"url": "https://example.com/no-date"},  # publishedキーが無い
        {"url": "https://example.com/a", "published": "2026-08-20T00:00:00+00:00"},
    ]
    merged = merge_items(existing, new_items)
    assert [item["url"] for item in merged] == [
        "https://example.com/a",
        "https://example.com/no-date",
    ]


def test_merge_items_existing_missing_url_does_not_raise():
    existing = [{"title": "既存だがurlが無い", "published": "2026-08-19T00:00:00+00:00"}]
    new_items = [{"url": "https://example.com/b", "published": "2026-08-20T00:00:00+00:00"}]
    merged = merge_items(existing, new_items)
    assert len(merged) == 2


def _mock_response(html_bytes: bytes) -> MagicMock:
    mock_response = MagicMock()
    mock_response.read.return_value = html_bytes
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    return mock_response


def test_fetch_og_image_extracts_og_image_content():
    html = b'<html><head><meta property="og:image" content="https://example.com/photo.jpg"></head></html>'
    with patch("scripts.fetch_feeds.urllib.request.urlopen", return_value=_mock_response(html)):
        assert fetch_og_image("https://example.com/article") == "https://example.com/photo.jpg"


def test_fetch_og_image_supports_content_before_property_attribute_order():
    # サイトによってはmetaタグの属性順がcontent→propertyの場合もある
    html = b'<meta content="https://example.com/photo2.jpg" property="og:image">'
    with patch("scripts.fetch_feeds.urllib.request.urlopen", return_value=_mock_response(html)):
        assert fetch_og_image("https://example.com/article") == "https://example.com/photo2.jpg"


def test_fetch_og_image_returns_none_when_tag_missing():
    html = b"<html><head><title>no og image here</title></head></html>"
    with patch("scripts.fetch_feeds.urllib.request.urlopen", return_value=_mock_response(html)):
        assert fetch_og_image("https://example.com/article") is None


def test_fetch_og_image_returns_none_on_network_error():
    with patch("scripts.fetch_feeds.urllib.request.urlopen", side_effect=OSError("timeout")):
        assert fetch_og_image("https://example.com/article") is None


def test_fetch_og_image_rejects_unsafe_scheme():
    html = b'<meta property="og:image" content="javascript:alert(1)">'
    with patch("scripts.fetch_feeds.urllib.request.urlopen", return_value=_mock_response(html)):
        assert fetch_og_image("https://example.com/article") is None


def test_backfill_og_images_skips_existing_urls():
    new_items = [
        {"url": "https://example.com/existing", "image_url": None},
        {"url": "https://example.com/new", "image_url": None},
    ]
    existing_urls = {"https://example.com/existing"}
    with patch("scripts.fetch_feeds.fetch_og_image", return_value="https://example.com/photo.jpg") as mock_fetch:
        _backfill_og_images(new_items, existing_urls)
    mock_fetch.assert_called_once_with("https://example.com/new")
    assert new_items[0]["image_url"] is None
    assert new_items[1]["image_url"] == "https://example.com/photo.jpg"


def test_backfill_og_images_skips_items_that_already_have_image():
    new_items = [{"url": "https://example.com/new", "image_url": "https://example.com/existing.jpg"}]
    with patch("scripts.fetch_feeds.fetch_og_image") as mock_fetch:
        _backfill_og_images(new_items, set())
    mock_fetch.assert_not_called()


def test_load_existing_items_returns_empty_list_when_missing(tmp_path):
    missing_path = tmp_path / "items.json"
    assert load_existing_items(missing_path) == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "items.json"
    items = [{"url": "https://example.com/a", "title": "テスト記事", "published": "2026-08-20T00:00:00+00:00"}]
    save_items(items, path)
    loaded = load_existing_items(path)
    assert loaded == items
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw == items


def test_fetch_source_returns_empty_list_on_parse_error():
    source = {"name": "BrokenMedia", "url": "https://example.com/broken.xml"}
    with patch("scripts.fetch_feeds.parse_feed", side_effect=ValueError("boom")):
        result = fetch_source(source)
    assert result == []


def test_fetch_source_returns_items_on_success():
    source = {"name": "SampleMedia", "url": "https://example.com/feed.xml"}
    fake_items = [{"url": "https://example.com/a", "title": "a", "published": "2026-08-20T00:00:00+00:00"}]
    with patch("scripts.fetch_feeds.parse_feed", return_value=fake_items):
        result = fetch_source(source)
    assert result == fake_items


def test_is_excluded_true_for_criminal_news_keyword_in_title():
    # 過去に実名入り刑事事件報道記事が混入した際と同種のパターン（タイトルに事件関連語）
    item = {"title": "〇〇容疑者を書類送検、△△の疑い", "summary": ""}
    assert _is_excluded(item) is True


def test_is_excluded_false_for_normal_fashion_item():
    item = {
        "title": "Marmot 2026AW コレクション",
        "summary": "「マーモット（Marmot）」が発表した2026年秋冬コレクション。",
    }
    assert _is_excluded(item) is False


def test_is_excluded_true_for_education_event_announcement():
    # QAレビューで実際に混入が確認された非ファッション記事(教育イベント告知)
    item = {
        "title": "「創造性とAIは学修成果を高めるのか」　アドビが教育イベントを筑波大学で開催",
        "summary": "",
    }
    assert _is_excluded(item) is True


def test_is_excluded_true_for_corporate_b2b_service_announcement():
    # QAレビューで実際に混入が確認された非ファッション記事(法人向けサービス告知)
    item = {
        "title": "良品計画がオフィスに必要な備品をセット販売する法人向けサービスをスタート",
        "summary": "",
    }
    assert _is_excluded(item) is True


def test_is_excluded_true_for_anime_announcement_unrelated_to_fashion():
    # QAレビューで実際に混入が確認された非ファッション記事(アニメ番組の発表)
    item = {
        "title": "TOHO Animation Sets October Debut for 'The Apothecary Diaries' Season 3",
        "summary": "",
    }
    assert _is_excluded(item) is True


def test_is_excluded_false_for_legitimate_fashion_anime_collaboration():
    # 「アニメ」という単語自体はブロックリストに含めていない。
    # 本番データに実在する正当なファッション×アニメコラボ記事が誤除外されないことを確認する。
    item = {
        "title": "コンバース トウキョウがまどマギと初コラボ　アートTシャツやアクセサリーなど発売",
        "summary": "「コンバース トウキョウ（CONVERSE TOKYO）」が、アニメ「魔法少女まどか☆マギカ」との"
        "初のコラボレーションアイテムを発売する。",
    }
    assert _is_excluded(item) is False


def test_is_excluded_true_for_cosmetics_and_beauty_items():
    # オーナー要望「服・スニーカー中心」への対応でコスメ・スキンケア・メイクアップ関連を
    # 除外対象に追加。実データ（data/items.json）で実際に混入していたタイトルを使用する。
    titles = [
        "弾むようなハリのある肌に　SUQQU「アクフォンス」から新スキンケアが登場",
        "【2026年クリスマスコフレ】キールズ：“ホテルライクなご褒美時間” を叶える限定スキンケア",
        "【2026年秋コスメ】シャネル：ココ マドモアゼルの精神を宿すメイクアップなどが登場",
        "無印良品「着るスキンケア」が一時販売停止　外箱に誤字が発覚",
        "【2026年秋コスメ】NARS：重ねてニュアンスを楽しむアイシャドウやリップライナーが登場",
        "「アンレーベル ラボ」集中美容液ヘアケアがリニューアル　“サロン級”補修成分を新配合",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title
    # 「バイユア」の実例はタイトルに直接キーワードを含まず、summary側
    # （「毛穴管理に着目したスキンケアライン」）でのみ「スキンケア」を含む実データのため、
    # summaryも合わせて判定されることを確認する。
    byur_item = {
        "title": "「バイユア」から毛穴汚れを吸着して落とす新ライン誕生",
        "summary": "「バイユア（ByUR）」が、毛穴管理に着目したスキンケアライン「クリーンリセット ブラックライン」を"
        "10月29日に発売する。",
    }
    assert _is_excluded(byur_item) is True


def test_is_excluded_true_for_fragrance_and_body_care_items():
    titles = [
        "より贅沢な濃度に　「ディオール」がジャスミンの香りを再解釈したフレグランス発売",
        "「ジバンシイ」が新フレグランスを伊勢丹新宿店で限定発売　ウッディシトラスの調香",
        "ディプティックから古代ギリシャの入浴文化に着想したボディケアコレクションが登場",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title


def test_is_excluded_true_for_finance_and_corporate_ma_news():
    # クレジットカード提携・M&A・株式取得など、ファッション商品と無関係な金融・法人ニュース
    item_card = {"title": "アメックスとANAの提携カードがリニューアル　旅行ニーズの変化に対応", "summary": ""}
    item_ma = {"title": "旧マックハウスが「クラネ」運営会社の株式取得　持株比率は19％", "summary": ""}
    assert _is_excluded(item_card) is True
    assert _is_excluded(item_ma) is True


def test_is_excluded_true_for_consumer_trouble_and_lifestyle_column_items():
    titles = [
        "ファッションサブスク「アールカワイイ」で解約トラブル多数　国民生活センターが注意喚起",
        "東京・高輪発のウェルネスコミュニティ「TOKYO BLANK CLUB」が始動",
        "「本を売る」だけではない書店ビジネス　ファッション業界にも通じるリアル店舗の生存戦略",
        "三宅香帆が語る、ブッククラブの可能性とファッションが心に与える体温",
        "【異業種に学ぶ】服や飲食など複合型ゴルフ練習場「ロイヤルグリーン水戸」",
        "人口減少と向き合った新しい地方の街づくりとは？ ニューローカルの石田遼さんを迎えた「カルチャースケーパーズ」。",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title


def test_is_excluded_true_for_pure_music_news_unrelated_to_fashion():
    # 「ライブ・アルバム」はこの1件の実例のみを狙った狭いキーワード。
    # 広く「音楽」「ライブ」単体をキーワードにはしていない（下のfalseテスト参照）。
    item = {
        "title": "KID FRESINOがワンマンライブ『21』のライブ・アルバムを配信リリース。"
        "『AOS』のライブ映像もYouTubeで公開です。",
        "summary": "",
    }
    assert _is_excluded(item) is True


def test_is_excluded_false_for_bags_jewelry_eyewear_and_street_style_items():
    # オーナーの明示的な方針: バッグ・ジュエリー／アクセサリー・アイウェアはファッション周辺の
    # 正当な商品ニュースとして除外しない。ストリートスナップも除外しない。
    items = [
        {"title": "グッチが新作バッグ「ジャッキー フラップ」発売、ショルダーとクロスボディの2way仕様", "summary": ""},
        {"title": "ポロ ラルフ ローレンが新作バッグ「ポロ ブレイズ」発売、ショルダーとトップハンドルの2種", "summary": ""},
        {"title": "シャネル出身デザイナーによるシルバージュエリー「オタノ」が渋谷でポップアップ開催", "summary": ""},
        {"title": "ハイクがエンドカスタムジュエラーズとコラボ　ネックレスやブレスレットなど8型を発売", "summary": ""},
        {"title": "ジンズが“中顔面を短く見せる”新作アイウェア発売　イコラブ大谷をヴィジュアルに起用", "summary": ""},
        {"title": "ストリートスタイル: Job: モデル", "summary": ""},
    ]
    for item in items:
        assert _is_excluded(item) is False, item["title"]


def test_is_excluded_false_for_gdragon_outfit_news_and_prior_anime_collabs():
    # 音楽アーティストが登場する記事でも、衣装・コラボ等のファッション本題であれば除外しない。
    # また過去のQA対応で許容された正当なファッション×アニメコラボ記事も引き続き除外しない。
    items = [
        {"title": "G-DRAGON、BIGBANG‎の新曲MVでタナカダイスケの衣装を着用", "summary": ""},
        {"title": "コンバース トウキョウがまどマギと初コラボ　アートTシャツやアクセサリーなど発売", "summary": ""},
        {"title": "グラニフが「呪術廻戦」とコラボ　Tシャツやパーカなど全21型", "summary": ""},
    ]
    for item in items:
        assert _is_excluded(item) is False, item["title"]


def test_is_excluded_true_for_obituary_secondhand_business_and_fragrance_column():
    # オーナー確認済みの境界事例3件（2026-08-21）。いずれも服・シューズの商品情報ではなく、
    # 「服・スニーカーを軸にする」という方針のもとで除外対象に追加した。
    titles = [
        "ディオールの名物PRディレクターが事故死　ジョナサン・アンダーソンらが追悼",
        "ファミマが中古品買取サービスを開始　ブックオフとタッグ",
        "音楽と香りのマリアージュをテーマに。フィッシュマンズの『LONG SEASON』"
        "リリース30周年を記念したOSAJIとの企画です。",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title


def test_is_excluded_false_for_fashion_items_mentioning_death_or_secondhand():
    # 上記3件の追加キーワードが、無関係な正当なファッション記事を誤って
    # 除外しないことの回帰確認。
    items = [
        {"title": "アディダスがトレイルレーシングシューズの最高峰モデルを発表", "summary": ""},
        {"title": "エルメスの二次流通専門店が青山に新規出店", "summary": "国内外で高まる希少モデル需要が追い風に"},
    ]
    for item in items:
        assert _is_excluded(item) is False, item["title"]


def test_is_excluded_true_for_4th_round_new_categories():
    # 実データ254件を全件確認して発見した新規混入カテゴリ（2026-08-25）。
    titles = [
        "【日曜日22時占い】今週の運勢は？12星座別 ＜8月23日〜9月5日＞",
        "ブックエクスチェンジや占術家によるセッションも。イソップが4日間にわたり新たなコレクションを祝福します。",
        "The Future of Cars Looks Surprisingly Retro",
        "Eccentrica Just Made Monterey Car Week Even Louder",
        "ウォルマートのサブスク新特典は写真も送金もパンク修理も無料　暮らしを囲い込む経済圏",
        "万引き防止だけじゃない？米小売のAI活用が従業員保護の用途にも拡大",
        "Nice Hand Soap Is The New Status Symbol",
        "How Eric Wareheim Went from Comedy Star to Los Angeles' Plant Guru",
        "ジャズ喫茶「新宿DUG」が閉店　65年の歴史に幕",
        "初心者向け「3Dプリンター」徹底ガイド｜個人の活用法と作品例",
        "累積赤字540億円、「クールジャパン機構」廃止へ　スパイバーや三越伊勢丹HDにも出資",
        "I-neが髪の内部まで美容成分を届ける浸透技術を開発",
        "マツキヨココカラ＆カンパニーが「ジョンマスターオーガニック」運営会社を買収",
        "BTS j-hopeがオーラルケア「コルゲート」歯磨き粉のアンバサダーに　日本展開は未定",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title


def test_is_excluded_true_for_apparel_business_columns():
    # 商品情報ではないアパレル業界のビジネスコラム（経営史・出店戦略・海外事業展開等）。
    # オーナー確認のうえ除外対象に追加した境界事例（2026-08-25）。
    titles = [
        "グンゼ・ボディワイルドが営業赤字でも残る理由（前編） ブランドの開発史",
        "セカストはなぜ全国最大規模の「メガ店舗」を川崎に出店するのか",
        "アシックス、ウォーキング事業でも世界へ　レザーシューズで中国のビジネスパーソンに照準",
        "America's Mid-Tier Fashion Market Is Thriving",
    ]
    for title in titles:
        assert _is_excluded({"title": title, "summary": ""}) is True, title


def test_is_excluded_false_for_watch_column_not_matching_naze_keyword():
    # 「セカストはなぜ...出店するのか」の「なぜ」を単体でキーワードにすると、
    # この時計コラムのような無関係な記事に誤爆する。「出店するのか」まで含めた
    # フレーズのみを対象にすることで、この記事は除外されない（回帰確認）。
    item = {"title": "ロレックスやカルティエはなぜ「名品」と呼ばれるの？——時計の基本の「キ」第2回", "summary": ""}
    assert _is_excluded(item) is False


def test_fetch_source_filters_out_excluded_items():
    source = {"name": "Fashionsnap", "url": "https://example.com/feed.xml"}
    fake_items = [
        {
            "url": "https://example.com/fashion",
            "title": "普通のファッション記事",
            "summary": "新作コレクションを発表した。",
            "published": "2026-08-20T00:00:00+00:00",
        },
        {
            "url": "https://example.com/incident",
            "title": "タレントが書類送検",
            "summary": "",
            "published": "2026-08-20T00:00:00+00:00",
        },
    ]
    with patch("scripts.fetch_feeds.parse_feed", return_value=fake_items):
        result = fetch_source(source)
    assert [item["url"] for item in result] == ["https://example.com/fashion"]
