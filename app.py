import random
import math
import copy
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import streamlit as st

# ============================================================
# ⚾ 野球チームメーカー / Streamlit 完全版 (疲労＆詳細ブルペン運用対応)
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
    "S": 95.0, "A": 85.0, "B": 75.0, "C": 65.0,
    "D": 55.0, "E": 45.0, "F": 30.0, "G": 10.0,
}

RANK_WEIGHT = {
    "S": 1.40, "A": 1.25, "B": 1.10, "C": 0.95,
    "D": 0.80, "E": 0.65, "F": 0.50, "G": 0.35,
}

BASE_PA = {
    "single": 0.160, "double": 0.048, "triple": 0.004,
    "hr": 0.018, "walk": 0.082, "so": 0.220,
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
    pitches: dict = field(default_factory=dict)
    batting: BatterStats = field(default_factory=BatterStats)
    pitching: PitcherStats = field(default_factory=PitcherStats)
    fielding: FielderStats = field(default_factory=FielderStats)
    
    # --- 疲労＆起用管理パラメーター ---
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
    if pd.isna(x):
        return default
    try:
        return float(x)
    except Exception:
        return default

def parse_defense(text):
    result = {}
    if pd.isna(text): return result
    for part in str(text).split("/"):
        part = part.strip()
        if ":" not in part: continue
        pos, value = part.split(":", 1)
        try:
            result[pos.strip().upper()] = float(value.strip())
        except ValueError: pass
    return result

def parse_pitches(text):
    result = {}
    if pd.isna(text): return result
    for part in str(text).split("/"):
        part = part.strip()
        if ":" not in part: continue
        name, rank = part.split(":", 1)
        rank = rank.strip().upper()
        if rank in RANK_VALUE:
            result[name.strip()] = rank
    return result

def require_columns(df, columns, label):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{label}に必要な列がありません: {', '.join(missing)}")

def load_fielders(source):
    df = pd.read_excel(source)
    require_columns(df, ["選手名", "チーム", "ミート", "パワー", "走力", "守備力"], "野手ファイル")
    players = []
    for _, row in df.iterrows():
        players.append(Player(
            name=str(row["選手名"]).strip(),
            team=str(row["チーム"]).strip(),
            contact=clean_number(row["ミート"]),
            power=clean_number(row["パワー"]),
            speed=clean_number(row["走力"]),
            defense=parse_defense(row["守備力"]),
        ))
    return players

def load_pitchers(source):
    df = pd.read_excel(source)
    require_columns(df, ["選手名", "チーム", "制球", "スタミナ", "球種ランク"], "投手ファイル")
    players = []
    for _, row in df.iterrows():
        players.append(Player(
            name=str(row["選手名"]).strip(),
            team=str(row["チーム"]).strip(),
            control=clean_number(row["制球"]),
            stamina=clean_number(row["スタミナ"]),
            pitches=parse_pitches(row["球種ランク"]),
        ))
    return players

# ============================================================
# 初期配置・チーム生成ロジック
# ============================================================
def assign_initial_positions(fielders, dh=True):
    remaining = list(fielders)
    lineup = []
    assigned_positions = set()
    assigned_players = set()
    
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

def count_pitches_of_rank(pitcher, ranks):
    return sum(1 for r in pitcher.pitches.values() if r in ranks)

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
    role_slots = ["抑え", "中継ぎエース", "中継ぎエース", "僅差", "僅差", "リード", "ビハインド", "敗戦処理", "敗戦処理"]
    
    for i, p in enumerate(remaining):
        if i < len(role_slots):
            roles[p.name] = role_slots[i]
        else:
            roles[p.name] = "敗戦処理"
    return roles

def build_teams(fielders, pitchers):
    teams = {}
    for p in fielders:
        teams.setdefault(p.team, {"fielders": [], "pitchers": []})
        teams[p.team]["fielders"].append(p)
    for p in pitchers:
        teams.setdefault(p.team, {"fielders": [], "pitchers": []})
        teams[p.team]["pitchers"].append(p)

    return {
        name: Team(name=name, fielders=data["fielders"], pitchers=data["pitchers"])
        for name, data in teams.items()
    }

def best_lineup_for_team(team, dh=True):
    lineup = assign_initial_positions(team.fielders, dh=dh)
    lineup = decide_batting_order(lineup)
    if len(lineup) > 9: lineup = lineup[:9]
    return lineup

def best_pitching_staff(team):
    roles = decide_pitcher_roles(team.pitchers)
    starters = [p for p in team.pitchers if roles.get(p.name) == "先発"]
    closer_list = [p for p in team.pitchers if roles.get(p.name) == "抑え"]
    closer = closer_list[0] if closer_list else None
    bullpen = [p for p in team.pitchers if roles.get(p.name) not in ("先発", "抑え")]
    
    bullpen_roles = {id(p): roles.get(p.name) for p in bullpen}
    return {"starters": starters, "bullpen": bullpen, "closer": closer, "bullpen_roles": bullpen_roles}

def build_opponent_team(team, dh):
    return {"team": team, "lineup": best_lineup_for_team(team, dh=dh), "staff": best_pitching_staff(team)}

def create_full_schedule(central_teams, pacific_teams):
    matchups = []
    for i in range(len(central_teams)):
        for j in range(i+1, len(central_teams)):
            for _ in range(25):
                matchups.append({"home": central_teams[i], "away": central_teams[j], "league": "セ・リーグ"})
                
    for i in range(len(pacific_teams)):
        for j in range(i+1, len(pacific_teams)):
            for _ in range(25):
                matchups.append({"home": pacific_teams[i], "away": pacific_teams[j], "league": "パ・リーグ"})

    for c_team in central_teams:
        for p_team in pacific_teams:
            for i in range(3):
                home = c_team if i % 2 == 0 else p_team
                away = p_team if home == c_team else c_team
                league_rule = "セ・リーグ" if home in central_teams else "パ・リーグ"
                matchups.append({"home": home, "away": away, "league": league_rule})

    random.shuffle(matchups)
    return matchups

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
# 野球シミュレーションロジック
# ============================================================
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def choose_pitch(pitcher):
    if not pitcher.pitches: return None
    names = list(pitcher.pitches.keys())
    weights = [RANK_WEIGHT.get(pitcher.pitches[n], 0.8) for n in names]
    return random.choices(names, weights=weights, k=1)[0]

def pitch_quality(pitcher, pitch_name):
    if pitch_name is None: return 55.0
    rank = pitcher.pitches.get(pitch_name, "C")
    return RANK_VALUE.get(rank, 55.0)

def fatigue_factor(pitcher, game_outs):
    innings = game_outs / 3.0
    if innings <= 4: return 1.0
    excess = innings - 4
    penalty = excess * max(0.0, (80.0 - pitcher.stamina)) * 0.0015
    return clamp(1.0 - penalty, 0.82, 1.0)

def at_bat_probabilities(batter, pitcher, game_outs):
    pitch_name = choose_pitch(pitcher)
    quality = pitch_quality(pitcher, pitch_name)
    fatigue = fatigue_factor(pitcher, game_outs)

    raw_contact_diff = batter.contact - quality
    control_diff = pitcher.control - 50.0

    contact_penalty = 0.0
    if batter.contact < 60.0:
        diff = 60.0 - max(40.0, batter.contact)
        contact_penalty = (diff * 0.4) + ((diff ** 2) * 0.01)

    power_penalty = 0.0
    if batter.power < 60.0:
        diff = 60.0 - max(40.0, batter.power)
        power_penalty = (diff * 0.4) + ((diff ** 2) * 0.01)

    variety_debuff = max(0, len(pitcher.pitches) - 2) * 0.0015

    walk_bonus = 0.0
    if batter.power > 50.0: walk_bonus += (batter.power - 50.0) * 0.0012
    if batter.contact > 50.0: walk_bonus += (batter.contact - 50.0) * 0.0006
    if batter.power >= 80.0: walk_bonus += (batter.power - 80.0) * 0.0015

    eff_contact, eff_power = batter.contact, batter.power
    total_cp = eff_contact + eff_power
    if total_cp > 141.0:
        excess = total_cp - 141.0
        eff_contact -= (excess * (eff_contact / total_cp)) * 0.80
        eff_power -= (excess * (eff_power / total_cp)) * 0.80

    hit_contact_diff = eff_contact - quality
    hit_power_diff = eff_power - quality

    hr_bonus = 0.0
    if eff_power >= 58.0:
        if eff_power < 80.0:
            d = eff_power - 58.0
            hr_bonus = (d * 0.0005) + ((d ** 2) * 0.00006)
        else:
            d_to_80 = 80.0 - 58.0
            base_80 = (d_to_80 * 0.0005) + ((d_to_80 ** 2) * 0.00006)
            hr_bonus = base_80 + ((eff_power - 80.0) * 0.0006)

    single = BASE_PA["single"] + hit_contact_diff * 0.0015 - (contact_penalty * 0.0010) - variety_debuff
    double = BASE_PA["double"] + hit_contact_diff * 0.00015 + hit_power_diff * 0.00025 - ((contact_penalty + power_penalty) * 0.0002) - (variety_debuff * 0.5)
    triple = BASE_PA["triple"] + batter.speed * 0.00006
    hr = BASE_PA["hr"] + hit_power_diff * 0.0004 - (power_penalty * 0.0012) + hr_bonus - (variety_debuff * 0.5)
    
    single -= hr_bonus * 0.75
    double -= hr_bonus * 0.25
    
    walk = BASE_PA["walk"] - control_diff * 0.0012 + walk_bonus
    so = BASE_PA["so"] - raw_contact_diff * 0.0008 + (contact_penalty * 0.0015) + (power_penalty * 0.0008) + variety_debuff

    q_delta = quality - 60.0
    single -= q_delta * 0.00045
    double -= q_delta * 0.00025
    hr -= q_delta * 0.00030
    so += q_delta * 0.0045

    if fatigue < 1.0:
        single += (1.0 - fatigue) * 0.03
        hr += (1.0 - fatigue) * 0.015
        walk += (1.0 - fatigue) * 0.02
        so -= (1.0 - fatigue) * 0.03

    single = clamp(single, 0.01, 0.30)
    double = clamp(double, 0.002, 0.12)
    triple = clamp(triple, 0.001, 0.03)
    hr = clamp(hr, 0.001, 0.12)
    walk = clamp(walk, 0.015, 0.25)
    so = clamp(so, 0.05, 0.45)

    used = single + double + triple + hr + walk + so
    out = max(0.02, 1.0 - used)
    total = used + out

    probs = [
        ("single", single / total), ("double", double / total), ("triple", triple / total),
        ("hr", hr / total), ("walk", walk / total), ("so", so / total), ("out", out / total),
    ]
    return probs, pitch_name

def choose_result(probs):
    r = random.random()
    cumulative = 0.0
    for result, prob in probs:
        cumulative += prob
        if r <= cumulative: return result
    return "out"

def choose_batted_ball_position(defense):
    positions = ["1B", "2B", "3B", "SS", "LF", "CF", "RF"]
    weights = [1.0, 1.1, 1.0, 1.2, 0.9, 1.0, 0.9]
    pos = random.choices(positions, weights=weights, k=1)[0]
    return pos, defense.get(pos)

def resolve_outcome(result, defense):
    pos, defender = choose_batted_ball_position(defense)
    if defender is None: return "field_out", pos, None

    ability = defender.defense_at(pos)
    error_prob = clamp(0.0028 * (1.0 + clamp((70.0 - ability) / 70.0, -0.35, 0.90)), 0.0009, 0.0050)

    if random.random() >= error_prob:
        defender.fielding.PO += 1
        defender.fielding.UZR += (ability - 50.0) / 1200.0
        return "field_out", pos, defender

    defender.fielding.E += 1
    defender.fielding.UZR -= 0.5 + max(0.0, (50.0 - ability) / 100.0)
    return "error", pos, defender

def advance_on_hit(bases, batter, result):
    new_bases = [None, None, None]
    runs = 0
    scoring = []

    if result == "hr":
        for runner in bases:
            if runner: runs += 1; scoring.append(runner)
        runs += 1; scoring.append(batter)
        return new_bases, runs, scoring

    if result == "triple":
        for runner in bases:
            if runner: runs += 1; scoring.append(runner)
        new_bases[2] = batter
        return new_bases, runs, scoring

    if result == "double":
        if bases[2]: runs += 1; scoring.append(bases[2])
        if bases[1]:
            if random.random() < clamp(0.55 + bases[1].speed / 300.0, 0.55, 0.90): runs += 1; scoring.append(bases[1])
            else: new_bases[2] = bases[1]
        if bases[0]:
            if random.random() < clamp(0.30 + bases[0].speed / 250.0, 0.30, 0.82): runs += 1; scoring.append(bases[0])
            else: new_bases[2] = bases[0]
        new_bases[1] = batter
        return new_bases, runs, scoring

    if bases[2]: runs += 1; scoring.append(bases[2])
    if bases[1]:
        if random.random() < clamp(0.55 + bases[1].speed / 250.0, 0.55, 0.95): runs += 1; scoring.append(bases[1])
        else: new_bases[2] = bases[1]
    if bases[0]:
        if random.random() < clamp(0.25 + bases[0].speed / 300.0, 0.10, 0.70): new_bases[2] = bases[0]
        else: new_bases[1] = bases[0]
            
    new_bases[0] = batter
    return new_bases, runs, scoring

def advance_on_walk(bases, batter):
    new_bases = list(bases)
    runs = 0
    scoring = []
    if bases[0] and bases[1] and bases[2]: runs = 1; scoring.append(bases[2])
    if bases[0] and bases[1]: new_bases[2] = bases[1]
    if bases[0]: new_bases[1] = bases[0]
    new_bases[0] = batter
    return new_bases, runs, scoring

def attempt_steal(bases, offense_lineup, defense, game_state=None):
    catcher = defense.get("C")
    if not catcher: return bases
    candidates = []
    if bases[0] and not bases[1]: candidates.append((0, 1, 0.10, 0.34))
    if bases[1] and not bases[2]: candidates.append((1, 2, 0.045, 0.22))
    if not candidates: return bases

    from_base, to_base, base_attempt, speed_factor = candidates[0]
    runner = bases[from_base]
    
    if random.random() >= clamp(base_attempt + runner.speed / 500.0, 0.03, 0.34 if from_base == 0 else 0.18):
        return bases

    success_prob = clamp(0.10 + (runner.speed - 30.0) * 0.007 - (catcher.defense_at("C") - 30.0) * 0.004, 0.03, 0.88)
    if random.random() < success_prob:
        bases[from_base] = None
        bases[to_base] = runner
        runner.batting.SB += 1
    else:
        bases[from_base] = None
        runner.batting.CS += 1
        if game_state: game_state["outs"] += 1
    return bases

# ============================================================
# 新設・投手起用ロジック (詳細優先度＆疲労システム)
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

    def get_role(self, pitcher):
        if pitcher in self.starters: return "先発"
        if pitcher is self.closer: return "抑え"
        return self.bullpen_roles.get(id(pitcher), "僅差")

    def get_role_priority(self, inning, score_diff):
        """シチュエーションに応じた登板優先度リストを返す (左ほど優先)"""
        if inning >= 9 and 0 < score_diff <= 3:
            return ["抑え", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]
        elif inning >= 12 and score_diff == 0:
            return ["抑え", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理"]
        elif 6 <= inning <= 8 and 0 < score_diff <= 3:
            return ["中継ぎエース", "僅差", "リード", "抑え", "ビハインド", "敗戦処理"]
        elif 1 <= inning <= 8 and score_diff >= 4:
            return ["リード", "僅差", "中継ぎエース", "ビハインド", "抑え", "敗戦処理"]
        elif inning >= 9 and score_diff >= 4:
            return ["リード", "抑え", "中継ぎエース", "僅差", "ビハインド", "敗戦処理"]
        elif -3 <= score_diff < 0:
            return ["ビハインド", "敗戦処理", "リード", "僅差", "中継ぎエース", "抑え"]
        elif score_diff <= -4:
            return ["敗戦処理", "ビハインド", "リード", "僅差", "中継ぎエース", "抑え"]
        elif 6 <= inning <= 12 and score_diff == 0:
            return ["僅差", "中継ぎエース", "リード", "抑え", "ビハインド", "敗戦処理"]
        elif inning <= 5 and score_diff >= 0:
            return ["リード", "僅差", "ビハインド", "中継ぎエース", "敗戦処理", "抑え"]
            
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
        pitches = p.game_pitches_today
        
        # スタミナ限界の決定（疲労を考慮）
        if p_id not in self.max_pitches:
            base_limit = min(p.stamina * random.uniform(1.1, 1.3), p.current_stamina + 20)
            if p not in self.starters:
                base_limit = min(base_limit, 45) # 中継ぎは最大でも45球制限
            self.max_pitches[p_id] = max(15, base_limit)
        max_limit = self.max_pitches[p_id]
        
        is_stamina_empty = pitches >= max_limit
        role = self.get_role(p)

        # ボコボコに打たれた場合は強制降板
        if runs >= 7: return True
        if runs >= 5 and current_outs >= 15: return True
        if runs >= 3 and current_outs >= 18: return True
        
        # スタミナ切れ
        if is_stamina_empty: return True

        # 先発は失点かスタミナ切れまで投げる
        if p in self.starters: return False

        # 中継ぎの回跨ぎ強制フラグ処理
        if p.force_continue_outs > 0 and current_outs < p.force_continue_outs:
            return False

        # シチュエーション変化による回跨ぎ判定
        priority = self.get_role_priority(inning, score_diff)
        if role == priority[0]:
            return False # 優先度1位なら続投（回跨ぎ）
            
        return True # それ以外は交代

    def _select_bullpen(self, inning, score_diff):
        priority = self.get_role_priority(inning, score_diff)
        
        # 登板可能投手のフィルタリング（4連投禁止、疲労過多禁止）
        available = []
        all_bullpen = self.bullpen + ([self.closer] if self.closer else [])
        for p in all_bullpen:
            if p in self.used_bullpen: continue
            if getattr(p, 'consecutive_games', 0) >= 3: continue # 4連投禁止
            if getattr(p, 'current_stamina', 50) < 10: continue
            available.append(p)

        # 3連投ハードルを上げる（連投数2未満のフレッシュな投手を優先）
        fresh_available = [p for p in available if getattr(p, 'consecutive_games', 0) < 2]

        def pick_by_priority(pool, prio_list):
            for r in prio_list:
                candidates = [p for p in pool if self.get_role(p) == r]
                if candidates:
                    candidates.sort(key=lambda x: getattr(x, 'current_stamina', 0), reverse=True)
                    return candidates[0]
            return None

        selected = None
        if fresh_available:
            selected = pick_by_priority(fresh_available, priority)
            
        if selected is None and available:
            selected = pick_by_priority(available, priority)
            
        # 誰もいない場合の緊急措置
        if selected is None:
            emergency = [p for p in all_bullpen if p not in self.used_bullpen]
            if emergency:
                emergency.sort(key=lambda x: getattr(x, 'current_stamina', 0), reverse=True)
                selected = emergency[0]
            else:
                return None # 完全空っぽなら交代不可

        # 強制回跨ぎフラグのセット（リード、敗戦処理）
        if selected:
            role = self.get_role(selected)
            if role == "リード" and priority[0] == "リード" and score_diff >= 4:
                if random.random() < 0.50:
                    selected.force_continue_outs = 6
            elif role == "敗戦処理" and priority[0] == "敗戦処理":
                r = random.random()
                if r < 0.40: selected.force_continue_outs = 9
                else: selected.force_continue_outs = 6
                    
        return selected

    def replace(self, inning, score_diff):
        old = self.current
        if old is None: return None
        new = self._select_bullpen(inning, score_diff)

        if new is None or new is old:
            return self.current

        old_id = id(old)
        entered_score_diff = self.hold_eligible.get(old_id)
        if old in self.bullpen and entered_score_diff is not None:
            if entered_score_diff > 0 and score_diff > 0 and old is not self.closer:
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

        if new in self.bullpen:
            self.hold_eligible[id(new)] = score_diff > 0
        if new is self.closer:
            self.save_eligible = inning >= 8 and 0 < score_diff <= 3

        return self.current

# ============================================================
# 1試合シミュレーション
# ============================================================
def simulate_half_inning(offense_lineup, batting_index, pitcher, defense, league, inning=1, top_bottom="表", game_state=None):
    outs = 0
    bases = [None, None, None]
    runs = 0
    hr_log = []

    while outs < 3:
        steal_state = {"outs": outs}
        before_outs = outs
        bases = attempt_steal(bases, offense_lineup, defense, steal_state)
        outs = steal_state["outs"]
        if outs > before_outs:
            pitcher.pitching.outs += (outs - before_outs)
        if outs >= 3: break

        batter = offense_lineup[batting_index[0] % len(offense_lineup)]
        batting_index[0] += 1
        batter.batting.PA += 1
        pitcher.pitching.BF += 1

        probs, pitch_name = at_bat_probabilities(batter, pitcher, pitcher.pitching.outs)
        result = choose_result(probs)

        if result in ("so", "walk"): pa_pitches = random.randint(4, 8)
        else: pa_pitches = random.randint(1, 6)
        
        pitcher.game_pitches_today += pa_pitches
        pitcher.did_pitch_today = True

        if result in ("single", "double", "triple", "hr"):
            batter.batting.AB += 1
            batter.batting.H += 1
            if result == "hr":
                runners_on = sum(1 for r in bases if r is not None)
                run_type_char = {0: "①", 1: "②", 2: "③", 3: "④"}[runners_on]
                batter.batting.HR += 1
                hr_log.append(f"{inning}回{top_bottom} {batter.name} {batter.batting.HR}号{run_type_char}")
                batter.batting.TB += 4
                pitcher.pitching.HR += 1
            elif result == "single": batter.batting.TB += 1
            elif result == "double": batter.batting.double += 1; batter.batting.TB += 2
            elif result == "triple": batter.batting.triple += 1; batter.batting.TB += 3
            pitcher.pitching.H += 1

            bases, scored, scoring = advance_on_hit(list(bases), batter, result)
            runs += scored
            if scored: batter.batting.RBI += scored
            for r in scoring: r.batting.R += 1
            if result == "hr": batter.batting.R += 1
        elif result == "walk":
            batter.batting.BB += 1
            pitcher.pitching.BB += 1
            bases, scored, scoring = advance_on_walk(bases, batter)
            runs += scored
            if scored: batter.batting.RBI += scored
            for r in scoring: r.batting.R += 1
        elif result == "so":
            batter.batting.AB += 1; batter.batting.SO += 1; pitcher.pitching.SO += 1
            outs += 1; pitcher.pitching.outs += 1
        else:
            outcome, pos, defender = resolve_outcome(result, defense)
            if outcome == "field_out":
                outs += 1; pitcher.pitching.outs += 1
                if defender: defender.fielding.A += 1
                
                is_sf = False
                if outs <= 2 and bases[2]:
                    runner = bases[2]
                    if pos in ["LF", "CF", "RF"]:
                        arm = defender.defense_at(pos) if defender else 30.0
                        if random.random() < clamp(0.50 + (runner.speed - arm) * 0.005, 0.10, 0.95):
                            runs += 1; batter.batting.RBI += 1; runner.batting.R += 1; batter.batting.SF += 1
                            bases[2] = None; is_sf = True
                    elif pos in ["1B", "2B", "3B", "SS"]:
                        base_prob = 0.45 if pos in ["2B", "SS"] else 0.25
                        if random.random() < clamp(base_prob + (runner.speed - 40.0) * 0.004, 0.05, 0.85):
                            runs += 1; batter.batting.RBI += 1; runner.batting.R += 1
                            bases[2] = None
                if not is_sf: batter.batting.AB += 1

                if outs <= 2 and not bases[2] and bases[1]:
                    r2 = bases[1]
                    adv = 0.0
                    if pos == "RF": adv = 0.55 + r2.speed * 0.004
                    elif pos == "CF": adv = 0.25 + r2.speed * 0.003
                    elif pos == "LF": adv = 0.05
                    elif pos in ["1B", "2B"]: adv = 0.50 + r2.speed * 0.004
                    elif pos in ["3B", "SS"]: adv = 0.10 + r2.speed * 0.002
                    if random.random() < clamp(adv, 0.05, 0.90): bases[2] = r2; bases[1] = None

                if outs <= 2 and not bases[1] and bases[0]:
                    if pos in ["1B", "2B", "3B", "SS"]:
                        if random.random() < clamp(0.35 + bases[0].speed * 0.002, 0.01, 0.40):
                            bases[1] = bases[0]; bases[0] = None
            else:
                batter.batting.AB += 1
                if not bases[0]: bases[0] = batter
                elif not bases[1]: bases[1] = bases[0]; bases[0] = batter
                elif not bases[2]: bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = batter
                else:
                    runs += 1; batter.batting.RBI += 1; bases[2].batting.R += 1
                    bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = batter

    return runs, hr_log

def simulate_game(my_lineup, my_staff, op_lineup, op_staff, league, my_game_number, op_game_number):
    my_pitching = PitchingState(my_staff)
    op_pitching = PitchingState(op_staff)

    my_pitcher = my_pitching.choose_starter(my_game_number)
    op_pitcher = op_pitching.choose_starter(op_game_number)

    lead_state = 0
    my_por = my_pitcher
    op_por = op_pitcher
    my_score = op_score = 0
    my_batting_index, op_batting_index = [0], [0]
    op_linescore, my_linescore, hr_events = [], [], []

    for p, _ in my_lineup: p.batting.G += 1
    for p, _ in op_lineup: p.batting.G += 1
    if league == "セ・リーグ":
        if my_pitcher: my_pitcher.batting.G += 1
        if op_pitcher: op_pitcher.batting.G += 1

    for inning in range(1, 13):
        # 表
        if my_pitching.should_replace(my_score - op_score, inning, my_pitcher.pitching.outs if my_pitcher else 0):
            my_pitcher = my_pitching.replace(inning, my_score - op_score)

        defense_my = {pos: player for player, pos in my_lineup if pos != "DH"}
        offense_op = list(op_lineup)
        if league == "セ・リーグ" and op_pitcher and len(offense_op) == 8: offense_op.append((op_pitcher, "P"))

        if my_pitcher:
            r_op, hrs_op = simulate_half_inning([p for p, _ in offense_op], op_batting_index, my_pitcher, defense_my, league, inning=inning, top_bottom="表")
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
            lead_state = -1; my_por = my_pitcher; op_por = op_pitcher
        elif op_score == my_score: lead_state = 0

        if inning >= 9 and my_score > op_score:
            my_linescore.append("X")
            break

        # 裏
        if op_pitching.should_replace(op_score - my_score, inning, op_pitcher.pitching.outs if op_pitcher else 0):
            op_pitcher = op_pitching.replace(inning, op_score - my_score)

        defense_op = {pos: player for player, pos in op_lineup if pos != "DH"}
        offense_my = list(my_lineup)
        if league == "セ・リーグ" and my_pitcher and len(offense_my) == 8: offense_my.append((my_pitcher, "P"))

        if op_pitcher:
            r_my, hrs_my = simulate_half_inning([p for p, _ in offense_my], my_batting_index, op_pitcher, defense_op, league, inning=inning, top_bottom="裏")
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
            lead_state = 1; my_por = my_pitcher; op_por = op_pitcher
        elif my_score == op_score: lead_state = 0

        if inning >= 9 and my_score != op_score: break

    def resolve_win(win_pitching_state, win_por):
        win_p = win_por
        if win_p and win_p in win_pitching_state.starters:
            outs = win_p.pitching.outs - win_pitching_state.appearance_start_outs.get(id(win_p), win_p.pitching.outs)
            if outs < 15:
                relievers = [p for p in win_pitching_state.game_pitchers if p not in win_pitching_state.starters]
                if relievers:
                    p_outs = [(p, p.pitching.outs - win_pitching_state.appearance_start_outs.get(id(p), p.pitching.outs)) for p in relievers]
                    max_outs = max((o for p, o in p_outs), default=0)
                    cands = [p for p, o in p_outs if o == max_outs]
                    if cands: win_p = random.choice(cands)
        return win_p

    save_pitcher = None
    if my_score > op_score:
        winning_pitcher = resolve_win(my_pitching, my_por)
        losing_pitcher = op_por
        if winning_pitcher:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in my_pitching.game_holds: my_pitching.game_holds.remove(winning_pitcher)
        if losing_pitcher: losing_pitcher.pitching.L += 1
        if my_pitcher and my_pitcher is my_pitching.closer and my_pitching.save_eligible and my_pitcher is not winning_pitcher:
            my_pitcher.pitching.SV += 1
            save_pitcher = my_pitcher
        return my_score, op_score, {"result": "W", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}
    elif my_score < op_score:
        winning_pitcher = resolve_win(op_pitching, op_por)
        losing_pitcher = my_por
        if winning_pitcher:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in op_pitching.game_holds: op_pitching.game_holds.remove(winning_pitcher)
        if losing_pitcher: losing_pitcher.pitching.L += 1
        if op_pitcher and op_pitcher is op_pitching.closer and op_pitching.save_eligible and op_pitcher is not winning_pitcher:
            op_pitcher.pitching.SV += 1
            save_pitcher = op_pitcher
        return my_score, op_score, {"result": "L", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}
    else:
        return my_score, op_score, {"result": "D", "winning_pitcher": None, "losing_pitcher": None, "save_pitcher": None, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

# ============================================================
# ユーティリティ・成績表示ヘルパー
# ============================================================
def batting_avg(p): return p.batting.H / p.batting.AB if p.batting.AB else 0.0
def obp(p):
    b = p.batting; den = b.AB + b.BB + b.SF
    return (b.H + b.BB) / den if den else 0.0
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
    mapping = {
        "C": ("捕", "#03A9F4", "捕手"), "1B": ("一", "#F9A825", "一塁手"),
        "2B": ("二", "#F9A825", "二塁手"), "3B": ("三", "#F9A825", "三塁手"),
        "SS": ("遊", "#F9A825", "遊撃手"), "LF": ("左", "#388E3C", "左翼手"),
        "CF": ("中", "#388E3C", "中堅手"), "RF": ("右", "#388E3C", "右翼手"),
        "DH": ("D", "#757575", "指名打者"), "P": ("投", "#E53935", "投手"),
    }
    return mapping.get(pos, ("?", "#999", "不明"))

def val_to_rank(val):
    if val >= 90: return "S", "#D4AF37"  
    elif val >= 80: return "A", "#E91E63" 
    elif val >= 70: return "B", "#F44336" 
    elif val >= 60: return "C", "#FF9800" 
    elif val >= 50: return "D", "#FFD600" 
    elif val >= 40: return "E", "#4CAF50" 
    elif val >= 20: return "F", "#2196F3" 
    else: return "G", "#9E9E9E"

# ============================================================
# UI (ドラフト・オーダー・投手起用)
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

    st.markdown("""<style>
    .draft-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 10px;}
    .draft-count { font-size: 28px; font-weight: bold; color: #111;}
    .draft-count-sub { font-size: 14px; color: #666; font-weight: normal; margin-left: 10px;}
    .skip-badge { background-color: #ffebee; color: #c62828; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 14px; }
    </style>""", unsafe_allow_html=True)

    rem_skips_html = f'<div class="skip-badge">見送り残り：{skip_limit - st.session_state[skip_key]}回</div>' if skip_limit else ""

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

    st.markdown("""<style>
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
    </style>""", unsafe_allow_html=True)

    main_pos_str = "・".join([POSITION_JP.get(pos, pos) for pos in candidate.defense.keys()]) if kind == "野手" and candidate.defense else "投手" if kind == "投手" else "不明"
    
    card_html = f'<div class="card"><div class="p-tag">{main_pos_str}</div><div class="p-name">{candidate.name}</div><div class="p-meta">{candidate.team} 所属</div><div class="stats-box">'
    stats = [("ミート", candidate.contact), ("パワー", candidate.power), ("走力", candidate.speed), ("守備力", max(candidate.defense.values()) if candidate.defense else 0)] if kind == "野手" else [("制球", candidate.control), ("スタミナ", candidate.stamina)]
        
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
        for p_name, rank in candidate.pitches.items(): card_html += f'<span class="pos-badge">{p_name} {rank}</span>'
        card_html += '</div>'
        
    card_html += '</div>'
    st.markdown(card_html, unsafe_allow_html=True)

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
            m_pos = "・".join([POSITION_JP.get(pos, pos) for pos in p.defense.keys()]) if kind == "野手" and p.defense else "投手" if kind == "投手" else "不明"
            sel_html += f'<div style="background-color: #f5f5f5; border: 1px solid #ddd; padding: 5px 12px; border-radius: 6px; font-size: 13px;"><b style="color:#555;">{m_pos}</b> {p.name}</div>'
        sel_html += '</div>'
        st.markdown(sel_html, unsafe_allow_html=True)

    return False

def order_page(fielders, league):
    st.header("④ オーダー設定")
    initial_lineup = assign_initial_positions(fielders, dh=(league == "パ・リーグ"))
    default_pos_map = {pos: p for p, pos in initial_lineup}

    lineup = []
    used = set()
    st.subheader("守備位置")

    for pos in POSITIONS:
        available = [p for p in fielders if p.name not in used]
        if not available:
            st.error("野手の人数が不足しています。")
            return None
        names = [p.name for p in available]
        default_p = default_pos_map.get(pos)
        idx = names.index(default_p.name) if default_p and default_p.name in names else 0
        selected_name = st.selectbox(f"{POSITION_JP[pos]} ({pos})", names, index=idx, key=f"order_{pos}")
        player = next(p for p in available if p.name == selected_name)
        lineup.append((player, pos))
        used.add(player.name)

    remaining = [p for p in fielders if p.name not in used]
    if league == "パ・リーグ":
        st.subheader("DH")
        names = [p.name for p in remaining]
        default_p = default_pos_map.get("DH")
        idx = names.index(default_p.name) if default_p and default_p.name in names else 0
        dh_name = st.selectbox("DH", names, index=idx, key="order_DH")
        dh = next(p for p in remaining if p.name == dh_name)
        lineup.append((dh, "DH"))

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
    if st.button("オーダー決定", type="primary"):
        return {"lineup": ordered, "bench": bench}
    return None

def pitching_page(pitchers):
    st.header("⑤ 投手起用設定")
    if "pitcher_roles" not in st.session_state:
        st.session_state.pitcher_roles = decide_pitcher_roles(pitchers)

    def update_role(p_name):
        st.session_state.pitcher_roles[p_name] = st.session_state[f"sel_{p_name}"]

    roles_list = list(st.session_state.pitcher_roles.values())
    sp_count = roles_list.count("先発")
    cl_count = roles_list.count("抑え")

    if sp_count != 6: st.warning(f"先発は6人ちょうどにしてください（いま{sp_count}人）")
    if cl_count != 1: st.warning(f"抑えは1人ちょうどにしてください（いま{cl_count}人）")

    role_options = ["先発", "中継ぎエース", "僅差", "リード", "ビハインド", "敗戦処理", "抑え"]

    for p in pitchers:
        c1, c2 = st.columns([3, 1])
        with c1: st.markdown(f'<b>{p.name}</b> / {p.team}所属・スタミナ {int(p.stamina)}', unsafe_allow_html=True)
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
# メインアプリケーション実行
# ============================================================

st.title("⚾ 野球チームメーカー")

try:
    fielders_all = load_fielders("野手能力データ_最新.xlsx")
    pitchers_all = load_pitchers("投手能力データ_最新.xlsx")
except Exception as e:
    st.error("Excel読み込みエラーが発生しました。app.pyと同じフォルダに指定されたExcelファイルがあるか確認してください。")
    st.stop()

if "step" not in st.session_state:
    st.session_state.step = "start"

st.session_state.teams = build_teams(fielders_all, pitchers_all)

if st.session_state.step == "start":
    if st.button("ゲームを始める", type="primary"):
        st.session_state.step = "league_setup"
        st.rerun()

elif st.session_state.step == "league_setup":
    st.header("① NPBリーグ設定")
    if st.button("リーグ設定を確認してドラフト開始", type="primary"):
        st.session_state.central = CENTRAL_TEAMS.copy()
        st.session_state.pacific = PACIFIC_TEAMS.copy()
        st.session_state.step = "draft_fielders"
        st.rerun()

elif st.session_state.step == "draft_fielders":
    if draft_page("野手", fielders_all, 9, skip_limit=5):
        st.session_state.step = "draft_pitchers"
        st.rerun()

elif st.session_state.step == "draft_pitchers":
    if draft_page("投手", pitchers_all, 15, skip_limit=5):
        st.session_state.step = "league_select"
        st.rerun()

elif st.session_state.step == "league_select":
    st.header("③ セ・パ選択")
    league = st.radio("どちらのリーグに所属しますか？", ["セ・リーグ", "パ・リーグ"])
    if st.button("リーグ決定", type="primary"):
        st.session_state.my_league = league
        st.session_state.step = "order"
        st.rerun()

elif st.session_state.step == "order":
    res = order_page(st.session_state.draft_fielders, st.session_state.my_league)
    if res:
        st.session_state.my_lineup = res["lineup"]
        st.session_state.my_bench = res["bench"]
        st.session_state.step = "pitching"
        st.rerun()

elif st.session_state.step == "pitching":
    res = pitching_page(st.session_state.draft_pitchers)
    if res:
        st.session_state.my_staff = res
        st.session_state.step = "ready"
        st.rerun()

elif st.session_state.step == "ready":
    st.header("⑥ 開幕前確認")
    if st.session_state.my_league == "セ・リーグ":
        st.session_state.league_central = random.sample(st.session_state.central.copy(), 5) + ["マイチーム"]
        st.session_state.league_pacific = random.sample(st.session_state.pacific.copy(), 6)
    else:
        st.session_state.league_pacific = random.sample(st.session_state.pacific.copy(), 5) + ["マイチーム"]
        st.session_state.league_central = random.sample(st.session_state.central.copy(), 6)
        
    if st.button("⚾ シーズン開始", type="primary"):
        st.session_state.step = "season"
        st.rerun()

elif st.session_state.step == "season":
    st.header("⑦ 全試合シミュレーション中...")
    
    all_sim_players = list(fielders_all) + list(pitchers_all)
    all_sim_players.extend([p for p, _ in st.session_state.my_lineup])
    if st.session_state.my_bench: all_sim_players.append(st.session_state.my_bench)
    all_sim_players.extend(st.session_state.my_staff["starters"])
    all_sim_players.extend(st.session_state.my_staff["bullpen"])
    if st.session_state.my_staff["closer"]: all_sim_players.append(st.session_state.my_staff["closer"])
    reset_stats(all_sim_players)
    
    all_teams_data = {}
    for t_name in st.session_state.league_central + st.session_state.league_pacific:
        if t_name == "マイチーム":
            lineup, staff = st.session_state.my_lineup, st.session_state.my_staff
        else:
            dh = (t_name in st.session_state.league_pacific)
            lineup = best_lineup_for_team(st.session_state.teams[t_name], dh=dh)
            staff = best_pitching_staff(st.session_state.teams[t_name])
        all_teams_data[t_name] = {"lineup": lineup, "staff": staff, "games_played": 0, "wins": 0, "losses": 0, "draws": 0, "runs_for": 0, "runs_against": 0}

    full_schedule = create_full_schedule(st.session_state.league_central, st.session_state.league_pacific)
    
    game_log = []
    progress = st.progress(0)
    
    for idx, match in enumerate(full_schedule, start=1):
        h_name, a_name = match["home"], match["away"]
        h_team, a_team = all_teams_data[h_name], all_teams_data[a_name]
        
        score_h, score_a, result = simulate_game(
            h_team["lineup"], h_team["staff"], a_team["lineup"], a_team["staff"],
            match["league"], h_team["games_played"], a_team["games_played"]
        )
        
        h_team["games_played"] += 1; a_team["games_played"] += 1
        h_team["runs_for"] += score_h; h_team["runs_against"] += score_a
        a_team["runs_for"] += score_a; a_team["runs_against"] += score_h
        
        if result["result"] == "W": h_team["wins"] += 1; a_team["losses"] += 1
        elif result["result"] == "L": h_team["losses"] += 1; a_team["wins"] += 1
        else: h_team["draws"] += 1; a_team["draws"] += 1

        # --- 疲労システムの更新（試合後日次処理） ---
        for t_name in [h_name, a_name]:
            t_data = all_teams_data[t_name]
            for p in t_data["staff"]["starters"] + t_data["staff"]["bullpen"] + ([t_data["staff"]["closer"]] if t_data["staff"]["closer"] else []):
                if p.did_pitch_today:
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
            
            my_res = "W" if result["result"] == "W" and is_home else "L" if result["result"] == "L" and is_home else "D"
            if result["result"] == "W" and not is_home: my_res = "L"
            if result["result"] == "L" and not is_home: my_res = "W"
                
            win_p = result["winning_pitcher"]; los_p = result["losing_pitcher"]; sv_p = result["save_pitcher"]
            my_ls = result["my_linescore"] if is_home else result["op_linescore"]
            op_ls = result["op_linescore"] if is_home else result["my_linescore"]
            
            game_log.append({
                "試合": all_teams_data["マイチーム"]["games_played"],
                "対戦相手": op_name, "勝敗": my_res, "スコア": f"{my_score} - {op_score}",
                "イニング": f"相: {format_linescore(op_ls)}\n自: {format_linescore(my_ls)}",
                "勝投手": win_p.name if win_p else "-", "敗投手": los_p.name if los_p else "-",
                "S投手": sv_p.name if sv_p else "-", "本塁打": "、".join(result.get("hrs", []))
            })
            
        if idx % 20 == 0 or idx == len(full_schedule):
            progress.progress(idx / len(full_schedule))

    st.session_state.season_result = {
        "wins": all_teams_data["マイチーム"]["wins"], "losses": all_teams_data["マイチーム"]["losses"],
        "draws": all_teams_data["マイチーム"]["draws"], "runs_for": all_teams_data["マイチーム"]["runs_for"],
        "runs_against": all_teams_data["マイチーム"]["runs_against"], "game_log": game_log, "all_teams_data": all_teams_data
    }
    st.session_state.step = "result"
    st.rerun()

elif st.session_state.step == "result":
    result = st.session_state.season_result
    st.header("シーズン終了！")
    
    st.dataframe(pd.DataFrame(result["game_log"]), hide_index=True, use_container_width=True)
    if st.button("もう1年やる", type="primary"):
        st.session_state.clear()
        st.rerun()
