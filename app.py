import random
import math
from dataclasses import dataclass, field
from collections import defaultdict

import pandas as pd
import streamlit as st


# ============================================================
# ⚾ 野球チームメーカー
#
# GitHubリポジトリ構成
#
# ├── app.py
# ├── 投手能力データ_最新.xlsx
# ├── 野手能力データ_最新.xlsx
# └── requirements.txt
#
# Excelの列
#
# 野手:
# 選手名 / チーム / ミート / パワー / 走力 / 守備力
#
# 投手:
# 選手名 / チーム / 制球 / スタミナ / 球種ランク
#
# ============================================================


st.set_page_config(
    page_title="野球チームメーカー",
    page_icon="⚾",
    layout="wide",
)


# ============================================================
# ファイル名
# ============================================================

PITCHER_FILE = "投手能力データ_最新.xlsx"
FIELDER_FILE = "野手能力データ_最新.xlsx"


# ============================================================
# 基本設定
# ============================================================

POSITIONS = [
    "C",
    "1B",
    "2B",
    "3B",
    "SS",
    "LF",
    "CF",
    "RF",
]

POSITION_JP = {
    "C": "捕手",
    "1B": "一塁",
    "2B": "二塁",
    "3B": "三塁",
    "SS": "遊撃",
    "LF": "左翼",
    "CF": "中堅",
    "RF": "右翼",
    "DH": "DH",
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


# ============================================================
# 成績データ
# ============================================================

@dataclass
class BatterStats:
    G: int = 0
    PA: int = 0
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

    # 野手能力
    contact: float = 0.0
    power: float = 0.0
    speed: float = 0.0
    defense: dict = field(default_factory=dict)

    # 投手能力
    control: float = 0.0
    stamina: float = 0.0
    pitches: dict = field(default_factory=dict)

    batting: BatterStats = field(default_factory=BatterStats)
    pitching: PitcherStats = field(default_factory=PitcherStats)
    fielding: FielderStats = field(default_factory=FielderStats)

    def is_pitcher(self):
        return bool(self.pitches) or self.control > 0 or self.stamina > 0

    def defense_at(self, position):
        return float(self.defense.get(position, 0))


@dataclass
class Team:
    name: str
    fielders: list
    pitchers: list


# ============================================================
# Excel読み込み
# ============================================================

def clean_number(value, default=0.0):
    if pd.isna(value):
        return default

    try:
        return float(value)
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

        position, value = part.split(":", 1)

        position = position.strip().upper()

        try:
            result[position] = float(value.strip())
        except Exception:
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

        pitch_name, rank = part.split(":", 1)

        pitch_name = pitch_name.strip()
        rank = rank.strip().upper()

        if rank in RANK_VALUE:
            result[pitch_name] = rank

    return result


def check_columns(df, required, filename):
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"{filename} に必要な列がありません。\n"
            f"不足列: {', '.join(missing)}"
        )


@st.cache_data
def load_data():

    # -------------------------
    # 野手
    # -------------------------

    fielder_df = pd.read_excel(FIELDER_FILE)

    check_columns(
        fielder_df,
        [
            "選手名",
            "チーム",
            "ミート",
            "パワー",
            "走力",
            "守備力",
        ],
        FIELDER_FILE,
    )

    fielders = []

    for _, row in fielder_df.iterrows():

        player = Player(
            name=str(row["選手名"]).strip(),
            team=str(row["チーム"]).strip(),
            contact=clean_number(row["ミート"]),
            power=clean_number(row["パワー"]),
            speed=clean_number(row["走力"]),
            defense=parse_defense(row["守備力"]),
        )

        fielders.append(player)

    # -------------------------
    # 投手
    # -------------------------

    pitcher_df = pd.read_excel(PITCHER_FILE)

    check_columns(
        pitcher_df,
        [
            "選手名",
            "チーム",
            "制球",
            "スタミナ",
            "球種ランク",
        ],
        PITCHER_FILE,
    )

    pitchers = []

    for _, row in pitcher_df.iterrows():

        player = Player(
            name=str(row["選手名"]).strip(),
            team=str(row["チーム"]).strip(),
            control=clean_number(row["制球"]),
            stamina=clean_number(row["スタミナ"]),
            pitches=parse_pitches(row["球種ランク"]),
        )

        pitchers.append(player)

    return fielders, pitchers


# ============================================================
# チーム作成
# ============================================================

def build_teams(fielders, pitchers):

    data = {}

    for player in fielders:

        if player.team not in data:
            data[player.team] = {
                "fielders": [],
                "pitchers": [],
            }

        data[player.team]["fielders"].append(player)

    for player in pitchers:

        if player.team not in data:
            data[player.team] = {
                "fielders": [],
                "pitchers": [],
            }

        data[player.team]["pitchers"].append(player)

    result = {}

    for team_name, values in data.items():

        result[team_name] = Team(
            name=team_name,
            fielders=values["fielders"],
            pitchers=values["pitchers"],
        )

    return result


# ============================================================
# 能力評価
# ============================================================

def offense_score(player):

    return (
        player.contact * 0.45
        + player.power * 0.40
        + player.speed * 0.15
    )


def pitching_score(player):

    if not player.pitches:
        return 0

    pitch_values = [
        RANK_VALUE.get(rank, 55)
        for rank in player.pitches.values()
    ]

    avg_pitch = sum(pitch_values) / len(pitch_values)

    return (
        player.control * 0.35
        + player.stamina * 0.20
        + avg_pitch * 0.45
    )


# ============================================================
# 自動オーダー
# ============================================================

def make_opponent_lineup(team, dh):

    remaining = list(team.fielders)

    lineup = []

    for position in POSITIONS:

        candidates = sorted(
            remaining,
            key=lambda p: (
                p.defense_at(position),
                offense_score(p),
            ),
            reverse=True,
        )

        if not candidates:
            continue

        player = candidates[0]

        lineup.append(
            (player, position)
        )

        remaining.remove(player)

    if dh and remaining:

        player = max(
            remaining,
            key=offense_score,
        )

        lineup.append(
            (player, "DH")
        )

    lineup.sort(
        key=lambda x: offense_score(x[0]),
        reverse=True,
    )

    return lineup[:9]


def make_opponent_staff(team):

    pitchers = sorted(
        team.pitchers,
        key=pitching_score,
        reverse=True,
    )

    starters = pitchers[:5]

    bullpen = pitchers[5:8]

    closer = (
        pitchers[8]
        if len(pitchers) > 8
        else pitchers[-1]
        if pitchers
        else None
    )

    return {
        "starters": starters,
        "bullpen": bullpen,
        "closer": closer,
    }


# ============================================================
# 成績リセット
# ============================================================

def reset_stats(players):

    for player in players:

        player.batting = BatterStats()
        player.pitching = PitcherStats()
        player.fielding = FielderStats()


# ============================================================
# 確率関連
# ============================================================

def clamp(value, low, high):

    return max(
        low,
        min(high, value),
    )


def choose_pitch(pitcher):

    if not pitcher.pitches:
        return None

    names = list(
        pitcher.pitches.keys()
    )

    weights = [
        RANK_WEIGHT.get(
            pitcher.pitches[name],
            0.8,
        )
        for name in names
    ]

    return random.choices(
        names,
        weights=weights,
        k=1,
    )[0]


def pitch_quality(pitcher, pitch_name):

    if pitch_name is None:
        return 55

    rank = pitcher.pitches.get(
        pitch_name,
        "C",
    )

    return RANK_VALUE.get(
        rank,
        55,
    )


def pitcher_fatigue(pitcher):

    innings = (
        pitcher.pitching.outs / 3
    )

    if innings <= 4:
        return 1.0

    excess = innings - 4

    penalty = (
        excess
        * max(
            0,
            80 - pitcher.stamina,
        )
        * 0.0015
    )

    return clamp(
        1 - penalty,
        0.82,
        1.0,
    )


def batter_probabilities(
    batter,
    pitcher,
):

    pitch_name = choose_pitch(
        pitcher
    )

    quality = pitch_quality(
        pitcher,
        pitch_name,
    )

    fatigue = pitcher_fatigue(
        pitcher
    )

    contact_diff = (
        batter.contact
        - quality
    )

    power_diff = (
        batter.power
        - quality
    )

    control_diff = (
        pitcher.control
        - 50
    )

    single = (
        0.150
        + contact_diff * 0.0012
    )

    double = (
        0.045
        + contact_diff * 0.00025
        + power_diff * 0.00035
    )

    triple = (
        0.005
        + batter.speed * 0.00002
    )

    homerun = (
        0.030
        + power_diff * 0.0010
    )

    walk = (
        0.080
        - control_diff * 0.0010
    )

    strikeout = (
        0.210
        - contact_diff * 0.0010
    )

    quality_delta = (
        quality - 55
    )

    single -= (
        quality_delta * 0.00035
    )

    double -= (
        quality_delta * 0.00018
    )

    homerun -= (
        quality_delta * 0.00020
    )

    strikeout += (
        quality_delta * 0.0010
    )

    if fatigue < 1:

        single += (
            1 - fatigue
        ) * 0.03

        homerun += (
            1 - fatigue
        ) * 0.015

        walk += (
            1 - fatigue
        ) * 0.02

        strikeout -= (
            1 - fatigue
        ) * 0.03

    single = clamp(
        single,
        0.02,
        0.35,
    )

    double = clamp(
        double,
        0.005,
        0.15,
    )

    triple = clamp(
        triple,
        0.001,
        0.03,
    )

    homerun = clamp(
        homerun,
        0.003,
        0.12,
    )

    walk = clamp(
        walk,
        0.015,
        0.18,
    )

    strikeout = clamp(
        strikeout,
        0.05,
        0.40,
    )

    used = (
        single
        + double
        + triple
        + homerun
        + walk
        + strikeout
    )

    out = max(
        0.02,
        1 - used,
    )

    total = (
        single
        + double
        + triple
        + homerun
        + walk
        + strikeout
        + out
    )

    return [
        ("single", single / total),
        ("double", double / total),
        ("triple", triple / total),
        ("hr", homerun / total),
        ("walk", walk / total),
        ("so", strikeout / total),
        ("out", out / total),
    ]


def random_result(probabilities):

    r = random.random()

    total = 0

    for result, probability in probabilities:

        total += probability

        if r <= total:
            return result

    return "out"


# ============================================================
# 守備
# ============================================================

def choose_defender(defense):

    positions = [
        "1B",
        "2B",
        "3B",
        "SS",
        "LF",
        "CF",
        "RF",
    ]

    weights = [
        1.0,
        1.1,
        1.0,
        1.2,
        0.9,
        1.0,
        0.9,
    ]

    position = random.choices(
        positions,
        weights=weights,
        k=1,
    )[0]

    return (
        position,
        defense.get(position),
    )


def fielding_result(defense):

    position, defender = (
        choose_defender(defense)
    )

    if defender is None:
        return "out", None

    ability = defender.defense_at(
        position
    )

    catch_probability = (
        0.72
        + ability / 400
    )

    catch_probability = clamp(
        catch_probability,
        0.70,
        0.98,
    )

    if random.random() < catch_probability:

        defender.fielding.PO += 1

        defender.fielding.UZR += (
            ability - 60
        ) / 100

        return "out", defender

    defender.fielding.E += 1

    defender.fielding.UZR -= 0.8

    return "error", defender


# ============================================================
# 走者
# ============================================================

def advance_hit(
    bases,
    batter,
    result,
):

    new_bases = [
        None,
        None,
        None,
    ]

    runs = 0
    scorers = []

    # 本塁打
    if result == "hr":

        for runner in bases:

            if runner is not None:

                runs += 1
                scorers.append(
                    runner
                )

        runs += 1
        scorers.append(batter)

        return (
            new_bases,
            runs,
            scorers,
        )

    # 三塁打
    if result == "triple":

        for runner in bases:

            if runner is not None:

                runs += 1
                scorers.append(
                    runner
                )

        new_bases[2] = batter

        return (
            new_bases,
            runs,
            scorers,
        )

    # 二塁打
    if result == "double":

        if bases[2] is not None:

            runs += 1
            scorers.append(
                bases[2]
            )

        if bases[1] is not None:

            probability = (
                0.55
                + bases[1].speed / 300
            )

            if random.random() < clamp(
                probability,
                0.55,
                0.90,
            ):

                runs += 1
                scorers.append(
                    bases[1]
                )

            else:

                new_bases[2] = (
                    bases[1]
                )

        if bases[0] is not None:

            probability = (
                0.30
                + bases[0].speed / 250
            )

            if random.random() < clamp(
                probability,
                0.30,
                0.82,
            ):

                runs += 1
                scorers.append(
                    bases[0]
                )

            else:

                new_bases[2] = (
                    bases[0]
                )

        new_bases[1] = batter

        return (
            new_bases,
            runs,
            scorers,
        )

    # 単打
    if bases[2] is not None:

        runs += 1

        scorers.append(
            bases[2]
        )

    if bases[1] is not None:

        probability = (
            0.45
            + bases[1].speed / 250
        )

        if random.random() < clamp(
            probability,
            0.45,
            0.90,
        ):

            runs += 1

            scorers.append(
                bases[1]
            )

        else:

            new_bases[2] = (
                bases[1]
            )

    if bases[0] is not None:

        new_bases[1] = bases[0]

    new_bases[0] = batter

    return (
        new_bases,
        runs,
        scorers,
    )


def advance_walk(
    bases,
    batter,
):

    new_bases = list(bases)

    runs = 0
    scorers = []

    if all(
        x is not None
        for x in bases
    ):

        runs = 1

        scorers.append(
            bases[2]
        )

    if (
        bases[0] is not None
        and bases[1] is not None
    ):

        new_bases[2] = bases[1]

    if bases[0] is not None:

        new_bases[1] = bases[0]

    new_bases[0] = batter

    return (
        new_bases,
        runs,
        scorers,
    )


# ============================================================
# 盗塁
# ============================================================

def attempt_steal(bases):

    # 1塁走者
    runner = bases[0]

    if runner is None:
        return bases, False

    if runner.speed < 70:
        return bases, False

    steal_probability = (
        (runner.speed - 65)
        / 250
    )

    steal_probability = clamp(
        steal_probability,
        0.03,
        0.22,
    )

    if random.random() > steal_probability:
        return bases, False

    success_probability = (
        0.55
        + (runner.speed - 70)
        / 200
    )

    success_probability = clamp(
        success_probability,
        0.55,
        0.90,
    )

    if random.random() < success_probability:

        if bases[1] is None:

            bases[1] = runner
            bases[0] = None

            runner.batting.SB += 1

            return bases, True

    else:

        bases[0] = None

        runner.batting.CS += 1

        return bases, True

    return bases, False


# ============================================================
# セ・リーグ用投手打撃
# ============================================================

def pitcher_as_batter(pitcher):

    return Player(
        name=pitcher.name,
        team=pitcher.team,
        contact=25,
        power=15,
        speed=20,
    )


# ============================================================
# 1イニング
# ============================================================

def simulate_half_inning(
    offense,
    batting_index,
    pitcher,
    defense,
):

    outs = 0

    bases = [
        None,
        None,
        None,
    ]

    runs = 0

    while outs < 3:

        batter = offense[
            batting_index[0]
            % len(offense)
        ]

        batting_index[0] += 1

        batter.batting.PA += 1

        batter.batting.G += 1

        pitcher.pitching.BF += 1

        # 盗塁
        if (
            random.random() < 0.06
            and bases[0] is not None
        ):

            bases, attempted = (
                attempt_steal(bases)
            )

        probabilities = (
            batter_probabilities(
                batter,
                pitcher,
            )
        )

        result = random_result(
            probabilities
        )

        # ---------------------------------
        # ヒット
        # ---------------------------------

        if result in (
            "single",
            "double",
            "triple",
            "hr",
        ):

            batter.batting.AB += 1
            batter.batting.H += 1

            pitcher.pitching.H += 1

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

            (
                bases,
                scored,
                scorers,
            ) = advance_hit(
                bases,
                batter,
                result,
            )

            runs += scored

            batter.batting.RBI += scored

            for runner in scorers:

                runner.batting.R += 1

            if result == "hr":

                batter.batting.R += 1

        # ---------------------------------
        # 四球
        # ---------------------------------

        elif result == "walk":

            batter.batting.BB += 1

            pitcher.pitching.BB += 1

            (
                bases,
                scored,
                scorers,
            ) = advance_walk(
                bases,
                batter,
            )

            runs += scored

            batter.batting.RBI += scored

            for runner in scorers:

                runner.batting.R += 1

        # ---------------------------------
        # 三振
        # ---------------------------------

        elif result == "so":

            batter.batting.AB += 1

            batter.batting.SO += 1

            pitcher.pitching.SO += 1

            outs += 1

            pitcher.pitching.outs += 1

        # ---------------------------------
        # アウト
        # ---------------------------------

        else:

            batter.batting.AB += 1

            outcome, defender = (
                fielding_result(
                    defense
                )
            )

            if outcome == "out":

                outs += 1

                pitcher.pitching.outs += 1

                if defender is not None:

                    defender.fielding.A += 1

            else:

                # エラーで出塁
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

    return runs


# ============================================================
# 投手起用
# ============================================================

class PitchingState:

    def __init__(
        self,
        staff,
        game_number,
    ):

        self.starters = staff[
            "starters"
        ]

        self.bullpen = staff[
            "bullpen"
        ]

        self.closer = staff[
            "closer"
        ]

        self.current = (
            self.choose_starter(
                game_number
            )
        )

        self.used = set()

        self.runs = defaultdict(int)

        self.entry_inning = 1

    def choose_starter(
        self,
        game_number,
    ):

        if not self.starters:
            return None

        return self.starters[
            game_number
            % len(self.starters)
        ]

    def replace(
        self,
        inning,
        score_difference,
    ):

        current = self.current

        if current is None:
            return None

        # 先発
        if current in self.starters:

            if (
                current.pitching.outs
                >= 18
            ):

                available = [
                    p
                    for p in self.bullpen
                    if p not in self.used
                ]

                if (
                    inning >= 8
                    and self.closer
                    and self.closer
                    not in self.used
                    and score_difference > 0
                ):

                    new_pitcher = (
                        self.closer
                    )

                elif available:

                    new_pitcher = (
                        available[0]
                    )

                else:

                    return current

            elif (
                self.runs[current]
                >= 5
            ):

                available = [
                    p
                    for p in self.bullpen
                    if p not in self.used
                ]

                if available:

                    new_pitcher = (
                        available[0]
                    )

                else:

                    return current

            else:

                return current

        elif current in self.bullpen:

            if (
                inning >= 9
                and self.closer
                and self.closer
                not in self.used
                and score_difference > 0
            ):

                new_pitcher = (
                    self.closer
                )

            else:

                available = [
                    p
                    for p in self.bullpen
                    if p not in self.used
                ]

                if available:

                    new_pitcher = (
                        available[0]
                    )

                else:

                    return current

        else:

            return current

        self.used.add(
            new_pitcher
        )

        new_pitcher.pitching.G += 1

        self.current = new_pitcher

        return new_pitcher


# ============================================================
# 1試合
# ============================================================

def simulate_game(
    my_lineup,
    my_staff,
    opponent_lineup,
    opponent_staff,
    league,
    game_number,
):

    my_pitching = PitchingState(
        my_staff,
        game_number,
    )

    opponent_pitching = PitchingState(
        opponent_staff,
        game_number,
    )

    my_pitcher = (
        my_pitching.current
    )

    opponent_pitcher = (
        opponent_pitching.current
    )

    if (
        my_pitcher is None
        or opponent_pitcher is None
    ):
        return 0, 0

    my_pitcher.pitching.G += 1
    my_pitcher.pitching.GS += 1

    opponent_pitcher.pitching.G += 1
    opponent_pitcher.pitching.GS += 1

    # -------------------------------------
    # 打線
    # -------------------------------------

    my_batting = [
        p
        for p, pos
        in my_lineup
    ]

    opponent_batting = [
        p
        for p, pos
        in opponent_lineup
    ]

    if league == "セ・リーグ":

        my_batting.append(
            pitcher_as_batter(
                my_pitcher
            )
        )

        opponent_batting.append(
            pitcher_as_batter(
                opponent_pitcher
            )
        )

    my_index = [0]
    opponent_index = [0]

    my_score = 0
    opponent_score = 0

    # -------------------------------------
    # 9回
    # -------------------------------------

    for inning in range(1, 10):

        # ---------------------------------
        # 表
        # ---------------------------------

        if (
            my_pitching.runs[
                my_pitcher
            ] >= 4
            or (
                inning >= 7
                and my_pitcher
                in my_pitching.starters
                and my_pitcher.pitching.outs
                >= 21
            )
        ):

            my_pitcher = (
                my_pitching.replace(
                    inning,
                    my_score
                    - opponent_score,
                )
            )

        my_defense = {
            position: player
            for player, position
            in my_lineup
            if position != "DH"
        }

        runs = (
            simulate_half_inning(
                opponent_batting,
                opponent_index,
                my_pitcher,
                my_defense,
            )
        )

        opponent_score += runs

        my_pitching.runs[
            my_pitcher
        ] += runs

        my_pitcher.pitching.R += runs
        my_pitcher.pitching.ER += runs

        # ---------------------------------
        # 裏
        # ---------------------------------

        if (
            opponent_pitching.runs[
                opponent_pitcher
            ] >= 4
            or (
                inning >= 7
                and opponent_pitcher
                in opponent_pitching.starters
                and opponent_pitcher.pitching.outs
                >= 21
            )
        ):

            opponent_pitcher = (
                opponent_pitching.replace(
                    inning,
                    opponent_score
                    - my_score,
                )
            )

        opponent_defense = {
            position: player
            for player, position
            in opponent_lineup
            if position != "DH"
        }

        runs = (
            simulate_half_inning(
                my_batting,
                my_index,
                opponent_pitcher,
                opponent_defense,
            )
        )

        my_score += runs

        opponent_pitching.runs[
            opponent_pitcher
        ] += runs

        opponent_pitcher.pitching.R += runs
        opponent_pitcher.pitching.ER += runs

        # 9回終了時に決着
        if (
            inning >= 9
            and my_score != opponent_score
        ):
            break

    # -------------------------------------
    # 勝敗
    # -------------------------------------

    if my_score > opponent_score:

        # 勝利投手
        my_pitcher.pitching.W += 1

    elif my_score < opponent_score:

        my_pitcher.pitching.L += 1

    return (
        my_score,
        opponent_score,
    )


# ============================================================
# 成績計算
# ============================================================

def batting_average(player):

    if player.batting.AB == 0:
        return 0

    return (
        player.batting.H
        / player.batting.AB
    )


def obp(player):

    denominator = (
        player.batting.AB
        + player.batting.BB
        + player.batting.SF
    )

    if denominator == 0:
        return 0

    return (
        player.batting.H
        + player.batting.BB
    ) / denominator


def slg(player):

    if player.batting.AB == 0:
        return 0

    return (
        player.batting.TB
        / player.batting.AB
    )


def ops(player):

    return (
        obp(player)
        + slg(player)
    )


def era(player):

    if player.pitching.outs == 0:
        return 0

    return (
        player.pitching.ER
        * 27
        / player.pitching.outs
    )


def innings_string(outs):

    return (
        f"{outs // 3}."
        f"{outs % 3}"
    )


# ============================================================
# ドラフト
# ============================================================

def player_card(player):

    if player.is_pitcher():

        return {
            "選手名": player.name,
            "チーム": player.team,
            "制球": player.control,
            "スタミナ": player.stamina,
            "球種": " / ".join(
                f"{name}:{rank}"
                for name, rank
                in player.pitches.items()
            ),
        }

    return {
        "選手名": player.name,
        "チーム": player.team,
        "ミート": player.contact,
        "パワー": player.power,
        "走力": player.speed,
        "守備": " / ".join(
            f"{pos}:{value:g}"
            for pos, value
            in player.defense.items()
        ),
    }


def draft_page(
    kind,
    all_players,
    target_count,
    skip_limit=None,
):

    if kind == "野手":

        selected_key = (
            "draft_fielders"
        )

        pool_key = (
            "fielder_pool"
        )

        skip_key = (
            "fielder_skips"
        )

    else:

        selected_key = (
            "draft_pitchers"
        )

        pool_key = (
            "pitcher_pool"
        )

        skip_key = (
            "pitcher_skips"
        )

    if selected_key not in st.session_state:

        st.session_state[
            selected_key
        ] = []

    if pool_key not in st.session_state:

        st.session_state[
            pool_key
        ] = list(all_players)

    if skip_key not in st.session_state:

        st.session_state[
            skip_key
        ] = 0

    selected = st.session_state[
        selected_key
    ]

    pool = st.session_state[
        pool_key
    ]

    # ---------------------------------
    # 候補選手を固定
    # ---------------------------------

    candidate_key = (
        f"{kind}_candidate"
    )

    if candidate_key not in st.session_state:

        st.session_state[
            candidate_key
        ] = random.choice(pool)

    candidate = st.session_state[
        candidate_key
    ]

    st.header(
        f"ドラフト：{kind}"
    )

    st.write(
        f"獲得：{len(selected)} / "
        f"{target_count}"
    )

    if skip_limit is not None:

        st.write(
            f"見送り："
            f"{st.session_state[skip_key]}"
            f" / {skip_limit}"
        )

    st.subheader(
        f"出現選手：{candidate.name}"
    )

    st.dataframe(
        pd.DataFrame([
            player_card(candidate)
        ]),
        hide_index=True,
        use_container_width=True,
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "✅ 取る",
            type="primary",
            use_container_width=True,
        ):

            selected.append(
                candidate
            )

            if candidate in pool:

                pool.remove(
                    candidate
                )

            del st.session_state[
                candidate_key
            ]

            st.rerun()

    with col2:

        skip_disabled = (
            skip_limit is not None
            and st.session_state[
                skip_key
            ] >= skip_limit
        )

        if st.button(
            "❌ 見送る",
            disabled=skip_disabled,
            use_container_width=True,
        ):

            if candidate in pool:

                pool.remove(
                    candidate
                )

            st.session_state[
                skip_key
            ] += 1

            del st.session_state[
                candidate_key
            ]

            st.rerun()

    st.divider()

    if selected:

        st.subheader(
            "現在の獲得選手"
        )

        st.dataframe(
            pd.DataFrame([
                player_card(p)
                for p in selected
            ]),
            hide_index=True,
            use_container_width=True,
        )

    if len(selected) >= target_count:

        return True

    return False


# ============================================================
# オーダー設定
# ============================================================

def order_page(
    fielders,
    league,
):

    st.header(
        "④ 守備位置・打順設定"
    )

    st.write(
        f"リーグ：**{league}**"
    )

    st.subheader(
        "守備位置"
    )

    lineup = []

    used = set()

    # ------------------------------
    # 守備位置
    # ------------------------------

    for position in POSITIONS:

        available = [
            p
            for p in fielders
            if p.name not in used
        ]

        available.sort(
            key=lambda p: (
                p.defense_at(position),
                offense_score(p),
            ),
            reverse=True,
        )

        names = [
            p.name
            for p in available
        ]

        selected_name = st.selectbox(
            POSITION_JP[position],
            names,
            key=f"pos_{position}",
        )

        player = next(
            p
            for p in available
            if p.name == selected_name
        )

        lineup.append(
            (player, position)
        )

        used.add(
            player.name
        )

        st.caption(
            f"{player.name}　"
            f"{position}守備力："
            f"{player.defense_at(position):.0f}"
        )

    # ------------------------------
    # DH / ベンチ
    # ------------------------------

    remaining = [
        p
        for p in fielders
        if p.name not in used
    ]

    if league == "パ・リーグ":

        if not remaining:

            st.error(
                "DHに入れる野手がいません。"
            )

            return None

        dh_name = st.selectbox(
            "DH",
            [
                p.name
                for p in remaining
            ],
            key="dh_select",
        )

        dh = next(
            p
            for p in remaining
            if p.name == dh_name
        )

        lineup.append(
            (dh, "DH")
        )

        bench = None

    else:

        bench = (
            remaining[0]
            if remaining
            else None
        )

        if bench:

            st.info(
                f"代打要員：{bench.name}"
            )

    # ------------------------------
    # 打順
    # ------------------------------

    st.subheader(
        "打順"
    )

    # セは8人＋投手を後で追加
    batting_players = list(
        lineup
    )

    batting_players.sort(
        key=lambda x: offense_score(
            x[0]
        ),
        reverse=True,
    )

    ordered = []

    for i in range(
        len(batting_players)
    ):

        remaining_pairs = [
            pair
            for pair in batting_players
            if pair[0].name
            not in [
                x[0].name
                for x in ordered
            ]
        ]

        names = [
            p.name
            for p, pos
            in remaining_pairs
        ]

        selected = st.selectbox(
            f"{i + 1}番",
            names,
            key=f"order_{i}",
        )

        pair = next(
            pair
            for pair in remaining_pairs
            if pair[0].name == selected
        )

        ordered.append(pair)

    if st.button(
        "オーダー決定",
        type="primary",
    ):

        return {
            "lineup": ordered,
            "bench": bench,
        }

    return None


# ============================================================
# 投手起用
# ============================================================

def pitching_page(
    pitchers
):

    st.header(
        "⑤ 投手起用設定"
    )

    names = [
        p.name
        for p in pitchers
    ]

    if len(names) < 9:

        st.error(
            "投手が9人未満です。"
            "先発5・中継ぎ3・抑え1を設定できません。"
        )

        return None

    starters = []

    st.subheader(
        "先発5人"
    )

    available_names = list(names)

    for i in range(5):

        selected = st.selectbox(
            f"先発{i + 1}",
            available_names,
            key=f"starter_{i}",
        )

        starters.append(
            next(
                p
                for p in pitchers
                if p.name == selected
            )
        )

        available_names.remove(
            selected
        )

    bullpen = []

    st.subheader(
        "中継ぎ3人"
    )

    for i in range(3):

        selected = st.selectbox(
            f"中継ぎ{i + 1}",
            available_names,
            key=f"bullpen_{i}",
        )

        bullpen.append(
            next(
                p
                for p in pitchers
                if p.name == selected
            )
        )

        available_names.remove(
            selected
        )

    st.subheader(
        "抑え"
    )

    closer_name = st.selectbox(
        "抑え",
        available_names,
        key="closer",
    )

    closer = next(
        p
        for p in pitchers
        if p.name == closer_name
    )

    if st.button(
        "投手起用決定",
        type="primary",
    ):

        return {
            "starters": starters,
            "bullpen": bullpen,
            "closer": closer,
        }

    return None


# ============================================================
# スケジュール
# ============================================================

def create_schedule(
    same_teams,
    inter_teams,
):

    schedule = []

    # 同リーグ
    for team in same_teams:

        for _ in range(25):

            schedule.append({
                "opponent": team,
                "type": "league",
            })

    # 交流戦
    for team in inter_teams:

        for _ in range(3):

            schedule.append({
                "opponent": team,
                "type": "interleague",
            })

    random.shuffle(
        schedule
    )

    return schedule


# ============================================================
# セッション初期化
# ============================================================

def initialize():

    defaults = {

        "step": "league_setup",

        "central": [],
        "pacific": [],

        "draft_fielders": [],
        "draft_pitchers": [],

        "fielder_pool": None,
        "pitcher_pool": None,

        "fielder_skips": 0,
        "pitcher_skips": 0,

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[
                key
            ] = value


# ============================================================
# データ読み込み
# ============================================================

st.title(
    "⚾ 野球チームメーカー"
)

st.caption(
    "ランダムに選手を獲得して24人のチームを作り、"
    "143試合をシミュレーションします。"
)

try:

    fielders_all, pitchers_all = (
        load_data()
    )

except FileNotFoundError as e:

    st.error(
        "Excelファイルが見つかりません。"
    )

    st.code(
        f"{FIELDER_FILE}\n"
        f"{PITCHER_FILE}"
    )

    st.info(
        "app.py と同じGitHubリポジトリの"
        "同じ階層に2つのExcelファイルを置いてください。"
    )

    st.stop()

except Exception as e:

    st.error(
        f"Excel読み込みエラー：{e}"
    )

    st.stop()


initialize()


teams = build_teams(
    fielders_all,
    pitchers_all,
)

team_names = sorted(
    teams.keys()
)


# ============================================================
# ① リーグ設定
# ============================================================

if st.session_state.step == "league_setup":

    st.header(
        "① リーグ設定"
    )

    st.write(
        "Excelにはリーグ情報がないため、"
        "ここで12球団をセ・パに分けます。"
    )

    st.write(
        f"読み込み球団数："
        f"**{len(team_names)}球団**"
    )

    if len(team_names) != 12:

        st.warning(
            "現在12球団ではありません。"
            "12球団ある場合はセ6球団・パ6球団になります。"
        )

    st.subheader(
        "セ・リーグ"
    )

    default_central = (
        team_names[:6]
        if len(team_names) >= 6
        else team_names
    )

    central = st.multiselect(
        "セ・リーグ6球団",
        team_names,
        default=default_central,
        max_selections=6,
    )

    pacific = [
        team
        for team in team_names
        if team not in central
    ]

    st.subheader(
        "パ・リーグ"
    )

    st.write(
        " / ".join(pacific)
    )

    if st.button(
        "リーグ設定決定",
        type="primary",
    ):

        if len(central) != 6:

            st.error(
                "セ・リーグを6球団にしてください。"
            )

        elif len(pacific) != 6:

            st.error(
                "パ・リーグを6球団にしてください。"
            )

        else:

            st.session_state.central = (
                central
            )

            st.session_state.pacific = (
                pacific
            )

            st.session_state.step = (
                "draft_fielders"
            )

            st.rerun()


# ============================================================
# ② 野手ドラフト
# ============================================================

elif (
    st.session_state.step
    == "draft_fielders"
):

    finished = draft_page(
        "野手",
        fielders_all,
        9,
        skip_limit=5,
    )

    if finished:

        st.session_state.step = (
            "draft_pitchers"
        )

        st.rerun()


# ============================================================
# ③ 投手ドラフト
# ============================================================

elif (
    st.session_state.step
    == "draft_pitchers"
):

    finished = draft_page(
        "投手",
        pitchers_all,
        15,
        skip_limit=None,
    )

    if finished:

        st.session_state.step = (
            "league_select"
        )

        st.rerun()


# ============================================================
# ④ セ・パ選択
# ============================================================

elif (
    st.session_state.step
    == "league_select"
):

    st.header(
        "④ セ・パ選択"
    )

    league = st.radio(
        "あなたのチームの所属リーグ",
        [
            "セ・リーグ",
            "パ・リーグ",
        ],
    )

    if league == "セ・リーグ":

        st.info(
            "DHなし。8人の野手＋投手が9番を打ちます。"
        )

    else:

        st.info(
            "DHあり。9人の野手で打線を組みます。"
        )

    if st.button(
        "リーグ決定",
        type="primary",
    ):

        st.session_state.my_league = (
            league
        )

        st.session_state.step = (
            "order"
        )

        st.rerun()


# ============================================================
# ⑤ オーダー
# ============================================================

elif (
    st.session_state.step
    == "order"
):

    result = order_page(
        st.session_state.draft_fielders,
        st.session_state.my_league,
    )

    if result:

        st.session_state.my_lineup = (
            result["lineup"]
        )

        st.session_state.my_bench = (
            result["bench"]
        )

        st.session_state.step = (
            "pitching"
        )

        st.rerun()


# ============================================================
# ⑥ 投手起用
# ============================================================

elif (
    st.session_state.step
    == "pitching"
):

    result = pitching_page(
        st.session_state.draft_pitchers
    )

    if result:

        st.session_state.my_staff = (
            result
        )

        st.session_state.step = (
            "ready"
        )

        st.rerun()


# ============================================================
# ⑦ 開幕前確認
# ============================================================

elif (
    st.session_state.step
    == "ready"
):

    st.header(
        "⑦ 開幕前確認"
    )

    league = (
        st.session_state.my_league
    )

    st.write(
        f"所属リーグ：**{league}**"
    )

    # ---------------------------------
    # 打線
    # ---------------------------------

    st.subheader(
        "打順"
    )

    lineup_rows = []

    for i, (player, position) in enumerate(
        st.session_state.my_lineup,
        start=1,
    ):

        lineup_rows.append({
            "打順": i,
            "選手": player.name,
            "守備": POSITION_JP.get(
                position,
                position,
            ),
            "ミート": player.contact,
            "パワー": player.power,
            "走力": player.speed,
            "守備力": player.defense_at(
                position
            ),
        })

    if league == "セ・リーグ":

        lineup_rows.append({
            "打順": 9,
            "選手": "投手",
            "守備": "投手",
            "ミート": "-",
            "パワー": "-",
            "走力": "-",
            "守備力": "-",
        })

    st.dataframe(
        pd.DataFrame(lineup_rows),
        hide_index=True,
        use_container_width=True,
    )

    if st.session_state.my_bench:

        st.write(
            "代打："
            f"**{st.session_state.my_bench.name}**"
        )

    # ---------------------------------
    # 投手
    # ---------------------------------

    st.subheader(
        "投手陣"
    )

    rows = []

    staff = (
        st.session_state.my_staff
    )

    for i, pitcher in enumerate(
        staff["starters"],
        start=1,
    ):

        rows.append({
            "役割": f"先発{i}",
            "選手": pitcher.name,
            "制球": pitcher.control,
            "スタミナ": pitcher.stamina,
            "球種": " / ".join(
                f"{name}:{rank}"
                for name, rank
                in pitcher.pitches.items()
            ),
        })

    for i, pitcher in enumerate(
        staff["bullpen"],
        start=1,
    ):

        rows.append({
            "役割": f"中継ぎ{i}",
            "選手": pitcher.name,
            "制球": pitcher.control,
            "スタミナ": pitcher.stamina,
            "球種": " / ".join(
                f"{name}:{rank}"
                for name, rank
                in pitcher.pitches.items()
            ),
        })

    closer = staff["closer"]

    rows.append({
        "役割": "抑え",
        "選手": closer.name,
        "制球": closer.control,
        "スタミナ": closer.stamina,
        "球種": " / ".join(
            f"{name}:{rank}"
            for name, rank
            in closer.pitches.items()
        ),
    })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
    )

    # ---------------------------------
    # 対戦相手
    # ---------------------------------

    st.subheader(
        "143試合スケジュール"
    )

    if league == "セ・リーグ":

        same_pool = [
            team
            for team in st.session_state.central
        ]

        inter_pool = [
            team
            for team in st.session_state.pacific
        ]

    else:

        same_pool = [
            team
            for team in st.session_state.pacific
        ]

        inter_pool = [
            team
            for team in st.session_state.central
        ]

    same_teams = random.sample(
        same_pool,
        5,
    )

    inter_teams = random.sample(
        inter_pool,
        6,
    )

    schedule = create_schedule(
        same_teams,
        inter_teams,
    )

    st.session_state.schedule = (
        schedule
    )

    st.write(
        "同リーグ："
        f"{len(same_teams)}球団 × 25試合 "
        f"＝ {len(same_teams) * 25}試合"
    )

    st.write(
        "交流戦："
        f"{len(inter_teams)}球団 × 3試合 "
        f"＝ {len(inter_teams) * 3}試合"
    )

    st.write(
        f"合計：**{len(schedule)}試合**"
    )

    if st.button(
        "⚾ シーズン開始",
        type="primary",
        use_container_width=True,
    ):

        st.session_state.step = (
            "season"
        )

        st.rerun()


# ============================================================
# ⑧ 143試合シミュレーション
# ============================================================

elif (
    st.session_state.step
    == "season"
):

    st.header(
        "⑧ 143試合シミュレーション"
    )

    # 成績を初期化
    reset_stats(
        st.session_state.draft_fielders
        + st.session_state.draft_pitchers
    )

    league = (
        st.session_state.my_league
    )

    my_lineup = (
        st.session_state.my_lineup
    )

    my_staff = (
        st.session_state.my_staff
    )

    schedule = (
        st.session_state.schedule
    )

    wins = 0
    losses = 0
    draws = 0

    runs_for = 0
    runs_against = 0

    game_log = []

    progress = st.progress(0)

    status = st.empty()

    for game_number, game in enumerate(
        schedule,
        start=1,
    ):

        opponent_name = (
            game["opponent"]
        )

        opponent_team = teams[
            opponent_name
        ]

        opponent_lineup = (
            make_opponent_lineup(
                opponent_team,
                dh=(
                    league
                    == "パ・リーグ"
                ),
            )
        )

        opponent_staff = (
            make_opponent_staff(
                opponent_team
            )
        )

        score_for, score_against = (
            simulate_game(
                my_lineup,
                my_staff,
                opponent_lineup,
                opponent_staff,
                league,
                game_number - 1,
            )
        )

        runs_for += score_for
        runs_against += score_against

        if score_for > score_against:

            result = "○"
            wins += 1

        elif score_for < score_against:

            result = "●"
            losses += 1

        else:

            result = "△"
            draws += 1

        game_log.append({
            "試合": game_number,
            "対戦相手": opponent_name,
            "区分": (
                "同リーグ"
                if game["type"] == "league"
                else "交流戦"
            ),
            "得点": score_for,
            "失点": score_against,
            "結果": result,
        })

        progress.progress(
            game_number / 143
        )

        status.write(
            f"{game_number}/143試合　"
            f"{opponent_name}　"
            f"{score_for}-{score_against}"
        )

    st.session_state.season_result = {

        "wins": wins,
        "losses": losses,
        "draws": draws,

        "runs_for": runs_for,
        "runs_against": runs_against,

        "game_log": game_log,
    }

    st.session_state.step = (
        "result"
    )

    st.rerun()


# ============================================================
# ⑨ シーズン結果
# ============================================================

elif (
    st.session_state.step
    == "result"
):

    result = (
        st.session_state.season_result
    )

    st.header(
        "🏆 シーズン終了"
    )

    wins = result["wins"]
    losses = result["losses"]
    draws = result["draws"]

    runs_for = (
        result["runs_for"]
    )

    runs_against = (
        result["runs_against"]
    )

    win_pct = (
        wins
        / (wins + losses)
        if wins + losses
        else 0
    )

    # ---------------------------------
    # チーム成績
    # ---------------------------------

    c1, c2, c3, c4, c5 = (
        st.columns(5)
    )

    c1.metric(
        "勝",
        wins,
    )

    c2.metric(
        "敗",
        losses,
    )

    c3.metric(
        "引分",
        draws,
    )

    c4.metric(
        "勝率",
        f"{win_pct:.3f}",
    )

    c5.metric(
        "得失点差",
        runs_for - runs_against,
    )

    st.subheader(
        "チーム成績"
    )

    batters = (
        st.session_state.draft_fielders
    )

    pitchers = (
        st.session_state.draft_pitchers
    )

    total_ab = sum(
        p.batting.AB
        for p in batters
    )

    total_hits = sum(
        p.batting.H
        for p in batters
    )

    total_outs = sum(
        p.pitching.outs
        for p in pitchers
    )

    total_er = sum(
        p.pitching.ER
        for p in pitchers
    )

    team_average = (
        total_hits / total_ab
        if total_ab
        else 0
    )

    team_era = (
        total_er * 27 / total_outs
        if total_outs
        else 0
    )

    st.write(
        f"得点：**{runs_for}**"
    )

    st.write(
        f"失点：**{runs_against}**"
    )

    st.write(
        f"得失点差："
        f"**{runs_for - runs_against}**"
    )

    st.write(
        f"チーム打率："
        f"**{team_average:.3f}**"
    )

    st.write(
        f"チーム防御率："
        f"**{team_era:.2f}**"
    )

    # ---------------------------------
    # 打者成績
    # ---------------------------------

    st.subheader(
        "打者個人成績"
    )

    batting_rows = []

    for player in batters:

        batting_rows.append({

            "選手": player.name,

            "試合": player.batting.G,

            "打席": player.batting.PA,

            "打数": player.batting.AB,

            "打率": round(
                batting_average(player),
                3,
            ),

            "安打": player.batting.H,

            "二塁打": (
                player.batting.double
            ),

            "三塁打": (
                player.batting.triple
            ),

            "本塁打": (
                player.batting.HR
            ),

            "打点": (
                player.batting.RBI
            ),

            "得点": (
                player.batting.R
            ),

            "四球": (
                player.batting.BB
            ),

            "三振": (
                player.batting.SO
            ),

            "盗塁": (
                player.batting.SB
            ),

            "盗塁死": (
                player.batting.CS
            ),

            "OPS": round(
                ops(player),
                3,
            ),

        })

    batting_df = pd.DataFrame(
        batting_rows
    )

    st.dataframe(
        batting_df,
        hide_index=True,
        use_container_width=True,
    )

    # ---------------------------------
    # 投手成績
    # ---------------------------------

    st.subheader(
        "投手個人成績"
    )

    pitching_rows = []

    for player in pitchers:

        pitching_rows.append({

            "選手": player.name,

            "試合": (
                player.pitching.G
            ),

            "先発": (
                player.pitching.GS
            ),

            "投球回": innings_string(
                player.pitching.outs
            ),

            "防御率": round(
                era(player),
                2,
            ),

            "勝": (
                player.pitching.W
            ),

            "敗": (
                player.pitching.L
            ),

            "H": (
                player.pitching.H
            ),

            "奪三振": (
                player.pitching.SO
            ),

            "四球": (
                player.pitching.BB
            ),

            "自責点": (
                player.pitching.ER
            ),

            "HLD": (
                player.pitching.HLD
            ),

            "S": (
                player.pitching.SV
            ),

        })

    pitching_df = pd.DataFrame(
        pitching_rows
    )

    st.dataframe(
        pitching_df,
        hide_index=True,
        use_container_width=True,
    )

    # ---------------------------------
    # 守備
    # ---------------------------------

    st.subheader(
        "守備成績 / 簡易UZR"
    )

    fielding_rows = []

    for player in batters:

        fielding_rows.append({

            "選手": player.name,

            "刺殺": (
                player.fielding.PO
            ),

            "補殺": (
                player.fielding.A
            ),

            "失策": (
                player.fielding.E
            ),

            "UZR": round(
                player.fielding.UZR,
                2,
            ),

        })

    fielding_df = pd.DataFrame(
        fielding_rows
    )

    st.dataframe(
        fielding_df,
        hide_index=True,
        use_container_width=True,
    )

    # ---------------------------------
    # 試合結果
    # ---------------------------------

    st.subheader(
        "143試合 全試合結果"
    )

    log_df = pd.DataFrame(
        result["game_log"]
    )

    st.dataframe(
        log_df,
        hide_index=True,
        use_container_width=True,
        height=500,
    )

    # ---------------------------------
    # CSV
    # ---------------------------------

    st.download_button(
        "打者成績CSV",
        batting_df.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=(
            "打者成績.csv"
        ),
        mime="text/csv",
    )

    st.download_button(
        "投手成績CSV",
        pitching_df.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=(
            "投手成績.csv"
        ),
        mime="text/csv",
    )

    st.download_button(
        "試合結果CSV",
        log_df.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name=(
            "試合結果.csv"
        ),
        mime="text/csv",
    )

    st.divider()

    if st.button(
        "🔄 最初からやり直す"
    ):

        st.session_state.clear()

        st.rerun()
