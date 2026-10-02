import random
import math
import copy
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import streamlit as st

# ============================================================
# ⚾ 野球チームメーカー / Streamlit 完全版
# ============================================================

st.set_page_config(
    page_title="野球チームメーカー",
    page_icon="⚾",
    layout="wide",
)

# ============================================================
# 定数
# ============================================================
POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]

POSITION_JP = {
    "C": "捕手", "1B": "一塁手", "2B": "二塁手", "3B": "三塁手",
    "SS": "遊撃手", "LF": "左翼手", "CF": "中堅手", "RF": "右翼手",
    "DH": "指名打者", "P": "投手",
}

RANK_VALUE = {
    "S": 98.0, "A": 88.0, "B": 79.0, "C": 68.0,
    "D": 63.0, "E": 57.0, "F": 45.0, "G": 25.0,
}

RANK_WEIGHT = {
    "S": 1.40, "A": 1.25, "B": 1.10, "C": 0.95,
    "D": 0.80, "E": 0.65, "F": 0.50, "G": 0.35,
}

SCHEDULE_SAME = 25
SCHEDULE_INTER = 3

CENTRAL_TEAMS = ["阪神", "DeNA", "巨人", "広島", "ヤクルト", "中日"]
PACIFIC_TEAMS = ["ソフトバンク", "日本ハム", "オリックス", "楽天", "西武", "ロッテ"]
ALL_NPB_TEAMS = CENTRAL_TEAMS + PACIFIC_TEAMS

# ============================================================
# データクラス
# ============================================================
@dataclass
class BatterStats:
    G: int = 0
    AB: int = 0
    H: int = 0
    double: int = 0
    triple: int = 0
    HR: int = 0
    BB: int = 0
    SO: int = 0
    RBI: int = 0
    R: int = 0
    SB: int = 0
    CS: int = 0
    TB: int = 0
    SF: int = 0
    PA: int = 0

@dataclass
class PitcherStats:
    G: int = 0
    GS: int = 0
    outs: int = 0
    H: int = 0
    ER: int = 0
    R: int = 0
    BB: int = 0
    SO: int = 0
    W: int = 0
    L: int = 0
    HLD: int = 0
    SV: int = 0
    HR: int = 0
    BF: int = 0

@dataclass
class FielderStats:
    PO: int = 0
    A: int = 0
    E: int = 0
    PB: int = 0  # <--- 捕逸（パスボール）を追加
    UZR: float = 0.0

@dataclass
class Player:
    name: str
    team: str
    contact: float = 0.0
    power: float = 0.0
    speed: float = 0.0
    defense: dict = field(default_factory=dict)
    control: float = 0.0
    stamina: float = 0.0
    pitch_power_base: float = 0.0  # 新設された「球威」
    pitches: dict = field(default_factory=dict)
    batting: BatterStats = field(default_factory=BatterStats)
    pitching: PitcherStats = field(default_factory=PitcherStats)
    fielding: FielderStats = field(default_factory=FielderStats)

    current_stamina: float = 0.0
    consecutive_games: int = 0
    did_pitch_today: bool = False
    game_pitches_today: int = 0
    force_continue_outs: int = 0

    def is_pitcher(self):
        return bool(self.pitches) or self.control > 0 or self.stamina > 0

    def defense_at(self, pos):
        return float(self.defense.get(pos, 0.0))

@dataclass
class Team:
    name: str
    fielders: list
    pitchers: list

# ============================================================
# Excel解析
# ============================================================
def clean_number(x, default=0.0):
    if pd.isna(x): return default
    try: return float(x)
    except Exception: return default

def parse_defense(text):
    result = {}
    if pd.isna(text): return result
    for part in str(text).split("/"):
        part = part.strip()
        if ":" not in part: continue
        pos, value = part.split(":", 1)
        try: result[pos.strip().upper()] = float(value.strip())
        except ValueError: pass
    return result

def require_columns(df, columns, label):
    missing = [c for c in columns if c not in df.columns]
    if missing: raise ValueError(f"{label}に必要な列がありません: {', '.join(missing)}")

def load_fielders(source):
    df = pd.read_excel(source)
    require_columns(df, ["選手名", "チーム", "ミート", "パワー", "走力", "守備力"], "野手ファイル")
    players = []
    for _, row in df.iterrows():
        name_val = row.get("選手名_出力", row.get("選手名", "不明"))
        players.append(Player(
            name=str(name_val).strip(), team=str(row["チーム"]).strip(),
            contact=clean_number(row["ミート"]), power=clean_number(row["パワー"]),
            speed=clean_number(row["走力"]), defense=parse_defense(row["守備力"])
        ))
    return players

def load_pitchers(source):
    df = pd.read_excel(source)
    require_columns(df, ["チーム", "球威", "制球", "スタミナ"], "投手ファイル")
    
    pitch_cols = [c for c in df.columns if str(c).startswith("球種_")]
    
    players = []
    for _, row in df.iterrows():
        name_val = row.get("選手名_出力", row.get("選手名", "不明"))
        
        # 新しい構造：各「球種_XXX」列から直接数値を抽出
        pitches = {}
        for c in pitch_cols:
            val = row[c]
            if pd.notna(val):
                pitch_name = c.replace("球種_", "")
                pitches[pitch_name] = float(val)
                
        p = Player(
            name=str(name_val).strip(),
            team=str(row["チーム"]).strip(),
            control=clean_number(row["制球"]),
            stamina=clean_number(row["スタミナ"]),
            pitch_power_base=clean_number(row["球威"]),
            pitches=pitches
        )
        p.current_stamina = p.stamina
        players.append(p)
    return players

# ============================================================
# セイバーメトリクス計算
# ============================================================
def calc_woba(p):
    b = p.batting
    if b.PA == 0: return 0.0
    single = b.H - b.double - b.triple - b.HR
    hbp = b.PA * 0.01 
    bb = b.BB
    numerator = 0.692 * bb + 0.73 * hbp + 0.865 * single + 1.334 * b.double + 1.725 * b.triple + 2.065 * b.HR
    denominator = b.AB + bb + hbp + b.SF
    if denominator == 0: return 0.0
    return numerator / denominator

def calc_wrc_plus(p):
    woba = calc_woba(p)
    if p.batting.PA == 0: return 0.0
    return (woba / 0.320) * 100

def calc_batter_war(p, main_pos):
    b = p.batting
    if b.PA == 0: return 0.0
    woba = calc_woba(p)
    league_woba = 0.320
    woba_scale = 1.24
    rpw = 9.5
    wraa = ((woba - league_woba) / woba_scale) * b.PA
    run_a = (b.SB * 0.20) + (b.CS * -0.40)
    single = b.H - b.double - b.triple - b.HR
    run_c = single + b.BB
    wsb = run_a - (0.05 * run_c)
    ubr = (p.speed - 50.0) * 0.003 * b.PA
    base_running = wsb + ubr
    pos_adj_table = { "C": 5.1, "1B": -4.1, "2B": 1.0, "3B": -1.5, "SS": 3.3, "LF": -5.0, "CF": 2.2, "RF": -2.0, "DH": -8.1, "代打": -8.1 }
    pos_adj = pos_adj_table.get(main_pos, -11.1) * (b.PA / 500.0)
    defense = p.fielding.UZR + pos_adj
    replacement = ((league_woba - 0.88 * league_woba) / woba_scale) * b.PA
    rar = wraa + base_running + defense + replacement
    return rar / rpw

def calc_tra(p):
    pt = p.pitching
    if pt.outs == 0: return 0.0
    bip = max(0, pt.BF - pt.SO - pt.BB - pt.HR)
    gb, fb, iff, ld = bip * 0.45, bip * 0.35, bip * 0.10, bip * 0.10
    hbp, bb = pt.BB * 0.10, pt.BB * 0.90
    numerator = (0.297 * bb + 0.327 * hbp - 0.108 * pt.SO + 1.401 * pt.HR + 0.036 * gb - 0.124 * iff + 0.132 * fb + 0.289 * ld)
    denominator = (pt.SO + 0.745 * gb + 0.304 * ld + 0.994 * iff + 0.675 * fb)
    if denominator == 0: return 0.0
    tra_raw = (numerator / denominator) * 27
    return tra_raw + 3.10

def calc_fip(p):
    pt = p.pitching
    if pt.outs == 0: return 0.0
    ip = pt.outs / 3.0
    fip = (13 * pt.HR + 3 * pt.BB - 2 * pt.SO) / ip + 3.10
    return max(0.0, fip)

def calc_pitcher_war(p):
    pt = p.pitching
    if pt.outs == 0: return 0.0
    tra = calc_tra(p)
    league_tra = 3.50
    rpw = 9.5
    hbp = pt.BB * 0.10
    total_bb = pt.BB + hbp
    sf_sh_roe = pt.BF * 0.03
    defense_independent_outs = pt.SO + max(0, pt.BF - pt.H - pt.SO - total_bb - sf_sh_roe)
    dio_innings = defense_independent_outs / 3.0
    starter_ratio = pt.GS / pt.G if pt.G > 0 else 0.0
    relief_ratio = 1.0 - starter_ratio
    sprar = ((1.19 * league_tra + 0.30 - tra) / 9) * dio_innings
    rprar = ((1.19 * league_tra - 0.55 - tra) / 9) * dio_innings
    war = (sprar * starter_ratio + rprar * relief_ratio) / rpw
    return war

# ============================================================
# 初期配置・チーム生成ロジック
# ============================================================
def assign_initial_positions(fielders, dh=True):
    remaining = list(fielders)
    lineup = []
    assigned_positions, assigned_players = set(), set()
    for pos in POSITIONS:
        capable = [p for p in remaining if p.defense_at(pos) > 0]
        if len(capable) == 1:
            p = capable[0]
            if p.name not in assigned_players:
                lineup.append((p, pos))
                assigned_positions.add(pos)
                assigned_players.add(p.name)
                remaining.remove(p)
    def total_score(p): return p.contact + p.power + p.speed
    remaining.sort(key=total_score, reverse=True)
    unassigned_pos = [pos for pos in POSITIONS if pos not in assigned_positions]
    for p in list(remaining):
        if not unassigned_pos: break
        capable_pos = [pos for pos in unassigned_pos if p.defense_at(pos) > 0]
        if capable_pos:
            best_pos = max(capable_pos, key=lambda pos: p.defense_at(pos))
            lineup.append((p, best_pos))
            unassigned_pos.remove(best_pos)
            remaining.remove(p)
    for pos in list(unassigned_pos):
        if remaining:
            p = remaining.pop(0)
            lineup.append((p, pos))
            unassigned_pos.remove(pos)
    if dh and remaining:
        dh_player = max(remaining, key=total_score)
        lineup.append((dh_player, "DH"))
        remaining.remove(dh_player)
    return lineup

def decide_batting_order(lineup_pairs):
    pool = list(lineup_pairs)
    order = [None] * len(pool)
    def assign_to_order(idx, score_func):
        if len(pool) > 0 and idx < len(order):
            p = max(pool, key=lambda x: score_func(x[0]))
            order[idx] = p
            pool.remove(p)
    assign_to_order(3, lambda p: p.power * 2 + p.contact * 1.2)
    assign_to_order(0, lambda p: p.contact * 1.7 + p.power * 0.4 + p.speed * 2)
    assign_to_order(1, lambda p: p.contact * 1.3 + p.power * 1.1 + p.speed)
    assign_to_order(4, lambda p: p.power * 2 + p.contact)
    assign_to_order(2, lambda p: p.contact + p.power * 2)
    pool.sort(key=lambda x: x[0].contact + x[0].power, reverse=True)
    empty_indices = [i for i, v in enumerate(order) if v is None]
    for p in pool:
        if empty_indices:
            idx = empty_indices.pop(0)
            order[idx] = p
    return [x for x in order if x is not None]

def val_to_rank(val):
    if val >= 90: return "S", "#D4AF37"  
    elif val >= 80: return "A", "#E91E63" 
    elif val >= 70: return "B", "#F44336" 
    elif val >= 60: return "C", "#FF9800" 
    elif val >= 50: return "D", "#FFD600" 
    elif val >= 40: return "E", "#4CAF50" 
    elif val >= 20: return "F", "#2196F3" 
    else: return "G", "#9E9E9E"

def count_pitches_of_rank(pitcher, ranks):
    count = 0
    for val in pitcher.pitches.values():
        r_str = val_to_rank(val)[0]
        if r_str in ranks:
            count += 1
    return count

def relief_sort_key(pitcher):
    a_count = count_pitches_of_rank(pitcher, ["S", "A"])
    b_count = count_pitches_of_rank(pitcher, ["B"])
    return (a_count, b_count, pitcher.control, random.random())

def decide_pitcher_roles(pitchers):
    sorted_by_stamina = sorted(pitchers, key=lambda p: p.stamina, reverse=True)
    starters = sorted_by_stamina[:6]
    remaining = sorted_by_stamina[6:]
    remaining.sort(key=relief_sort_key, reverse=True)
    roles = {}
    for p in starters: roles[p.name] = "先発"
    role_slots = ["抑え", "中継ぎエース", "僅差", "僅差", "リード", "リード", "ビハインド", "ビハインド", "敗戦処理"]
    for i, p in enumerate(remaining):
        if i < len(role_slots): roles[p.name] = role_slots[i]
        else: roles[p.name] = "敗戦処理"
    return roles

def build_teams(fielders, pitchers):
    teams = {}
    for p in fielders:
        teams.setdefault(p.team, {"fielders": [], "pitchers": []})
        teams[p.team]["fielders"].append(p)
    for p in pitchers:
        teams.setdefault(p.team, {"fielders": [], "pitchers": []})
        teams[p.team]["pitchers"].append(p)
    return { name: Team(name=name, fielders=data["fielders"], pitchers=data["pitchers"]) for name, data in teams.items() }

# ============================================================
# 他球団 固定オーダー定義
# ============================================================
OPPONENT_LINEUPS = {
    "阪神": {"order": [("近本光司", "CF"), ("中野拓夢", "2B"), ("森下翔太", "RF"), ("佐藤輝明", "3B"), ("大山悠輔", "1B"), ("前川右京", "LF"), ("坂本誠志郎", "C"), ("元山飛優", "SS")], "sub": "熊谷敬宥"},
    "DeNA": {"order": [("度会隆輝", "LF"), ("牧秀悟", "2B"), ("佐野恵太", "1B"), ("エンカーナシオン", "RF"), ("宮﨑敏郎", "3B"), ("蝦名達夫", "CF"), ("宮下朝陽", "SS"), ("松尾汐恩", "C")], "sub": "勝又温史"},
    "巨人": {"order": [("浦田俊輔", "2B"), ("松本剛", "LF"), ("泉口友汰", "SS"), ("ダルベック", "1B"), ("大城卓三", "C"), ("キャベッジ", "CF"), ("坂本勇人", "3B"), ("中山礼都", "RF")], "sub": "佐々木俊輔"},
    "中日": {"order": [("岡林勇希", "CF"), ("村松開人", "SS"), ("細川成也", "LF"), ("サノー", "1B"), ("石川昂弥", "3B"), ("石伊雄太", "C"), ("ボスラー", "RF"), ("田中幹也", "2B")], "sub": "福永裕基"},
    "広島": {"order": [("名原典彦", "RF"), ("菊池涼介", "2B"), ("ファビアン", "LF"), ("坂倉将吾", "3B"), ("モンテロ", "1B"), ("小園海斗", "SS"), ("大盛穂", "CF"), ("持丸泰輝", "C")], "sub": "佐々木泰"},
    "ヤクルト": {"order": [("長岡秀樹", "SS"), ("サンタナ", "LF"), ("古賀優大", "C"), ("オスナ", "1B"), ("岩田幸宏", "CF"), ("増田珠", "RF"), ("内山壮真", "2B"), ("武岡龍世", "3B")], "sub": "赤羽由紘"},
    
    "ソフトバンク": {"order": [("正木智也", "1B"), ("周東佑京", "CF"), ("近藤健介", "LF"), ("栗原陵矢", "3B"), ("柳田悠岐", "DH"), ("柳町達", "RF"), ("牧原大成", "2B"), ("海野隆司", "C"), ("庄子雄大", "SS")]},
    "日本ハム": {"order": [("水野達稀", "SS"), ("清宮幸太郎", "1B"), ("レイエス", "DH"), ("郡司裕也", "3B"), ("万波中正", "RF"), ("野村佑希", "LF"), ("カストロ", "CF"), ("田宮裕涼", "C"), ("奈良間大己", "2B")]},
    "オリックス": {"order": [("宗佑磨", "3B"), ("山中稜真", "1B"), ("西川龍馬", "LF"), ("太田椋", "2B"), ("森友哉", "DH"), ("来田涼斗", "RF"), ("紅林弘太郎", "SS"), ("若月健矢", "C"), ("渡部遼人", "CF")]},
    "楽天": {"order": [("中島大輔", "LF"), ("黒川史陽", "3B"), ("辰己涼介", "CF"), ("マッカスカー", "DH"), ("村林一輝", "SS"), ("浅村栄斗", "1B"), ("佐藤直樹", "RF"), ("太田光", "C"), ("小深田大翔", "2B")]},
    "西武": {"order": [("カナリオ", "RF"), ("小島大河", "C"), ("渡部聖弥", "3B"), ("ネビン", "1B"), ("林安可", "DH"), ("桑原将志", "LF"), ("石井一成", "2B"), ("源田壮亮", "SS"), ("西川愛也", "CF")]},
    "ロッテ": {"order": [("藤原恭大", "CF"), ("西川史礁", "RF"), ("寺地隆成", "3B"), ("山口航輝", "LF"), ("佐藤都志也", "C"), ("ソト", "1B"), ("友杉篤輝", "SS"), ("ポランコ", "DH"), ("小川龍成", "2B")]}
}

def best_lineup_for_team(team, dh=True):
    bench = None
    if team.name in OPPONENT_LINEUPS:
        lineup = []
        target = OPPONENT_LINEUPS[team.name]
        
        def get_p(name):
            c_name = str(name).replace(" ", "").replace(" ", "").replace("・", "")
            for p in team.fielders:
                if p.name.replace(" ", "").replace(" ", "").replace("・", "") == c_name:
                    return p
            return None
        
        for name, pos in target["order"]:
            if not dh and pos == "DH": continue
            player = get_p(name)
            if player: lineup.append((player, pos))
        
        if dh and len(lineup) == 8 and "sub" in target:
            sub_player = get_p(target["sub"])
            if sub_player: lineup.append((sub_player, "DH"))
            
        if not dh and "sub" in target:
            sub_player = get_p(target["sub"])
            if sub_player: bench = sub_player
                
        needed = 9 if dh else 8
        if len(lineup) < needed:
            used = [p.name for p, _ in lineup]
            remain = sorted([p for p in team.fielders if p.name not in used], key=lambda x: x.contact + x.power, reverse=True)
            while len(lineup) < needed and remain:
                lineup.append((remain.pop(0), "DH" if dh and len(lineup) == 8 else "不明"))
                
        if not dh and not bench:
            used = [p.name for p, _ in lineup]
            remain = sorted([p for p in team.fielders if p.name not in used], key=lambda x: x.contact + x.power, reverse=True)
            if remain: bench = remain[0]
            
        return lineup, bench
        
    lineup = assign_initial_positions(team.fielders, dh=dh)
    lineup = decide_batting_order(lineup)
    if len(lineup) > 9: lineup = lineup[:9]
    
    used = [p.name for p, _ in lineup]
    remain = [p for p in team.fielders if p.name not in used]
    if not dh and remain: bench = max(remain, key=lambda x: x.contact + x.power)
    
    return lineup, bench

# ============================================================
# 他球団 固定投手起用定義
# ============================================================
OPPONENT_PITCHERS = {
    "阪神": {
        "先発": ["村上頌樹", "髙橋遥人", "才木浩人", "大竹耕太郎", "西勇輝", "伊原陵人"],
        "抑え": "ドリス",
        "中継ぎエース": "工藤泰成",
        "僅差": ["木下里都", "岩崎優"],
        "リード": ["及川雅貴", "セベリーノ"],
        "ビハインド": ["湯浅京己", "神宮僚介"],
        "敗戦処理": ["桐敷拓馬"]
    },
    "DeNA": {
        "先発": ["東克樹", "石田裕太郎", "平良拳太郎", "尾形崇斗", "深沢鳳介", "片山皓心"],
        "抑え": "レイノルズ",
        "中継ぎエース": "中川虎大",
        "僅差": ["伊勢大夢", "浜地真澄"],
        "リード": ["ルイーズ", "岩田将貴"],
        "ビハインド": ["吉野光樹", "宮城滝太"],
        "敗戦処理": ["坂本裕哉"]
    },
    "巨人": {
        "先発": ["井上温大", "戸郷翔征", "小笠原慎之介", "ウィットリー", "竹丸和幸", "田中将大"],
        "抑え": "マルティネス",
        "中継ぎエース": "田中瑛斗",
        "僅差": ["大勢", "中川皓太"],
        "リード": ["船迫大雅", "堀田賢慎"],
        "ビハインド": ["赤星優志", "森田駿哉"],
        "敗戦処理": ["田和廉"]
    },
    "ヤクルト": {
        "先発": ["山野太一", "奥川恭伸", "高梨裕稔", "松本健吾", "吉村貢司郎", "高橋奎二"],
        "抑え": "キハダ",
        "中継ぎエース": "清水昇",
        "僅差": ["星知弥", "リランソ"],
        "リード": ["廣澤優", "丸山翔大"],
        "ビハインド": ["阪口皓亮", "石原勇輝"],
        "敗戦処理": ["荘司宏太"]
    },
    "中日": {
        "先発": ["髙橋宏斗", "柳裕也", "大野雄大", "金丸夢斗", "マラー", "涌井秀章"],
        "抑え": "松山晋也",
        "中継ぎエース": "吉田聖弥",
        "僅差": ["橋本侑樹", "齋藤綱記"],
        "リード": ["藤嶋健人", "森博人"],
        "ビハインド": ["メヒア", "草加勝"],
        "敗戦処理": ["伊藤茉央"]
    },
    "広島": {
        "先発": ["栗林良吏", "床田寛樹", "森下暢仁", "森翔平", "玉村昇悟", "斉藤優汰"],
        "抑え": "森浦大輔",
        "中継ぎエース": "ハーン",
        "僅差": ["遠藤淳志", "髙太一"],
        "リード": ["岡本駿", "中﨑翔太"],
        "ビハインド": ["鈴木健矢", "塹江敦哉"],
        "敗戦処理": ["辻大雅"]
    },
    "日本ハム": {
        "先発": ["北山亘基", "伊藤大海", "達孝太", "加藤貴之", "細野晴希", "有原航平"],
        "抑え": "柳川大晟",
        "中継ぎエース": "島本浩也",
        "僅差": ["堀瑞輝", "田中正義"],
        "リード": ["福島蓮", "上原健太"],
        "ビハインド": ["孫易磊", "山﨑福也"],
        "敗戦処理": ["生田目翼"]
    },
    "ソフトバンク": {
        "先発": ["前田悠伍", "上沢直之", "大津亮介", "松本晴", "モイネロ", "スチュワート・ジュニア"],
        "抑え": "杉山一樹",
        "中継ぎエース": "松本裕樹",
        "僅差": ["オスナ", "津森宥紀"],
        "リード": ["ヘルナンデス", "上茶谷大河"],
        "ビハインド": ["木村光", "鈴木豪太"],
        "敗戦処理": ["伊藤優輔"]
    },
    "ロッテ": {
        "先発": ["ジャクソン", "小島和哉", "田中晴也", "廣池康志郎", "毛利海大", "ルケーシー"],
        "抑え": "横山陸人",
        "中継ぎエース": "鈴木昭汰",
        "僅差": ["八木彬", "中森俊介"],
        "リード": ["益田直也", "高野脩汰"],
        "ビハインド": ["澤田圭佑", "小野郁"],
        "敗戦処理": ["坂本光士郎"]
    },
    "オリックス": {
        "先発": ["エスピノーザ", "九里亜蓮", "ジェリー", "曽谷龍平", "髙島泰都", "田嶋大樹"],
        "抑え": "マチャド",
        "中継ぎエース": "椋木蓮",
        "僅差": ["山﨑颯一郎", "寺西成騎"],
        "リード": ["入山海斗", "吉田輝星"],
        "ビハインド": ["博志", "片山楽生"],
        "敗戦処理": ["岩嵜翔"]
    },
    "楽天": {
        "先発": ["早川隆久", "前田健太", "岸孝之", "古謝樹", "荘司康誠", "瀧中瞭太"],
        "抑え": "藤平尚真",
        "中継ぎエース": "加治屋蓮",
        "僅差": ["九谷瑠", "鈴木翔天"],
        "リード": ["西垣雅矢", "柴田大地"],
        "ビハインド": ["泰勝利", "田中千晴"],
        "敗戦処理": ["津留﨑大成"]
    },
    "西武": {
        "先発": ["隅田知一郎", "平良海馬", "髙橋光成", "武内夏暉", "渡邉勇太朗", "菅井信也"],
        "抑え": "ウィンゲンター",
        "中継ぎエース": "甲斐野央",
        "僅差": ["豆田泰志", "岩城颯空"],
        "リード": ["佐藤隼輔", "篠原響"],
        "ビハインド": ["森脇亮介", "黒田将矢"],
        "敗戦処理": ["浜屋将太"]
    }
}

def best_pitching_staff(team):
    if team.name in OPPONENT_PITCHERS:
        target = OPPONENT_PITCHERS[team.name]
        starters = []
        bullpen = []
        closer = None
        bullpen_roles = {}
        
        # 全角/半角スペース、中点、小文字化を統一して照合
        def get_p(name):
            c_name = str(name).replace(" ", "").replace(" ", "").replace("・", "").lower()
            for p in team.pitchers:
                p_clean = str(p.name).replace(" ", "").replace(" ", "").replace("・", "").lower()
                if p_clean == c_name:
                    return p
            return None

        for name in target.get("先発", []):
            player = get_p(name)
            if player: starters.append(player)
            
        c_name = target.get("抑え", "")
        if c_name:
            c_player = get_p(c_name)
            if c_player: closer = c_player

        for role in ["中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]:
            names = target.get(role, [])
            if isinstance(names, str): names = [names]
            for name in names:
                player = get_p(name)
                if player:
                    bullpen.append(player)
                    bullpen_roles[id(player)] = role
                    
        used_ids = set([id(p) for p in starters + bullpen + ([closer] if closer else [])])
        remain = [p for p in team.pitchers if id(p) not in used_ids]
        remain.sort(key=lambda x: x.stamina, reverse=True)
        
        # 万が一指定ミスで人数が足りない場合のみ、枠の上限まで補充する
        while len(starters) < 6 and remain:
            starters.append(remain.pop(0))
            
        if not closer and remain:
            remain.sort(key=lambda x: x.control, reverse=True)
            closer = remain.pop(0)
            
        # ★修正：中継ぎは「8人」で完全に打ち切る！2軍投手の1軍入りを阻止
        while len(bullpen) < 8 and remain:
            p = remain.pop(0)
            bullpen.append(p)
            bullpen_roles[id(p)] = "敗戦処理"
            
        return {
            "starters": starters,
            "bullpen": bullpen,
            "closer": closer,
            "bullpen_roles": bullpen_roles,
        }

    roles = decide_pitcher_roles(team.pitchers)
    starters = [p for p in team.pitchers if roles.get(p.name) == "先発"]
    closer_list = [p for p in team.pitchers if roles.get(p.name) == "抑え"]
    closer = closer_list[0] if closer_list else None
    bullpen = [p for p in team.pitchers if roles.get(p.name) not in ("先発", "抑え")]
    bullpen_roles = {id(p): roles.get(p.name) for p in bullpen}
    return { "starters": starters, "bullpen": bullpen, "closer": closer, "bullpen_roles": bullpen_roles }

def build_opponent_team(team, dh):
    lineup, bench = best_lineup_for_team(team, dh=dh)
    staff = best_pitching_staff(team)
    return {"team": team, "lineup": lineup, "bench": bench, "staff": staff}

# ============================================================
# 全試合スケジュールの生成
# ============================================================
def create_full_schedule(league_central, league_pacific):
    schedule_text = """
1 (3/27)	巨	神	Ｄ	ヤ	広	中	ロ	西	オ	楽	ソ	日
2 (3/28)	巨	神	Ｄ	ヤ	広	中	ロ	西	オ	楽	ソ	日
3 (3/29)	巨	神	Ｄ	ヤ	広	中	ロ	西	オ	楽	ソ	日
4 (3/31)	ヤ	広	中	巨	神	Ｄ	日	ロ	楽	ソ	西	オ
5 (4/1)	ヤ	広	中	巨	神	Ｄ	日	ロ	楽	ソ	西	オ
6 (4/2)	ヤ	広	中	巨	神	Ｄ	日	ロ	楽	ソ	西	オ
7 (4/3)	巨	Ｄ	ヤ	中	広	神	日	オ	西	楽	ロ	ソ
8 (4/4)	巨	Ｄ	ヤ	中	広	神	日	オ	西	楽	ロ	ソ
9 (4/5)	巨	Ｄ	ヤ	中	広	神	日	オ	西	楽	ロ	ソ
10 (4/7)	Ｄ	中	神	ヤ	広	巨	楽	日	オ	ロ	ソ	西
11 (4/8)	Ｄ	中	神	ヤ	広	巨	楽	日	オ	ロ	ソ	西
12 (4/9)	神	ヤ	広	巨	楽	日	オ	ロ	ソ	西
13 (4/10)	巨	ヤ	Ｄ	広	中	神	楽	オ	西	ロ
14 (4/11)	巨	ヤ	Ｄ	広	中	神	日	ソ	楽	オ	西	ロ
15 (4/12)	巨	ヤ	Ｄ	広	中	神	日	ソ	楽	オ	西	ロ
16 (4/14)	ヤ	Ｄ	中	広	神	巨	ロ	日	オ	西	ソ	楽
17 (4/15)	中	広	神	巨	ロ	日	オ	西	ソ	楽
18 (4/16)	ヤ	Ｄ	神	巨	ロ	日	オ	西	ソ	楽
19 (4/17)	ヤ	巨	神	中	広	Ｄ	日	西	楽	ロ	ソ	オ
20 (4/18)	ヤ	巨	神	中	広	Ｄ	日	西	楽	ロ	ソ	オ
21 (4/19)	ヤ	巨	神	中	広	Ｄ	日	西	楽	ロ	ソ	オ
22 (4/21)	巨	中	Ｄ	神	広	ヤ	日	楽	西	ソ	ロ	オ
23 (4/22)	巨	中	Ｄ	神	広	ヤ	日	楽	西	ソ	ロ	オ
24 (4/23)	Ｄ	神	広	ヤ	日	楽	西	ソ	ロ	オ
25 (4/24)	Ｄ	巨	中	ヤ	オ	日
26 (4/25)	Ｄ	巨	中	ヤ	神	広	楽	西	オ	日	ソ	ロ
27 (4/26)	Ｄ	巨	中	ヤ	神	広	楽	西	オ	日	ソ	ロ
28 (4/28)	巨	広	ヤ	神	中	Ｄ	西	日	ロ	楽	オ	ソ
29 (4/29)	巨	広	ヤ	神	中	Ｄ	西	日	ロ	楽	オ	ソ
30 (4/30)	巨	広	ヤ	神	中	Ｄ	西	日
31 (5/1)	ヤ	Ｄ	神	巨	広	中	日	オ	ロ	西	ソ	楽
32 (5/2)	ヤ	Ｄ	神	巨	広	中	日	オ	ロ	西	ソ	楽
33 (5/3)	ヤ	Ｄ	神	巨	広	中	日	オ	ロ	西	ソ	楽
34 (5/4)	巨	ヤ	Ｄ	広	中	神	楽	日	西	ソ	オ	ロ
35 (5/5)	巨	ヤ	Ｄ	広	中	神	楽	日	西	ソ	オ	ロ
36 (5/6)	巨	ヤ	Ｄ	広	中	神	楽	日	西	ソ	オ	ロ
37 (5/8)	中	巨	神	Ｄ	広	ヤ	西	楽	オ	日	ソ	ロ
38 (5/9)	中	巨	神	Ｄ	広	ヤ	西	楽	オ	日	ソ	ロ
39 (5/10)	中	巨	神	Ｄ	広	ヤ	西	楽	オ	日	ソ	ロ
40 (5/12)	巨	広	ヤ	神	Ｄ	中	楽	オ	ロ	日	ソ	西
41 (5/13)	巨	広	ヤ	神	Ｄ	中	ロ	日	ソ	西
42 (5/14)	Ｄ	中	楽	オ	ロ	日
43 (5/15)	巨	Ｄ	中	ヤ	神	広	日	西	楽	ソ	ロ	オ
44 (5/16)	巨	Ｄ	中	ヤ	神	広	日	西	楽	ソ	ロ	オ
45 (5/17)	巨	Ｄ	中	ヤ	神	広	日	西	楽	ソ	ロ	オ
46 (5/19)	ヤ	巨	神	中	広	Ｄ	日	楽	西	ロ	オ	ソ
47 (5/20)	ヤ	巨	神	中	広	Ｄ	日	楽	西	ロ	オ	ソ
48 (5/21)	神	中	広	Ｄ
49 (5/22)	巨	神	中	広	楽	ロ	西	オ	ソ	日
50 (5/23)	巨	神	Ｄ	ヤ	中	広	楽	ロ	西	オ	ソ	日
51 (5/24)	巨	神	Ｄ	ヤ	中	広	楽	ロ	西	オ	ソ	日
52 (5/26)	巨	ソ	ヤ	西	Ｄ	オ	中	楽	神	日	広	ロ
53 (5/27)	巨	ソ	ヤ	西	Ｄ	オ	中	楽	神	日	広	ロ
54 (5/28)	巨	ソ	ヤ	西	Ｄ	オ	中	楽	神	日	広	ロ
55 (5/29)	日	巨	楽	ヤ	西	Ｄ	ロ	神	オ	中	ソ	広
56 (5/30)	日	巨	楽	ヤ	西	Ｄ	ロ	神	オ	中	ソ	広
57 (5/31)	日	巨	楽	ヤ	西	Ｄ	ロ	神	オ	中	ソ	広
58 (6/2)	巨	オ	ヤ	ロ	Ｄ	楽	中	ソ	神	西	広	日
59 (6/3)	巨	オ	ヤ	ロ	Ｄ	楽	中	ソ	神	西	広	日
60 (6/4)	巨	オ	ヤ	ロ	Ｄ	楽	中	ソ	神	西	広	日
61 (6/5)	巨	ロ	ヤ	日	Ｄ	ソ	中	西	神	楽	広	オ
62 (6/6)	巨	ロ	ヤ	日	Ｄ	ソ	中	西	神	楽	広	オ
63 (6/7)	巨	ロ	ヤ	日	Ｄ	ソ	中	西	神	楽	広	オ
64 (6/9)	日	Ｄ	楽	巨	西	広	ロ	中	オ	ヤ	ソ	神
65 (6/10)	日	Ｄ	楽	巨	西	広	ロ	中	オ	ヤ	ソ	神
66 (6/11)	日	Ｄ	楽	巨	西	広	ロ	中	オ	ヤ	ソ	神
67 (6/12)	日	中	楽	広	西	巨	ロ	Ｄ	オ	神	ソ	ヤ
68 (6/13)	日	中	楽	広	西	巨	ロ	Ｄ	オ	神	ソ	ヤ
69 (6/14)	日	中	楽	広	西	巨	ロ	Ｄ	オ	神	ソ	ヤ
70 (6/19)	巨	中	ヤ	広	Ｄ	神	日	ソ	ロ	楽	オ	西
71 (6/20)	巨	中	ヤ	広	Ｄ	神	日	ソ	ロ	楽	オ	西
72 (6/21)	巨	中	ヤ	広	Ｄ	神	日	ソ	ロ	楽	オ	西
73 (6/22)	楽	西
74 (6/23)	中	Ｄ	神	ヤ	広	巨	日	ロ	楽	西	ソ	オ
75 (6/24)	中	Ｄ	神	ヤ	広	巨	日	ロ	ソ	オ
76 (6/25)	中	Ｄ	神	ヤ	楽	西	ソ	オ
77 (6/26)	ヤ	中	Ｄ	巨	広	神	西	日	ロ	ソ	オ	楽
78 (6/27)	ヤ	中	Ｄ	巨	広	神	西	日	ロ	ソ	オ	楽
79 (6/28)	ヤ	中	Ｄ	巨	広	神	西	日	ロ	ソ	オ	楽
80 (6/30)	巨	ヤ	Ｄ	広	神	中	日	オ	楽	ロ	ソ	西
81 (7/1)	巨	ヤ	神	中	日	オ	楽	ロ	ソ	西
82 (7/2)	Ｄ	広	神	中	日	オ	ソ	西
83 (7/3)	ヤ	Ｄ	中	巨	神	広	楽	日	オ	西	ソ	ロ
84 (7/4)	ヤ	Ｄ	中	巨	神	広	楽	日	オ	西	ソ	ロ
85 (7/5)	ヤ	Ｄ	中	巨	神	広	楽	日	オ	西	ソ	ロ
86 (7/7)	巨	神	Ｄ	中	広	ヤ	西	楽	ロ	日	オ	ソ
87 (7/8)	巨	神	Ｄ	中	広	ヤ	西	楽	ロ	日	オ	ソ
88 (7/9)	巨	神	Ｄ	中	広	ヤ
89 (7/10)	Ｄ	巨	中	広	神	ヤ	日	西	ロ	オ	ソ	楽
90 (7/11)	Ｄ	巨	中	広	神	ヤ	日	西	ロ	オ	ソ	楽
91 (7/12)	Ｄ	巨	中	広	神	ヤ	日	西	ロ	オ	ソ	楽
92 (7/14)	ヤ	巨	中	神	広	Ｄ	日	ソ	楽	オ	西	ロ
93 (7/15)	ヤ	巨	中	神	広	Ｄ	日	ソ	楽	オ	西	ロ
94 (7/16)	ヤ	巨	中	神	日	ソ	楽	オ	西	ロ
95 (7/17)	巨	中	Ｄ	ヤ	広	神
96 (7/18)	巨	中	Ｄ	ヤ	広	神	楽	西	ロ	ソ	オ	日
97 (7/19)	巨	中	Ｄ	ヤ	広	神	楽	西	ロ	ソ	オ	日
98 (7/20)	巨	広	ヤ	中	神	Ｄ	楽	西	ロ	ソ	オ	日
99 (7/21)	巨	広	ヤ	中	神	Ｄ	ソ	オ
100 (7/22)	巨	広	ヤ	中	神	Ｄ	西	日	ロ	楽	ソ	オ
101 (7/23)	西	日	ロ	楽	ソ	オ
102 (7/24)	ヤ	広	中	Ｄ	神	巨	西	ソ	オ	ロ
103 (7/25)	ヤ	広	中	Ｄ	神	巨	日	楽	西	ソ	オ	ロ
104 (7/26)	ヤ	広	中	Ｄ	神	巨	日	楽	西	ソ	オ	ロ
105 (7/31)	巨	Ｄ	ヤ	神	広	中	日	ロ	楽	ソ	西	オ
106 (8/1)	巨	Ｄ	ヤ	神	広	中	日	ロ	楽	ソ	西	オ
107 (8/2)	巨	Ｄ	ヤ	神	広	中	日	ロ	楽	ソ	西	オ
108 (8/3)	オ	楽
109 (8/4)	Ｄ	神	中	ヤ	広	巨	ロ	西	ソ	日
110 (8/5)	Ｄ	神	中	ヤ	広	巨	ロ	西	オ	楽	ソ	日
111 (8/6)	Ｄ	神	中	ヤ	広	巨	オ	楽	ソ	日
112 (8/7)	巨	ヤ	Ｄ	広	神	中	日	楽	西	ソ	ロ	オ
113 (8/8)	巨	ヤ	Ｄ	広	神	中	日	楽	西	ソ	ロ	オ
114 (8/9)	巨	ヤ	Ｄ	広	神	中	日	楽	西	ソ	ロ	オ
115 (8/11)	巨	神	ヤ	広	中	Ｄ	日	西	楽	オ	ソ	ロ
116 (8/12)	巨	神	ヤ	広	中	Ｄ	日	西	楽	オ	ソ	ロ
117 (8/13)	巨	神	ヤ	広	中	Ｄ	日	西	楽	オ	ソ	ロ
118 (8/14)	ヤ	Ｄ	中	巨	広	神	西	ロ	オ	日	ソ	楽
119 (8/15)	ヤ	Ｄ	中	巨	広	神	西	ロ	オ	日	ソ	楽
120 (8/16)	ヤ	Ｄ	中	巨	広	神	西	ロ	オ	日	ソ	楽
121 (8/18)	Ｄ	巨	神	ヤ	広	中	日	ソ	楽	ロ	西	オ
122 (8/19)	Ｄ	巨	神	ヤ	広	中	日	ソ	楽	ロ	西	オ
123 (8/20)	Ｄ	巨	神	ヤ	広	中	日	ソ	楽	ロ	西	オ
124 (8/21)	巨	広	Ｄ	神	中	ヤ	楽	西	ロ	日
125 (8/22)	巨	広	Ｄ	神	中	ヤ	楽	西	ロ	日	ソ	オ
126 (8/23)	巨	広	Ｄ	神	中	ヤ	楽	西	ロ	日	ソ	オ
127 (8/25)	ヤ	巨	中	神	広	Ｄ	西	日	ロ	ソ	オ	楽
128 (8/26)	ヤ	巨	中	神	広	Ｄ	西	日	ロ	ソ	オ	楽
129 (8/27)	ヤ	巨	中	神	広	Ｄ	ロ	ソ	オ	楽
130 (8/28)	Ｄ	中	神	巨	広	ヤ	日	ロ	西	楽	オ	ソ
131 (8/29)	Ｄ	中	神	巨	広	ヤ	日	ロ	西	楽	オ	ソ
132 (8/30)	Ｄ	中	神	巨	広	ヤ	日	ロ	西	楽	オ	ソ
133 (9/1)	巨	Ｄ	ヤ	神	中	広	日	ソ	楽	オ	ロ	西
134 (9/2)	巨	Ｄ	ヤ	神	中	広	日	ソ	楽	オ
135 (9/3)	ヤ	神	中	広
136 (9/4)	ヤ	中	広	巨	楽	日	オ	ロ	ソ	西
137 (9/5)	ヤ	中	神	Ｄ	広	巨	楽	日	オ	ロ	ソ	西
138 (9/6)	ヤ	中	神	Ｄ	広	巨	楽	日	オ	ロ	ソ	西
139 (9/8)	巨	中	Ｄ	ヤ	神	広	ロ	楽	オ	西	ソ	日
140 (9/9)	巨	中	Ｄ	ヤ	神	広	ロ	楽	オ	西	ソ	日
141 (9/10)	巨	中	Ｄ	ヤ	神	広	ロ	楽	オ	西	ソ	日
142 (9/11)	広	Ｄ
143 (9/12)	巨	神	中	ヤ	広	Ｄ	西	日	オ	楽	ソ	ロ
144 (9/13)	ヤ	広	Ｄ	巨	神	中	西	日	ソ	ロ
145 (9/15)	日	ロ	楽	西	オ	ソ
146 (9/16)	ロ	楽	オ	ソ
147 (9/17)	日	西	ロ	楽	オ	ソ
148 (9/18)	巨	中	Ｄ	ヤ	神	広
149 (9/19)	巨	中	Ｄ	ヤ	神	広	日	オ	楽	ソ	ロ	西
150 (9/20)	巨	ヤ	中	広	神	Ｄ	日	オ	楽	ソ	ロ	西
151 (9/21)	ヤ	神	中	広	神	Ｄ	日	オ	楽	ソ	ロ	西
152 (9/22)	ヤ	神	Ｄ	中	広	巨	日	楽	ソ	西
153 (9/23)	Ｄ	中	広	巨	日	楽	ロ	オ	ソ	西
154 (9/24)	日	楽
155 (9/25)	西	ロ	オ	ソ
156 (9/26)	西	ロ	オ	日	ソ	楽
157 (9/27)	西	楽	ロ	日	ソ	オ
158 (9/28)	西	楽	ロ	日
159 (9/29)	楽	ロ	西	オ
160 (9/30)	楽	ロ
"""
    # 短縮名とシステム上のチーム名を紐付け
    team_map = {
        "神": "阪神", "Ｄ": "DeNA", "巨": "巨人", "ヤ": "ヤクルト", "中": "中日", "広": "広島",
        "日": "日本ハム", "ロ": "ロッテ", "楽": "楽天", "西": "西武", "オ": "オリックス", "ソ": "ソフトバンク"
    }
    
    full_schedule = []
    
    # いただいたテキストを行ごとに分割して読み込み
    for line in schedule_text.strip().split("\n"):
        parts = line.split() # タブや空白で分割
        
        # parts[0]は「1」、parts[1]は「(3/27)」。parts[2]以降にチーム名が「ホーム」「ビジター」の順に並ぶ
        if len(parts) < 4:
            continue
            
        # チーム名を2つ（ホームとビジター）ずつ取り出す
        for i in range(2, len(parts), 2):
            if i + 1 < len(parts):
                h_abbr = parts[i]
                v_abbr = parts[i+1]
                
                if h_abbr in team_map and v_abbr in team_map:
                    h_team = team_map[h_abbr]
                    v_team = team_map[v_abbr]
                    
                    # ホームチームがパ・リーグならDHあり（パ・リーグ）、セ・リーグならDHなし（セ・リーグ）
                    league_rule = "パ・リーグ" if h_team in league_pacific else "セ・リーグ"
                    full_schedule.append({"home": h_team, "away": v_team, "league": league_rule})
                    
    return full_schedule

def reset_stats(players):
    for p in players:
        p.batting = BatterStats()
        p.pitching = PitcherStats()
        p.fielding = FielderStats()
        p.current_stamina = p.stamina
        p.consecutive_games = 0
        p.did_pitch_today = False
        p.game_pitches_today = 0
        p.force_continue_outs = 0

# ============================================================
# 能力値 → 確率 （2段階抽選システム）
# ============================================================
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def choose_pitch(pitcher):
    if not pitcher.pitches:
        return None
    names = list(pitcher.pitches.keys())
    weights = [max(1.0, pitcher.pitches[n]) for n in names]
    return random.choices(names, weights=weights, k=1)[0]

def fatigue_factor(pitcher, game_outs):
    innings = game_outs / 3.0
    if innings <= 4:
        return 1.0
    excess = innings - 4
    penalty = excess * max(0.0, (80.0 - pitcher.stamina)) * 0.0015
    return clamp(1.0 - penalty, 0.82, 1.0)

def at_bat_probabilities(batter, pitcher, game_outs):
    pitch_name = choose_pitch(pitcher)
    pitch_quality = pitcher.pitches.get(pitch_name, 50.0) if pitch_name else 50.0
    
    p_pow = getattr(pitcher, 'pitch_power_base', 50.0)
    p_ctrl = pitcher.control

    so_quality = (pitch_quality * 0.4) + (p_pow * 0.4) + (p_ctrl * 0.2) + 5.0
    bb_quality = (p_ctrl * 0.8) + (pitch_quality * 0.2) + 5.0
    batted_quality = (p_pow * 0.4) + (pitch_quality * 0.4) + (p_ctrl * 0.2) + 5.0

    fatigue = fatigue_factor(pitcher, game_outs)
    bb_diff = bb_quality - 50.0
    raw_contact_diff = batter.contact - so_quality

    contact_penalty = 0.0
    if batter.contact < 45.0:
        effective_contact = max(40.0, batter.contact)
        diff = 45.0 - effective_contact
        contact_penalty = (diff * 0.4) + ((diff ** 2) * 0.01)

    power_penalty = 0.0
    if batter.power < 60.0:
        effective_power = max(40.0, batter.power)
        diff = 60.0 - effective_power
        power_penalty = (diff * 0.4) + ((diff ** 2) * 0.01)

    pitch_variety = len(pitcher.pitches)
    variety_debuff = max(0, pitch_variety - 2) * 0.0015

    walk_bonus = 0.0
    if batter.power > 50.0: walk_bonus += (batter.power - 50.0) * 0.0012
    if batter.contact > 50.0: walk_bonus += (batter.contact - 50.0) * 0.0006
    if batter.power >= 80.0: walk_bonus += (batter.power - 80.0) * 0.0015

    # ====================================================
    # 【ステップ1】 三振・四球・インプレーの3択
    # ====================================================
    base_walk = 0.055  
    base_so = 0.185    

    walk = base_walk - (bb_diff * 0.0015) + walk_bonus
    so_quality_delta = so_quality - 60.0
    so = base_so - (raw_contact_diff * 0.0008) + (contact_penalty * 0.0015) + (power_penalty * 0.0008) + variety_debuff + (so_quality_delta * 0.0055)

    if fatigue < 1.0:
        walk += (1.0 - fatigue) * 0.02
        so -= (1.0 - fatigue) * 0.03

    walk = clamp(walk, 0.010, 0.20)
    so = clamp(so, 0.05, 0.45)
    in_play = max(0.20, 1.0 - (walk + so))
    
    total_step1 = walk + so + in_play
    step1_probs = [("walk", walk / total_step1), ("so", so / total_step1), ("in_play", in_play / total_step1)]

    return step1_probs, pitch_name

def resolve_statcast_in_play(batter, pitcher, defense):
    gb_prob = 0.45; fb_prob = 0.25; ld_prob = 0.20; pu_prob = 0.10
    
    # ====================================================
    # ▼ 打者の能力による補正
    # ====================================================
    if batter.power > 65: fb_prob += 0.05; gb_prob -= 0.05
    if getattr(batter, 'contact', 50) > 65: ld_prob += 0.05; pu_prob -= 0.05

    # ====================================================
    # ▼ 投手の能力による補正（ここが追加部分！）
    # ====================================================
    p_pow = getattr(pitcher, 'pitch_power_base', 50.0)
    p_ctrl = pitcher.control

    if p_ctrl > 55.0:
        # 制球が高いと、低めに集めて「ゴロ」を打たせる（鋭い打球が減る）
        bonus = (p_ctrl - 55.0) * 0.0025
        gb_prob += bonus
        ld_prob -= bonus / 2
        fb_prob -= bonus / 2

    if p_pow > 55.0:
        # 球威が高いと、力で押し込んで「ポップフライ」にする（鋭い打球が減る）
        bonus = (p_pow - 55.0) * 0.0025
        pu_prob += bonus
        ld_prob -= bonus / 2
        fb_prob -= bonus / 2

    # 確率がマイナスにならないようにガード
    gb_prob = max(0.05, gb_prob)
    fb_prob = max(0.05, fb_prob)
    ld_prob = max(0.05, ld_prob)
    pu_prob = max(0.01, pu_prob)
        
    batted_type = random.choices(["GB", "FB", "LD", "PU"], weights=[gb_prob, fb_prob, ld_prob, pu_prob])[0]
    
    if batted_type == "PU": pos = random.choices(["C", "1B", "2B", "3B", "SS"], weights=[0.2, 0.2, 0.2, 0.2, 0.2])[0]
    elif batted_type == "GB": pos = random.choices(["1B", "2B", "3B", "SS"], weights=[0.15, 0.35, 0.15, 0.35])[0]
    elif batted_type == "FB": pos = random.choices(["LF", "CF", "RF"], weights=[0.33, 0.34, 0.33])[0]
    else: pos = random.choices(["1B", "2B", "3B", "SS", "LF", "CF", "RF"], weights=[0.05, 0.10, 0.05, 0.10, 0.20, 0.30, 0.20])[0]
        
    defender = defense.get(pos)
    ability = defender.defense_at(pos) if defender else 30.0
    
    pos_base_error = {"3B": 0.045, "SS": 0.030, "2B": 0.020, "1B": 0.010, "LF": 0.005, "CF": 0.005, "RF": 0.005, "C": 0.003}
    base_err = pos_base_error.get(pos, 0.02)
    
    outcome = "out"
    
    if batted_type == "GB":
        base_reach = 0.75
        reach_prob = 0.35 if ability == 0.0 else clamp(base_reach + (ability - 55.0)*0.006, 0.40, 0.95)
        if random.random() > reach_prob:
            # ▼ 修正：ゴロが1・3塁線を抜けて二塁打になる確率を 20% → 10% に減少
            outcome = "double" if pos in ["1B", "3B"] and random.random() < 0.10 else "single"
        else:
            err_prob = 0.20 if ability == 0.0 else clamp(base_err * (1.0 + (55.0 - ability)/40.0), base_err*0.2, base_err*3.0)
            outcome = "error" if random.random() < err_prob else "out"
            
    elif batted_type == "FB":
        # ▼ 修正：パワーによるHR率を劇的に引き上げ（パワー依存の二次関数で爆発的に増える）
        diff = max(0.0, batter.power - 40.0)
        hr_prob = clamp((diff * 0.004) + ((diff ** 2) * 0.00015), 0.0, 0.65)
        
        if random.random() < hr_prob:
            outcome = "hr"
        else:
            base_reach = 0.85
            reach_prob = 0.30 if ability == 0.0 else clamp(base_reach + (ability - 55.0)*0.005, 0.40, 0.99)
            if random.random() > reach_prob:
                # ▼ 修正：外野に落ちたフライが二塁打になる確率を 50% → 30% に減少
                outcome = random.choices(["single", "double", "triple"], weights=[0.65, 0.30, 0.05])[0]
            else:
                err_prob = 0.10 if ability == 0.0 else clamp(base_err * (1.0 + (55.0 - ability)/40.0), base_err*0.2, base_err*3.0)
                outcome = "error" if random.random() < err_prob else "out"
                
    elif batted_type == "LD":
        base_reach = 0.30
        reach_prob = 0.10 if ability == 0.0 else clamp(base_reach + (ability - 55.0)*0.005, 0.10, 0.60)
        if random.random() > reach_prob:
            # ▼ 修正：外野を抜けるライナーが二塁打になる確率を 40% → 25% に減少
            outcome = random.choices(["single", "double", "triple"], weights=[0.70, 0.25, 0.05])[0]
        else:
            err_prob = 0.15 if ability == 0.0 else clamp(base_err * (1.0 + (55.0 - ability)/40.0), base_err*0.2, base_err*3.0)
            outcome = "error" if random.random() < err_prob else "out"
            
    elif batted_type == "PU":
        base_reach = 0.98
        reach_prob = 0.60 if ability == 0.0 else clamp(base_reach + (ability - 55.0)*0.002, 0.60, 1.0)
        if random.random() > reach_prob:
            outcome = "single"
        else:
            err_prob = 0.15 if ability == 0.0 else clamp(base_err * (1.0 + (55.0 - ability)/40.0), base_err*0.2, base_err*3.0)
            outcome = "error" if random.random() < err_prob else "out"
            
    return outcome, pos, defender

def choose_result(probs, batter, pitcher, defense):
    r1 = random.random()
    cumulative1 = 0.0
    step1_result = "in_play"
    for result, prob in probs:
        cumulative1 += prob
        if r1 <= cumulative1:
            step1_result = result
            break
            
    if step1_result in ("so", "walk"):
        return step1_result, None, None
        
    # ▼ ピッチャーの情報も渡すように変更！
    return resolve_statcast_in_play(batter, pitcher, defense)

# ============================================================
# 走者処理
# ============================================================
def advance_on_hit(bases, batter, result):
    new_bases = [None, None, None]
    runs = 0
    scoring = []
    if result == "hr":
        for runner in bases:
            if runner is not None:
                runs += 1
                scoring.append(runner)
        runs += 1
        scoring.append(batter)
        return new_bases, runs, scoring
    if result == "triple":
        for runner in bases:
            if runner is not None:
                runs += 1
                scoring.append(runner)
        new_bases[2] = batter
        return new_bases, runs, scoring
    if result == "double":
        if bases[2] is not None:
            runs += 1
            scoring.append(bases[2])
        if bases[1] is not None:
            if random.random() < clamp(0.55 + bases[1].speed / 300.0, 0.55, 0.90):
                runs += 1
                scoring.append(bases[1])
            else: new_bases[2] = bases[1]
        if bases[0] is not None:
            if random.random() < clamp(0.30 + bases[0].speed / 250.0, 0.30, 0.82):
                runs += 1
                scoring.append(bases[0])
            else: new_bases[2] = bases[0]
        new_bases[1] = batter
        return new_bases, runs, scoring

    if bases[2] is not None:
        runs += 1
        scoring.append(bases[2])
    if bases[1] is not None:
        if random.random() < clamp(0.55 + bases[1].speed / 250.0, 0.55, 0.95):
            runs += 1
            scoring.append(bases[1])
        else: new_bases[2] = bases[1]
    if bases[0] is not None:
        if random.random() < clamp(0.25 + bases[0].speed / 300.0, 0.10, 0.70):
            new_bases[2] = bases[0]
        else: new_bases[1] = bases[0]
    new_bases[0] = batter
    return new_bases, runs, scoring

def advance_on_walk(bases, batter):
    new_bases = list(bases)
    runs = 0
    scoring = []
    if bases[0] is not None and bases[1] is not None and bases[2] is not None:
        runs = 1
        scoring.append(bases[2])
    if bases[0] is not None and bases[1] is not None: new_bases[2] = bases[1]
    if bases[0] is not None: new_bases[1] = bases[0]
    new_bases[0] = batter
    return new_bases, runs, scoring

def attempt_steal(bases, offense_lineup, defense, game_state=None):
    catcher = defense.get("C")
    if catcher is None: return bases
    candidates = []
    if bases[0] is not None and bases[1] is None: candidates.append((0, 1))
    if bases[1] is not None and bases[2] is None: candidates.append((1, 2))
    if not candidates: return bases
    from_base, to_base = candidates[0]
    runner = bases[from_base]

    if from_base == 0: attempt_prob = 0.01 + max(0.0, runner.speed - 40.0) * 0.003
    else: attempt_prob = 0.002 + max(0.0, runner.speed - 65.0) * 0.002
    attempt_prob = clamp(attempt_prob, 0.005, 0.35)

    if random.random() >= attempt_prob: return bases

    success_prob = 0.70 + (runner.speed - 50.0) * 0.008 - (catcher.defense_at("C") - 50.0) * 0.006
    success_prob = clamp(success_prob, 0.10, 0.95)

    if random.random() < success_prob:
        bases[from_base] = None
        bases[to_base] = runner
        runner.batting.SB += 1
    else:
        bases[from_base] = None
        runner.batting.CS += 1
        if game_state is not None: game_state["outs"] += 1
    return bases

# ============================================================
# 試合用投手交代
# ============================================================
class PitchingState:
    def __init__(self, staff):
        self.starters = staff.get("starters", [])
        self.bullpen = staff.get("bullpen", [])
        self.closer = staff.get("closer")
        self.bullpen_roles = staff.get("bullpen_roles", {})
        self.current = None
        self.current_start_outs = 0
        self.used_bullpen = []
        self.appearance_start_outs = {}
        self.hold_eligible = {}
        self.save_eligible = False
        self.game_pitchers = []
        self.game_holds = []
        self.pitcher_runs = defaultdict(int)
        self.pitcher_earned = defaultdict(int)
        self.max_pitches = {} 
        self.entry_score_diff = {}

    def get_role(self, pitcher):
        if pitcher in self.starters: return "先発"
        if pitcher is self.closer: return "抑え"
        return self.bullpen_roles.get(id(pitcher), "僅差")

    def get_role_priority(self, inning, score_diff):
        if 9 <= inning <= 12 and 1 <= score_diff <= 4: return ["抑え", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]
        elif inning == 12 and score_diff == 0: return ["抑え", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]
        elif 6 <= inning <= 8 and 1 <= score_diff <= 3: return ["中継ぎエース", "僅差", "リード", "抑え", "ビハインド", "敗戦処理"]
        elif 1 <= inning <= 8 and score_diff >= 4: return ["リード", "僅差", "中継ぎエース", "ビハインド", "抑え", "敗戦処理"]
        elif 9 <= inning <= 12 and score_diff >= 4: return ["リード", "抑え", "中継ぎエース", "僅差", "ビハインド", "敗戦処理"]
        elif 1 <= inning <= 9 and -3 <= score_diff <= -1: return ["ビハインド", "敗戦処理", "リード", "僅差", "中継ぎエース", "抑え"]
        elif 1 <= inning <= 9 and score_diff <= -4: return ["敗戦処理", "ビハインド", "リード", "僅差", "中継ぎエース", "抑え"]
        elif 6 <= inning <= 8 and score_diff == 0: return ["僅差", "中継ぎエース", "リード", "抑え", "ビハインド", "敗戦処理"]
        elif 1 <= inning <= 5 and score_diff >= 0: return ["リード", "僅差", "ビハインド", "中継ぎエース", "敗戦処理", "抑え"]
        if inning >= 10 and score_diff < 0: return ["ビハインド", "僅差", "リード", "敗戦処理", "中継ぎエース", "抑え"]
        if inning >= 9 and score_diff == 0: return ["抑え", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]
        return ["僅差", "中継ぎエース", "ビハインド", "リード", "敗戦処理", "抑え"]

    def choose_starter(self, game_number):
        if not self.starters: return None
        self.current = self.starters[game_number % len(self.starters)]
        self.current.game_pitches_today = 0 
        self.current.did_pitch_today = True
        self.current_start_outs = 0
        self.appearance_start_outs[id(self.current)] = self.current.pitching.outs
        self.current.pitching.G += 1
        self.current.pitching.GS += 1
        self.game_pitchers.append(self.current)
        return self.current

    def should_replace(self, score_diff, inning, outs):
        p = self.current
        if p is None: return False
        p_id = id(p)
        runs = self.pitcher_runs[p_id]
        current_outs = self.current_start_outs

        # ▼ 【追加】中継ぎの回跨ぎ禁止ルール（リード＆3点差以内の勝ちパターンの場合のみ）
        if p not in self.starters and current_outs >= 3:
            if 1 <= score_diff <= 3 and p != self.closer:
                return True

        # ▼ 【追加】9回のセーブシチュエーションなら抑えに強制交代
        if inning >= 9 and 1 <= score_diff <= 3 and self.closer and p != self.closer:
            # 抑えが「まだ今日投げていない」かつ「3連投以内（4連投回避）」なら絶対に出す
            if getattr(self.closer, 'game_pitches_today', 0) == 0 and getattr(self.closer, 'consecutive_games', 0) < 3:
                return True

        pitches = p.game_pitches_today
        if p_id not in self.max_pitches:
            # ▼ 追加：先発投手でスタミナが53以下の場合は、調子係数を厳しめに設定
            if p in self.starters and p.current_stamina <= 53.0:
                limit = p.current_stamina * random.uniform(0.8, 1.1) + 20
            else:
                limit = p.current_stamina * random.uniform(1.1, 1.3) + 20
                
            if p not in self.starters: limit = min(limit, 45)
            self.max_pitches[p_id] = max(15, limit)
        max_limit = self.max_pitches[p_id]
        
        is_stamina_empty = pitches >= max_limit
        role = self.get_role(p)

        if runs >= 6: return True
        if runs >= 5 and current_outs >= 9: return True
        if runs >= 4 and current_outs >= 15: return True
        if runs >= 3 and current_outs >= 18: return True
        if is_stamina_empty: return True
        if p in self.starters: return False
        if role in ["僅差", "中継ぎエース", "抑え"] and current_outs > 0: return True
        if p.force_continue_outs > 0 and current_outs < p.force_continue_outs: return False
        priority = self.get_role_priority(inning, score_diff)
        if priority and role == priority[0]: return False
        return True

    def _select_bullpen(self, inning, score_diff):
        priority = self.get_role_priority(inning, score_diff)
        available = []
        all_bullpen = self.bullpen + ([self.closer] if self.closer else [])
        for p in all_bullpen:
            if p in self.used_bullpen: continue
            if getattr(p, 'consecutive_games', 0) >= 3: continue
            if getattr(p, 'current_stamina', 50) < 10: continue
            available.append(p)

        fresh_available = [p for p in available if getattr(p, 'consecutive_games', 0) < 3]

        def pick_by_priority(pool, prio_list):
            for r in prio_list:
                candidates = [p for p in pool if self.get_role(p) == r]
                if candidates:
                    candidates.sort(key=lambda x: getattr(x, 'current_stamina', 0), reverse=True)
                    return candidates[0]
            return None

        selected = None
        if fresh_available: selected = pick_by_priority(fresh_available, priority)
        if selected is None and available: selected = pick_by_priority(available, priority)
        if selected is None:
            emergency = [p for p in all_bullpen if p not in self.used_bullpen]
            if emergency:
                emergency.sort(key=lambda x: getattr(x, 'current_stamina', 0), reverse=True)
                selected = emergency[0]
            else: return None 

        if selected:
            role = self.get_role(selected)
            if role == "リード" and priority[0] == "リード" and score_diff >= 4:
                if random.random() < 0.50: selected.force_continue_outs = 6
            elif role == "敗戦処理" and priority[0] == "敗戦処理":
                if random.random() < 0.40: selected.force_continue_outs = 9
                else: selected.force_continue_outs = 6
        return selected

    def replace(self, inning, score_diff):
        old = self.current
        if old is None: return None
        new = self._select_bullpen(inning, score_diff)
        if new is None or new is old: return self.current

        old_id = id(old)
        entered_score = self.hold_eligible.get(old_id)
        if old in self.bullpen and entered_score is not None:
            outs_got = old.pitching.outs - self.appearance_start_outs.get(old_id, old.pitching.outs)
            if outs_got > 0 and old is not self.closer:
                is_hold = False
                if 1 <= entered_score <= 3 and score_diff > 0: is_hold = True
                elif entered_score >= 4 and score_diff > 0 and outs_got >= 9: is_hold = True
                elif entered_score == 0 and score_diff >= 0: is_hold = True
                if is_hold:
                    old.pitching.HLD += 1
                    self.game_holds.append(old)

        if new not in self.used_bullpen and (new in self.bullpen or new is self.closer):
            self.used_bullpen.append(new)

        new.game_pitches_today = 0 
        new.did_pitch_today = True
        new.pitching.G += 1
        self.game_pitchers.append(new)
        self.current = new
        self.current_start_outs = 0
        self.appearance_start_outs[id(new)] = new.pitching.outs
        self.entry_score_diff[id(new)] = score_diff
        if new in self.bullpen: self.hold_eligible[id(new)] = score_diff
        return self.current

# ============================================================
# 1試合シミュレーションロジック
# ============================================================
def simulate_half_inning(offense_lineup, batting_index, pitcher, defense, league, inning=1, top_bottom="表", game_state=None, bench_player=None):
    outs = 0
    bases = [None, None, None]
    runs = 0
    hr_log = []

    if game_state is None: game_state = {}

    while outs < 3:
        steal_state = {"outs": outs}
        before_outs = outs
        bases = attempt_steal(bases, offense_lineup, defense, steal_state)
        outs = steal_state["outs"]
        if outs > before_outs: pitcher.pitching.outs += (outs - before_outs)
        if outs >= 3: break

        if any(bases):
            catcher = defense.get("C")
            c_def = catcher.defense_at("C") if catcher else 30.0
            
            if catcher and c_def == 0.0:
                pb_prob = 0.10  
            else:
                pb_prob = clamp(0.003 - c_def * 0.00003, 0.0005, 0.005)
                
            wp_prob = clamp(0.004 - pitcher.control * 0.00004, 0.0005, 0.005)
            
            if random.random() < (pb_prob + wp_prob):
                new_bases = [None, None, None]
                if bases[2] is not None:
                    runs += 1
                    bases[2].batting.R += 1
                if bases[1] is not None: new_bases[2] = bases[1]
                if bases[0] is not None: new_bases[1] = bases[0]
                bases = new_bases
                
                if catcher and random.random() < pb_prob / (pb_prob + wp_prob):
                    catcher.fielding.PB += 1
                    catcher.fielding.UZR -= 0.3

        batter_tuple = offense_lineup[batting_index[0] % len(offense_lineup)]
        if isinstance(batter_tuple, tuple):
            batter = batter_tuple[0]
            is_pitcher = (batter_tuple[1] == "P")
        else:
            batter = batter_tuple
            is_pitcher = False

        if is_pitcher and bench_player and not game_state.get("used_pinch_hitter"):
            is_scoring_pos = (bases[1] is not None or bases[2] is not None)
            is_tired = (batter.game_pitches_today >= batter.stamina + 10) or (batter.pitching.R >= 3)
            
            if inning >= 6 and (is_scoring_pos or is_tired):
                batter = bench_player
                game_state["used_pinch_hitter"] = True

        batting_index[0] += 1
        batter.batting.PA += 1
        pitcher.pitching.BF += 1

        if is_pitcher and batter == batter_tuple[0]:
            calc_batter = copy.copy(batter)
            calc_batter.contact = 18.0
            calc_batter.power = 18.0
            calc_batter.speed = 40.0
        else:
            calc_batter = batter

        probs, pitch_name = at_bat_probabilities(calc_batter, pitcher, pitcher.pitching.outs)
        result, pos, defender = choose_result(probs, calc_batter, pitcher, defense)
        
        if result in ("so", "walk"): pa_pitches = random.randint(4, 8)
        else: pa_pitches = random.randint(1, 6)
        pitcher.game_pitches_today = getattr(pitcher, 'game_pitches_today', 0) + pa_pitches
        pitcher.did_pitch_today = True

        if result in ("single", "double", "triple", "hr", "error", "hidden_hit"):
            batter.batting.AB += 1
            if result != "error":
                batter.batting.H += 1
            else:
                if defender is not None:
                    defender.fielding.E += 1
                    defender.fielding.UZR -= 0.5 + max(0.0, (50.0 - defender.defense_at(pos)) / 100.0)

            if result == "hr":
                runners_on = sum(1 for runner in bases if runner is not None)
                run_type_char = {0: "①", 1: "②", 2: "③", 3: "④"}[runners_on]
                batter.batting.HR += 1
                hr_log.append(f"{inning}回{top_bottom} {batter.name} {batter.batting.HR}号{run_type_char}")
                batter.batting.TB += 4
                pitcher.pitching.HR += 1
            elif result in ("single", "error", "hidden_hit"):
                if result != "error": batter.batting.TB += 1
            elif result == "double": batter.batting.double += 1; batter.batting.TB += 2
            elif result == "triple": batter.batting.triple += 1; batter.batting.TB += 3
            
            if result not in ("error",): pitcher.pitching.H += 1
            
            old_bases = list(bases)
            adv_res = "single" if result in ("error", "hidden_hit") else result
            bases, scored, scoring = advance_on_hit(old_bases, batter, adv_res)
            runs += scored
            if scored: batter.batting.RBI += scored
            for runner in scoring: runner.batting.R += 1
            if result == "hr": batter.batting.R += 1
                
        elif result == "walk":
            batter.batting.BB += 1
            pitcher.pitching.BB += 1
            bases, scored, scoring = advance_on_walk(bases, batter)
            runs += scored
            if scored: batter.batting.RBI += scored
            for runner in scoring: runner.batting.R += 1
                
        elif result == "so":
            batter.batting.AB += 1
            batter.batting.SO += 1
            pitcher.pitching.SO += 1
            outs += 1
            pitcher.pitching.outs += 1
            
        elif result in ("out", "field_out"):
            outs += 1
            pitcher.pitching.outs += 1
            if defender is not None: 
                defender.fielding.PO += 1
                defender.fielding.UZR += (defender.defense_at(pos) - 50.0) / 1200.0
            
            is_sf = False
            if outs <= 2 and bases[2] is not None:
                runner = bases[2]
                arm = defender.defense_at(pos) if defender else 30.0
                if pos in ["LF", "CF", "RF"]:
                    sf_prob = clamp(0.50 + (runner.speed - arm) * 0.008, 0.05, 0.95)
                    if random.random() < sf_prob:
                        runs += 1
                        batter.batting.RBI += 1
                        runner.batting.R += 1
                        batter.batting.SF += 1
                        bases[2] = None
                        is_sf = True
                elif pos in ["1B", "2B", "3B", "SS"]:
                    run_prob = clamp(0.25 + (runner.speed - arm) * 0.005, 0.02, 0.85)
                    if random.random() < run_prob:
                        runs += 1
                        batter.batting.RBI += 1
                        runner.batting.R += 1
                        bases[2] = None
            if not is_sf: batter.batting.AB += 1
            
            if outs <= 2 and bases[2] is None and bases[1] is not None:
                runner2 = bases[1]
                arm = defender.defense_at(pos) if defender else 30.0
                adv_prob = 0.0
                if pos == "RF": adv_prob = 0.55 + (runner2.speed - arm) * 0.005
                elif pos == "CF": adv_prob = 0.25 + (runner2.speed - arm) * 0.004
                elif pos == "LF": adv_prob = 0.05
                elif pos in ["1B", "2B"]: adv_prob = 0.50 + (runner2.speed - arm) * 0.005
                elif pos in ["3B", "SS"]: adv_prob = 0.10 + (runner2.speed - arm) * 0.003
                if random.random() < clamp(adv_prob, 0.05, 0.90):
                    bases[2] = runner2
                    bases[1] = None
            if outs <= 2 and bases[1] is None and bases[0] is not None:
                runner1 = bases[0]
                arm = defender.defense_at(pos) if defender else 30.0
                adv_prob = 0.0
                if pos in ["1B", "2B", "3B", "SS"]: adv_prob = 0.35 + (runner1.speed - arm) * 0.004
                if random.random() < clamp(adv_prob, 0.01, 0.40):
                    bases[1] = runner1
                    bases[0] = None

    return runs, hr_log

def simulate_game(my_lineup, my_staff, op_lineup, op_staff, league, my_game_number, op_game_number, my_bench=None, op_bench=None):
    my_pitching = PitchingState(my_staff)
    op_pitching = PitchingState(op_staff)

    my_pitcher = my_pitching.choose_starter(my_game_number)
    op_pitcher = op_pitching.choose_starter(op_game_number)

    lead_state = 0
    my_por = my_pitcher
    op_por = op_pitcher

    my_score = 0
    op_score = 0
    my_batting_index = [0]
    op_batting_index = [0]
    
    op_linescore = []
    my_linescore = []
    hr_events = []
    
    my_game_state = {"used_pinch_hitter": False}
    op_game_state = {"used_pinch_hitter": False}

    for p, _ in my_lineup: p.batting.G += 1
    for p, _ in op_lineup: p.batting.G += 1
    if league == "セ・リーグ":
        if my_pitcher: my_pitcher.batting.G += 1
        if op_pitcher: op_pitcher.batting.G += 1

    for inning in range(1, 13):
        # --- 1回表 ---
        if my_pitching.should_replace(my_score - op_score, inning, my_pitcher.pitching.outs if my_pitcher else 0):
            my_pitcher = my_pitching.replace(inning, my_score - op_score)

        defense_my = {pos: player for player, pos in my_lineup if pos != "DH"}
        offense_op = list(op_lineup)
        if league == "セ・リーグ" and op_pitcher:
            if len(offense_op) == 8: offense_op.append((op_pitcher, "P"))

        if my_pitcher:
            r_op, hrs_op = simulate_half_inning(offense_op, op_batting_index, my_pitcher, defense_my, league, inning=inning, top_bottom="表", game_state=op_game_state, bench_player=op_bench)
        else:
            r_op, hrs_op = 0, []
            
        op_score += r_op
        op_linescore.append(str(r_op))
        hr_events.extend(hrs_op)
        
        if my_pitcher:
            my_pitching.current_start_outs = (my_pitcher.pitching.outs - my_pitching.appearance_start_outs.get(id(my_pitcher), my_pitcher.pitching.outs))
            my_pitching.pitcher_runs[id(my_pitcher)] += r_op
            my_pitching.pitcher_earned[id(my_pitcher)] += r_op
            my_pitcher.pitching.R += r_op
            my_pitcher.pitching.ER += r_op

        if op_score > my_score and lead_state != -1:
            lead_state = -1
            my_por = my_pitcher
            op_por = op_pitcher
        elif op_score == my_score: lead_state = 0

        if inning >= 9 and my_score > op_score:
            my_linescore.append("X")
            break

        # --- 1回裏 ---
        if op_pitching.should_replace(op_score - my_score, inning, op_pitcher.pitching.outs if op_pitcher else 0):
            op_pitcher = op_pitching.replace(inning, op_score - my_score)

        defense_op = {pos: player for player, pos in op_lineup if pos != "DH"}
        offense_my = list(my_lineup)
        if league == "セ・リーグ" and my_pitcher:
            if len(offense_my) == 8: offense_my.append((my_pitcher, "P"))

        if op_pitcher:
            r_my, hrs_my = simulate_half_inning(offense_my, my_batting_index, op_pitcher, defense_op, league, inning=inning, top_bottom="裏", game_state=my_game_state, bench_player=my_bench)
        else:
            r_my, hrs_my = 0, []
            
        my_score += r_my
        my_linescore.append(str(r_my))
        hr_events.extend(hrs_my)
        
        if op_pitcher:
            op_pitching.current_start_outs = (op_pitcher.pitching.outs - op_pitching.appearance_start_outs.get(id(op_pitcher), op_pitcher.pitching.outs))
            op_pitching.pitcher_runs[id(op_pitcher)] += r_my
            op_pitching.pitcher_earned[id(op_pitcher)] += r_my
            op_pitcher.pitching.R += r_my
            op_pitcher.pitching.ER += r_my

        if my_score > op_score and lead_state != 1:
            lead_state = 1
            my_por = my_pitcher
            op_por = op_pitcher
        elif my_score == op_score: lead_state = 0

        if inning >= 9 and my_score != op_score: break

    def resolve_win(win_pitching_state, win_por):
        win_p = win_por
        if win_p and win_p in win_pitching_state.starters:
            outs = win_p.pitching.outs - win_pitching_state.appearance_start_outs.get(id(win_p), win_p.pitching.outs)
            if outs < 15:
                relievers = [p for p in win_pitching_state.game_pitchers if p not in win_pitching_state.starters]
                if relievers:
                    pitcher_outs = [(p, p.pitching.outs - win_pitching_state.appearance_start_outs.get(id(p), p.pitching.outs)) for p in relievers]
                    max_outs = max((o for p, o in pitcher_outs), default=0)
                    candidates = [p for p, o in pitcher_outs if o == max_outs]
                    if candidates: win_p = random.choice(candidates)
        return win_p

    save_pitcher = None
    if my_score > op_score:
        winning_pitcher = resolve_win(my_pitching, my_por)
        losing_pitcher = op_por
        if winning_pitcher is not None:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in my_pitching.game_holds:
                winning_pitcher.pitching.HLD -= 1 
                my_pitching.game_holds.remove(winning_pitcher)
        if losing_pitcher is not None: losing_pitcher.pitching.L += 1
        finishing_pitcher = my_pitcher
        if finishing_pitcher and finishing_pitcher not in my_pitching.starters and finishing_pitcher is not winning_pitcher:
            f_id = id(finishing_pitcher)
            entry_diff = my_pitching.entry_score_diff.get(f_id)
            if entry_diff is not None and entry_diff > 0:
                outs_got = finishing_pitcher.pitching.outs - my_pitching.appearance_start_outs.get(f_id, finishing_pitcher.pitching.outs)
                if (1 <= entry_diff <= 3) or outs_got >= 9:
                    finishing_pitcher.pitching.SV += 1
                    save_pitcher = finishing_pitcher
                    if finishing_pitcher in my_pitching.game_holds:
                        finishing_pitcher.pitching.HLD -= 1
                        my_pitching.game_holds.remove(finishing_pitcher)
        return my_score, op_score, {"result": "W", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

    elif my_score < op_score:
        winning_pitcher = resolve_win(op_pitching, op_por)
        losing_pitcher = my_por
        if winning_pitcher is not None:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in op_pitching.game_holds:
                winning_pitcher.pitching.HLD -= 1 
                op_pitching.game_holds.remove(winning_pitcher)
        if losing_pitcher is not None: losing_pitcher.pitching.L += 1
        finishing_pitcher = op_pitcher
        if finishing_pitcher and finishing_pitcher not in op_pitching.starters and finishing_pitcher is not winning_pitcher:
            f_id = id(finishing_pitcher)
            entry_diff = op_pitching.entry_score_diff.get(f_id)
            if entry_diff is not None and entry_diff > 0:
                outs_got = finishing_pitcher.pitching.outs - op_pitching.appearance_start_outs.get(f_id, finishing_pitcher.pitching.outs)
                if (1 <= entry_diff <= 3) or outs_got >= 9:
                    finishing_pitcher.pitching.SV += 1
                    save_pitcher = finishing_pitcher
                    if finishing_pitcher in op_pitching.game_holds:
                        finishing_pitcher.pitching.HLD -= 1
                        op_pitching.game_holds.remove(finishing_pitcher)
        return my_score, op_score, {"result": "L", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}
    else:
        return my_score, op_score, {"result": "D", "winning_pitcher": None, "losing_pitcher": None, "save_pitcher": None, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

# ============================================================
# 成績表示・UI表示ヘルパー
# ============================================================
def batting_avg(p): return p.batting.H / p.batting.AB if p.batting.AB else 0.0
def obp(p):
    den = p.batting.AB + p.batting.BB + p.batting.SF
    return (p.batting.H + p.batting.BB) / den if den else 0.0
def slg(p): return p.batting.TB / p.batting.AB if p.batting.AB else 0.0
def ops(p): return obp(p) + slg(p)
def era(p): return p.pitching.ER * 27 / p.pitching.outs if p.pitching.outs else 0.0
def innings_str(outs): return f"{outs // 3}.{outs % 3}"
def format_linescore(ls): return " ".join("".join(ls[i:i+3]) for i in range(0, len(ls), 3))
def fmt_pct(val):
    s = f"{val:.3f}"
    if s.startswith("0."): return s[1:]
    elif s.startswith("-0."): return "-" + s[2:]
    return s
def pos_icon(pos):
    mapping = { "C": ("捕", "#03A9F4", "捕手"), "1B": ("一", "#F9A825", "一塁手"), "2B": ("二", "#F9A825", "二塁手"), "3B": ("三", "#F9A825", "三塁手"), "SS": ("遊", "#F9A825", "遊撃手"), "LF": ("左", "#388E3C", "左翼手"), "CF": ("中", "#388E3C", "中堅手"), "RF": ("右", "#388E3C", "右翼手"), "DH": ("D", "#757575", "指名打者"), "P": ("投", "#E53935", "投手") }
    return mapping.get(pos, ("?", "#999", "不明"))

# ============================================================
# 12球団オートペナント用関数
# ============================================================
def render_12teams_pennant(fielders_base, pitchers_base):
    st.header("🏟️ 12球団オートペナント")
    st.write("NPBの12球団のみで1シーズン（全日程）を自動シミュレーションします！")
    
    if "auto_pennant_results" not in st.session_state:
        st.session_state.auto_pennant_results = None

    if st.button("⚾ ペナントレース開幕！", type="primary", use_container_width=True):
        teams = build_teams(fielders_base, pitchers_base)
        all_teams_data = {}
        for t_name in ALL_NPB_TEAMS:
            team_obj = teams[t_name]
            dh = (t_name in PACIFIC_TEAMS)
            lineup, bench = best_lineup_for_team(team_obj, dh=dh)
            staff = best_pitching_staff(team_obj)
            all_teams_data[t_name] = { "lineup": lineup, "staff": staff, "bench": bench, "games_played": 0, "wins": 0, "losses": 0, "draws": 0, "runs_for": 0, "runs_against": 0 }

        schedule = create_full_schedule(CENTRAL_TEAMS, PACIFIC_TEAMS)
        
        progress = st.progress(0)
        status = st.empty()
        
        for idx, match in enumerate(schedule, 1):
            h_team, a_team = all_teams_data[match["home"]], all_teams_data[match["away"]]
            score_h, score_a, res = simulate_game(h_team["lineup"], h_team["staff"], a_team["lineup"], a_team["staff"], match["league"], h_team["games_played"], a_team["games_played"], my_bench=h_team["bench"], op_bench=a_team["bench"])
            
            h_team["games_played"] += 1; a_team["games_played"] += 1
            h_team["runs_for"] += score_h; h_team["runs_against"] += score_a
            a_team["runs_for"] += score_a; a_team["runs_against"] += score_h
            if res["result"] == "W": h_team["wins"] += 1; a_team["losses"] += 1
            elif res["result"] == "L": h_team["losses"] += 1; a_team["wins"] += 1
            else: h_team["draws"] += 1; a_team["draws"] += 1

            for t in [h_team, a_team]:
                for p in t["staff"]["starters"] + t["staff"]["bullpen"] + ([t["staff"]["closer"]] if t["staff"]["closer"] else []):
                    if getattr(p, 'did_pitch_today', False):
                        p.current_stamina = max(0.0, p.current_stamina - p.game_pitches_today)
                        p.consecutive_games += 1
                    else:
                        p.current_stamina = min(p.stamina, p.current_stamina + p.stamina / 5.0)
                        p.consecutive_games = 0
                    p.did_pitch_today = False; p.game_pitches_today = 0; p.force_continue_outs = 0

            if idx % 20 == 0 or idx == len(schedule):
                progress.progress(idx / len(schedule))
                status.write(f"シミュレーション進行中... {idx}/{len(schedule)}試合終了")
                
        status.success("全日程終了！")
        st.session_state.auto_pennant_results = all_teams_data

    if st.session_state.auto_pennant_results:
        all_teams_data = st.session_state.auto_pennant_results
        
        c1, c2 = st.columns(2)
        for league_name, t_list, col in [("セ・リーグ", CENTRAL_TEAMS, c1), ("パ・リーグ", PACIFIC_TEAMS, c2)]:
            with col:
                st.subheader(f"🏆 {league_name}")
                std = []
                for t in t_list:
                    d = all_teams_data[t]
                    w, l, dr = d["wins"], d["losses"], d["draws"]
                    std.append({"チーム": t, "勝": w, "敗": l, "分": dr, "勝率": w/(w+l) if (w+l)>0 else 0, "差": "-"})
                std.sort(key=lambda x: x["勝率"], reverse=True)
                top_w, top_l = std[0]["勝"], std[0]["敗"]
                for r in std:
                    gb = ((top_w - r["勝"]) + (r["敗"] - top_l)) / 2.0
                    r["差"] = "－" if gb == 0 else f"{gb:.1f}"
                    r["勝率"] = f"{r['勝率']:.3f}".replace("0.", ".")
                st.dataframe(pd.DataFrame(std), hide_index=True, use_container_width=True)

# ============================================================
# ドラフト・設定UI
# ============================================================
def draft_page(kind, all_players, count, skip_limit=None):
    selected_key = "draft_fielders" if kind == "野手" else "draft_pitchers"
    pool_key = "draft_fielder_pool" if kind == "野手" else "draft_pitcher_pool"
    candidate_key = "draft_fielder_candidate" if kind == "野手" else "draft_pitcher_candidate"
    skip_key = "fielder_skips" if kind == "野手" else "pitcher_skips"

    if selected_key not in st.session_state: st.session_state[selected_key] = []
    if pool_key not in st.session_state: st.session_state[pool_key] = list(all_players)
    if skip_key not in st.session_state: st.session_state[skip_key] = 0

    selected = st.session_state[selected_key]
    pool = st.session_state[pool_key]

    st.markdown("""
    <style>
    .draft-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 10px;}
    .draft-count { font-size: 28px; font-weight: bold; color: #111;}
    .draft-count-sub { font-size: 14px; color: #666; font-weight: normal; margin-left: 10px;}
    .skip-badge { background-color: #ffebee; color: #c62828; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

    rem_skips_html = ""
    if skip_limit is not None:
        rem_skips = skip_limit - st.session_state[skip_key]
        rem_skips_html = f'<div class="skip-badge">見送り残り：{rem_skips}回</div>'

    st.markdown(f"""
    <div style="font-size: 12px; font-weight: bold; color: #666;">{kind}を獲得</div>
    <div class="draft-header">
        <div class="draft-count">{len(selected)} / {count} <span class="draft-count-sub">あと{count - len(selected)}人</span></div>
        {rem_skips_html}
    </div>
    """, unsafe_allow_html=True)

    if len(selected) >= count:
        st.session_state.pop(candidate_key, None)
        return True

    selected_ids = {id(p) for p in selected}
    pool = [p for p in pool if id(p) not in selected_ids]
    st.session_state[pool_key] = pool

    if not pool:
        st.error(f"{kind}の候補選手がなくなりました。")
        st.session_state.pop(candidate_key, None)
        return False

    candidate = st.session_state.get(candidate_key)
    if candidate is None or candidate not in pool:
        candidate = random.choice(pool)
        st.session_state[candidate_key] = candidate

    st.markdown("""
    <style>
    .card { border: 1px solid #e0e0e0; border-radius: 12px; padding: 20px; background-color: #fff; margin-top: 10px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);}
    .p-tag { background-color: #00796b; color: white; padding: 4px 12px; border-radius: 15px; font-size: 12px; font-weight: bold; display: inline-block; margin-bottom: 8px;}
    .p-name { font-size: 28px; font-weight: 900; margin: 0 0 5px 0; color: #111;}
    .p-meta { font-size: 13px; color: #777; margin-bottom: 20px; }
    .stats-box { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 15px;}
    .stat-item { background-color: #f7f7f7; border: 1px solid #ececec; border-radius: 8px; padding: 10px 5px; text-align: center; min-width: 65px; flex: 1;}
    .stat-label { font-size: 11px; color: #666; margin-bottom: 2px;}
    .stat-rank { font-size: 26px; font-weight: 900; margin-bottom: 0px;}
    .stat-val { font-size: 12px; color: #999; }
    .pos-list { margin-top: 15px; border-top: 1px dashed #ddd; padding-top: 15px; font-size: 13px; color: #555; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;}
    .pos-badge { background-color: #e8f5e9; color: #2e7d32; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px;}
    </style>
    """, unsafe_allow_html=True)

    if kind == "野手":
        if candidate.defense: main_pos_str = "・".join([POSITION_JP.get(pos, pos) for pos in candidate.defense.keys()])
        else: main_pos_str = "不明"
    else: main_pos_str = "投手"
    
    card_html = f'<div class="card"><div class="p-tag">{main_pos_str}</div><div class="p-name">{candidate.name}</div><div class="p-meta">{candidate.team} 所属</div><div class="stats-box">'
    
    if kind == "野手":
        max_def = max(candidate.defense.values()) if candidate.defense else 0
        stats = [("ミート", candidate.contact), ("パワー", candidate.power), ("走力", candidate.speed), ("守備力", max_def)]
    else:
        stats = [("球威", getattr(candidate, "pitch_power_base", 50.0)), ("制球", candidate.control), ("スタミナ", candidate.stamina)]
        
    for label, val in stats:
        rank_str, color = val_to_rank(val)
        card_html += f'<div class="stat-item"><div class="stat-label">{label}</div><div class="stat-rank" style="color: {color};">{rank_str}</div><div class="stat-val">{int(val)}</div></div>'
        
    card_html += '</div>'

    if kind == "野手":
        card_html += '<div class="pos-list">守れる所：'
        for pos, val in candidate.defense.items():
            r_str, _ = val_to_rank(val)
            card_html += f'<span class="pos-badge">{POSITION_JP.get(pos, pos)} {r_str}</span>'
        card_html += '</div>'
    else:
        card_html += '<div class="pos-list">球種：'
        for p_name, val in candidate.pitches.items():
            r_str, _ = val_to_rank(val)
            card_html += f'<span class="pos-badge">{p_name} {r_str}</span>'
        card_html += '</div>'
        
    card_html += '</div>'
    st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("""
    <style>
    div[data-testid="column"]:nth-of-type(1) div.stButton > button { background-color: #c62828 !important; color: white !important; height: 75px; font-size: 22px; font-weight: bold; border: none; border-radius: 8px; box-shadow: 0 4px 0 #8e0000; transition: 0.1s; }
    div[data-testid="column"]:nth-of-type(1) div.stButton > button:active { box-shadow: 0 0 0 #8e0000; transform: translateY(4px); }
    div[data-testid="column"]:nth-of-type(2) div.stButton > button { background-color: #2e7d32 !important; color: white !important; height: 75px; font-size: 22px; font-weight: bold; border: none; border-radius: 8px; box-shadow: 0 4px 0 #005005; transition: 0.1s; }
    div[data-testid="column"]:nth-of-type(2) div.stButton > button:active { box-shadow: 0 0 0 #005005; transform: translateY(4px); }
    </style>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        skip_disabled = (skip_limit is not None and st.session_state[skip_key] >= skip_limit)
        btn_label = f"見送る (残り{skip_limit - st.session_state[skip_key]}回)" if skip_limit else "見送る"
        if st.button(btn_label, disabled=skip_disabled, use_container_width=True, key=f"skip_{kind}_{len(selected)}"):
            st.session_state[pool_key] = [p for p in pool if p is not candidate]
            st.session_state[skip_key] += 1
            st.session_state.pop(candidate_key, None)
            st.rerun()
            
    with c2:
        if st.button("取る", use_container_width=True, key=f"take_{kind}_{len(selected)}"):
            selected.append(candidate)
            st.session_state[pool_key] = [p for p in pool if p is not candidate]
            st.session_state.pop(candidate_key, None)
            st.rerun()

    st.markdown('<div style="font-size: 14px; font-weight: bold; color: #333; margin-top: 40px; border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-bottom: 15px;">獲得した選手</div>', unsafe_allow_html=True)
    if selected:
        sel_html = '<div style="display: flex; flex-wrap: wrap; gap: 8px;">'
        for p in selected:
            if kind == "野手": m_pos = "・".join([POSITION_JP.get(pos, pos) for pos in p.defense.keys()]) if p.defense else "不明"
            else: m_pos = "投手"
            sel_html += f'<div style="background-color: #f5f5f5; border: 1px solid #ddd; padding: 5px 12px; border-radius: 6px; font-size: 13px;"><b style="color:#555;">{m_pos}</b> {p.name}</div>'
        sel_html += '</div>'
        st.markdown(sel_html, unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size: 13px; color: #888;">まだ0人。ここに獲得した選手が並びます。</div>', unsafe_allow_html=True)

    return False

def order_page(fielders, league):
    st.header("④ オーダー設定")
    st.info(f"選択リーグ：{league}")

    initial_lineup = assign_initial_positions(fielders, dh=(league == "パ・リーグ"))
    default_pos_map = {pos: p for p, pos in initial_lineup}

    lineup, used = [], set()
    st.subheader("守備位置")

    for pos in POSITIONS:
        available = [p for p in fielders if p.name not in used]
        if not available: st.error("野手の人数が不足しています。"); return None
            
        names = [p.name for p in available]
        default_p = default_pos_map.get(pos)
        idx = names.index(default_p.name) if default_p and default_p.name in names else 0
            
        selected_name = st.selectbox(f"{POSITION_JP[pos]} ({pos})", names, index=idx, key=f"order_{pos}")
        player = next(p for p in available if p.name == selected_name)
        lineup.append((player, pos))
        used.add(player.name)
        st.caption(f"守備力 {pos}: {player.defense_at(pos):g}")

    remaining = [p for p in fielders if p.name not in used]

    if league == "パ・リーグ":
        st.subheader("DH")
        if not remaining: st.error("DH候補がいません。"); return None
        names = [p.name for p in remaining]
        default_p = default_pos_map.get("DH")
        idx = names.index(default_p.name) if default_p and default_p.name in names else 0
        dh_name = st.selectbox("DH", names, index=idx, key="order_DH")
        dh = next(p for p in remaining if p.name == dh_name)
        lineup.append((dh, "DH"))
    else:
        st.info("セ・リーグなので余った野手は代打要員になります。")

    st.subheader("打順")
    lineup_default = decide_batting_order(lineup)
    names = [p.name for p, _ in lineup_default]
    ordered = []

    for i in range(len(lineup_default)):
        remaining_names = [n for n in names if n not in [p.name for p, _ in ordered]]
        default_name = lineup_default[i][0].name
        idx = remaining_names.index(default_name) if default_name in remaining_names else 0
        selected_name = st.selectbox(f"{i + 1}番", remaining_names, index=idx, key=f"batting_order_{i}")
        if selected_name is None: continue
        pair = next(x for x in lineup if x[0].name == selected_name)
        ordered.append(pair)

    bench = remaining[0] if league == "セ・リーグ" and remaining else None
    if bench: st.write(f"代打要員：**{bench.name}**")

    if st.button("オーダー決定", type="primary"):
        return {"lineup": ordered, "bench": bench}
    return None

def pitching_page(pitchers):
    st.header("⑤ 投手起用設定")
    names = [p.name for p in pitchers]

    if len(names) < 15:
        st.error("投手が15人未満です。先発6人＋中継ぎ8人＋抑え1人が必要です。")
        return None

    if "pitcher_roles" not in st.session_state: st.session_state.pitcher_roles = decide_pitcher_roles(pitchers)

    def update_role(p_name): st.session_state.pitcher_roles[p_name] = st.session_state[f"sel_{p_name}"]

    roles_list = list(st.session_state.pitcher_roles.values())
    sp_count, cl_count = roles_list.count("先発"), roles_list.count("抑え")

    if sp_count != 6: st.markdown(f'<div style="background-color: #FBE9E7; padding: 15px; border-radius: 8px; color: #D32F2F; font-weight: bold; margin-bottom: 20px;">先発は6人ちょうどにしてください（いま{sp_count}人）</div>', unsafe_allow_html=True)
    if cl_count != 1: st.markdown(f'<div style="background-color: #FBE9E7; padding: 15px; border-radius: 8px; color: #D32F2F; font-weight: bold; margin-bottom: 20px;">抑えは1人ちょうどにしてください（いま{cl_count}人）</div>', unsafe_allow_html=True)

    role_options = ["先発", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理", "抑え"]

    for p in pitchers:
        with st.container():
            c1, c2 = st.columns([3, 1])
            with c1: st.markdown(f'<div style="padding-top: 5px;"><span style="font-size: 18px; font-weight: 900; color: #111;">{p.name}</span><br><span style="font-size: 13px; color: #777;">{p.team}所属・球威 {int(p.pitch_power_base)}・制球 {int(p.control)}・スタミナ {int(p.stamina)}</span></div>', unsafe_allow_html=True)
            with c2:
                current_role = st.session_state.pitcher_roles.get(p.name, "僅差")
                idx = role_options.index(current_role) if current_role in role_options else 2
                st.selectbox("役割", role_options, index=idx, key=f"sel_{p.name}", label_visibility="collapsed", on_change=update_role, args=(p.name,))
        st.markdown("<hr style='margin: 0 0 10px 0;'>", unsafe_allow_html=True)

    if st.button("投手起用決定", type="primary", disabled=(sp_count != 6 or cl_count != 1)):
        starters = [p for p in pitchers if st.session_state.pitcher_roles[p.name] == "先発"]
        closer = [p for p in pitchers if st.session_state.pitcher_roles[p.name] == "抑え"][0]
        bullpen = [p for p in pitchers if st.session_state.pitcher_roles[p.name] not in ("先発", "抑え")]
        bullpen_roles = {id(p): st.session_state.pitcher_roles[p.name] for p in bullpen}
        return {"starters": starters, "bullpen": bullpen, "closer": closer, "bullpen_roles": bullpen_roles}
    return None

# ============================================================
# クローンペナントレース（サブゲーム）用関数
# ============================================================
def render_clone_pennant(fielders_base):
    st.header("🧬 クローンチーム・ペナントレース")
    st.write("「全員が同じ野手」で構成されたチームを6つ作り、120試合のペナントレースを行います！")
    st.caption("※投手陣は全チーム共通の能力（先発オール60、リリーフ球威70等）の架空投手が自動で登板します。")

    # ▼ 追加：結果を記憶しておくための設定
    if "clone_results" not in st.session_state:
        st.session_state.clone_results = None
    if "clone_selected" not in st.session_state:
        st.session_state.clone_selected = []

    all_names = sorted(list(set(p.name for p in fielders_base)))
    selected_names = st.multiselect("参戦させる選手を6人選んでください", options=all_names, max_selections=6)

    # 選手を選び直したら記憶をリセットする
    if set(selected_names) != set(st.session_state.clone_selected):
        st.session_state.clone_results = None
        st.session_state.clone_selected = selected_names

    if len(selected_names) == 6:
        if st.button("⚾ ペナントレース開幕！", type="primary", use_container_width=True):
            # --- チーム作成 ---
            all_teams_data = {}
            for name in selected_names:
                base_p = next(p for p in fielders_base if p.name == name)
                
                # 9人のクローン野手を作成
                lineup = []
                positions = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
                for i, pos in enumerate(positions, 1):
                    clone_p = copy.deepcopy(base_p)
                    clone_p.name = f"{base_p.name}({pos})"
                    clone_p.batting = BatterStats()
                    clone_p.fielding = FielderStats()
                    lineup.append((clone_p, pos))
                    
                # ご指定の投手陣を作成
                starters, bullpen = [], []
                bullpen_roles = {}
                
                def make_pitcher(role, idx):
                    p = Player(name=f"{role}{idx}", team=f"{name}ズ")
                    if role == "先発":
                        p.pitch_power_base = 60; p.control = 60; p.stamina = 60
                        p.pitches = {"フォーシーム": 65, "フォーク": 55, "スライダー": 55, "カーブ": 55}
                    else:
                        p.pitch_power_base = 70; p.control = 65; p.stamina = 40
                        p.pitches = {"フォーシーム": 70, "フォーク": 55, "スライダー": 55, "カーブ": 55}
                    p.current_stamina = p.stamina
                    return p
                    
                for i in range(6): starters.append(make_pitcher("先発", i+1))
                for i in range(8):
                    bp = make_pitcher("中継ぎ", i+1)
                    bullpen.append(bp)
                    roles_dist = ["中継ぎエース", "僅差", "僅差", "リード", "リード", "ビハインド", "ビハインド", "敗戦処理"]
                    bullpen_roles[id(bp)] = roles_dist[i]
                closer = make_pitcher("抑え", 1)
                
                all_teams_data[name] = {
                    "lineup": lineup,
                    "staff": {"starters": starters, "bullpen": bullpen, "closer": closer, "bullpen_roles": bullpen_roles},
                    "bench": None,
                    "games_played": 0, "wins": 0, "losses": 0, "draws": 0,
                    "runs_for": 0, "runs_against": 0
                }
            
            # --- 日程作成（総当たり戦 各120試合） ---
            schedule = []
            for t1 in selected_names:
                for t2 in selected_names:
                    if t1 != t2:
                        for _ in range(12): schedule.append({"home": t1, "away": t2, "league": "パ・リーグ"})
            random.shuffle(schedule)
            
            progress = st.progress(0)
            status = st.empty()
            
            # --- シミュレーション実行 ---
            for idx, match in enumerate(schedule, 1):
                h_team = all_teams_data[match["home"]]
                a_team = all_teams_data[match["away"]]
                
                score_h, score_a, res = simulate_game(
                    h_team["lineup"], h_team["staff"], a_team["lineup"], a_team["staff"], 
                    match["league"], h_team["games_played"], a_team["games_played"]
                )
                
                h_team["games_played"] += 1; a_team["games_played"] += 1
                h_team["runs_for"] += score_h; h_team["runs_against"] += score_a
                a_team["runs_for"] += score_a; a_team["runs_against"] += score_h
                
                if res["result"] == "W": h_team["wins"] += 1; a_team["losses"] += 1
                elif res["result"] == "L": h_team["losses"] += 1; a_team["wins"] += 1
                else: h_team["draws"] += 1; a_team["draws"] += 1
                
                for t in [h_team, a_team]:
                    stf = t["staff"]
                    for p in stf["starters"] + stf["bullpen"] + [stf["closer"]]:
                        if getattr(p, 'did_pitch_today', False):
                            p.current_stamina = max(0.0, p.current_stamina - p.game_pitches_today)
                            p.consecutive_games += 1
                        else:
                            p.current_stamina = min(p.stamina, p.current_stamina + p.stamina / 5.0)
                            p.consecutive_games = 0
                        p.did_pitch_today = False
                        p.game_pitches_today = 0
                        p.force_continue_outs = 0
                        
                if idx % 10 == 0 or idx == len(schedule):
                    progress.progress(idx / len(schedule))
                    status.write(f"ペナントレース進行中... {idx}/{len(schedule)}試合終了")
                    
            status.success("全日程（1リーグ360試合）が終了しました！")
            
            # ▼ 追加：終わったデータを「記憶（session_state）」に保存する！
            st.session_state.clone_results = all_teams_data

        # ▼ 追加：ボタンの中（if文）から外に出し、「記憶」があれば常に表示する仕組みに変更
        if st.session_state.clone_results is not None:
            all_teams_data = st.session_state.clone_results
            
            # --- 結果表示 ---
            st.subheader("🏆 クローンペナント 最終順位表")
            standings = []
            for name in selected_names:
                d = all_teams_data[name]
                w, l, dr = d["wins"], d["losses"], d["draws"]
                pct = w / (w+l) if (w+l) > 0 else 0
                
                # クローン9人分の合計成績を算出
                t_ab = sum(p.batting.AB for p, _ in d["lineup"])
                t_h = sum(p.batting.H for p, _ in d["lineup"])
                t_hr = sum(p.batting.HR for p, _ in d["lineup"])
                t_e = sum(p.fielding.E for p, _ in d["lineup"])
                t_pb = sum(getattr(p.fielding, 'PB', 0) for p, _ in d["lineup"])
                t_avg = t_h / t_ab if t_ab > 0 else 0
                
                standings.append({
                    "チーム": f"{name}ズ", "勝": w, "敗": l, "分": dr, "勝率": pct, "ゲーム差": "-",
                    "得点": d["runs_for"], "失点": d["runs_against"], 
                    "打率": f"{t_avg:.3f}".replace("0.", "."), "本塁打": t_hr, "失策": t_e, "捕逸": t_pb
                })
                
            standings.sort(key=lambda x: x["勝率"], reverse=True)
            
            # ゲーム差の計算
            top_w, top_l = standings[0]["勝"], standings[0]["敗"]
            for row in standings:
                gb = ((top_w - row["勝"]) + (row["敗"] - top_l)) / 2.0
                row["ゲーム差"] = "－" if gb == 0 else f"{gb:.1f}"
                row["勝率"] = f"{row['勝率']:.3f}".replace("0.", ".")
                
            df_std = pd.DataFrame(standings)[["チーム", "勝", "敗", "分", "勝率", "ゲーム差", "得点", "失点", "打率", "本塁打", "失策", "捕逸"]]
            st.dataframe(df_std, hide_index=True, use_container_width=True)

            # --- 個人成績（HTMLカード）の表示 ---
            st.markdown("---")
            st.subheader("👤 個人成績（ポジション別・クローン9人）")
            
            selected_team_name = st.selectbox("成績を見るチームを選択", selected_names, key="clone_team_select")
            
            t_data = all_teams_data[selected_team_name]
            batters_to_show = t_data["lineup"]
            
            # 本編と同じCSSを適用
            st.markdown("""
            <style>
            .stats-container { background-color: #F8F7F5; padding: 5px; border-radius: 8px; margin-bottom: 10px; }
            .stats-row { border-bottom: 1px solid #E5E5E5; padding: 20px 10px 15px; }
            .stats-row:last-child { border-bottom: none; }
            .player-hdr { display: flex; align-items: center; margin-bottom: 15px; }
            .p-order { font-size: 18px; font-weight: bold; color: #A0A0A0; width: 25px; text-align: center; }
            .p-icon { width: 34px; height: 34px; border-radius: 50%; color: white; display: flex; justify-content: center; align-items: center; font-size: 14px; font-weight: bold; margin: 0 15px 0 5px; }
            .p-name-container { line-height: 1.2; }
            .p-fullname { font-size: 18px; font-weight: 900; color: #111; }
            .p-pos { font-size: 11px; color: #888; margin-top: 4px; }
            .main-stats { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 15px; padding: 0 5px; }
            .ms-item { display: flex; align-items: baseline; }
            .ms-label { font-size: 11px; color: #888; margin-right: 5px; font-weight: bold; }
            .ms-val { font-size: 24px; font-weight: 900; color: #111; }
            .ms-val-small { font-size: 20px; font-weight: bold; color: #111; }
            .sub-stats { display: flex; justify-content: space-between; background-color: #EFEFEF; padding: 10px 15px; border-radius: 4px; }
            .ss-item { font-size: 11px; color: #777; }
            .ss-item b { color: #333; font-size: 12px; margin-left: 4px; }
            </style>
            """, unsafe_allow_html=True)
            
            html_bat = '<div class="stats-container">'
            for i, (p, pos) in enumerate(batters_to_show, start=1):
                icon_char, color, jp_pos = pos_icon(pos)
                order_str = str(i)
                avg_str, ops_str = fmt_pct(batting_avg(p)), fmt_pct(ops(p))
                uzr = p.fielding.UZR
                uzr_str = f"+{uzr:.1f}" if uzr > 0 else f"{uzr:.1f}"
                if pos in ["DH"]: uzr_str = "－"
                
                # 捕手のみ捕逸を表示
                pb_html = f'<div class="ss-item">捕逸<b>{getattr(p.fielding, "PB", 0)}</b></div>' if pos == "C" else ""
                
                html_bat += f'<div class="stats-row"><div class="player-hdr"><div class="p-order">{order_str}</div><div class="p-icon" style="background-color: {color};">{icon_char}</div><div class="p-name-container"><div class="p-fullname">{p.name}</div><div class="p-pos">{jp_pos}</div></div></div><div class="main-stats"><div class="ms-item"><span class="ms-label">打率</span><span class="ms-val">{avg_str}</span></div><div class="ms-item"><span class="ms-label">本塁打</span><span class="ms-val-small">{p.batting.HR}</span></div><div class="ms-item"><span class="ms-label">打点</span><span class="ms-val-small">{p.batting.RBI}</span></div><div class="ms-item"><span class="ms-label">盗塁</span><span class="ms-val-small">{p.batting.SB}</span></div><div class="ms-item"><span class="ms-label">OPS</span><span class="ms-val">{ops_str}</span></div></div><div class="sub-stats"><div class="ss-item">試合<b>{p.batting.G}</b></div><div class="ss-item">打席<b>{p.batting.PA}</b></div><div class="ss-item">打数<b>{p.batting.AB}</b></div><div class="ss-item">安打<b>{p.batting.H}</b></div><div class="ss-item">犠飛<b>{p.batting.SF}</b></div><div class="ss-item">UZR<b>{uzr_str}</b></div><div class="ss-item">失策<b>{p.fielding.E}</b></div>{pb_html}</div></div>'
            html_bat += '</div>'
            
            st.markdown(html_bat, unsafe_allow_html=True)
# ============================================================
# メインアプリケーション実行
# ============================================================
st.title("⚾ 野球チームメーカー")

with st.sidebar:
    st.header("モード選択")
    app_mode = st.radio("機能を選んでください", [
        "チームメーカー（ランダムドラフト）", 
        "カスタムチーム（自由編成）", 
        "12球団オートペナント", 
        "クローンペナント（サブゲーム）"
    ])
    st.markdown("---")
    st.header("選手データ")
    st.write("GitHubリポジトリ内のExcelを自動読み込みします。")

FIELD_FILE = "野手能力データ_最新.xlsx"
PITCH_FILE = "投手能力データ_最新.xlsx"

try:
    fielders_all = load_fielders(FIELD_FILE)
    pitchers_all = load_pitchers(PITCH_FILE)
except Exception as e:
    st.error("Excel読み込みエラーが発生しました。")
    st.stop()

st.sidebar.success(f"野手 {len(fielders_all)}人 / 投手 {len(pitchers_all)}人")

# ▼ 【修正点1】モードが切り替わったら、過去の「画面状態」をリセットする！
if "last_app_mode" not in st.session_state:
    st.session_state.last_app_mode = app_mode

if st.session_state.last_app_mode != app_mode:
    st.session_state.last_app_mode = app_mode
    st.session_state.step = "start"
    # 前のモードで選んだ選手もリセット
    for k in ["draft_fielders", "draft_pitchers", "draft_fielder_pool", "draft_pitcher_pool", "fielder_skips", "pitcher_skips"]:
        st.session_state.pop(k, None)

# ▼ 各モードへの分岐
if app_mode == "12球団オートペナント":
    render_12teams_pennant(fielders_all, pitchers_all)

elif app_mode == "クローンペナント（サブゲーム）":
    render_clone_pennant(fielders_all)

else:
    if "step" not in st.session_state: st.session_state.step = "start"
    st.session_state.teams = build_teams(fielders_all, pitchers_all)

    # ▼ スタート画面
    if st.session_state.step == "start":
        if app_mode == "カスタムチーム（自由編成）":
            st.header("🛠️ カスタムチーム編成")
            st.write("全選手リストから、野手9名以上、投手15名を選んで最強チームを作ろう！")
            
            f_names = sorted(list(set(p.name for p in fielders_all)))
            p_names = sorted(list(set(p.name for p in pitchers_all)))
            
            sel_f = st.multiselect("野手を選択（最低9名）", f_names)
            sel_p = st.multiselect("投手を選択（必ず15名：先発6, 中継8, 抑え1）", p_names)
            
            if st.button("このメンバーで決定！", type="primary"):
                if len(sel_f) < 9: st.error("野手が足りません（最低9名）")
                elif len(sel_p) != 15: st.error("投手はちょうど15名選んでください")
                else:
                    st.session_state.draft_fielders = [p for p in fielders_all if p.name in sel_f]
                    st.session_state.draft_pitchers = [p for p in pitchers_all if p.name in sel_p]
                    # 選んだら、リーグ選択（本編の流れ）に合流！
                    st.session_state.step = "league_select"
                    st.rerun()
        else:
            st.markdown('<div style="font-size: 36px; font-weight: 900; text-align: center; margin-bottom: 20px;">野球チームメーカー</div>', unsafe_allow_html=True)
            st.write("ランダムに現れる選手を取捨選択して、チームを作れ！")
            if st.button("ゲームを始める", type="primary", use_container_width=True):
                # ▼ 【修正点2】リーグ設定画面を消して、裏で設定してからすぐドラフトへ！
                st.session_state.central = CENTRAL_TEAMS.copy()
                st.session_state.pacific = PACIFIC_TEAMS.copy()
                st.session_state.step = "draft_fielders"
                st.rerun()

    # ▼ これ以降は「ランダムドラフト」用の処理（カスタムではスキップされる）
    elif st.session_state.step == "draft_fielders":
        if draft_page("野手", fielders_all, 9, skip_limit=5):
            st.session_state.step = "draft_pitchers"
            st.rerun()

    elif st.session_state.step == "draft_pitchers":
        if draft_page("投手", pitchers_all, 15, skip_limit=5):
            st.session_state.step = "league_select"
            st.rerun()

    # ▼ ここから下は本編（カスタムもランダムも共通して通る道）
    elif st.session_state.step == "league_select":
        st.header("③ セ・パ選択")
        league = st.radio("あなたのチームはどちらのリーグに所属しますか？", ["セ・リーグ", "パ・リーグ"])
        if st.button("リーグ決定", type="primary"):
            st.session_state.my_league = league
            st.session_state.step = "order"
            st.rerun()

    elif st.session_state.step == "order":
        result = order_page(st.session_state.draft_fielders, st.session_state.my_league)
        if result is not None:
            st.session_state.my_lineup = result["lineup"]
            st.session_state.my_bench = result["bench"]
            st.session_state.step = "pitching"
            st.rerun()

    elif st.session_state.step == "pitching":
        result = pitching_page(st.session_state.draft_pitchers)
        if result is not None:
            st.session_state.my_staff = result
            st.session_state.step = "ready"
            st.rerun()

    elif st.session_state.step == "ready":
        st.header("⑥ 開幕前確認")
        st.write("設定が完了しました！")
        
        # 簡易的にチーム割り当てを設定
        if st.session_state.my_league == "セ・リーグ":
            st.session_state.league_central = random.sample(CENTRAL_TEAMS, 5) + ["マイチーム"]
            st.session_state.league_pacific = random.sample(PACIFIC_TEAMS, 6)
        else:
            st.session_state.league_pacific = random.sample(PACIFIC_TEAMS, 5) + ["マイチーム"]
            st.session_state.league_central = random.sample(CENTRAL_TEAMS, 6)

        if st.button("⚾ シーズン開始", type="primary", use_container_width=True):
            st.session_state.step = "season"
            st.rerun()

    elif st.session_state.step == "season":
        st.header("⑦ 全試合シミュレーション中...")
        teams = st.session_state.teams
        my_league = st.session_state.my_league
        
        for t_name, team_obj in teams.items():
            if t_name == "日本ハム":
                for p in team_obj.fielders: p.contact = max(1.0, p.contact - 4.0); p.power = max(1.0, p.power + 2.0); p.speed = max(1.0, p.speed - 2.0)
                for p in team_obj.pitchers: p.control = max(1.0, p.control - 3.0); p.stamina = max(1.0, p.stamina - 3.0); p.pitch_power_base = max(1.0, getattr(p, "pitch_power_base", 50.0) - 3.0)
            elif t_name == "ソフトバンク":
                for p in team_obj.fielders: p.contact = max(1.0, p.contact - 2.0); p.power = max(1.0, p.power - 2.0); p.speed = max(1.0, p.speed - 1.0)
                for p in team_obj.pitchers: p.control = max(1.0, p.control - 2.0); p.stamina = max(1.0, p.stamina - 2.0); p.pitch_power_base = max(1.0, getattr(p, "pitch_power_base", 50.0) - 2.0)
                    
        all_sim_players = list(fielders_all) + list(pitchers_all)
        all_sim_players.extend([p for p, _ in st.session_state.my_lineup])
        if st.session_state.my_bench: all_sim_players.append(st.session_state.my_bench)
        all_sim_players.extend(st.session_state.my_staff["starters"])
        all_sim_players.extend(st.session_state.my_staff["bullpen"])
        if st.session_state.my_staff["closer"]: all_sim_players.append(st.session_state.my_staff["closer"])
        reset_stats(all_sim_players)
        
        all_teams_data = {}
        all_participating_teams = st.session_state.league_central + st.session_state.league_pacific
        for t_name in all_participating_teams:
            if t_name == "マイチーム":
                lineup = st.session_state.my_lineup
                staff = st.session_state.my_staff
                bench = st.session_state.my_bench
            else:
                team_obj = teams[t_name]
                dh = (t_name in st.session_state.league_pacific)
                lineup, bench = best_lineup_for_team(team_obj, dh=dh)
                staff = best_pitching_staff(team_obj)
            all_teams_data[t_name] = { "lineup": lineup, "staff": staff, "bench": bench, "games_played": 0, "wins": 0, "losses": 0, "draws": 0, "runs_for": 0, "runs_against": 0 }

        full_schedule = create_full_schedule(st.session_state.league_central, st.session_state.league_pacific)
        
        # マイチームがどの球団と入れ替わったかを判定し、日程表を自動で書き換える
        default_teams = ["阪神", "DeNA", "巨人", "ヤクルト", "中日", "広島", "日本ハム", "ロッテ", "楽天", "西武", "オリックス", "ソフトバンク"]
        missing_teams = [t for t in default_teams if t not in all_participating_teams]
        if "マイチーム" in all_participating_teams and missing_teams:
            replaced_team = missing_teams[0]
            for match in full_schedule:
                if match["home"] == replaced_team:
                    match["home"] = "マイチーム"
                if match["away"] == replaced_team:
                    match["away"] = "マイチーム"

        game_log = []
        progress = st.progress(0)
        status = st.empty()
        
        for idx, match in enumerate(full_schedule, start=1):
            h_name, a_name, league_rule = match["home"], match["away"], match["league"]
            h_team, a_team = all_teams_data[h_name], all_teams_data[a_name]
            score_h, score_a, result = simulate_game(h_team["lineup"], h_team["staff"], a_team["lineup"], a_team["staff"], league_rule, h_team["games_played"], a_team["games_played"], my_bench=h_team["bench"], op_bench=a_team["bench"])
            
            h_team["games_played"] += 1; a_team["games_played"] += 1
            h_team["runs_for"] += score_h; h_team["runs_against"] += score_a
            a_team["runs_for"] += score_a; a_team["runs_against"] += score_h
            
            if result["result"] == "W": h_team["wins"] += 1; a_team["losses"] += 1
            elif result["result"] == "L": h_team["losses"] += 1; a_team["wins"] += 1
            else: h_team["draws"] += 1; a_team["draws"] += 1

            for t_name in [h_name, a_name]:
                t_data = all_teams_data[t_name]
                staff_list = t_data["staff"]["starters"] + t_data["staff"]["bullpen"] + ([t_data["staff"]["closer"]] if t_data["staff"]["closer"] else [])
                for p in staff_list:
                    if getattr(p, 'did_pitch_today', False):
                        p.current_stamina = max(0.0, p.current_stamina - p.game_pitches_today)
                        p.consecutive_games += 1
                    else:
                        p.current_stamina = min(p.stamina, p.current_stamina + p.stamina / 5.0)
                        p.consecutive_games = 0
                    p.did_pitch_today = False
                    p.game_pitches_today = 0
                    p.force_continue_outs = 0

            if h_name == "マイチーム" or a_name == "マイチーム":
                is_home = (h_name == "マイチーム")
                my_score = score_h if is_home else score_a
                op_score = score_a if is_home else score_h
                op_name = a_name if is_home else h_name
                if result["result"] == "W": my_res = "W" if is_home else "L"
                elif result["result"] == "L": my_res = "L" if is_home else "W"
                else: my_res = "D"
                    
                win_p, los_p, sv_p = result["winning_pitcher"], result["losing_pitcher"], result["save_pitcher"]
                my_ls = result["my_linescore"] if is_home else result["op_linescore"]
                op_ls = result["op_linescore"] if is_home else result["my_linescore"]
                game_log.append({
                    "試合": all_teams_data["マイチーム"]["games_played"], "対戦相手": op_name, "勝敗": my_res,
                    "スコア": f"{my_score} - {op_score}", "イニング": f"相: {format_linescore(op_ls)}\n自: {format_linescore(my_ls)}",
                    "勝投手": win_p.name if win_p else "-", "敗投手": los_p.name if los_p else "-", "S投手": sv_p.name if sv_p else "-",
                    "本塁打": "、".join(result.get("hrs", []))
                })
                
            if idx % 20 == 0 or idx == len(full_schedule):
                progress.progress(idx / len(full_schedule))
                status.write(f"全12球団 シーズン進行中... {idx}/{len(full_schedule)}試合終了")

        st.session_state.season_result = {
            "wins": all_teams_data["マイチーム"]["wins"], "losses": all_teams_data["マイチーム"]["losses"], "draws": all_teams_data["マイチーム"]["draws"],
            "runs_for": all_teams_data["マイチーム"]["runs_for"], "runs_against": all_teams_data["マイチーム"]["runs_against"],
            "game_log": game_log, "all_teams_data": all_teams_data
        }
        st.session_state.step = "result"
        st.rerun()

    elif st.session_state.step == "result":
        result = st.session_state.season_result

        st.markdown("""
        <style>
        .disclaimer-box { font-size: 11px; color: #888; background-color: #f9f9f9; padding: 12px; border: 1px solid #eee; margin-bottom: 20px; line-height: 1.5; }
        .stats-container { background-color: #F8F7F5; padding: 5px; border-radius: 8px; margin-bottom: 10px; }
        .stats-row { border-bottom: 1px solid #E5E5E5; padding: 20px 10px 15px; }
        .stats-row:last-child { border-bottom: none; }
        .player-hdr { display: flex; align-items: center; margin-bottom: 15px; }
        .p-order { font-size: 18px; font-weight: bold; color: #A0A0A0; width: 25px; text-align: center; }
        .p-icon { width: 34px; height: 34px; border-radius: 50%; color: white; display: flex; justify-content: center; align-items: center; font-size: 14px; font-weight: bold; margin: 0 15px 0 5px; }
        .p-name-container { line-height: 1.2; }
        .p-fullname { font-size: 18px; font-weight: 900; color: #111; }
        .p-pos { font-size: 11px; color: #888; margin-top: 4px; }
        .main-stats { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 15px; padding: 0 5px; }
        .ms-item { display: flex; align-items: baseline; }
        .ms-label { font-size: 11px; color: #888; margin-right: 5px; font-weight: bold; }
        .ms-val { font-size: 24px; font-weight: 900; color: #111; }
        .ms-val-small { font-size: 20px; font-weight: bold; color: #111; }
        .sub-stats { display: flex; justify-content: space-between; background-color: #EFEFEF; padding: 10px 15px; border-radius: 4px; }
        .ss-item { font-size: 11px; color: #777; }
        .ss-item b { color: #333; font-size: 12px; margin-left: 4px; }
        .season-end-wrap { text-align: center; margin: 30px 0 10px; color: #666; font-size: 15px; }
        .season-end-box { border: 2px solid #222; border-radius: 8px; padding: 40px 20px; text-align: center; background-color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.03); margin-bottom: 25px; }
        .se-sub { font-size: 13px; color: #555; font-weight: bold; letter-spacing: 3px; margin-bottom: 15px; }
        .se-main { font-size: 38px; font-weight: 900; margin-bottom: 30px; color: #111; }
        .se-stats { display: flex; justify-content: center; align-items: baseline; gap: 15px; flex-wrap: wrap; }
        .se-rank-label { font-size: 15px; color: #666; }
        .se-rank-val { font-size: 32px; font-weight: 900; color: #111; }
        .se-rec { font-size: 15px; color: #555; margin-left: 10px; }
        .next-year-wrapper div[data-testid="stButton"] > button { background-color: #1a1a1a !important; color: white !important; height: 110px !important; border-radius: 10px !important; border: none !important; position: relative; }
        .next-year-wrapper div[data-testid="stButton"] > button p { font-size: 26px !important; font-weight: 900 !important; margin-bottom: 25px !important; }
        .next-year-wrapper div[data-testid="stButton"] > button::after { content: "3人まで入れ替えて、来季を戦います"; position: absolute; bottom: 25px; left: 0; width: 100%; text-align: center; font-size: 13px; font-weight: bold; color: #ccc; }
        </style>
        """, unsafe_allow_html=True)

        st.markdown('<div class="disclaimer-box">全12球団が143試合を戦い抜いた、完全なシミュレーション結果です。</div>', unsafe_allow_html=True)

        all_teams_data = result["all_teams_data"]
        team_list = ["マイチーム"] + [t for t in all_teams_data.keys() if t != "マイチーム"]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            selected_team = st.selectbox("📊 成績を表示するチーム", team_list)

        tab_bat, tab_pitch, tab_detail, tab_team, tab_standings, tab_log = st.tabs(["打撃成績", "投球成績", "個人詳細成績", "チーム成績", "順位表", "全試合ログ"])

        t_data = all_teams_data[selected_team]
        batters_to_show = list(t_data["lineup"])
        
        if selected_team == "マイチーム":
            if st.session_state.my_bench:
                batters_to_show.append((st.session_state.my_bench, "代打"))
        else:
            if t_data.get("bench"):
                batters_to_show.append((t_data["bench"], "代打"))
            
        staff = t_data["staff"]
        pitchers_list = staff["starters"] + staff["bullpen"] + ([staff["closer"]] if staff["closer"] else [])

        html_bat = '<div class="stats-container">'
        for i, (p, pos) in enumerate(batters_to_show, start=1):
            if pos == "代打": icon_char, color, jp_pos, order_str = "代", "#888888", "代打", "-"
            else: icon_char, color, jp_pos = pos_icon(pos); order_str = str(i)
            avg_str, ops_str = fmt_pct(batting_avg(p)), fmt_pct(ops(p))
            uzr = p.fielding.UZR
            uzr_str = f"+{uzr:.1f}" if uzr > 0 else f"{uzr:.1f}"
            if pos in ["DH", "代打"]: uzr_str = "－"
            html_bat += f'<div class="stats-row"><div class="player-hdr"><div class="p-order">{order_str}</div><div class="p-icon" style="background-color: {color};">{icon_char}</div><div class="p-name-container"><div class="p-fullname">{p.name}</div><div class="p-pos">{jp_pos}</div></div></div><div class="main-stats"><div class="ms-item"><span class="ms-label">打率</span><span class="ms-val">{avg_str}</span></div><div class="ms-item"><span class="ms-label">本塁打</span><span class="ms-val-small">{p.batting.HR}</span></div><div class="ms-item"><span class="ms-label">打点</span><span class="ms-val-small">{p.batting.RBI}</span></div><div class="ms-item"><span class="ms-label">盗塁</span><span class="ms-val-small">{p.batting.SB}</span></div><div class="ms-item"><span class="ms-label">OPS</span><span class="ms-val">{ops_str}</span></div></div><div class="sub-stats"><div class="ss-item">試合<b>{p.batting.G}</b></div><div class="ss-item">打席<b>{p.batting.PA}</b></div><div class="ss-item">打数<b>{p.batting.AB}</b></div><div class="ss-item">安打<b>{p.batting.H}</b></div><div class="ss-item">犠飛<b>{p.batting.SF}</b></div><div class="ss-item">UZR<b>{uzr_str}</b></div><div class="ss-item">失策<b>{p.fielding.E}</b></div></div></div>'
        html_bat += '</div>'

        html_pitch = '<div class="stats-container">'
        for i, p in enumerate(pitchers_list, start=1):
            icon_char = "投"
            if p in staff["starters"]: role_str, color = "先発", "#E53935"
            elif p == staff["closer"]: role_str, color = "抑え", "#EC407A"
            else: role_str, color = staff["bullpen_roles"].get(id(p), "中継ぎ"), "#EC407A"
            era_str = f"{era(p):.2f}"
            relief_wins = p.pitching.W if role_str != "先発" else 0
            hp_val = p.pitching.HLD + relief_wins
            html_pitch += f'<div class="stats-row"><div class="player-hdr"><div class="p-order">{i}</div><div class="p-icon" style="background-color: {color};">{icon_char}</div><div class="p-name-container"><div class="p-fullname">{p.name}</div><div class="p-pos">{role_str}</div></div></div><div class="main-stats"><div class="ms-item"><span class="ms-label">防御率</span><span class="ms-val">{era_str}</span></div><div class="ms-item"><span class="ms-label">勝</span><span class="ms-val-small">{p.pitching.W}</span></div><div class="ms-item"><span class="ms-label">敗</span><span class="ms-val-small">{p.pitching.L}</span></div><div class="ms-item"><span class="ms-label">HP</span><span class="ms-val-small">{hp_val}</span></div><div class="ms-item"><span class="ms-label">S</span><span class="ms-val-small">{p.pitching.SV}</span></div><div class="ms-item"><span class="ms-label">奪三振</span><span class="ms-val-small">{p.pitching.SO}</span></div></div><div class="sub-stats"><div class="ss-item">試合<b>{p.pitching.G}</b></div><div class="ss-item">先発<b>{p.pitching.GS}</b></div><div class="ss-item">投球回<b>{innings_str(p.pitching.outs)}</b></div><div class="ss-item">四球<b>{p.pitching.BB}</b></div><div class="ss-item">自責点<b>{p.pitching.ER}</b></div></div></div>'
        html_pitch += '</div>'
        
        with tab_bat: st.markdown(html_bat, unsafe_allow_html=True)
        with tab_pitch: st.markdown(html_pitch, unsafe_allow_html=True)

        with tab_detail:
            st.subheader("打者詳細成績")
            bat_df_data = []
            for p, pos in batters_to_show:
                b = p.batting
                main_pos = max(p.defense.items(), key=lambda x: x[1])[0] if p.defense else "DH"
                bat_df_data.append({
                    "選手名": p.name, "打率": fmt_pct(batting_avg(p)),
                    "試合": b.G, "打席": b.PA, "打数": b.AB, "得点": b.R, "安打": b.H, "二塁打": b.double, "三塁打": b.triple, "本塁打": b.HR,
                    "塁打": b.TB, "打点": b.RBI, "盗塁": b.SB, "盗塁死": b.CS, "四球": b.BB, "三振": b.SO, "犠飛": b.SF,
                    "出塁率": fmt_pct(obp(p)), "長打率": fmt_pct(slg(p)), "OPS": fmt_pct(ops(p)), "wRC+": round(calc_wrc_plus(p), 1),
                    "UZR": round(p.fielding.UZR, 1) if pos not in ["DH", "代打"] else "-", "失策": p.fielding.E, "WAR": round(calc_batter_war(p, main_pos), 1)
                })
            st.dataframe(pd.DataFrame(bat_df_data), hide_index=True, use_container_width=True)

            st.subheader("投手詳細成績")
            pit_df_data = []
            for p in pitchers_list:
                pt = p.pitching
                whip = (pt.H + pt.BB) / (pt.outs / 3) if pt.outs > 0 else 0.0
                pit_df_data.append({
                    "選手名": p.name, "防御率": f"{era(p):.2f}", "FIP": f"{calc_fip(p):.2f}",
                    "登板": pt.G, "先発": pt.GS, "勝": pt.W, "敗": pt.L, "セーブ": pt.SV, "ホールド": pt.HLD,
                    "勝率": fmt_pct(pt.W / (pt.W + pt.L) if (pt.W + pt.L) > 0 else 0),
                    "投球回": innings_str(pt.outs), "打者": pt.BF, "被安打": pt.H, "被本塁打": pt.HR, "与四球": pt.BB, "奪三振": pt.SO,
                    "失点": pt.R, "自責点": pt.ER, "WHIP": f"{whip:.2f}", "WAR": round(calc_pitcher_war(p), 1)
                })
            st.dataframe(pd.DataFrame(pit_df_data), hide_index=True, use_container_width=True)

        with tab_team:
            st.subheader(f"{selected_team} 通算成績")
            my_players = [p for p, _ in batters_to_show]
            
            t_ab = sum(p.batting.AB for p in my_players)
            t_h = sum(p.batting.H for p in my_players)
            t_hr = sum(p.batting.HR for p in my_players)
            t_avg = t_h / t_ab if t_ab > 0 else 0.0
            
            t_er = sum(p.pitching.ER for p in pitchers_list)
            t_outs = sum(p.pitching.outs for p in pitchers_list)
            t_era = t_er * 27 / t_outs if t_outs > 0 else 0.0

            col1, col2, col3 = st.columns(3)
            col1.metric("チーム得点", t_data["runs_for"])
            col2.metric("チーム打率", fmt_pct(t_avg))
            col3.metric("チーム本塁打", t_hr)
            
            col4, col5, col6 = st.columns(3)
            col4.metric("チーム失点", t_data["runs_against"])
            col5.metric("チーム防御率", f"{t_era:.2f}")

        with tab_standings:
            all_teams_data = result["all_teams_data"]
            standings_data = []
            my_league_teams = st.session_state.league_central if st.session_state.my_league == "セ・リーグ" else st.session_state.league_pacific
            
            for t_name in my_league_teams:
                t_data = all_teams_data[t_name]
                w, l, d = t_data["wins"], t_data["losses"], t_data["draws"]
                pct = w / (w + l) if (w + l) > 0 else 0
                standings_data.append({"team": t_name, "W": w, "L": l, "D": d, "pct": pct, "is_me": (t_name == "マイチーム")})

            standings_data.sort(key=lambda x: x["pct"], reverse=True)
            top_w, top_l = standings_data[0]["W"], standings_data[0]["L"]
            my_rank = next(i for i, r in enumerate(standings_data, 1) if r["is_me"])
            
            html_table = f'<div style="text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #111;">6チーム中 <span style="font-size: 38px;">{my_rank}位</span></div>'
            html_table += '<div style="border-radius: 8px; overflow: hidden; border: 1px solid #E5E5E5;"><table style="width: 100%; border-collapse: collapse; text-align: center; font-size: 15px; background-color: #FAFAFA; color: #333;"><tr style="background-color: #EFEFEF; color: #777; font-size: 13px;"><th style="padding: 12px; font-weight: normal;">順位</th><th style="padding: 12px; text-align: left; font-weight: normal;">チーム</th><th style="padding: 12px; font-weight: normal;">勝</th><th style="padding: 12px; font-weight: normal;">敗</th><th style="padding: 12px; font-weight: normal;">分</th><th style="padding: 12px; font-weight: normal;">勝率</th><th style="padding: 12px; font-weight: normal;">差</th></tr>'
            
            for i, row in enumerate(standings_data, start=1):
                bg_color = "background-color: #E8F5E9;" if row["is_me"] else ("background-color: #FFF;" if i % 2 == 0 else "")
                t_name = f'<span style="color: #2E7D32;">{row["team"]} 自分</span>' if row["is_me"] else row["team"]
                gb = ((top_w - row["W"]) + (row["L"] - top_l)) / 2.0
                gb_str = "－" if gb == 0 else f"{gb:.1f}"
                html_table += f'<tr style="border-top: 1px solid #E5E5E5; {bg_color}"><td style="padding: 12px; color: #555;">{i}</td><td style="padding: 12px; text-align: left; font-weight: bold;">{t_name}</td><td style="padding: 12px;">{row["W"]}</td><td style="padding: 12px;">{row["L"]}</td><td style="padding: 12px;">{row["D"]}</td><td style="padding: 12px; font-weight: bold;">{fmt_pct(row["pct"])}</td><td style="padding: 12px; color: #666;">{gb_str}</td></tr>'
            html_table += '</table></div>'
            st.markdown(html_table, unsafe_allow_html=True)

        with tab_log:
            st.subheader("全143試合 スコア・詳細記録")
            log_df = pd.DataFrame(result["game_log"])
            st.dataframe(log_df, hide_index=True, use_container_width=True, height=600, column_config={ "イニング": st.column_config.TextColumn("スコアボード", width="medium"), "本塁打": st.column_config.TextColumn("本塁打", width="large") })
            st.download_button("試合結果CSVをダウンロード", log_df.to_csv(index=False).encode("utf-8-sig"), file_name="game_results.csv", mime="text/csv")

        wins, losses, draws = result["wins"], result["losses"], result["draws"]
        win_pct = wins / (wins + losses) if (wins + losses) > 0 else 0
        if my_rank == 1: cs_text = "見事リーグ優勝を果たしました！"
        elif my_rank <= 3: cs_text = "見事CS進出を果たしました！"
        else: cs_text = "CS進出はなりませんでした。"

        st.markdown(f'<div class="season-end-wrap">6チーム中{my_rank}位。{cs_text}</div><div class="season-end-box"><div class="se-sub">１４３試合を終えて</div><div class="se-main">シーズン終了</div><div class="se-stats"><div class="se-rank-label">6チーム中</div><div class="se-rank-val">{my_rank}位</div><div class="se-rec">{wins}勝 {losses}敗 {draws}分</div><div class="se-rec">勝率 {fmt_pct(win_pct)}</div></div></div>', unsafe_allow_html=True)

        st.markdown('<div class="next-year-wrapper">', unsafe_allow_html=True)
        if st.button("もう1年やる", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
