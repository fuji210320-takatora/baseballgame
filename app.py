
import random
import math
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import streamlit as st


# ============================================================
# ⚾ 野球チームメーカー / Streamlit 完全版・土台
#
# 想定ファイル:
#   data/野手.xlsx
#   data/投手.xlsx
#
# 野手列:
#   選手名, チーム, ミート, パワー, 走力, 守備力
#
# 例:
#   佐藤輝明, 阪神, 81, 85, 66, 3B:51 / LF:55 / RF:60
#
# 投手列:
#   選手名, チーム, 制球, スタミナ, 球種ランク
#
# 例:
#   村上頌樹, 阪神, 84, 79,
#   フォーシーム:C / カットボール:A / フォーク:S / ...
#
# リーグ所属はExcelに無いため、画面上で「12球団のリーグ」を設定する。
# 初回はチーム名の一覧を見て6球団ずつ振り分けられるようにしている。
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
    "1B": "一塁",
    "2B": "二塁",
    "3B": "三塁",
    "SS": "遊撃",
    "LF": "左翼",
    "CF": "中堅",
    "RF": "右翼",
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

# 基本打席確率。
# 実際のゲーム結果を見ながらここを調整する。
BASE_PA = {
    "single": 0.170,
    "double": 0.055,
    "triple": 0.006,
    "hr": 0.032,
    "walk": 0.085,
    "so": 0.205,
}

SCHEDULE_SAME = 25
SCHEDULE_INTER = 3

# NPB固定リーグ
CENTRAL_TEAMS = [
    "阪神", "DeNA", "巨人", "広島", "ヤクルト", "中日",
]

PACIFIC_TEAMS = [
    "ソフトバンク", "日本ハム", "オリックス", "楽天", "西武", "ロッテ",
]

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
        raise ValueError(
            f"{label}に必要な列がありません: {', '.join(missing)}"
        )


def load_fielders(source):
    df = pd.read_excel(source)
    require_columns(
        df,
        ["選手名", "チーム", "ミート", "パワー", "走力", "守備力"],
        "野手ファイル",
    )

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
    require_columns(
        df,
        ["選手名", "チーム", "制球", "スタミナ", "球種ランク"],
        "投手ファイル",
    )

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
    return (
        p.contact * 0.45
        + p.power * 0.40
        + p.speed * 0.15
    )


def player_pitching_score(p):
    if not p.pitches:
        return 0.0
    pitch_values = [
        RANK_VALUE.get(rank, 55)
        for rank in p.pitches.values()
    ]
    avg_pitch = sum(pitch_values) / len(pitch_values)
    variety_bonus = min(len(p.pitches), 6) * 1.5
    return (
        p.control * 0.35
        + p.stamina * 0.20
        + avg_pitch * 0.45
        + variety_bonus
    )


def best_lineup_for_team(team, dh=True):
    # 単純自動編成。
    # まず各守備位置で最高適性を探し、重複は次善選手へ回す。
    remaining = list(team.fielders)
    lineup = []

    for pos in POSITIONS:
        candidates = sorted(
            remaining,
            key=lambda p: (
                p.defense_at(pos),
                player_offense_score(p),
            ),
            reverse=True,
        )
        if candidates:
            chosen = candidates[0]
            lineup.append((chosen, pos))
            remaining.remove(chosen)

    if dh and remaining:
        dh_player = max(remaining, key=player_offense_score)
        lineup.append((dh_player, "DH"))

    # 打順は攻撃力を基本にしつつ、1番は走力を少し評価
    lineup.sort(
        key=lambda x: player_offense_score(x[0]),
        reverse=True,
    )

    if len(lineup) > 9:
        lineup = lineup[:9]

    return lineup


def best_pitching_staff(team):
    """
    投手15人を
      先発6人 / 中継ぎ8人 / 抑え1人
    に固定。

    中継ぎ8人は能力順を基本に、
      2人 = 中継ぎエース
      3人 = 僅差
      3人 = ビハインド
    として役割を持たせる。
    """
    pitchers = sorted(
        team.pitchers,
        key=player_pitching_score,
        reverse=True,
    )

    starters = pitchers[:6]
    bullpen = pitchers[6:14]
    closer = pitchers[14] if len(pitchers) > 14 else (pitchers[-1] if pitchers else None)

    # 中継ぎ8人を役割別に固定。
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
    weights = [
        RANK_WEIGHT.get(pitcher.pitches[n], 0.8)
        for n in names
    ]

    return random.choices(names, weights=weights, k=1)[0]


def pitch_quality(pitcher, pitch_name):
    if pitch_name is None:
        return 55.0
    rank = pitcher.pitches.get(pitch_name, "C")
    return RANK_VALUE.get(rank, 55.0)


def fatigue_factor(pitcher, game_outs):
    # 先発が長い回を投げるほど少しずつ悪化。
    innings = game_outs / 3.0
    if innings <= 4:
        return 1.0

    excess = innings - 4
    # スタミナ80なら緩やか、50なら大きめ。
    penalty = excess * max(0.0, (80.0 - pitcher.stamina)) * 0.0015
    return clamp(1.0 - penalty, 0.82, 1.0)


def at_bat_probabilities(batter, pitcher, game_outs):
    pitch_name = choose_pitch(pitcher)
    quality = pitch_quality(pitcher, pitch_name)

    fatigue = fatigue_factor(pitcher, game_outs)

    contact_diff = batter.contact - quality
    power_diff = batter.power - quality
    control_diff = pitcher.control - 50.0

    # 球種品質と打者能力の差を中心に補正。
    single = BASE_PA["single"] + contact_diff * 0.0012
    double = BASE_PA["double"] + contact_diff * 0.00025 + power_diff * 0.00035
    triple = BASE_PA["triple"] + batter.speed * 0.00002
    hr = BASE_PA["hr"] + power_diff * 0.0010
    walk = BASE_PA["walk"] - control_diff * 0.0010
    so = BASE_PA["so"] - contact_diff * 0.0010

    # 良い球種ほど長打・安打を抑え、三振を増やす。
    quality_delta = quality - 55.0
    single -= quality_delta * 0.00035
    double -= quality_delta * 0.00018
    hr -= quality_delta * 0.00020
    so += quality_delta * 0.0010

    # 疲労すると投手能力が少し落ちる。
    if fatigue < 1.0:
        single += (1.0 - fatigue) * 0.03
        hr += (1.0 - fatigue) * 0.015
        walk += (1.0 - fatigue) * 0.02
        so -= (1.0 - fatigue) * 0.03

    single = clamp(single, 0.02, 0.35)
    double = clamp(double, 0.005, 0.15)
    triple = clamp(triple, 0.001, 0.03)
    hr = clamp(hr, 0.003, 0.12)
    walk = clamp(walk, 0.015, 0.18)
    so = clamp(so, 0.05, 0.40)

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
    # 打球方向をランダム。
    positions = [
        "1B", "2B", "3B", "SS",
        "LF", "CF", "RF"
    ]

    # 内野にやや多め。
    weights = [
        1.0, 1.1, 1.0, 1.2,
        0.9, 1.0, 0.9
    ]

    pos = random.choices(positions, weights=weights, k=1)[0]

    # その守備位置の選手を探す。
    defender = defense.get(pos)

    return pos, defender


def resolve_outcome(result, defense):
    """
    result == out のときだけ守備判定。
    戻り値:
      field_out, error, position, defender
    """
    pos, defender = choose_batted_ball_position(defense)

    if defender is None:
        return "field_out", pos, None

    ability = defender.defense_at(pos)

    # 守備力0～100を捕球率へ。
    catch_prob = 0.72 + ability / 400.0
    catch_prob = clamp(catch_prob, 0.70, 0.98)

    # ごく低確率の失策。
    if random.random() < catch_prob:
        defender.fielding.PO += 1
        defender.fielding.UZR += (ability - 60.0) / 100.0
        return "field_out", pos, defender

    # エラー。
    defender.fielding.E += 1
    defender.fielding.UZR -= 0.8
    return "error", pos, defender


# ============================================================
# 走者処理
# ============================================================

def advance_on_hit(bases, batter, result):
    """
    bases = [1塁, 2塁, 3塁]
    戻り値: new_bases, runs, scoring_runners
    """
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
        # 3塁
        if bases[2] is not None:
            runs += 1
            scoring.append(bases[2])

        # 2塁
        if bases[1] is not None:
            run_prob = 0.55 + bases[1].speed / 300.0
            if random.random() < clamp(run_prob, 0.55, 0.90):
                runs += 1
                scoring.append(bases[1])
            else:
                new_bases[2] = bases[1]

        # 1塁
        if bases[0] is not None:
            run_prob = 0.30 + bases[0].speed / 250.0
            if random.random() < clamp(run_prob, 0.30, 0.82):
                runs += 1
                scoring.append(bases[0])
            else:
                new_bases[2] = bases[0]

        new_bases[1] = batter
        return new_bases, runs, scoring

    # single
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
# 試合用投手交代
# ============================================================

class PitchingState:
    def __init__(self, staff):
        # 新形式のスタッフ辞書。旧形式も一応受け付ける。
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
        self.pitcher_runs = defaultdict(int)  # key: id(Player)
        self.pitcher_earned = defaultdict(int)  # key: id(Player)

    def choose_starter(self, game_number):
        if not self.starters:
            return None
        self.current = self.starters[game_number % len(self.starters)]
        self.current_start_outs = 0
        self.appearance_start_outs[id(self.current)] = self.current.pitching.outs
        self.current.pitching.G += 1
        self.current.pitching.GS += 1
        return self.current

    def _available_bullpen(self):
        return [p for p in self.bullpen if p not in self.used_bullpen]

    def should_replace(self, score_diff, inning, outs):
        p = self.current
        if p is None:
            return False

        # 先発は原則6回。6回終了後は中継ぎへ。
        if p in self.starters:
            if self.current_start_outs >= 18:
                return True
            if self.pitcher_runs[id(p)] >= 5:
                return True
            # 5回以降に大量失点した場合も交代。
            if inning >= 5 and self.pitcher_runs[id(p)] >= 4:
                return True
            return False

        # 中継ぎは原則1イニング。
        # ただし7回以前の中継ぎエースは最大2イニングまで許可。
        role = self.bullpen_roles.get(id(p), "僅差")
        if role == "中継ぎエース" and inning <= 7:
            max_outs = 6
        else:
            max_outs = 3

        if self.current_start_outs >= max_outs:
            return True

        # 失点が重なった場合は即交代候補。
        if self.pitcher_runs[id(p)] >= 3:
            return True

        return False

    def _select_bullpen(self, inning, score_diff):
        available = self._available_bullpen()
        if not available:
            return None

        # 8回以降でリードなら抑えを優先。
        if inning >= 8 and score_diff > 0 and self.closer is not None and self.closer not in self.used_bullpen:
            return self.closer

        # リード時は「中継ぎエース」→「僅差」。
        if score_diff > 0:
            preferred = [
                p for p in available
                if self.bullpen_roles.get(id(p)) == "中継ぎエース"
            ]
            if preferred:
                return preferred[0]
            preferred = [
                p for p in available
                if self.bullpen_roles.get(id(p)) == "僅差"
            ]
            if preferred:
                return preferred[0]

        # 同点・ビハインドは状況に応じて。
        if score_diff <= -2:
            preferred = [
                p for p in available
                if self.bullpen_roles.get(id(p)) == "ビハインド"
            ]
            if preferred:
                return preferred[0]

        preferred = [
            p for p in available
            if self.bullpen_roles.get(id(p)) == "僅差"
        ]
        if preferred:
            return preferred[0]

        return available[0]

    def replace(self, inning, score_diff):
        old = self.current
        if old is None:
            return None

        new = None
        if old in self.starters:
            new = self._select_bullpen(inning, score_diff)
        elif old in self.bullpen:
            new = self._select_bullpen(inning, score_diff)
        elif old is self.closer:
            # クローザーを途中交代させる必要がある場合のみ残りから選択。
            new = self._select_bullpen(inning, score_diff)

        if new is None or new is old:
            return self.current

        # 交代前の投手が「リードして降板」ならホールド。
        old_id = id(old)
        entered_score_diff = self.hold_eligible.get(old_id)
        if old in self.bullpen and entered_score_diff is not None:
            if entered_score_diff > 0 and score_diff > 0 and old is not self.closer:
                old.pitching.HLD += 1

        if new not in self.used_bullpen and new in self.bullpen:
            self.used_bullpen.append(new)

        new.pitching.G += 1
        self.current = new
        self.current_start_outs = 0
        self.appearance_start_outs[id(new)] = new.pitching.outs

        # 中継ぎとして入った時点でリードしていたかを記録。
        if new in self.bullpen:
            self.hold_eligible[id(new)] = score_diff > 0

        if new is self.closer:
            # 8回以降、リード3点差以内で入った抑えはセーブ機会。
            self.save_eligible = inning >= 8 and 0 < score_diff <= 3

        return self.current


# ============================================================
# 1試合
# ============================================================

def simulate_half_inning(
    offense_lineup,
    batting_index,
    pitcher,
    defense,
    league,
    home_team=False,
    inning=1,
    game_state=None,
):
    outs = 0
    bases = [None, None, None]
    runs = 0

    while outs < 3:
        batter = offense_lineup[batting_index[0] % len(offense_lineup)]
        batting_index[0] += 1

        batter.batting.PA += 1
        pitcher.pitching.BF += 1

        probs, pitch_name = at_bat_probabilities(
            batter,
            pitcher,
            pitcher.pitching.outs,
        )
        result = choose_result(probs)

        # -----------------------------
        # ヒット
        # -----------------------------
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
            bases, scored, scoring = advance_on_hit(
                old_bases,
                batter,
                result,
            )

            runs += scored

            if scored:
                batter.batting.RBI += scored

            for runner in scoring:
                runner.batting.R += 1

            # HRは打者自身も得点
            if result == "hr":
                batter.batting.R += 1

        # -----------------------------
        # 四球
        # -----------------------------
        elif result == "walk":
            batter.batting.BB += 1
            pitcher.pitching.BB += 1

            bases, scored, scoring = advance_on_walk(
                bases,
                batter,
            )

            runs += scored

            if scored:
                batter.batting.RBI += scored

            for runner in scoring:
                runner.batting.R += 1

        # -----------------------------
        # 三振
        # -----------------------------
        elif result == "so":
            batter.batting.AB += 1
            batter.batting.SO += 1
            pitcher.pitching.SO += 1
            outs += 1
            pitcher.pitching.outs += 1

        # -----------------------------
        # 打球アウト / エラー
        # -----------------------------
        else:
            batter.batting.AB += 1

            outcome, pos, defender = resolve_outcome(
                result,
                defense,
            )

            if outcome == "field_out":
                outs += 1
                pitcher.pitching.outs += 1

                if defender is not None:
                    defender.fielding.A += 1

            else:
                # エラーは打数にはなるがアウトにならない。
                # UZRは守備側に記録済み。
                if defender is not None:
                    # 出塁として扱う。
                    pass

                # エラー時は打者一塁。
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


def simulate_game(
    my_lineup,
    my_staff,
    op_lineup,
    op_staff,
    league,
    game_number,
):
    """
    自チーム視点で1試合。
    自チームは後攻。
    """

    my_pitching = PitchingState(my_staff)
    op_pitching = PitchingState(op_staff)

    my_pitcher = my_pitching.choose_starter(game_number)
    op_pitcher = op_pitching.choose_starter(game_number)

    if my_pitcher is None or op_pitcher is None:
        return 0, 0, {}

    my_score = 0
    op_score = 0

    my_batting_index = [0]
    op_batting_index = [0]

    # 9回＋延長最大3回
    for inning in range(1, 13):

        # 表：相手攻撃
        if my_pitching.should_replace(
            my_score - op_score,
            inning,
            my_pitcher.pitching.outs,
        ):
            my_pitcher = my_pitching.replace(
                inning,
                my_score - op_score,
            )

        defense_my = {
            pos: player
            for player, pos in my_lineup
            if pos != "DH"
        }

        # DHなしの場合、投手が打席に入る。
        offense_op = list(op_lineup)

        if league == "セ・リーグ":
            # 自動編成でop_lineupがDHを含まない場合、
            # 投手を9番に入れる。
            if len(offense_op) == 8:
                offense_op.append((op_pitcher, "P"))

        op_runs_before = op_score

        r, _ = simulate_half_inning(
            [p for p, _ in offense_op],
            op_batting_index,
            my_pitcher,
            defense_my,
            league,
            inning=inning,
        )

        op_score += r

        # この登板で投げたアウト数を更新。
        my_pitching.current_start_outs = (
            my_pitcher.pitching.outs
            - my_pitching.appearance_start_outs.get(id(my_pitcher), my_pitcher.pitching.outs)
        )

        # このイニングで失点した分を投手へ.
        my_pitching.pitcher_runs[id(my_pitcher)] += r
        my_pitching.pitcher_earned[id(my_pitcher)] += r
        my_pitcher.pitching.R += r
        my_pitcher.pitching.ER += r

        # 裏：自チーム攻撃
        if op_pitching.should_replace(
            op_score - my_score,
            inning,
            op_pitcher.pitching.outs,
        ):
            op_pitcher = op_pitching.replace(
                inning,
                op_score - my_score,
            )

        defense_op = {
            pos: player
            for player, pos in op_lineup
            if pos != "DH"
        }

        offense_my = list(my_lineup)

        if league == "セ・リーグ":
            if len(offense_my) == 8:
                offense_my.append((my_pitcher, "P"))

        r, _ = simulate_half_inning(
            [p for p, _ in offense_my],
            my_batting_index,
            op_pitcher,
            defense_op,
            league,
            inning=inning,
        )

        my_score += r

        op_pitching.current_start_outs = (
            op_pitcher.pitching.outs
            - op_pitching.appearance_start_outs.get(id(op_pitcher), op_pitcher.pitching.outs)
        )

        op_pitching.pitcher_runs[id(op_pitcher)] += r
        op_pitching.pitcher_earned[id(op_pitcher)] += r
        op_pitcher.pitching.R += r
        op_pitcher.pitching.ER += r

        # 9回終了時点で勝敗がついていれば終了。
        if inning >= 9 and my_score != op_score:
            break

    # 勝敗・勝利投手・セーブ。
    # リリーフに交代した場合は、その試合で最後に投げて勝利を確定させた投手を勝利投手とする簡易ルール。
    if my_score > op_score:
        my_pitcher.pitching.W += 1
        if my_pitcher is my_pitching.closer and my_pitching.save_eligible:
            my_pitcher.pitching.SV += 1
        return my_score, op_score, {"result": "W"}
    elif my_score < op_score:
        my_pitcher.pitching.L += 1
        return my_score, op_score, {"result": "L"}
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


# ============================================================
# スケジュール
# ============================================================

def create_schedule(my_league, same_teams, inter_teams):
    """
    25試合×5チーム + 3試合×6チーム = 143試合
    """
    schedule = []

    for team in same_teams:
        for _ in range(SCHEDULE_SAME):
            schedule.append({
                "opponent": team,
                "type": "league",
            })

    for team in inter_teams:
        for _ in range(SCHEDULE_INTER):
            schedule.append({
                "opponent": team,
                "type": "interleague",
            })

    random.shuffle(schedule)
    return schedule[:143]


# ============================================================
# ドラフト
# ============================================================

def candidate_card(p):
    if p.is_pitcher():
        return {
            "選手名": p.name,
            "チーム": p.team,
            "制球": p.control,
            "スタミナ": p.stamina,
            "球種": " / ".join(
                f"{k}:{v}" for k, v in p.pitches.items()
            ),
        }

    return {
        "選手名": p.name,
        "チーム": p.team,
        "ミート": p.contact,
        "パワー": p.power,
        "走力": p.speed,
        "守備": " / ".join(
            f"{k}:{v:g}" for k, v in p.defense.items()
        ),
    }


def draft_page(kind, all_players, count, skip_limit=None):
    """
    1人ずつ候補を表示するドラフト。
    Streamlitの再実行で候補が勝手に変わらないよう、候補をsession_stateに保存する。
    候補が空の場合もrandom.choiceを呼ばず、安全に終了する。
    """
    selected_key = "draft_fielders" if kind == "野手" else "draft_pitchers"
    pool_key = "draft_fielder_pool" if kind == "野手" else "draft_pitcher_pool"
    candidate_key = "draft_fielder_candidate" if kind == "野手" else "draft_pitcher_candidate"
    skip_key = "fielder_skips" if kind == "野手" else "pitcher_skips"

    if selected_key not in st.session_state:
        st.session_state[selected_key] = []

    if pool_key not in st.session_state:
        st.session_state[pool_key] = list(all_players)

    if skip_key not in st.session_state:
        st.session_state[skip_key] = 0

    selected = st.session_state[selected_key]
    pool = st.session_state[pool_key]

    st.header(f"ドラフト：{kind}")
    st.write(f"獲得 {len(selected)} / {count}人")

    if skip_limit is not None:
        st.write(f"見送り {st.session_state[skip_key]} / {skip_limit}")

    if len(selected) >= count:
        st.session_state.pop(candidate_key, None)
        return True

    # 古いセッションやデータ変更でpoolが空になってもクラッシュしない。
    selected_ids = {id(p) for p in selected}
    pool = [p for p in pool if id(p) not in selected_ids]
    st.session_state[pool_key] = pool

    if not pool:
        st.error(
            f"{kind}の候補選手がなくなりました。"
            "必要人数を確保できるだけの選手データがExcelにあるか確認してください。"
        )
        st.session_state.pop(candidate_key, None)
        return False

    candidate = st.session_state.get(candidate_key)

    # 保存されている候補が現在のpoolに存在しない場合だけ再抽選。
    if candidate is None or candidate not in pool:
        candidate = random.choice(pool)
        st.session_state[candidate_key] = candidate

    st.subheader(f"出現選手：{candidate.name}")

    st.dataframe(
        pd.DataFrame([candidate_card(candidate)]),
        hide_index=True,
        use_container_width=True,
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button(
            "✅ 取る",
            type="primary",
            use_container_width=True,
            key=f"take_{kind}_{len(selected)}_{st.session_state[skip_key]}",
        ):
            selected.append(candidate)
            st.session_state[pool_key] = [p for p in pool if p is not candidate]
            st.session_state.pop(candidate_key, None)
            st.rerun()

    with c2:
        skip_disabled = (
            skip_limit is not None
            and st.session_state[skip_key] >= skip_limit
        )

        if st.button(
            "❌ 見送る",
            disabled=skip_disabled,
            use_container_width=True,
            key=f"skip_{kind}_{len(selected)}_{st.session_state[skip_key]}",
        ):
            st.session_state[pool_key] = [p for p in pool if p is not candidate]
            st.session_state[skip_key] += 1
            st.session_state.pop(candidate_key, None)
            st.rerun()

    st.divider()

    if selected:
        st.write("現在の獲得選手")
        st.dataframe(
            pd.DataFrame([candidate_card(p) for p in selected]),
            hide_index=True,
            use_container_width=True,
        )

    return False


# ============================================================
# オーダー画面
# ============================================================

def order_page(fielders, league):
    st.header("④ オーダー設定")

    st.info(
        f"選択リーグ：{league}"
    )

    # 各守備位置に1人ずつ割り当てる。
    # 同じ選手を複数ポジションに置けないようにする。
    lineup = []

    used = set()

    st.subheader("守備位置")

    for pos in POSITIONS:
        available = [
            p for p in fielders
            if p.name not in used
        ]

        if not available:
            st.error("野手の人数が不足しています。")
            return None

        # 適性がある選手を上に。
        available = sorted(
            available,
            key=lambda p: (
                p.defense_at(pos),
                player_offense_score(p)
            ),
            reverse=True,
        )

        names = [p.name for p in available]

        default_index = 0

        selected_name = st.selectbox(
            f"{POSITION_JP[pos]} ({pos})",
            names,
            index=default_index,
            key=f"order_{pos}",
        )

        player = next(
            p for p in available
            if p.name == selected_name
        )

        lineup.append((player, pos))
        used.add(player.name)

        st.caption(
            f"守備力 {pos}: {player.defense_at(pos):g}"
        )

    remaining = [
        p for p in fielders
        if p.name not in used
    ]

    if league == "パ・リーグ":
        st.subheader("DH")

        if not remaining:
            st.error("DH候補がいません。")
            return None

        dh_name = st.selectbox(
            "DH",
            [p.name for p in remaining],
            key="order_DH",
        )

        dh = next(
            p for p in remaining
            if p.name == dh_name
        )

        lineup.append((dh, "DH"))

    else:
        st.info(
            "セ・リーグなので余った野手は代打要員になります。"
        )

    st.subheader("打順")

    # 守備設定済みの9人を打順に並べる。
    # 初期値は攻撃力順。
    lineup_default = sorted(
        lineup,
        key=lambda x: player_offense_score(x[0]),
        reverse=True,
    )

    names = [p.name for p, _ in lineup_default]

    ordered = []

    for i in range(9):
        remaining_names = [
            n for n in names
            if n not in [p.name for p, _ in ordered]
        ]

        selected_name = st.selectbox(
            f"{i + 1}番",
            remaining_names,
            key=f"batting_order_{i}",
        )

        pair = next(
            x for x in lineup_default
            if x[0].name == selected_name
        )

        ordered.append(pair)

    bench = remaining[0] if league == "セ・リーグ" and remaining else None

    if bench:
        st.write(
            f"代打要員：**{bench.name}**"
        )

    if st.button("オーダー決定", type="primary"):
        return {
            "lineup": ordered,
            "bench": bench,
        }

    return None


# ============================================================
# 投手起用画面
# ============================================================

def pitching_page(pitchers):
    st.header("⑤ 投手起用設定")

    names = [p.name for p in pitchers]

    if len(names) < 15:
        st.error("投手が15人未満です。先発6人＋中継ぎ8人＋抑え1人が必要です。")
        return None

    starters = []
    st.subheader("先発6人")
    for i in range(6):
        selected_name = st.selectbox(
            f"先発{i + 1}",
            names,
            key=f"starter_{i}",
        )
        p = next(x for x in pitchers if x.name == selected_name)
        starters.append(p)

    bullpen = []
    bullpen_roles = {}
    role_labels = [
        "中継ぎエース1", "中継ぎエース2",
        "僅差1", "僅差2", "僅差3",
        "ビハインド1", "ビハインド2", "ビハインド3",
    ]
    role_values = [
        "中継ぎエース", "中継ぎエース",
        "僅差", "僅差", "僅差",
        "ビハインド", "ビハインド", "ビハインド",
    ]

    st.subheader("中継ぎ8人")
    for i, (label, role) in enumerate(zip(role_labels, role_values)):
        selected_name = st.selectbox(
            f"{label}（{role}）",
            names,
            key=f"bullpen_{i}",
        )
        p = next(x for x in pitchers if x.name == selected_name)
        bullpen.append(p)
        bullpen_roles[id(p)] = role

    st.subheader("抑え1人")
    closer_name = st.selectbox(
        "抑え",
        names,
        key="closer",
    )
    closer = next(x for x in pitchers if x.name == closer_name)

    chosen = starters + bullpen + [closer]
    duplicates = len(chosen) != len(set(id(p) for p in chosen))

    if duplicates:
        st.warning(
            "同じ投手が複数の役割に設定されています。"
            "先発6・中継ぎ8・抑え1をそれぞれ別の投手にしてください。"
        )

    if st.button("投手起用決定", type="primary"):
        if duplicates:
            st.error("投手の重複を解消してから決定してください。")
            return None

        return {
            "starters": starters,
            "bullpen": bullpen,
            "closer": closer,
            "bullpen_roles": bullpen_roles,
        }

    return None


# ============================================================
# 相手球団を自動作成
# ============================================================

def build_opponent_team(team, dh):
    lineup = best_lineup_for_team(team, dh=dh)
    staff = best_pitching_staff(team)

    return {
        "team": team,
        "lineup": lineup,
        "staff": staff,
    }


# ============================================================
# 画面
# ============================================================

st.title("⚾ 野球チームメーカー")

st.caption(
    "ランダムに登場する選手を取捨選択し、24人のチームを作って143試合をシミュレーションします。"
)


# ============================================================
# データ読み込み
# ============================================================

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


# 同じ名前が重複していた場合の注意
st.sidebar.success(
    f"野手 {len(fielders_all)}人 / 投手 {len(pitchers_all)}人"
)


# ============================================================
# セッション初期化
# ============================================================

if "step" not in st.session_state:
    st.session_state.step = "league_setup"

st.session_state.teams = build_teams(
    fielders_all,
    pitchers_all,
)


# ============================================================
# リーグ設定
# ============================================================

if st.session_state.step == "league_setup":

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


# ============================================================
# 野手ドラフト
# ============================================================

elif st.session_state.step == "draft_fielders":

    finished = draft_page(
        "野手",
        fielders_all,
        9,
        skip_limit=5,
    )

    if finished:
        st.session_state.step = "draft_pitchers"
        st.rerun()


# ============================================================
# 投手ドラフト
# ============================================================

elif st.session_state.step == "draft_pitchers":

    # 野手として取った選手と名前が同じ選手を除外。
    # 通常は投手ファイルと野手ファイルが分離されているため問題なし。
    finished = draft_page(
        "投手",
        pitchers_all,
        15,
        skip_limit=None,
    )

    if finished:
        st.session_state.step = "league_select"
        st.rerun()


# ============================================================
# セ・パ選択
# ============================================================

elif st.session_state.step == "league_select":

    st.header("③ セ・パ選択")

    league = st.radio(
        "あなたのチームはどちらのリーグに所属しますか？",
        ["セ・リーグ", "パ・リーグ"],
    )

    if league == "セ・リーグ":
        st.info(
            "DHなし。野手8人＋投手9番。余った野手1人は代打要員。"
        )
    else:
        st.info(
            "DHあり。野手9人で打線を組みます。"
        )

    if st.button("リーグ決定", type="primary"):
        st.session_state.my_league = league
        st.session_state.step = "order"
        st.rerun()


# ============================================================
# オーダー
# ============================================================

elif st.session_state.step == "order":

    result = order_page(
        st.session_state.draft_fielders,
        st.session_state.my_league,
    )

    if result is not None:
        st.session_state.my_lineup = result["lineup"]
        st.session_state.my_bench = result["bench"]
        st.session_state.step = "pitching"
        st.rerun()


# ============================================================
# 投手起用
# ============================================================

elif st.session_state.step == "pitching":

    result = pitching_page(
        st.session_state.draft_pitchers
    )

    if result is not None:
        st.session_state.my_staff = result
        st.session_state.step = "ready"
        st.rerun()


# ============================================================
# 開幕前確認
# ============================================================

elif st.session_state.step == "ready":

    st.header("⑥ 開幕前確認")

    league = st.session_state.my_league

    st.write(f"**リーグ：** {league}")

    st.subheader("打順")

    lineup_rows = []

    for i, (p, pos) in enumerate(
        st.session_state.my_lineup,
        start=1
    ):
        lineup_rows.append({
            "打順": i,
            "選手": p.name,
            "守備": POSITION_JP.get(pos, pos),
            "ミート": p.contact,
            "パワー": p.power,
            "走力": p.speed,
            "守備力": p.defense_at(pos) if pos != "DH" else 0,
        })

    st.dataframe(
        pd.DataFrame(lineup_rows),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("投手陣")

    pitching_rows = []

    for i, p in enumerate(
        st.session_state.my_staff["starters"],
        start=1
    ):
        pitching_rows.append({
            "役割": f"先発{i}",
            "選手": p.name,
            "制球": p.control,
            "スタミナ": p.stamina,
            "球種": " / ".join(
                f"{n}:{r}" for n, r in p.pitches.items()
            ),
        })

    for i, p in enumerate(
        st.session_state.my_staff["bullpen"],
        start=1
    ):
        pitching_rows.append({
            "役割": st.session_state.my_staff.get("bullpen_roles", {}).get(id(p), "中継ぎ"),
            "選手": p.name,
            "制球": p.control,
            "スタミナ": p.stamina,
            "球種": " / ".join(
                f"{n}:{r}" for n, r in p.pitches.items()
            ),
        })

    p = st.session_state.my_staff["closer"]

    pitching_rows.append({
        "役割": "抑え",
        "選手": p.name if p else "-",
        "制球": p.control if p else 0,
        "スタミナ": p.stamina if p else 0,
        "球種": " / ".join(
            f"{n}:{r}" for n, r in p.pitches.items()
        ) if p else "",
    })

    st.dataframe(
        pd.DataFrame(pitching_rows),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("対戦球団")

    if league == "セ・リーグ":
        same = [
            x for x in st.session_state.central
        ]
        inter = [
            x for x in st.session_state.pacific
        ]
    else:
        same = [
            x for x in st.session_state.pacific
        ]
        inter = [
            x for x in st.session_state.central
        ]

    # 自分のチームは既存球団ではないため、
    # same/interともに既存6球団から選ぶ。
    # 同リーグは5球団にする。
    same = random.sample(same, min(5, len(same)))
    inter = random.sample(inter, min(6, len(inter)))

    schedule = create_schedule(
        league,
        same,
        inter,
    )

    st.session_state.schedule = schedule

    st.write(
        f"同リーグ：{len(same)}球団 × {SCHEDULE_SAME}試合"
    )
    st.write(
        f"交流戦：{len(inter)}球団 × {SCHEDULE_INTER}試合"
    )
    st.write(
        f"合計：{len(schedule)}試合"
    )

    if st.button(
        "⚾ シーズン開始",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.step = "season"
        st.rerun()


# ============================================================
# シーズン
# ============================================================

elif st.session_state.step == "season":

    st.header("⑦ 143試合シミュレーション")

    # 相手球団を生成。
    teams = st.session_state.teams
    league = st.session_state.my_league

    my_lineup = st.session_state.my_lineup
    my_staff = st.session_state.my_staff

    # 143試合で成績をリセット。
    reset_stats(
        st.session_state.draft_fielders
        + st.session_state.draft_pitchers
    )

    # 相手球団の個人成績は表示・保存しない。
    # 試合ごとに必要なものだけ使う。
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

        opponent = build_opponent_team(
            opponent_team,
            dh=(league == "パ・リーグ"),
        )

        # 自チームの打順はそのまま。
        # 相手の打順は自動生成。
        op_lineup = opponent["lineup"]

        # 自チームの投手スタッフはその試合で使う。
        # 先発ローテはgame_noで選択。
        # simulate_gameがgame_numberから先発を決める。
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

        if result["result"] == "W":
            wins += 1
        elif result["result"] == "L":
            losses += 1
        else:
            draws += 1

        game_log.append({
            "試合": game_no,
            "対戦相手": opponent_name,
            "区分": "同リーグ" if item["type"] == "league" else "交流戦",
            "得点": score_my,
            "失点": score_op,
            "結果": result["result"],
        })

        progress.progress(game_no / 143)
        status.write(
            f"{game_no}/143試合　"
            f"{opponent_name}　"
            f"{score_my}-{score_op}"
        )

    # ------------------------------------------
    # 成績保存
    # ------------------------------------------
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


# ============================================================
# 結果
# ============================================================

elif st.session_state.step == "result":

    result = st.session_state.season_result

    st.header("🏆 シーズン終了")

    wins = result["wins"]
    losses = result["losses"]
    draws = result["draws"]
    rf = result["runs_for"]
    ra = result["runs_against"]

    win_pct = (
        wins / (wins + losses)
        if wins + losses > 0
        else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("勝", wins)
    c2.metric("敗", losses)
    c3.metric("引分", draws)
    c4.metric("勝率", f"{win_pct:.3f}")
    c5.metric("得失点差", rf - ra)

    st.subheader("チーム成績")

    pitchers = st.session_state.draft_pitchers
    batters = st.session_state.draft_fielders

    total_pitching_outs = sum(
        p.pitching.outs for p in pitchers
    )
    total_er = sum(
        p.pitching.ER for p in pitchers
    )

    team_era = (
        total_er * 27 / total_pitching_outs
        if total_pitching_outs
        else 0
    )

    total_ab = sum(
        p.batting.AB for p in batters
    )
    total_h = sum(
        p.batting.H for p in batters
    )

    team_avg = (
        total_h / total_ab
        if total_ab
        else 0
    )

    st.write(
        f"**得点：** {rf}　"
        f"**失点：** {ra}　"
        f"**得失点差：** {rf - ra}"
    )

    st.write(
        f"**チーム打率：** {team_avg:.3f}　"
        f"**チーム防御率：** {team_era:.2f}"
    )

    # ------------------------------------------
    # 野手成績
    # ------------------------------------------

    st.subheader("打者個人成績")

    batting_rows = []

    for p in batters:

        batting_rows.append({
            "選手": p.name,
            "試合": p.batting.G,
            "打席": p.batting.PA,
            "打数": p.batting.AB,
            "打率": round(batting_avg(p), 3),
            "安打": p.batting.H,
            "二塁打": p.batting.double,
            "三塁打": p.batting.triple,
            "本塁打": p.batting.HR,
            "四球": p.batting.BB,
            "三振": p.batting.SO,
            "打点": p.batting.RBI,
            "得点": p.batting.R,
            "盗塁": p.batting.SB,
            "OPS": round(ops(p), 3),
        })

    batting_df = pd.DataFrame(batting_rows)

    st.dataframe(
        batting_df,
        hide_index=True,
        use_container_width=True,
    )

    # ------------------------------------------
    # 投手成績
    # ------------------------------------------

    st.subheader("投手個人成績")

    pitching_rows = []

    for p in pitchers:

        pitching_rows.append({
            "選手": p.name,
            "試合": p.pitching.G,
            "先発": p.pitching.GS,
            "投球回": innings_str(p.pitching.outs),
            "防御率": round(era(p), 2),
            "勝": p.pitching.W,
            "敗": p.pitching.L,
            "H": p.pitching.HLD,
            "S": p.pitching.SV,
            "奪三振": p.pitching.SO,
            "四球": p.pitching.BB,
            "自責点": p.pitching.ER,
        })

    pitching_df = pd.DataFrame(pitching_rows)

    st.dataframe(
        pitching_df,
        hide_index=True,
        use_container_width=True,
    )

    # ------------------------------------------
    # 守備成績
    # ------------------------------------------

    st.subheader("守備成績 / 簡易UZR")

    fielding_rows = []

    for p in batters:

        fielding_rows.append({
            "選手": p.name,
            "刺殺": p.fielding.PO,
            "補殺": p.fielding.A,
            "失策": p.fielding.E,
            "UZR": round(p.fielding.UZR, 2),
        })

    fielding_df = pd.DataFrame(fielding_rows)

    st.dataframe(
        fielding_df,
        hide_index=True,
        use_container_width=True,
    )

    # ------------------------------------------
    # 試合結果
    # ------------------------------------------

    st.subheader("全試合結果")

    log_df = pd.DataFrame(result["game_log"])

    st.dataframe(
        log_df,
        hide_index=True,
        use_container_width=True,
        height=500,
    )

    # CSVダウンロード
    st.download_button(
        "打撃成績CSV",
        batting_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="batting_results.csv",
        mime="text/csv",
    )

    st.download_button(
        "投手成績CSV",
        pitching_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="pitching_results.csv",
        mime="text/csv",
    )

    st.download_button(
        "試合結果CSV",
        log_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="game_results.csv",
        mime="text/csv",
    )

    st.divider()

    if st.button("最初からやり直す"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

