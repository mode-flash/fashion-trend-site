"""ブランド一覧ページ用の、主要ブランド検出辞書.

RSSフィードにはブランドの構造化データ（カテゴリ等）が含まれておらず、
タイトルのテキストから判定するしかない。日本の小規模インディーズブランドが
非常に多く（実データで「PONTI」「divka」等の新作コレクション記事が多数）
完全な網羅は現実的ではないため、記事に頻出する主要ブランドのみを対象にした
簡易的な検出とする（オーナー確認済み、2026-08-25）。

キーは表示用の代表名、値はタイトル中にこの文字列が含まれればそのブランドと
みなす候補語（日本語表記・英語表記のバリエーション）のリスト。実データ245件で
検証し、誤爆（無関係な記事への意図しないマッチ）が無いことを確認済み。
"""

BRAND_KEYWORDS: dict[str, list[str]] = {
    "Nike": ["Nike", "ナイキ"],
    "adidas": ["adidas", "アディダス"],
    "New Balance": ["New Balance", "ニューバランス"],
    "ASICS": ["ASICS", "アシックス"],
    "Vans": ["Vans", "バンズ"],
    "Salomon": ["Salomon", "サロモン"],
    "Reebok": ["Reebok", "リーボック"],
    "Crocs": ["Crocs", "クロックス"],
    "Converse": ["Converse", "コンバース"],
    "Jordan": ["Jordan"],
    "Mizuno": ["Mizuno", "ミズノ"],
    "Supreme": ["Supreme", "シュプリーム"],
    "BAPE": ["BAPE", "ベイプ", "A BATHING APE"],
    "Palace": ["Palace"],
    "Stussy": ["Stüssy", "ステューシー"],
    "BEAMS": ["BEAMS", "ビームス"],
    "UNIQLO": ["UNIQLO", "ユニクロ"],
    "Dickies": ["Dickies", "ディッキーズ"],
    "Gucci": ["Gucci", "グッチ"],
    "Chanel": ["Chanel", "シャネル"],
    "Fendi": ["Fendi", "フェンディ"],
    "Valentino": ["Valentino", "ヴァレンティノ"],
    "Saint Laurent": ["Saint Laurent", "サンローラン"],
    "Balenciaga": ["Balenciaga", "バレンシアガ"],
    "Miu Miu": ["Miu Miu", "ミュウミュウ"],
    "Bottega Veneta": ["Bottega Veneta", "ボッテガ・ヴェネタ", "ボッテガヴェネタ"],
    "Maison Margiela": ["Margiela", "マルジェラ"],
    "COMME des GARCONS": ["COMME des GAR", "コム デ ギャルソン", "コムデギャルソン"],
    "Arc'teryx": ["Arc'teryx", "アークテリクス"],
    "The North Face": ["The North Face", "ザ・ノース・フェイス", "ノースフェイス"],
    "Patagonia": ["Patagonia", "パタゴニア"],
    "Marmot": ["Marmot", "マーモット"],
    "Levi's": ["Levi's", "リーバイス"],
    "Ralph Lauren": ["Ralph Lauren", "ラルフ ローレン", "ラルフローレン"],
    "United Arrows": ["United Arrows", "ユナイテッドアローズ"],
    "Hermes": ["Hermès", "エルメス"],
}
