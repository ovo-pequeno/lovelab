# タロット78枚のファイル名→日本語名 対応表。
# assets/cards/ に置いた画像（ファイル名）だけが抽選対象になる。
# 小アルカナを追加したら、対応する画像を置くだけで自動的に引けるようになる。

TAROT_DECK = {
    # ===== 大アルカナ 22枚 =====
    "00_fool": "愚者", "01_magician": "魔術師", "02_high_priestess": "女教皇",
    "03_empress": "女帝", "04_emperor": "皇帝", "05_hierophant": "教皇",
    "06_lovers": "恋人", "07_chariot": "戦車", "08_strength": "力",
    "09_hermit": "隠者", "10_wheel": "運命の輪", "11_justice": "正義",
    "12_hanged_man": "吊るされた男", "13_death": "死神", "14_temperance": "節制",
    "15_devil": "悪魔", "16_tower": "塔", "17_star": "星",
    "18_moon": "月", "19_sun": "太陽", "20_judgement": "審判", "21_world": "世界",
    # ===== 小アルカナ ワンド（棒）14枚 =====
    "wands_ace": "ワンドのエース", "wands_02": "ワンドの2", "wands_03": "ワンドの3",
    "wands_04": "ワンドの4", "wands_05": "ワンドの5", "wands_06": "ワンドの6",
    "wands_07": "ワンドの7", "wands_08": "ワンドの8", "wands_09": "ワンドの9",
    "wands_10": "ワンドの10", "wands_page": "ワンドのペイジ", "wands_knight": "ワンドのナイト",
    "wands_queen": "ワンドのクイーン", "wands_king": "ワンドのキング",
    # ===== 小アルカナ カップ（聖杯）14枚 =====
    "cups_ace": "カップのエース", "cups_02": "カップの2", "cups_03": "カップの3",
    "cups_04": "カップの4", "cups_05": "カップの5", "cups_06": "カップの6",
    "cups_07": "カップの7", "cups_08": "カップの8", "cups_09": "カップの9",
    "cups_10": "カップの10", "cups_page": "カップのペイジ", "cups_knight": "カップのナイト",
    "cups_queen": "カップのクイーン", "cups_king": "カップのキング",
    # ===== 小アルカナ ソード（剣）14枚 =====
    "swords_ace": "ソードのエース", "swords_02": "ソードの2", "swords_03": "ソードの3",
    "swords_04": "ソードの4", "swords_05": "ソードの5", "swords_06": "ソードの6",
    "swords_07": "ソードの7", "swords_08": "ソードの8", "swords_09": "ソードの9",
    "swords_10": "ソードの10", "swords_page": "ソードのペイジ", "swords_knight": "ソードのナイト",
    "swords_queen": "ソードのクイーン", "swords_king": "ソードのキング",
    # ===== 小アルカナ ペンタクル（金貨）14枚 =====
    "pentacles_ace": "ペンタクルのエース", "pentacles_02": "ペンタクルの2", "pentacles_03": "ペンタクルの3",
    "pentacles_04": "ペンタクルの4", "pentacles_05": "ペンタクルの5", "pentacles_06": "ペンタクルの6",
    "pentacles_07": "ペンタクルの7", "pentacles_08": "ペンタクルの8", "pentacles_09": "ペンタクルの9",
    "pentacles_10": "ペンタクルの10", "pentacles_page": "ペンタクルのペイジ", "pentacles_knight": "ペンタクルのナイト",
    "pentacles_queen": "ペンタクルのクイーン", "pentacles_king": "ペンタクルのキング",
}

import os, random

def available_cards(card_dir):
    """card_dir に実在する .png のうち、対応表にあるものだけを返す。
    小アルカナ画像を足せば自動的に抽選対象が増える。"""
    cards = []
    if os.path.isdir(card_dir):
        for fname in os.listdir(card_dir):
            if not fname.lower().endswith(".png"):
                continue
            key = fname[:-4]  # .png除去
            if key in TAROT_DECK:
                cards.append({"file": key, "jp": TAROT_DECK[key]})
    return cards

def draw_from_dir(card_dir, n=1, reverse_rate=0.4):
    """実在画像から重複なしでn枚引く。画像が足りない/無い場合は
    対応表全体（大アルカナ）からフォールバックで引く。"""
    pool = available_cards(card_dir)
    if len(pool) < n:
        # 画像が足りなければ対応表の大アルカナ22枚から補完（画像なしでも名前で出せる）
        major = [{"file": k, "jp": v} for k, v in list(TAROT_DECK.items())[:22]]
        # 実在ぶんを優先しつつ不足を大アルカナで埋める
        seen = {c["file"] for c in pool}
        for c in major:
            if len(pool) >= max(n, 22):
                break
            if c["file"] not in seen:
                pool.append(c); seen.add(c["file"])
    picks = random.sample(pool, min(n, len(pool)))
    for c in picks:
        c["reversed"] = random.random() < reverse_rate
    return picks
