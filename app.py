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
    "C": "捕手",
    "1B": "一塁手",
    "2B": "二塁手",
    "3B": "三塁手",
    "SS": "遊撃手",
    "LF": "左翼手",
    "CF": "中堅手",
    "RF": "右翼手",
    "DH": "指名打者",
    "P": "投手",
}

RANK_VALUE = {
    "S": 95.0,
    "A": 85.0,
    "B": 75.0,
    "C": 65.0,
    "D": 55.0,
    "E": 45.0,
    "F": 30.0,
    "G": 10.0,
}

RANK_WEIGHT = {
    "S": 1.40,
    "A": 1.25,
    "B": 1.10,
    "C": 0.95,
    "D": 0.80,
    "E": 0.65,
    "F": 0.50,
    "G": 0.35,
}

BASE_PA = {
    "single": 0.155,
    "double": 0.045,
    "triple": 0.004,
    "hr": 0.018,
    "walk": 0.075,
    "so": 0.230,
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
    if pd.isna(text):
        return result
    for part in str(text).split("/"):
        part = part.strip()
        if ":" not in part:
            continue
        pos, value = part.split(":", 1)
        pos = pos.strip().upper()
        try:
            result[pos] = float(value.strip())
        except ValueError:
            pass
    return result

def parse_pitches(text):
    result = {}
    if pd.isna(text):
        return result
    for part in str(text).split("/"):
        part = part.strip()
        if ":" not in part:
            continue
        name, rank = part.split(":", 1)
        name = name.strip()
        rank = rank.strip().upper()
        if rank in RANK_VALUE:
            result[name] = rank
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
        players.append(
            Player(
                name=str(row["選手名"]).strip(),
                team=str(row["チーム"]).strip(),
                contact=clean_number(row["ミート"]),
                power=clean_number(row["パワー"]),
                speed=clean_number(row["走力"]),
                defense=parse_defense(row["守備力"]),
            )
        )
    return players

def load_pitchers(source):
    df = pd.read_excel(source)
    require_columns(df, ["選手名", "チーム", "制球", "スタミナ", "球種ランク"], "投手ファイル")
    players = []
    for _, row in df.iterrows():
        players.append(
            Player(
                name=str(row["選手名"]).strip(),
                team=str(row["チーム"]).strip(),
                control=clean_number(row["制球"]),
                stamina=clean_number(row["スタミナ"]),
                pitches=parse_pitches(row["球種ランク"]),
            )
        )
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
                
    def total_score(p):
        return p.contact + p.power + p.speed

    remaining.sort(key=total_score, reverse=True)
    unassigned_pos = [pos for pos in POSITIONS if pos not in assigned_positions]
    
    for p in list(remaining):
        if not unassigned_pos:
            break
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
    for p in starters:
        roles[p.name] = "先発"
        
    role_slots = ["抑え", "中継ぎエース", "中継ぎエース", "僅差", "僅差", "ビハインド", "ビハインド", "ビハインド", "ビハインド"]
    
    for i, p in enumerate(remaining):
        if i < len(role_slots):
            roles[p.name] = role_slots[i]
        else:
            roles[p.name] = "ビハインド"
            
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
        name: Team(
            name=name,
            fielders=data["fielders"],
            pitchers=data["pitchers"],
        )
        for name, data in teams.items()
    }

def best_lineup_for_team(team, dh=True):
    lineup = assign_initial_positions(team.fielders, dh=dh)
    lineup = decide_batting_order(lineup)
    if len(lineup) > 9:
        lineup = lineup[:9]
    return lineup

def best_pitching_staff(team):
    roles = decide_pitcher_roles(team.pitchers)
    starters = [p for p in team.pitchers if roles.get(p.name) == "先発"]
    closer_list = [p for p in team.pitchers if roles.get(p.name) == "抑え"]
    closer = closer_list[0] if closer_list else None
    bullpen = [p for p in team.pitchers if roles.get(p.name) not in ("先発", "抑え")]
    
    bullpen_roles = {id(p): roles.get(p.name) for p in bullpen}
    
    return {
        "starters": starters,
        "bullpen": bullpen,
        "closer": closer,
        "bullpen_roles": bullpen_roles,
    }

def build_opponent_team(team, dh):
    lineup = best_lineup_for_team(team, dh=dh)
    staff = best_pitching_staff(team)
    return {"team": team, "lineup": lineup, "staff": staff}

# ============================================================
# 全試合スケジュールの生成
# ============================================================
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

# ============================================================
# 成績初期化
# ============================================================
def reset_stats(players):
    for p in players:
        p.batting = BatterStats()
        p.pitching = PitcherStats()
        p.fielding = FielderStats()

# ============================================================
# 能力値 → 確率
# ============================================================
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def choose_pitch(pitcher):
    if not pitcher.pitches:
        return None
    names = list(pitcher.pitches.keys())
    weights = [RANK_WEIGHT.get(pitcher.pitches[n], 0.8) for n in names]
    return random.choices(names, weights=weights, k=1)[0]

def pitch_quality(pitcher, pitch_name):
    if pitch_name is None:
        return 55.0
    rank = pitcher.pitches.get(pitch_name, "C")
    return RANK_VALUE.get(rank, 55.0)

def fatigue_factor(pitcher, game_outs):
    innings = game_outs / 3.0
    if innings <= 4:
        return 1.0
    excess = innings - 4
    penalty = excess * max(0.0, (80.0 - pitcher.stamina)) * 0.0015
    return clamp(1.0 - penalty, 0.82, 1.0)

def at_bat_probabilities(batter, pitcher, game_outs):
    pitch_name = choose_pitch(pitcher)
    quality = pitch_quality(pitcher, pitch_name)
    fatigue = fatigue_factor(pitcher, game_outs)

    contact_diff = batter.contact - quality
    power_diff = batter.power - quality
    control_diff = pitcher.control - 50.0

    contact_penalty = 0.0
    if batter.contact < 60.0:
        effective_contact = max(40.0, batter.contact)
        diff = 60.0 - effective_contact
        contact_penalty = (diff * 0.5) + ((diff ** 2) * 0.02)

    power_penalty = 0.0
    if batter.power < 60.0:
        effective_power = max(40.0, batter.power)
        diff = 60.0 - effective_power
        power_penalty = (diff * 0.5) + ((diff ** 2) * 0.02)

    power_bonus = 0.0
    if batter.power > 60.0:
        diff = batter.power - 60.0
        power_bonus = (diff ** 2) * 0.000075

    # 【追加】ミート・パワーが60〜79の層へのHR確率アップ補正
    if 60.0 <= batter.power <= 79.0:
        power_bonus += (batter.power - 60.0) * 0.0006
    if 60.0 <= batter.contact <= 79.0:
        power_bonus += (batter.contact - 60.0) * 0.0003

    pitch_variety = len(pitcher.pitches)
    variety_debuff = max(0, pitch_variety - 2) * 0.0015

    single = BASE_PA["single"] + contact_diff * 0.0008 - (contact_penalty * 0.0010) - variety_debuff
    double = BASE_PA["double"] + contact_diff * 0.00015 + power_diff * 0.00025 - ((contact_penalty + power_penalty) * 0.0002) - (variety_debuff * 0.5)
    triple = BASE_PA["triple"] + batter.speed * 0.000015
    hr = BASE_PA["hr"] + power_diff * 0.0004 - (power_penalty * 0.0012) + power_bonus - (variety_debuff * 0.5)
    walk = BASE_PA["walk"] - control_diff * 0.0012
    so = BASE_PA["so"] - contact_diff * 0.0008 + (contact_penalty * 0.0015) + (power_penalty * 0.0008) + variety_debuff

    quality_delta = quality - 60.0
    single -= quality_delta * 0.00045
    double -= quality_delta * 0.00025
    hr -= quality_delta * 0.00030
    
    # 【変更】奪三振における球種ランク（球質）の影響力を強くする (0.0015 -> 0.0028)
    so += quality_delta * 0.0028

    if fatigue < 1.0:
        single += (1.0 - fatigue) * 0.03
        hr += (1.0 - fatigue) * 0.015
        walk += (1.0 - fatigue) * 0.02
        so -= (1.0 - fatigue) * 0.03

    single = clamp(single, 0.01, 0.30)
    double = clamp(double, 0.002, 0.12)
    triple = clamp(triple, 0.001, 0.03)
    hr = clamp(hr, 0.001, 0.12)
    walk = clamp(walk, 0.015, 0.15)
    so = clamp(so, 0.05, 0.45)

    used = single + double + triple + hr + walk + so
    out = max(0.02, 1.0 - used)
    total = single + double + triple + hr + walk + so + out

    probs = [
        ("single", single / total),
        ("double", double / total),
        ("triple", triple / total),
        ("hr", hr / total),
        ("walk", walk / total),
        ("so", so / total),
        ("out", out / total),
    ]
    return probs, pitch_name

def choose_result(probs):
    r = random.random()
    cumulative = 0.0
    for result, prob in probs:
        cumulative += prob
        if r <= cumulative:
            return result
    return "out"

# ============================================================
# 守備・UZR
# ============================================================
def choose_batted_ball_position(defense):
    positions = ["1B", "2B", "3B", "SS", "LF", "CF", "RF"]
    weights = [1.0, 1.1, 1.0, 1.2, 0.9, 1.0, 0.9]
    pos = random.choices(positions, weights=weights, k=1)[0]
    defender = defense.get(pos)
    return pos, defender

def resolve_outcome(result, defense):
    pos, defender = choose_batted_ball_position(defense)
    if defender is None:
        return "field_out", pos, None

    ability = defender.defense_at(pos)
    base_error_prob = 0.0028
    ability_factor = clamp((70.0 - ability) / 70.0, -0.35, 0.90)
    error_prob = base_error_prob * (1.0 + ability_factor)
    error_prob = clamp(error_prob, 0.0009, 0.0050)

    if random.random() >= error_prob:
        defender.fielding.PO += 1
        defender.fielding.UZR += (ability - 50.0) / 1200.0
        return "field_out", pos, defender

    defender.fielding.E += 1
    defender.fielding.UZR -= 0.5 + max(0.0, (50.0 - ability) / 100.0)
    return "error", pos, defender

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
            run_prob = 0.55 + bases[1].speed / 300.0
            if random.random() < clamp(run_prob, 0.55, 0.90):
                runs += 1
                scoring.append(bases[1])
            else:
                new_bases[2] = bases[1]
        if bases[0] is not None:
            run_prob = 0.30 + bases[0].speed / 250.0
            if random.random() < clamp(run_prob, 0.30, 0.82):
                runs += 1
                scoring.append(bases[0])
            else:
                new_bases[2] = bases[0]
        new_bases[1] = batter
        return new_bases, runs, scoring

    if bases[2] is not None:
        runs += 1
        scoring.append(bases[2])
    if bases[1] is not None:
        run_prob = 0.45 + bases[1].speed / 250.0
        if random.random() < clamp(run_prob, 0.45, 0.90):
            runs += 1
            scoring.append(bases[1])
        else:
            new_bases[2] = bases[1]
    if bases[0] is not None:
        new_bases[1] = bases[0]
    new_bases[0] = batter
    return new_bases, runs, scoring

def advance_on_walk(bases, batter):
    new_bases = list(bases)
    runs = 0
    scoring = []
    if bases[0] is not None and bases[1] is not None and bases[2] is not None:
        runs = 1
        scoring.append(bases[2])
    if bases[0] is not None and bases[1] is not None:
        new_bases[2] = bases[1]
    if bases[0] is not None:
        new_bases[1] = bases[0]
    new_bases[0] = batter
    return new_bases, runs, scoring

# ============================================================
# 試合用投手交代 (球数スタミナ制)
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

    def choose_starter(self, game_number):
        if not self.starters:
            return None
        self.current = self.starters[game_number % len(self.starters)]
        self.current.game_pitches = 0 
        self.current_start_outs = 0
        self.appearance_start_outs[id(self.current)] = self.current.pitching.outs
        self.current.pitching.G += 1
        self.current.pitching.GS += 1
        self.game_pitchers.append(self.current)
        return self.current

    def _available_bullpen(self):
        return [p for p in self.bullpen if p not in self.used_bullpen]

    def should_replace(self, score_diff, inning, outs):
        p = self.current
        if p is None:
            return False

        p_id = id(p)
        runs = self.pitcher_runs[p_id]
        current_outs = self.current_start_outs
        pitches = getattr(p, 'game_pitches', 0)
        
        if p_id not in self.max_pitches:
            self.max_pitches[p_id] = p.stamina * random.uniform(1.1, 1.5)
        max_limit = self.max_pitches[p_id]
        
        is_stamina_empty = pitches >= max_limit
        
        if p in self.starters:
            role = "先発"
        elif p is self.closer:
            role = "抑え"
        else:
            role = self.bullpen_roles.get(p_id, "僅差")

        if runs >= 7:
            return True

        if role == "ビハインド" and is_stamina_empty:
            if current_outs % 3 != 0:
                is_stamina_empty = False 

        if runs >= 5 and current_outs >= 15: 
            return True
        if runs >= 3 and current_outs >= 18: 
            return True
        if runs >= 2 and current_outs >= 21: 
            return True

        if is_stamina_empty:
            return True

        if p not in self.starters and role != "ビハインド":
            max_outs = 6 if (role == "中継ぎエース" and inning <= 7) else 3
            if current_outs >= max_outs:
                return True
                
        return False

    def _select_bullpen(self, inning, score_diff):
        available = self._available_bullpen()
        if not available:
            return None
            
        available.sort(key=lambda x: x.pitching.G)

        if inning >= 9 and score_diff > 0 and self.closer is not None and self.closer not in self.used_bullpen:
            return self.closer
            
        if score_diff <= -2:
            preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "ビハインド"]
            if preferred: return preferred[0]
            preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "僅差"]
            if preferred: return preferred[0]
            preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "中継ぎエース"]
            if preferred: return preferred[0]

        if score_diff > 0:
            preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "中継ぎエース"]
            if preferred: return preferred[0]
            preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "僅差"]
            if preferred: return preferred[0]
            
        preferred = [p for p in available if self.bullpen_roles.get(id(p)) == "僅差"]
        if preferred: return preferred[0]
        
        return available[0]

    def replace(self, inning, score_diff):
        old = self.current
        if old is None: return None
        new = None
        if old in self.starters:
            new = self._select_bullpen(inning, score_diff)
        elif old in self.bullpen:
            new = self._select_bullpen(inning, score_diff)
        elif old is self.closer:
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

        new.game_pitches = 0 
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
# 1試合
# ============================================================
def attempt_steal(bases, offense_lineup, defense, game_state=None):
    catcher = defense.get("C")
    if catcher is None: return bases
    candidates = []
    if bases[0] is not None and bases[1] is None:
        candidates.append((0, 1, 0.10, 0.34))
    if bases[1] is not None and bases[2] is None:
        candidates.append((1, 2, 0.045, 0.22))
    if not candidates: return bases

    from_base, to_base, base_attempt, speed_factor = candidates[0]
    runner = bases[from_base]
    attempt_prob = base_attempt + runner.speed / 500.0
    attempt_prob = clamp(attempt_prob, 0.03, 0.34 if from_base == 0 else 0.18)

    if random.random() >= attempt_prob:
        return bases

    catcher_def = catcher.defense_at("C")
    success_prob = (0.10 + (runner.speed - 30.0) * 0.007 - (catcher_def - 30.0) * 0.004)
    success_prob = clamp(success_prob, 0.03, 0.88)

    if random.random() < success_prob:
        bases[from_base] = None
        bases[to_base] = runner
        runner.batting.SB += 1
    else:
        bases[from_base] = None
        runner.batting.CS += 1
        if game_state is not None:
            game_state["outs"] += 1
    return bases

def simulate_half_inning(offense_lineup, batting_index, pitcher, defense, league, home_team=False, inning=1, top_bottom="表", game_state=None):
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

        if result in ("so", "walk"):
            pa_pitches = random.randint(4, 8)
        else:
            pa_pitches = random.randint(1, 6)
        pitcher.game_pitches = getattr(pitcher, 'game_pitches', 0) + pa_pitches

        if result in ("single", "double", "triple", "hr"):
            batter.batting.AB += 1
            batter.batting.H += 1
            if result == "hr":
                runners_on = sum(1 for runner in bases if runner is not None)
                run_type_char = {0: "①", 1: "②", 2: "③", 3: "④"}[runners_on]
                batter.batting.HR += 1
                hr_log.append(f"{inning}回{top_bottom} {batter.name} {batter.batting.HR}号{run_type_char}")
                batter.batting.TB += 4
                pitcher.pitching.HR += 1
            elif result == "single":
                batter.batting.TB += 1
            elif result == "double":
                batter.batting.double += 1
                batter.batting.TB += 2
            elif result == "triple":
                batter.batting.triple += 1
                batter.batting.TB += 3
            
            pitcher.pitching.H += 1

            old_bases = list(bases)
            bases, scored, scoring = advance_on_hit(old_bases, batter, result)
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
        else:
            outcome, pos, defender = resolve_outcome(result, defense)
            if outcome == "field_out":
                outs += 1
                pitcher.pitching.outs += 1
                if defender is not None: defender.fielding.A += 1
                
                is_sf = False
                if outs <= 2 and bases[2] is not None:
                    runner = bases[2]
                    if pos in ["LF", "CF", "RF"]:
                        arm = defender.defense_at(pos) if defender else 30.0
                        sf_prob = 0.50 + (runner.speed - arm) * 0.005
                        sf_prob = clamp(sf_prob, 0.10, 0.95)
                        if random.random() < sf_prob:
                            runs += 1
                            batter.batting.RBI += 1
                            runner.batting.R += 1
                            batter.batting.SF += 1
                            bases[2] = None
                            is_sf = True
                    elif pos in ["1B", "2B", "3B", "SS"]:
                        base_prob = 0.45 if pos in ["2B", "SS"] else 0.25
                        run_prob = base_prob + (runner.speed - 40.0) * 0.004
                        run_prob = clamp(run_prob, 0.05, 0.85)
                        if random.random() < run_prob:
                            runs += 1
                            batter.batting.RBI += 1
                            runner.batting.R += 1
                            bases[2] = None
                
                if not is_sf:
                    batter.batting.AB += 1

                if outs <= 2 and bases[2] is None and bases[1] is not None:
                    runner2 = bases[1]
                    adv_prob = 0.0
                    if pos == "RF":
                        adv_prob = 0.55 + runner2.speed * 0.004
                    elif pos == "CF":
                        adv_prob = 0.25 + runner2.speed * 0.003
                    elif pos == "LF":
                        adv_prob = 0.05
                    elif pos in ["1B", "2B"]:
                        adv_prob = 0.50 + runner2.speed * 0.004
                    elif pos in ["3B", "SS"]:
                        adv_prob = 0.10 + runner2.speed * 0.002
                    if random.random() < clamp(adv_prob, 0.05, 0.90):
                        bases[2] = runner2
                        bases[1] = None

                if outs <= 2 and bases[1] is None and bases[0] is not None:
                    runner1 = bases[0]
                    adv_prob = 0.0
                    if pos in ["1B", "2B", "3B", "SS"]:
                        adv_prob = 0.15 + runner1.speed * 0.002
                    if random.random() < clamp(adv_prob, 0.01, 0.40):
                        bases[1] = runner1
                        bases[0] = None
            else:
                batter.batting.AB += 1
                if defender is not None: pass
                if bases[0] is None:
                    bases[0] = batter
                elif bases[1] is None:
                    bases[1] = bases[0]
                    bases[0] = batter
                elif bases[2] is None:
                    bases[2] = bases[1]
                    bases[1] = bases[0]
                    bases[0] = batter
                else:
                    runs += 1
                    batter.batting.RBI += 1
                    bases[2].batting.R += 1
                    bases[2] = bases[1]
                    bases[1] = bases[0]
                    bases[0] = batter

    return runs, hr_log

def simulate_game(my_lineup, my_staff, op_lineup, op_staff, league, my_game_number, op_game_number):
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
        if league == "セ・リーグ" and op_pitcher:
            if len(offense_op) == 8: offense_op.append((op_pitcher, "P"))

        if my_pitcher:
            r_op, hrs_op = simulate_half_inning(
                [p for p, _ in offense_op], op_batting_index, my_pitcher, defense_my, league, inning=inning, top_bottom="表"
            )
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
        elif op_score == my_score:
            lead_state = 0

        if inning >= 9 and my_score > op_score:
            my_linescore.append("X")
            break

        # 裏
        if op_pitching.should_replace(op_score - my_score, inning, op_pitcher.pitching.outs if op_pitcher else 0):
            op_pitcher = op_pitching.replace(inning, op_score - my_score)

        defense_op = {pos: player for player, pos in op_lineup if pos != "DH"}
        offense_my = list(my_lineup)
        if league == "セ・リーグ" and my_pitcher:
            if len(offense_my) == 8: offense_my.append((my_pitcher, "P"))

        if op_pitcher:
            r_my, hrs_my = simulate_half_inning(
                [p for p, _ in offense_my], my_batting_index, op_pitcher, defense_op, league, inning=inning, top_bottom="裏"
            )
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
        elif my_score == op_score:
            lead_state = 0

        if inning >= 9 and my_score != op_score:
            break

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
                    if candidates:
                        win_p = random.choice(candidates)
        return win_p

    save_pitcher = None
    if my_score > op_score:
        winning_pitcher = resolve_win(my_pitching, my_por)
        losing_pitcher = op_por

        if winning_pitcher is not None:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in my_pitching.game_holds:
                my_pitching.game_holds.remove(winning_pitcher)

        if losing_pitcher is not None:
            losing_pitcher.pitching.L += 1

        if my_pitcher and my_pitcher is my_pitching.closer and my_pitching.save_eligible and my_pitcher is not winning_pitcher:
            my_pitcher.pitching.SV += 1
            save_pitcher = my_pitcher

        return my_score, op_score, {"result": "W", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

    elif my_score < op_score:
        winning_pitcher = resolve_win(op_pitching, op_por)
        losing_pitcher = my_por

        if winning_pitcher is not None:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in op_pitching.game_holds:
                op_pitching.game_holds.remove(winning_pitcher)

        if losing_pitcher is not None:
            losing_pitcher.pitching.L += 1

        if op_pitcher and op_pitcher is op_pitching.closer and op_pitching.save_eligible and op_pitcher is not winning_pitcher:
            op_pitcher.pitching.SV += 1
            save_pitcher = op_pitcher

        return my_score, op_score, {"result": "L", "winning_pitcher": winning_pitcher, "losing_pitcher": losing_pitcher, "save_pitcher": save_pitcher, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

    else:
        return my_score, op_score, {"result": "D", "winning_pitcher": None, "losing_pitcher": None, "save_pitcher": None, "my_linescore": my_linescore, "op_linescore": op_linescore, "hrs": hr_events}

# ============================================================
# テストシミュレーター用関数 (実戦他球団対決・1シーズン換算)
# ============================================================
def render_test_simulator(fielders_base, pitchers_base):
    st.header("🧪 実戦シミュレーター（他球団対戦・1シーズン換算）")
    st.write("対象となる全選手が「マイチーム」に所属し、NPB各球団（コンピュータの主力チーム）と実戦形式で対戦します。")
    st.write("設定した打席数・投球回に達するまで試合を行い、**「1シーズン分（500打席 / 143投球回）に換算したらどうなるか」**を算出します。")
    
    all_teams = sorted(list(set([p.team for p in fielders_base])))
    exclude_teams = st.multiselect("除外するチーム（所属選手をテスト対象外とし、対戦相手からも除外）", options=all_teams, default=[])
    
    col1, col2 = st.columns(2)
    with col1:
        target_pa = st.number_input("シミュレーション打席数（多めに回すほど安定します）", min_value=100, max_value=5000, value=1500)
    with col2:
        target_ip = st.number_input("シミュレーション投球回（多めに回すほど安定します）", min_value=30, max_value=1000, value=300)
        
    if st.button("シミュレーションを実行", type="primary"):
        test_fielders = [copy.deepcopy(p) for p in fielders_base if p.team not in exclude_teams]
        test_pitchers = [copy.deepcopy(p) for p in pitchers_base if p.team not in exclude_teams]
        
        # 相手コンピュータ球団の構築
        comp_fielders = copy.deepcopy(fielders_base)
        comp_pitchers = copy.deepcopy(pitchers_base)
        for p in comp_fielders + comp_pitchers:
            if p.team == "ソフトバンク":
                p.contact = max(1.0, p.contact - 8.0)
                p.power = max(1.0, p.power - 8.0)
                p.speed = max(1.0, p.speed - 5.0)
                p.control = max(1.0, p.control - 8.0)
                p.stamina = max(1.0, p.stamina - 8.0)
            elif p.team == "阪神":
                p.contact = max(1.0, p.contact - 4.0)
                p.power = max(1.0, p.power - 4.0)
                p.speed = max(1.0, p.speed - 2.0)
                p.control = max(1.0, p.control - 4.0)
                p.stamina = max(1.0, p.stamina - 4.0)
                
        opp_teams = build_teams(comp_fielders, comp_pitchers)
        available_opp_names = [t for t in opp_teams.keys() if t not in exclude_teams]
        
        if not test_fielders or not test_pitchers or not available_opp_names:
            st.error("選手または対戦球団が不足しています。")
            return
            
        reset_stats(test_fielders + test_pitchers)
        target_outs = target_ip * 3
        
        completed_fielders = set()
        completed_pitchers = set()
        
        f_pool = list(test_fielders)
        p_pool = list(test_pitchers)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        total_targets = len(test_fielders) + len(test_pitchers)
        
        # フラットな基準守備陣
        dummy_def = Player(name="Dummy", team="Dummy")
        dummy_def.defense = {pos: 50.0 for pos in POSITIONS}
        def_dict = {pos: dummy_def for pos in POSITIONS}
        
        b_idx = 0
        p_idx = 0
        
        # 全員が目標に達するまで対戦を回す
        while len(completed_fielders) < len(test_fielders) or len(completed_pitchers) < len(test_pitchers):
            opp_name = random.choice(available_opp_names)
            opp_team = opp_teams[opp_name]
            opp_obj = build_opponent_team(opp_team, dh=True)
            opp_staff = opp_obj["staff"]
            opp_pitcher = random.choice(opp_staff["starters"] + opp_staff["bullpen"])
            opp_def = {pos: p for p, pos in opp_obj["lineup"] if pos != "DH"}
            
            # --- マイチームの攻撃（1イニング） ---
            if len(completed_fielders) < len(test_fielders):
                inning_outs = 0
                bases = [None, None, None]
                while inning_outs < 3:
                    batter = f_pool[b_idx % len(f_pool)]
                    b_idx += 1
                    
                    rec_b = (batter.name not in completed_fielders)
                    if rec_b: batter.batting.PA += 1
                    
                    probs, _ = at_bat_probabilities(batter, opp_pitcher, 0)
                    result = choose_result(probs)
                    
                    if result in ("single", "double", "triple", "hr"):
                        if rec_b:
                            batter.batting.AB += 1
                            batter.batting.H += 1
                            if result == "single": batter.batting.TB += 1
                            elif result == "double": batter.batting.double += 1; batter.batting.TB += 2
                            elif result == "triple": batter.batting.triple += 1; batter.batting.TB += 3
                            elif result == "hr": batter.batting.HR += 1; batter.batting.TB += 4
                        old_bases = list(bases)
                        bases, scored, _ = advance_on_hit(old_bases, batter, result)
                        if rec_b and scored > 0: batter.batting.RBI += scored
                    elif result == "walk":
                        if rec_b: batter.batting.BB += 1
                        bases, scored, _ = advance_on_walk(bases, batter)
                        if rec_b and scored > 0: batter.batting.RBI += scored
                    elif result == "so":
                        if rec_b: batter.batting.AB += 1; batter.batting.SO += 1
                        inning_outs += 1
                    else:
                        outcome, pos, defender = resolve_outcome(result, opp_def)
                        if outcome == "field_out":
                            inning_outs += 1
                            is_sf = False
                            if inning_outs <= 2 and bases[2] is not None:
                                runner = bases[2]
                                if pos in ["LF", "CF", "RF"]:
                                    sf_prob = 0.50 + (runner.speed - 50.0) * 0.005
                                    if random.random() < clamp(sf_prob, 0.10, 0.95):
                                        if rec_b: batter.batting.RBI += 1; batter.batting.SF += 1
                                        bases[2] = None
                                        is_sf = True
                                elif pos in ["1B", "2B", "3B", "SS"]:
                                    run_prob = 0.35 + (runner.speed - 40.0) * 0.004
                                    if random.random() < clamp(run_prob, 0.05, 0.85):
                                        if rec_b: batter.batting.RBI += 1
                                        bases[2] = None
                            if not is_sf and rec_b: batter.batting.AB += 1
                        else:
                            if rec_b: batter.batting.AB += 1
                            if bases[0] is None: bases[0] = batter
                            elif bases[1] is None: bases[1] = bases[0]; bases[0] = batter
                            elif bases[2] is None: bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = batter
                            else:
                                if rec_b: batter.batting.RBI += 1
                                bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = batter

                    if rec_b and batter.batting.PA >= target_pa:
                        completed_fielders.add(batter.name)
                        f_pool = [p for p in test_fielders if p.name not in completed_fielders]
                        if not f_pool: break

            # --- マイチームの守備（1イニング） ---
            if len(completed_pitchers) < len(test_pitchers):
                pitcher = p_pool[p_idx % len(p_pool)]
                p_idx += 1
                rec_p = (pitcher.name not in completed_pitchers)
                
                opp_lineup = [p for p, _ in opp_obj["lineup"]]
                inning_outs = 0
                bases = [None, None, None]
                game_outs = 0
                
                while inning_outs < 3:
                    opp_batter = random.choice(opp_lineup)
                    if rec_p: pitcher.pitching.BF += 1
                    
                    probs, _ = at_bat_probabilities(opp_batter, pitcher, game_outs)
                    result = choose_result(probs)
                    
                    if result in ("single", "double", "triple", "hr"):
                        if rec_p:
                            pitcher.pitching.H += 1
                            if result == "hr": pitcher.pitching.HR += 1
                        old_bases = list(bases)
                        bases, scored, _ = advance_on_hit(old_bases, opp_batter, result)
                        if rec_p:
                            pitcher.pitching.R += scored
                            pitcher.pitching.ER += scored
                    elif result == "walk":
                        if rec_p: pitcher.pitching.BB += 1
                        bases, scored, _ = advance_on_walk(bases, opp_batter)
                        if rec_p:
                            pitcher.pitching.R += scored
                            pitcher.pitching.ER += scored
                    elif result == "so":
                        if rec_p: pitcher.pitching.SO += 1
                        inning_outs += 1
                        game_outs += 1
                        if rec_p:
                            pitcher.pitching.outs += 1
                            if pitcher.pitching.outs >= target_outs:
                                completed_pitchers.add(pitcher.name)
                                p_pool = [p for p in test_pitchers if p.name not in completed_pitchers]
                                if not p_pool: break
                    else:
                        outcome, pos, defender = resolve_outcome(result, def_dict)
                        if outcome == "field_out":
                            inning_outs += 1
                            game_outs += 1
                            if rec_p:
                                pitcher.pitching.outs += 1
                                if pitcher.pitching.outs >= target_outs:
                                    completed_pitchers.add(pitcher.name)
                                    p_pool = [p for p in test_pitchers if p.name not in completed_pitchers]
                                    if not p_pool: break
                            if inning_outs <= 2 and bases[2] is not None:
                                sf_prob = 0.50 + (bases[2].speed - 50.0) * 0.005
                                if random.random() < clamp(sf_prob, 0.10, 0.95):
                                    if rec_p:
                                        pitcher.pitching.R += 1
                                        pitcher.pitching.ER += 1
                                    bases[2] = None
                        else:
                            if bases[0] is None: bases[0] = opp_batter
                            elif bases[1] is None: bases[1] = bases[0]; bases[0] = opp_batter
                            elif bases[2] is None: bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = opp_batter
                            else:
                                if rec_p:
                                    pitcher.pitching.R += 1
                                    pitcher.pitching.ER += 1
                                bases[2] = bases[1]; bases[1] = bases[0]; bases[0] = opp_batter

            done_count = len(completed_fielders) + len(completed_pitchers)
            if done_count % 5 == 0 or done_count == total_targets:
                progress_bar.progress(done_count / total_targets)
                status_text.write(f"実戦対戦中... 打席完了: {len(completed_fielders)}/{len(test_fielders)}人 | 投球完了: {len(completed_pitchers)}/{len(test_pitchers)}人")

        status_text.success("シミュレーション完了！1シーズン相当に換算したデータを算出しました。")
        
        # --- 1シーズン（500打席換算）の打撃成績 ---
        bat_rows = []
        for p in test_fielders:
            b = p.batting
            scale = 500.0 / b.PA if b.PA > 0 else 1.0
            avg = b.H / b.AB if b.AB > 0 else 0
            obp = (b.H + b.BB) / (b.AB + b.BB + b.SF) if (b.AB + b.BB + b.SF) > 0 else 0
            slg = b.TB / b.AB if b.AB > 0 else 0
            ops = obp + slg
            
            bat_rows.append({
                "球団": p.team,
                "選手名": p.name,
                "打率": f"{avg:.3f}".replace("0.", "."),
                "本塁打(500打席換算)": round(b.HR * scale, 1),
                "打点(500打席換算)": round(b.RBI * scale, 1),
                "安打(500打席換算)": round(b.H * scale, 1),
                "二塁打": round(b.double * scale, 1),
                "三塁打": round(b.triple * scale, 1),
                "四球": round(b.BB * scale, 1),
                "三振": round(b.SO * scale, 1),
                "OPS": f"{ops:.3f}".replace("0.", "."),
                "実打席数": b.PA
            })
            
        # --- 1シーズン（143投球回換算）の投球成績 ---
        pit_rows = []
        for p in test_pitchers:
            pt = p.pitching
            ip = pt.outs / 3.0
            scale = 143.0 / ip if ip > 0 else 1.0
            era = pt.ER * 27 / pt.outs if pt.outs > 0 else 0
            whip = (pt.H + pt.BB) / ip if ip > 0 else 0
            k9 = pt.SO * 27 / pt.outs if pt.outs > 0 else 0
            
            pit_rows.append({
                "球団": p.team,
                "選手名": p.name,
                "防御率": f"{era:.2f}",
                "WHIP": f"{whip:.2f}",
                "奪三振率": f"{k9:.2f}",
                "奪三振(143回換算)": round(pt.SO * scale, 1),
                "被安打(143回換算)": round(pt.H * scale, 1),
                "被本塁打(143回換算)": round(pt.HR * scale, 1),
                "与四球(143回換算)": round(pt.BB * scale, 1),
                "自責点(143回換算)": round(pt.ER * scale, 1),
                "実投球回": round(ip, 1)
            })
            
        st.subheader("📊 1シーズン相当（500打席換算）の平均打撃成績")
        st.dataframe(pd.DataFrame(bat_rows).sort_values("本塁打(500打席換算)", ascending=False), hide_index=True, use_container_width=True)
        
        st.subheader("📊 1シーズン相当（143投球回換算）の平均投球成績")
        st.dataframe(pd.DataFrame(pit_rows).sort_values("防御率", ascending=True), hide_index=True, use_container_width=True)


# ============================================================
# ドラフト画面
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
        if candidate.defense:
            main_pos_str = "・".join([POSITION_JP.get(pos, pos) for pos in candidate.defense.keys()])
        else:
            main_pos_str = "不明"
    else:
        main_pos_str = "投手"
    
    card_html = f'<div class="card">'
    card_html += f'<div class="p-tag">{main_pos_str}</div>'
    card_html += f'<div class="p-name">{candidate.name}</div>'
    card_html += f'<div class="p-meta">{candidate.team} 所属</div>'
    
    card_html += '<div class="stats-box">'
    if kind == "野手":
        max_def = max(candidate.defense.values()) if candidate.defense else 0
        stats = [("ミート", candidate.contact), ("パワー", candidate.power), ("走力", candidate.speed), ("守備力", max_def)]
    else:
        stats = [("制球", candidate.control), ("スタミナ", candidate.stamina)]
        
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
        for p_name, rank in candidate.pitches.items():
            card_html += f'<span class="pos-badge">{p_name} {rank}</span>'
        card_html += '</div>'
        
    card_html += '</div>'
    st.markdown(card_html, unsafe_allow_html=True)

    st.markdown("""
    <style>
    div[data-testid="column"]:nth-of-type(1) div.stButton > button {
        background-color: #c62828 !important; color: white !important; height: 75px; font-size: 22px; font-weight: bold; border: none; border-radius: 8px; box-shadow: 0 4px 0 #8e0000; transition: 0.1s;
    }
    div[data-testid="column"]:nth-of-type(1) div.stButton > button:active { box-shadow: 0 0 0 #8e0000; transform: translateY(4px); }
    
    div[data-testid="column"]:nth-of-type(2) div.stButton > button {
        background-color: #2e7d32 !important; color: white !important; height: 75px; font-size: 22px; font-weight: bold; border: none; border-radius: 8px; box-shadow: 0 4px 0 #005005; transition: 0.1s;
    }
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
            if kind == "野手":
                if p.defense:
                    m_pos = "・".join([POSITION_JP.get(pos, pos) for pos in p.defense.keys()])
                else:
                    m_pos = "不明"
            else:
                m_pos = "投手"
            sel_html += f'<div style="background-color: #f5f5f5; border: 1px solid #ddd; padding: 5px 12px; border-radius: 6px; font-size: 13px;"><b style="color:#555;">{m_pos}</b> {p.name}</div>'
        sel_html += '</div>'
        st.markdown(sel_html, unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size: 13px; color: #888;">まだ0人。ここに獲得した選手が並びます。</div>', unsafe_allow_html=True)

    return False

# ============================================================
# オーダー画面
# ============================================================
def order_page(fielders, league):
    st.header("④ オーダー設定")
    st.info(f"選択リーグ：{league}")

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
        idx = 0
        if default_p and default_p.name in names:
            idx = names.index(default_p.name)
            
        selected_name = st.selectbox(
            f"{POSITION_JP[pos]} ({pos})",
            names,
            index=idx,
            key=f"order_{pos}",
        )
        player = next(p for p in available if p.name == selected_name)
        lineup.append((player, pos))
        used.add(player.name)
        st.caption(f"守備力 {pos}: {player.defense_at(pos):g}")

    remaining = [p for p in fielders if p.name not in used]

    if league == "パ・リーグ":
        st.subheader("DH")
        if not remaining:
            st.error("DH候補がいません。")
            return None
            
        names = [p.name for p in remaining]
        default_p = default_pos_map.get("DH")
        idx = 0
        if default_p and default_p.name in names:
            idx = names.index(default_p.name)
            
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
        if selected_name is None:
            continue
        pair = next(x for x in lineup if x[0].name == selected_name)
        ordered.append(pair)

    bench = remaining[0] if league == "セ・リーグ" and remaining else None
    if bench:
        st.write(f"代打要員：**{bench.name}**")

    if st.button("オーダー決定", type="primary"):
        return {"lineup": ordered, "bench": bench}

    return None

# ============================================================
# 投手起用画面
# ============================================================
def pitching_page(pitchers):
    st.header("⑤ 投手起用設定")
    names = [p.name for p in pitchers]

    if len(names) < 15:
        st.error("投手が15人未満です。先発6人＋中継ぎ8人＋抑え1ড়ান্ত
