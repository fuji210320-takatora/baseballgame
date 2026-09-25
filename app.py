import random
import math
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
    "S": 100.0,
    "A": 85.0,
    "B": 70.0,
    "C": 55.0,
    "D": 40.0,
    "E": 25.0,
}

RANK_WEIGHT = {
    "S": 1.30,
    "A": 1.15,
    "B": 1.00,
    "C": 0.85,
    "D": 0.70,
    "E": 0.55,
}

# 【投高打低調整】基準となる確率
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
# チーム生成
# ============================================================
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

def player_offense_score(p):
    return p.contact * 0.45 + p.power * 0.40 + p.speed * 0.15

def player_pitching_score(p):
    if not p.pitches:
        return 0.0
    pitch_values = [RANK_VALUE.get(rank, 55) for rank in p.pitches.values()]
    avg_pitch = sum(pitch_values) / len(pitch_values)
    variety_bonus = min(len(p.pitches), 6) * 1.5
    return p.control * 0.35 + p.stamina * 0.20 + avg_pitch * 0.45 + variety_bonus

def best_lineup_for_team(team, dh=True):
    remaining = list(team.fielders)
    lineup = []
    for pos in POSITIONS:
        candidates = sorted(
            remaining,
            key=lambda p: (p.defense_at(pos), player_offense_score(p)),
            reverse=True,
        )
        if candidates:
            chosen = candidates[0]
            lineup.append((chosen, pos))
            remaining.remove(chosen)
    if dh and remaining:
        dh_player = max(remaining, key=player_offense_score)
        lineup.append((dh_player, "DH"))

    lineup.sort(key=lambda x: player_offense_score(x[0]), reverse=True)
    if len(lineup) > 9:
        lineup = lineup[:9]
    return lineup

def best_pitching_staff(team):
    pitchers = sorted(team.pitchers, key=player_pitching_score, reverse=True)
    starters = pitchers[:6]
    bullpen = pitchers[6:14]
    closer = pitchers[14] if len(pitchers) > 14 else (pitchers[-1] if pitchers else None)

    bullpen_roles = {}
    for i, p in enumerate(bullpen):
        if i < 2:
            bullpen_roles[id(p)] = "中継ぎエース"
        elif i < 5:
            bullpen_roles[id(p)] = "僅差"
        else:
            bullpen_roles[id(p)] = "ビハインド"

    return {
        "starters": starters,
        "bullpen": bullpen,
        "closer": closer,
        "bullpen_roles": bullpen_roles,
    }

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

    # 【修正】能力値59〜40までのデバフ（緩やかな二次曲線）
    # 40でペナルティを打ち止めにし、係数も下げてマイルドに
    contact_penalty = 0.0
    if batter.contact < 60.0:
        effective_contact = max(40.0, batter.contact)
        diff = 60.0 - effective_contact
        contact_penalty = (diff * 0.8) + ((diff ** 2) * 0.05)

    power_penalty = 0.0
    if batter.power < 60.0:
        effective_power = max(40.0, batter.power)
        diff = 60.0 - effective_power
        power_penalty = (diff * 0.8) + ((diff ** 2) * 0.05)

    # パワー60以上の打者へのアーチストボーナス
    power_bonus = 0.0
    if batter.power > 60.0:
        diff = batter.power - 60.0
        power_bonus = (diff ** 2) * 0.000075

    # ペナルティとボーナスを確率に反映
    single = BASE_PA["single"] + contact_diff * 0.0008 - (contact_penalty * 0.0010)
    double = BASE_PA["double"] + contact_diff * 0.00015 + power_diff * 0.00025 - ((contact_penalty + power_penalty) * 0.0002)
    triple = BASE_PA["triple"] + batter.speed * 0.000015
    hr = BASE_PA["hr"] + power_diff * 0.0004 - (power_penalty * 0.0012) + power_bonus
    walk = BASE_PA["walk"] - control_diff * 0.0012
    so = BASE_PA["so"] - contact_diff * 0.0008 + (contact_penalty * 0.0015) + (power_penalty * 0.0008)

    # 投手の能力（球質）による制圧力
    quality_delta = quality - 55.0
    single -= quality_delta * 0.00045
    double -= quality_delta * 0.00025
    hr -= quality_delta * 0.00030
    so += quality_delta * 0.0015

    if fatigue < 1.0:
        single += (1.0 - fatigue) * 0.03
        hr += (1.0 - fatigue) * 0.015
        walk += (1.0 - fatigue) * 0.02
        so -= (1.0 - fatigue) * 0.03

    # 打撃成績の天井と底
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

    # UZRのスケール適正化
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
            
        # 中継ぎの登板数を均等にするため、試合数が少ない順に並び替え
        available.sort(key=lambda x: x.pitching.G)

        if inning >= 8 and score_diff > 0 and self.closer is not None and self.closer not in self.used_bullpen:
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

        if new not in self.used_bullpen and new in self.bullpen:
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

def simulate_half_inning(offense_lineup, batting_index, pitcher, defense, league, home_team=False, inning=1, game_state=None):
    outs = 0
    bases = [None, None, None]
    runs = 0

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

        # 1打席あたりの球数を加算
        if result in ("so", "walk"):
            pa_pitches = random.randint(4, 8)
        else:
            pa_pitches = random.randint(1, 6)
        pitcher.game_pitches = getattr(pitcher, 'game_pitches', 0) + pa_pitches

        if result in ("single", "double", "triple", "hr"):
            batter.batting.AB += 1
            batter.batting.H += 1
            if result == "single":
                batter.batting.TB += 1
            elif result == "double":
                batter.batting.double += 1
                batter.batting.TB += 2
            elif result == "triple":
                batter.batting.triple += 1
                batter.batting.TB += 3
            elif result == "hr":
                batter.batting.HR += 1
                batter.batting.TB += 4
                pitcher.pitching.HR += 1
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
            batter.batting.AB += 1
            outcome, pos, defender = resolve_outcome(result, defense)
            if outcome == "field_out":
                outs += 1
                pitcher.pitching.outs += 1
                if defender is not None: defender.fielding.A += 1
            else:
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

    return runs, batting_index[0]

def simulate_game(my_lineup, my_staff, op_lineup, op_staff, league, game_number):
    my_pitching = PitchingState(my_staff)
    op_pitching = PitchingState(op_staff)

    my_pitcher = my_pitching.choose_starter(game_number)
    op_pitcher = op_pitching.choose_starter(game_number)

    my_losing_candidate = None
    op_losing_candidate = None
    my_score_diff_prev = 0
    op_score_diff_prev = 0

    if my_pitcher is None or op_pitcher is None:
        return 0, 0, {}

    my_score = 0
    op_score = 0
    my_batting_index = [0]
    op_batting_index = [0]

    for p, _ in my_lineup: p.batting.G += 1
    for p, _ in op_lineup: p.batting.G += 1

    if league == "セ・リーグ":
        my_pitcher.batting.G += 1
        op_pitcher.batting.G += 1

    for inning in range(1, 13):
        my_diff = my_score - op_score
        if my_diff < 0 and my_score_diff_prev >= 0:
            my_losing_candidate = my_pitcher
        elif my_diff >= 0:
            my_losing_candidate = None

        if my_pitching.should_replace(my_diff, inning, my_pitcher.pitching.outs):
            old_pitcher = my_pitcher
            my_pitcher = my_pitching.replace(inning, my_diff)
            if my_diff < 0 and my_losing_candidate is None:
                my_losing_candidate = old_pitcher

        defense_my = {pos: player for player, pos in my_lineup if pos != "DH"}
        offense_op = list(op_lineup)
        if league == "セ・リーグ":
            if len(offense_op) == 8: offense_op.append((op_pitcher, "P"))

        op_runs_before = op_score
        r, _ = simulate_half_inning(
            [p for p, _ in offense_op], op_batting_index, my_pitcher, defense_my, league, inning=inning
        )
        op_score += r
        my_pitching.current_start_outs = (my_pitcher.pitching.outs - my_pitching.appearance_start_outs.get(id(my_pitcher), my_pitcher.pitching.outs))
        my_pitching.pitcher_runs[id(my_pitcher)] += r
        my_pitching.pitcher_earned[id(my_pitcher)] += r
        my_pitcher.pitching.R += r
        my_pitcher.pitching.ER += r
        my_score_diff_prev = my_score - op_score

        op_diff = op_score - my_score
        if op_diff < 0 and op_score_diff_prev >= 0:
            op_losing_candidate = op_pitcher
        elif op_diff >= 0:
            op_losing_candidate = None

        if op_pitching.should_replace(op_diff, inning, op_pitcher.pitching.outs):
            old_pitcher = op_pitcher
            op_pitcher = op_pitching.replace(inning, op_diff)
            if op_diff < 0 and op_losing_candidate is None:
                op_losing_candidate = old_pitcher

        defense_op = {pos: player for player, pos in op_lineup if pos != "DH"}
        offense_my = list(my_lineup)
        if league == "セ・リーグ":
            if len(offense_my) == 8: offense_my.append((my_pitcher, "P"))

        r, _ = simulate_half_inning(
            [p for p, _ in offense_my], my_batting_index, op_pitcher, defense_op, league, inning=inning
        )
        my_score += r
        op_pitching.current_start_outs = (op_pitcher.pitching.outs - op_pitching.appearance_start_outs.get(id(op_pitcher), op_pitcher.pitching.outs))
        op_pitching.pitcher_runs[id(op_pitcher)] += r
        op_pitching.pitcher_earned[id(op_pitcher)] += r
        op_pitcher.pitching.R += r
        op_pitcher.pitching.ER += r
        op_score_diff_prev = op_score - my_score

        if inning >= 9 and my_score != op_score:
            break

    if my_score > op_score:
        starter = my_pitching.starters[game_number % len(my_pitching.starters)] if my_pitching.starters else None
        starter_outs = 0
        if starter is not None:
            starter_outs = starter.pitching.outs - my_pitching.appearance_start_outs.get(id(starter), starter.pitching.outs)

        if starter is not None and starter_outs >= 15:
            winning_pitcher = starter
        else:
            pitcher_outs = []
            for p in my_pitching.game_pitchers:
                outs_p = p.pitching.outs - my_pitching.appearance_start_outs.get(id(p), p.pitching.outs)
                pitcher_outs.append((p, outs_p))
            max_outs = max((outs_p for _, outs_p in pitcher_outs), default=0)
            candidates = [p for p, outs_p in pitcher_outs if outs_p == max_outs]
            winning_pitcher = random.choice(candidates) if candidates else starter

        if winning_pitcher is not None:
            winning_pitcher.pitching.W += 1
            if winning_pitcher in my_pitching.game_holds:
                winning_pitcher.pitching.HLD -= 1
                my_pitching.game_holds.remove(winning_pitcher)
            if winning_pitcher is my_pitching.closer:
                my_pitching.save_eligible = False

        if my_pitcher is my_pitching.closer and my_pitching.save_eligible and my_pitcher is not winning_pitcher:
            my_pitcher.pitching.SV += 1

        return my_score, op_score, {"result": "W", "winning_pitcher": winning_pitcher}
    elif my_score < op_score:
        losing_pitcher = my_losing_candidate or my_pitcher
        if losing_pitcher is not None:
            losing_pitcher.pitching.L += 1
        return my_score, op_score, {"result": "L", "losing_pitcher": losing_pitcher}
    else:
        return my_score, op_score, {"result": "D"}

# ============================================================
# 成績計算
# ============================================================
def batting_avg(p):
    return p.batting.H / p.batting.AB if p.batting.AB else 0.0

def obp(p):
    b = p.batting
    den = b.AB + b.BB + b.SF
    return (b.H + b.BB) / den if den else 0.0

def slg(p):
    return p.batting.TB / p.batting.AB if p.batting.AB else 0.0

def ops(p):
    return obp(p) + slg(p)

def era(p):
    return p.pitching.ER * 27 / p.pitching.outs if p.pitching.outs else 0.0

def innings_str(outs):
    return f"{outs // 3}.{outs % 3}"

def team_runs_for(players):
    return sum(p.batting.R for p in players)

def team_runs_against(pitchers):
    return sum(p.pitching.R for p in pitchers)

def fmt_pct(val):
    s = f"{val:.3f}"
    if s.startswith("0."):
        return s[1:]
    elif s.startswith("-0."):
        return "-" + s[2:]
    return s

def pos_icon(pos):
    mapping = {
        "C": ("捕", "#C68A12", "捕手"),
        "1B": ("一", "#B22222", "一塁手"),
        "2B": ("二", "#008080", "二塁手"),
        "3B": ("三", "#006400", "三塁手"),
        "SS": ("遊", "#7E57C2", "遊撃手"),
        "LF": ("左", "#D81B60", "左翼手"),
        "CF": ("中", "#E65100", "中堅手"),
        "RF": ("右", "#2E8B57", "右翼手"),
        "DH": ("D", "#424242", "指名打者"),
        "P": ("投", "#1E88E5", "投手"),
    }
    return mapping.get(pos, ("?", "#999", "不明"))

# ============================================================
# スケジュール
# ============================================================
def create_schedule(my_league, same_teams, inter_teams):
    schedule = []
    for team in same_teams:
        for _ in range(SCHEDULE_SAME):
            schedule.append({"opponent": team, "type": "league"})
    for team in inter_teams:
        for _ in range(SCHEDULE_INTER):
            schedule.append({"opponent": team, "type": "interleague"})
    random.shuffle(schedule)
    return schedule[:143]

# ============================================================
# 能力値をランクと色に変換する関数
# ============================================================
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

    lineup = []
    used = set()
    st.subheader("守備位置")

    for pos in POSITIONS:
        available = [p for p in fielders if p.name not in used]
        if not available:
            st.error("野手の人数が不足しています。")
            return None
        available = sorted(
            available,
            key=lambda p: (p.defense_at(pos), player_offense_score(p)),
            reverse=True,
        )
        names = [p.name for p in available]
        selected_name = st.selectbox(
            f"{POSITION_JP[pos]} ({pos})",
            names,
            index=0,
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
        dh_name = st.selectbox("DH", [p.name for p in remaining], key="order_DH")
        dh = next(p for p in remaining if p.name == dh_name)
        lineup.append((dh, "DH"))
    else:
        st.info("セ・リーグなので余った野手は代打要員になります。")

    st.subheader("打順")
    lineup_default = sorted(lineup, key=lambda x: player_offense_score(x[0]), reverse=True)
    names = [p.name for p, _ in lineup_default]
    ordered = []

    # セ・リーグ打線のエラー回避用
    for i in range(len(lineup_default)):
        remaining_names = [n for n in names if n not in [p.name for p, _ in ordered]]
        selected_name = st.selectbox(f"{i + 1}番", remaining_names, key=f"batting_order_{i}")
        if selected_name is None:
            continue
        pair = next(x for x in lineup_default if x[0].name == selected_name)
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
        st.error("投手が15人未満です。先発6人＋中継ぎ8人＋抑え1ర్ణ人が必要です。")
        return None

    if "pitcher_roles" not in st.session_state:
        stamina_sorted = sorted(pitchers, key=lambda p: p.stamina, reverse=True)
        roles = {}
        for i, p in enumerate(stamina_sorted):
            if i < 6: roles[p.name] = "先発"
            elif i < 14: roles[p.name] = "僅差"
            else: roles[p.name] = "抑え"
        st.session_state.pitcher_roles = roles

    def update_role(p_name):
        st.session_state.pitcher_roles[p_name] = st.session_state[f"sel_{p_name}"]

    roles_list = list(st.session_state.pitcher_roles.values())
    sp_count = roles_list.count("先発")
    cl_count = roles_list.count("抑え")

    if sp_count != 6:
        st.markdown(f'<div style="background-color: #FBE9E7; padding: 15px; border-radius: 8px; color: #D32F2F; font-weight: bold; margin-bottom: 20px;">先発は6人ちょうどにしてください（いま{sp_count}人）</div>', unsafe_allow_html=True)
    if cl_count != 1:
        st.markdown(f'<div style="background-color: #FBE9E7; padding: 15px; border-radius: 8px; color: #D32F2F; font-weight: bold; margin-bottom: 20px;">抑えは1人ちょうどにしてください（いま{cl_count}人）</div>', unsafe_allow_html=True)

    role_options = ["先発", "中継ぎエース", "僅差", "ビハインド", "抑え"]

    for p in pitchers:
        with st.container():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f'<div style="padding-top: 5px;"><span style="font-size: 18px; font-weight: 900; color: #111;">{p.name}</span><br><span style="font-size: 13px; color: #777;">{p.team}所属・制球 {int(p.control)}・スタミナ {int(p.stamina)}</span></div>', unsafe_allow_html=True)
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

def build_opponent_team(team, dh):
    lineup = best_lineup_for_team(team, dh=dh)
    staff = best_pitching_staff(team)
    return {"team": team, "lineup": lineup, "staff": staff}

# ============================================================
# アプリケーション実行
# ============================================================

st.title("⚾ 野球チームメーカー")

with st.sidebar:
    st.header("選手データ")
    st.write("GitHubリポジトリ内のExcelを自動読み込みします。")
    st.code("野手能力データ_最新.xlsx\n投手能力データ_最新.xlsx")

FIELD_FILE = "野手能力データ_最新.xlsx"
PITCH_FILE = "投手能力データ_最新.xlsx"

try:
    fielders_all = load_fielders(FIELD_FILE)
    pitchers_all = load_pitchers(PITCH_FILE)
except Exception as e:
    st.error(
        "Excel読み込みエラーが発生しました。\n\n"
        f"{e}\n\n"
        "app.pyと同じフォルダに、指定されたExcelファイルがあるか確認してください。"
    )
    st.stop()

st.sidebar.success(f"野手 {len(fielders_all)}人 / 投手 {len(pitchers_all)}人")

# ============================================================
# セッション初期化
# ============================================================
if "step" not in st.session_state:
    st.session_state.step = "start"

st.session_state.teams = build_teams(
    fielders_all,
    pitchers_all,
)

# ============================================================
# 初期画面
# ============================================================
if st.session_state.step == "start":
    st.markdown("""
    <style>
    .title-sub { font-size: 14px; color: #888; text-align: center; letter-spacing: 3px; margin-top: 30px; font-weight: bold;}
    .title-main { font-size: 36px; font-weight: 900; text-align: center; margin-bottom: 20px; color: #111;}
    .title-desc { font-size: 15px; color: #555; text-align: center; margin-bottom: 40px; line-height: 1.6; }
    .rule-box { border-top: 1px solid #ccc; border-bottom: 1px solid #ccc; padding: 25px 0; margin-bottom: 30px; }
    .rule-item { margin-bottom: 18px; font-size: 15px; color: #333; display: flex; align-items: flex-start;}
    .rule-num { font-weight: bold; color: #999; margin-right: 15px; font-size: 16px; width: 15px;}
    .rule-text { flex: 1; }
    .disclaimer { font-size: 12px; color: #666; background-color: #f9f9f9; padding: 15px; border-radius: 5px; border: 1px solid #eee; line-height: 1.6;}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="title-sub">BASEBALL TEAM BUILDER</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-main">野球チームメーカー</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-desc">ランダムに現れる選手を取捨選択して、<br>24人のチームを作れ！</div>', unsafe_allow_html=True)

    st.markdown('<div style="font-size: 13px; font-weight: bold; color: #555; margin-bottom: 10px;">ルール</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="rule-box">
        <div class="rule-item"><span class="rule-num">1</span> <span class="rule-text">架空の選手がポジション関係なく<span style="color:#1565C0; font-weight:bold;">完全ランダム</span>で1人ずつ登場</span></div>
        <div class="rule-item"><span class="rule-num">2</span> <span class="rule-text">できるのは<b>「取る」</b>か<b>「見送る」</b>だけ</span></div>
        <div class="rule-item"><span class="rule-num">3</span> <span class="rule-text">まず<span style="color:#1565C0; font-weight:bold;">野手9人</span>（見送り5回まで）</span></div>
        <div class="rule-item"><span class="rule-num">4</span> <span class="rule-text">つぎに<span style="color:#1565C0; font-weight:bold;">投手15人</span>（先発6人・救援9人をセットで選ぶ）</span></div>
        <div class="rule-item"><span class="rule-num">5</span> <span class="rule-text">役割を決め、打順を組んで<span style="color:#1565C0; font-weight:bold;">143試合</span>を戦う</span></div>
        <div class="rule-item"><span class="rule-num">6</span> <span class="rule-text">シーズン中は選手が急に伸びたり、不調に落ちたりする</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="disclaimer">
    本サイトは日本野球機構（NPB）・各球団・選手本人とは関係のない<b>非公式のファンサイト</b>です。選手名・成績・能力値はすべて本ゲームのための架空のもので、実在の選手とは関係ありません。試合結果・シーズン成績・順位も<b>本ゲームのシミュレーションによる架空のもの</b>です。
    </div>
    <br>
    """, unsafe_allow_html=True)

    if st.button("ゲームを始める", type="primary", use_container_width=True):
        st.session_state.step = "league_setup"
        st.rerun()

# ============================================================
# 状態遷移の制御
# ============================================================
elif st.session_state.step == "league_setup":
    st.header("① NPBリーグ設定")
    st.write("12球団のリーグ所属は固定です。")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("セ・リーグ")
        for team in CENTRAL_TEAMS:
            st.write(f"・{team}")
    with c2:
        st.subheader("パ・リーグ")
        for team in PACIFIC_TEAMS:
            st.write(f"・{team}")

    team_names = sorted(st.session_state.teams.keys())
    missing_teams = [team for team in ALL_NPB_TEAMS if team not in team_names]
    if missing_teams:
        st.error(
            "Excelに以下のチームが見つかりません。チーム名を確認してください。\n\n"
            + "\n".join(f"- {team}" for team in missing_teams)
        )
        st.stop()
    if len(team_names) != 12:
        st.warning(f"Excelから読み込んだ球団数は {len(team_names)} 球団です。12球団以外のチームも含まれている可能性があります。")

    if st.button("リーグ設定を確認してドラフト開始", type="primary"):
        st.session_state.central = CENTRAL_TEAMS.copy()
        st.session_state.pacific = PACIFIC_TEAMS.copy()
        st.session_state.step = "draft_fielders"
        st.rerun()

elif st.session_state.step == "draft_fielders":
    finished = draft_page("野手", fielders_all, 9, skip_limit=5)
    if finished:
        st.session_state.step = "draft_pitchers"
        st.rerun()

elif st.session_state.step == "draft_pitchers":
    finished = draft_page("投手", pitchers_all, 15, skip_limit=5)
    if finished:
        st.session_state.step = "league_select"
        st.rerun()

elif st.session_state.step == "league_select":
    st.header("③ セ・パ選択")
    league = st.radio("あなたのチームはどちらのリーグに所属しますか？", ["セ・リーグ", "パ・リーグ"])
    if league == "セ・リーグ":
        st.info("DHなし。野手8人＋投手9番。余った野手1人は代打要員。")
    else:
        st.info("DHあり。野手9人で打線を組みます。")
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
    league = st.session_state.my_league
    st.write(f"**リーグ：** {league}")

    st.subheader("打順")
    lineup_rows = []
    for i, (p, pos) in enumerate(st.session_state.my_lineup, start=1):
        lineup_rows.append({
            "打順": i,
            "選手": p.name,
            "守備": POSITION_JP.get(pos, pos),
            "ミート": p.contact,
            "パワー": p.power,
            "走力": p.speed,
            "守備力": p.defense_at(pos) if pos != "DH" else 0,
        })
    st.dataframe(pd.DataFrame(lineup_rows), hide_index=True, use_container_width=True)

    st.subheader("投手陣")
    pitching_rows = []
    for i, p in enumerate(st.session_state.my_staff["starters"], start=1):
        pitching_rows.append({
            "役割": f"先発{i}",
            "選手": p.name,
            "制球": p.control,
            "スタミナ": p.stamina,
            "球種": " / ".join(f"{n}:{r}" for n, r in p.pitches.items()),
        })
    for i, p in enumerate(st.session_state.my_staff["bullpen"], start=1):
        pitching_rows.append({
            "役割": st.session_state.my_staff.get("bullpen_roles", {}).get(id(p), "中継ぎ"),
            "選手": p.name,
            "制球": p.control,
            "スタミナ": p.stamina,
            "球種": " / ".join(f"{n}:{r}" for n, r in p.pitches.items()),
        })
    p = st.session_state.my_staff["closer"]
    pitching_rows.append({
        "役割": "抑え",
        "選手": p.name if p else "-",
        "制球": p.control if p else 0,
        "スタミナ": p.stamina if p else 0,
        "球種": " / ".join(f"{n}:{r}" for n, r in p.pitches.items()) if p else "",
    })
    st.dataframe(pd.DataFrame(pitching_rows), hide_index=True, use_container_width=True)

    st.subheader("対戦球団")
    if league == "セ・リーグ":
        same = [x for x in st.session_state.central]
        inter = [x for x in st.session_state.pacific]
    else:
        same = [x for x in st.session_state.pacific]
        inter = [x for x in st.session_state.central]

    same = random.sample(same, min(5, len(same)))
    inter = random.sample(inter, min(6, len(inter)))
    schedule = create_schedule(league, same, inter)
    st.session_state.schedule = schedule

    st.write(f"同リーグ：{len(same)}球団 × {SCHEDULE_SAME}試合")
    st.write(f"交流戦：{len(inter)}球団 × {SCHEDULE_INTER}試合")
    st.write(f"合計：{len(schedule)}試合")

    if st.button("⚾ シーズン開始", type="primary", use_container_width=True):
        st.session_state.step = "season"
        st.rerun()

elif st.session_state.step == "season":
    st.header("⑦ 143試合シミュレーション")
    teams = st.session_state.teams
    league = st.session_state.my_league
    my_lineup = st.session_state.my_lineup
    my_staff = st.session_state.my_staff

    reset_stats(st.session_state.draft_fielders + st.session_state.draft_pitchers)
    schedule = st.session_state.schedule

    wins = 0
    losses = 0
    draws = 0
    runs_for = 0
    runs_against = 0
    game_log = []
    progress = st.progress(0)
    status = st.empty()

    for game_no, item in enumerate(schedule, start=1):
        opponent_name = item["opponent"]
        opponent_team = teams[opponent_name]
        opponent = build_opponent_team(opponent_team, dh=(league == "パ・リーグ"))
        op_lineup = opponent["lineup"]

        score_my, score_op, result = simulate_game(
            my_lineup,
            my_staff,
            op_lineup,
            opponent["staff"],
            league,
            game_no - 1,
        )

        runs_for += score_my
        runs_against += score_op
        if result["result"] == "W": wins += 1
        elif result["result"] == "L": losses += 1
        else: draws += 1

        game_log.append({
            "試合": game_no,
            "対戦相手": opponent_name,
            "区分": "同リーグ" if item["type"] == "league" else "交流戦",
            "得点": score_my,
            "失点": score_op,
            "結果": result["result"],
        })
        progress.progress(game_no / 143)
        status.write(f"{game_no}/143試合 {opponent_name} {score_my}-{score_op}")

    st.session_state.season_result = {
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "runs_for": runs_for,
        "runs_against": runs_against,
        "game_log": game_log,
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

    .help-text { font-size: 11px; color: #777; line-height: 1.6; margin: 20px 10px 40px; }

    .season-end-wrap { text-align: center; margin: 30px 0 10px; color: #666; font-size: 15px; }
    .season-end-box { border: 2px solid #222; border-radius: 8px; padding: 40px 20px; text-align: center; background-color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.03); margin-bottom: 25px; }
    .se-sub { font-size: 13px; color: #555; font-weight: bold; letter-spacing: 3px; margin-bottom: 15px; }
    .se-main { font-size: 38px; font-weight: 900; margin-bottom: 30px; color: #111; }
    .se-stats { display: flex; justify-content: center; align-items: baseline; gap: 15px; flex-wrap: wrap; }
    .se-rank-label { font-size: 15px; color: #666; }
    .se-rank-val { font-size: 32px; font-weight: 900; color: #111; }
    .se-rec { font-size: 15px; color: #555; margin-left: 10px; }
    
    .next-year-wrapper div[data-testid="stButton"] > button {
        background-color: #1a1a1a !important; 
        color: white !important; 
        height: 110px !important; 
        border-radius: 10px !important;
        border: none !important;
        position: relative;
    }
    .next-year-wrapper div[data-testid="stButton"] > button p {
        font-size: 26px !important; 
        font-weight: 900 !important;
        margin-bottom: 25px !important;
    }
    .next-year-wrapper div[data-testid="stButton"] > button::after {
        content: "3人まで入れ替えて、来季を戦います";
        position: absolute;
        bottom: 25px;
        left: 0;
        width: 100%;
        text-align: center;
        font-size: 13px;
        font-weight: bold;
        color: #ccc;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="disclaimer-box">
    名・成績・能力値はすべて架空のもので、実際の試合結果ではありません。
    </div>
    """, unsafe_allow_html=True)

    tab_bat, tab_pitch, tab_log = st.tabs(["打撃成績", "投球成績", "順位表"])

    # 打撃成績 HTML生成
    html_bat = '<div class="stats-container">'
    batters_to_show = list(st.session_state.my_lineup)
    if st.session_state.my_bench:
        batters_to_show.append((st.session_state.my_bench, "代打"))

    for i, (p, pos) in enumerate(batters_to_show, start=1):
        if pos == "代打":
            icon_char, color, jp_pos = "代", "#888888", "代打"
            order_str = "-"
        else:
            icon_char, color, jp_pos = pos_icon(pos)
            order_str = str(i)

        avg_val = batting_avg(p)
        avg_str = fmt_pct(avg_val)
        ops_val = ops(p)
        ops_str = fmt_pct(ops_val)
        
        uzr = p.fielding.UZR
        uzr_str = f"+{uzr:.1f}" if uzr > 0 else f"{uzr:.1f}"
        if pos == "DH" or pos == "代打": 
            uzr_str = "－"
        
        html_bat += f'<div class="stats-row"><div class="player-hdr"><div class="p-order">{order_str}</div><div class="p-icon" style="background-color: {color};">{icon_char}</div><div class="p-name-container"><div class="p-fullname">{p.name}</div><div class="p-pos">{jp_pos}</div></div></div><div class="main-stats"><div class="ms-item"><span class="ms-label">打率</span><span class="ms-val">{avg_str}</span></div><div class="ms-item"><span class="ms-label">本塁打</span><span class="ms-val-small">{p.batting.HR}</span></div><div class="ms-item"><span class="ms-label">打点</span><span class="ms-val-small">{p.batting.RBI}</span></div><div class="ms-item"><span class="ms-label">盗塁</span><span class="ms-val-small">{p.batting.SB}</span></div><div class="ms-item"><span class="ms-label">OPS</span><span class="ms-val">{ops_str}</span></div></div><div class="sub-stats"><div class="ss-item">試合<b>{p.batting.G}</b></div><div class="ss-item">打席<b>{p.batting.PA}</b></div><div class="ss-item">打数<b>{p.batting.AB}</b></div><div class="ss-item">安打<b>{p.batting.H}</b></div><div class="ss-item">UZR<b>{uzr_str}</b></div></div></div>'

    html_bat += '</div>'

    # 投球成績 HTML生成
    html_pitch = '<div class="stats-container">'
    staff = st.session_state.my_staff
    pitchers_list = staff["starters"] + staff["bullpen"] + ([staff["closer"]] if staff["closer"] else [])
    
    for i, p in enumerate(pitchers_list, start=1):
        icon_char, color, jp_pos = pos_icon("P")
        if p in staff["starters"]:
            role_str = "先発"
        elif p == staff["closer"]:
            role_str = "抑え"
        else:
            role_str = staff["bullpen_roles"].get(id(p), "中継ぎ")
            
        era_str = f"{era(p):.2f}"
        
        html_pitch += f'<div class="stats-row"><div class="player-hdr"><div class="p-order">{i}</div><div class="p-icon" style="background-color: {color};">{icon_char}</div><div class="p-name-container"><div class="p-fullname">{p.name}</div><div class="p-pos">{role_str}</div></div></div><div class="main-stats"><div class="ms-item"><span class="ms-label">防御率</span><span class="ms-val">{era_str}</span></div><div class="ms-item"><span class="ms-label">勝</span><span class="ms-val-small">{p.pitching.W}</span></div><div class="ms-item"><span class="ms-label">敗</span><span class="ms-val-small">{p.pitching.L}</span></div><div class="ms-item"><span class="ms-label">HP</span><span class="ms-val-small">{p.pitching.HLD}</span></div><div class="ms-item"><span class="ms-label">S</span><span class="ms-val-small">{p.pitching.SV}</span></div><div class="ms-item"><span class="ms-label">奪三振</span><span class="ms-val-small">{p.pitching.SO}</span></div></div><div class="sub-stats"><div class="ss-item">試合<b>{p.pitching.G}</b></div><div class="ss-item">先発<b>{p.pitching.GS}</b></div><div class="ss-item">投球回<b>{innings_str(p.pitching.outs)}</b></div><div class="ss-item">四球<b>{p.pitching.BB}</b></div><div class="ss-item">自責点<b>{p.pitching.ER}</b></div></div></div>'

    html_pitch += '</div>'

    # タブ内にHTMLを展開
    with tab_bat:
        st.markdown(html_bat, unsafe_allow_html=True)
        st.markdown("""
        <div class="help-text">
        UZR ... 守備で防いだ失点。0が平均。DHの選手は守備に就かないので「－」。<br>
        成績は実績をもとに作っていますが、その年に大きく伸びたり、不調に落ちたりすることがあります。同じ選手でも毎年同じ数字にはなりません。
        </div>
        """, unsafe_allow_html=True)

    with tab_pitch:
        st.markdown(html_pitch, unsafe_allow_html=True)

    with tab_log:
        league_opponents = list(set(item["opponent"] for item in st.session_state.schedule if item["type"] == "league"))
        
        standings_data = []
        my_w = result["wins"]
        my_l = result["losses"]
        my_d = result["draws"]
        my_pct = my_w / (my_w + my_l) if (my_w + my_l) > 0 else 0
        standings_data.append({"team": "マイチーム", "W": my_w, "L": my_l, "D": my_d, "pct": my_pct, "is_me": True})

        rng = random.Random(my_w + my_l)
        for opp in league_opponents:
            opp_d = rng.randint(2, 9)
            opp_w = rng.randint(50, 85)
            opp_l = 143 - opp_w - opp_d
            opp_pct = opp_w / (opp_w + opp_l)
            standings_data.append({"team": opp, "W": opp_w, "L": opp_l, "D": opp_d, "pct": opp_pct, "is_me": False})

        standings_data.sort(key=lambda x: x["pct"], reverse=True)
        top_w = standings_data[0]["W"]
        top_l = standings_data[0]["L"]
        
        my_rank = next(i for i, r in enumerate(standings_data, 1) if r["is_me"])
        
        html_table = f'<div style="text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #111;">6チーム中 <span style="font-size: 38px;">{my_rank}位</span></div>'
        html_table += '<div style="border-radius: 8px; overflow: hidden; border: 1px solid #E5E5E5;"><table style="width: 100%; border-collapse: collapse; text-align: center; font-size: 15px; background-color: #FAFAFA; color: #333;">'
        html_table += '<tr style="background-color: #EFEFEF; color: #777; font-size: 13px;"><th style="padding: 12px; font-weight: normal;">順位</th><th style="padding: 12px; text-align: left; font-weight: normal;">チーム</th><th style="padding: 12px; font-weight: normal;">勝</th><th style="padding: 12px; font-weight: normal;">敗</th><th style="padding: 12px; font-weight: normal;">分</th><th style="padding: 12px; font-weight: normal;">勝率</th><th style="padding: 12px; font-weight: normal;">差</th></tr>'
        
        for i, row in enumerate(standings_data, start=1):
            bg_color = "background-color: #E8F5E9;" if row["is_me"] else ("background-color: #FFF;" if i % 2 == 0 else "")
            t_name = f'<span style="color: #2E7D32;">{row["team"]} 自分</span>' if row["is_me"] else row["team"]
            gb = ((top_w - row["W"]) + (row["L"] - top_l)) / 2.0
            gb_str = "－" if gb == 0 else f"{gb:.1f}"
            pct_str = fmt_pct(row["pct"])
            
            html_table += f'<tr style="border-top: 1px solid #E5E5E5; {bg_color}"><td style="padding: 12px; color: #555;">{i}</td><td style="padding: 12px; text-align: left; font-weight: bold;">{t_name}</td><td style="padding: 12px;">{row["W"]}</td><td style="padding: 12px;">{row["L"]}</td><td style="padding: 12px;">{row["D"]}</td><td style="padding: 12px; font-weight: bold;">{pct_str}</td><td style="padding: 12px; color: #666;">{gb_str}</td></tr>'
        
        html_table += '</table></div>'
        html_table += '<div style="font-size: 13px; color: #777; margin-top: 15px; line-height: 1.6;">どのチームも143試合。勝率は引き分けを除いて計算しています（勝÷（勝＋敗））。<br>「差」は首位とのゲーム差です。<br>※自分以外の5球団の成績は、このゲームによる架空のシミュレーションです。</div>'
        
        st.markdown(html_table, unsafe_allow_html=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

        log_df = pd.DataFrame(result["game_log"])
        with st.expander("全試合ログを表示"):
            st.dataframe(log_df, hide_index=True, use_container_width=True, height=300)
            st.download_button("試合結果CSV", log_df.to_csv(index=False).encode("utf-8-sig"), file_name="game_results.csv", mime="text/csv")

    # シーズン終了演出
    wins = result["wins"]
    losses = result["losses"]
    draws = result["draws"]
    win_pct = wins / (wins + losses) if (wins + losses) > 0 else 0
    
    if my_rank == 1:
        cs_text = "見事リーグ優勝を果たしました！"
    elif my_rank <= 3:
        cs_text = "見事CS進出を果たしました！"
    else:
        cs_text = "CS進出はなりませんでした。"

    st.markdown(f"""
    <div class="season-end-wrap">
    6チーム中{my_rank}位。{cs_text}
    </div>

    <div class="season-end-box">
        <div class="se-sub">１４３試合を終えて</div>
        <div class="se-main">シーズン終了</div>
        <div class="se-stats">
            <div class="se-rank-label">6チーム中</div>
            <div class="se-rank-val">{my_rank}位</div>
            <div class="se-rec">{wins}勝 {losses}敗 {draws}分</div>
            <div class="se-rec">勝率 {fmt_pct(win_pct)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="next-year-wrapper">', unsafe_allow_html=True)
    if st.button("もう1年やる", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
