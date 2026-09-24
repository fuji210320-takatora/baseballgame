import streamlit as st
import pandas as pd
import random
from dataclasses import dataclass, field
from collections import defaultdict

# ============================================================
# 0. 基本設定・シミュレーション用クラスと関数
# ============================================================
SEASON_GAMES = 143
MAX_INNINGS = 12

CHANGE_LEVEL = {
    "S": 100,
    "A": 85,
    "B": 70,
    "C": 55,
    "D": 40,
    "E": 25,
}

def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

def weighted_choice(items):
    total = sum(weight for _, weight in items)
    if total <= 0:
        return items[-1][0]
    r = random.uniform(0, total)
    current = 0
    for item, weight in items:
        current += weight
        if r <= current:
            return item
    return items[-1][0]

@dataclass
class Batter:
    name: str
    team_name: str
    contact: int
    power: int
    speed: int
    defense: int
    position: str = "捕手"
    stats: dict = field(default_factory=lambda: defaultdict(int))

    def reset_stats(self):
        self.stats = defaultdict(int)

@dataclass
class Pitcher:
    name: str
    team_name: str
    control: int
    stamina: int
    breaking_balls: dict
    pitcher_role: str = "先発"
    stats: dict = field(default_factory=lambda: defaultdict(float))

    def reset_stats(self):
        self.stats = defaultdict(float)

@dataclass
class Team:
    name: str
    batters: list
    pitchers: list
    wins: int = 0
    losses: int = 0
    draws: int = 0
    runs_for: int = 0
    runs_against: int = 0

    def reset_stats(self):
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.runs_for = 0
        self.runs_against = 0
        for batter in self.batters:
            batter.reset_stats()
        for pitcher in self.pitchers:
            pitcher.reset_stats()

def breaking_ball_value(pitcher):
    if not pitcher.breaking_balls:
        return 25
    values = []
    for rank in pitcher.breaking_balls.values():
        if rank in CHANGE_LEVEL:
            values.append(CHANGE_LEVEL[rank])
    if not values:
        return 25
    average = sum(values) / len(values)
    variety_bonus = min(len(values) - 1, 3) * 3
    return clamp(average + variety_bonus, 25, 100)

def pitcher_strength(pitcher):
    breaking = breaking_ball_value(pitcher)
    return pitcher.control * 0.55 + breaking * 0.45

def pitcher_fatigue_factor(pitcher):
    innings = pitcher.stats["outs_recorded"] / 3
    fatigue_start = 3.5 + pitcher.stamina / 20
    if innings <= fatigue_start:
        return 1.0
    fatigue = (innings - fatigue_start) * 0.04
    return clamp(1.0 - fatigue, 0.70, 1.0)

def should_replace_pitcher(pitcher):
    innings = pitcher.stats["outs_recorded"] / 3
    factor = pitcher_fatigue_factor(pitcher)
    if factor <= 0.82:
        return True
    if pitcher.stamina <= 40 and innings >= 5:
        return True
    if pitcher.stamina <= 60 and innings >= 7:
        return True
    return False

def choose_reliever(team, current_pitcher):
    available = [p for p in team.pitchers if p is not current_pitcher]
    if not available:
        return current_pitcher
    available.sort(key=lambda p: p.stats["outs_recorded"])
    return available[0]

def plate_appearance_result(batter, pitcher):
    fatigue = pitcher_fatigue_factor(pitcher)
    effective_control = pitcher.control * fatigue
    effective_breaking = breaking_ball_value(pitcher) * fatigue

    contact_match = batter.contact - effective_control
    power_match = batter.power - (effective_control * 0.5 + effective_breaking * 0.5)

    strikeout = 22
    walk = 8
    single = 15
    double = 5
    triple = 1
    homerun = 3
    out = 46

    strikeout -= contact_match * 0.20
    single += contact_match * 0.12
    out -= contact_match * 0.15

    homerun += power_match * 0.10
    double += power_match * 0.08
    walk += (50 - effective_control) * 0.12
    strikeout += (effective_breaking - 50) * 0.12
    triple += (batter.speed - 50) * 0.025

    strikeout = max(3, strikeout)
    walk = max(2, walk)
    single = max(5, single)
    double = max(1, double)
    triple = max(0.2, triple)
    homerun = max(0.3, homerun)
    out = max(10, out)

    return weighted_choice([
        ("strikeout", strikeout),
        ("walk", walk),
        ("single", single),
        ("double", double),
        ("triple", triple),
        ("homerun", homerun),
        ("out", out),
    ])

@dataclass
class Runner:
    batter: Batter
    reached_by_hit: bool = False
    reached_by_error: bool = False
    reached_by_walk: bool = False

def give_rbi(batter, amount=1):
    batter.stats["rbi"] += amount

def advance_all_runners(state, bases):
    old = state["bases"][:]
    state["bases"] = [None, None, None]
    for i in range(2, -1, -1):
        runner = old[i]
        if runner is None:
            continue
        destination = i + bases
        if destination >= 3:
            state["runs"] += 1
            runner.batter.stats["runs"] += 1
            state["scored_runners"].append(runner)
        else:
            state["bases"][destination] = runner

def handle_walk(state, batter):
    batter.stats["walks"] += 1
    runner = Runner(batter=batter, reached_by_walk=True)
    if state["bases"][0] is not None and state["bases"][1] is not None and state["bases"][2] is not None:
        forced_runner = state["bases"][2]
        state["runs"] += 1
        forced_runner.batter.stats["runs"] += 1
        give_rbi(batter)
        state["bases"][2] = state["bases"][1]
        state["bases"][1] = state["bases"][0]
        state["bases"][0] = runner
        state["scored_runners"].append(forced_runner)
    elif state["bases"][0] is not None:
        if state["bases"][1] is not None:
            state["bases"][2] = state["bases"][1]
        state["bases"][1] = state["bases"][0]
        state["bases"][0] = runner
    else:
        state["bases"][0] = runner

def handle_hit(state, batter, result):
    if result == "single":
        advance_all_runners(state, 1)
        state["bases"][0] = Runner(batter=batter, reached_by_hit=True)
        batter.stats["hits"] += 1
        batter.stats["singles"] += 1
    elif result == "double":
        advance_all_runners(state, 2)
        state["bases"][1] = Runner(batter=batter, reached_by_hit=True)
        batter.stats["hits"] += 1
        batter.stats["doubles"] += 1
    elif result == "triple":
        advance_all_runners(state, 3)
        state["bases"][2] = Runner(batter=batter, reached_by_hit=True)
        batter.stats["hits"] += 1
        batter.stats["triples"] += 1
    elif result == "homerun":
        runners = [runner for runner in state["bases"] if runner is not None]
        for runner in runners:
            state["runs"] += 1
            runner.batter.stats["runs"] += 1
        state["runs"] += 1
        batter.stats["runs"] += 1
        give_rbi(batter, len(runners) + 1)
        batter.stats["hits"] += 1
        batter.stats["homeruns"] += 1
        state["bases"] = [None, None, None]

def make_out(state, batter, pitcher):
    state["outs"] += 1
    batter.stats["outs"] += 1
    pitcher.stats["outs_recorded"] += 1

def handle_error(state, batter):
    batter.stats["reached_on_error"] += 1
    state["bases"][0] = Runner(batter=batter, reached_by_error=True)

def play_plate_appearance(batting_team, pitcher, state, batting_index):
    batter = batting_team.batters[batting_index % 9]
    batting_index += 1
    batter.stats["plate_appearances"] += 1
    pitcher.stats["batters_faced"] += 1

    result = plate_appearance_result(batter, pitcher)

    if result == "strikeout":
        batter.stats["at_bats"] += 1
        batter.stats["strikeouts"] += 1
        pitcher.stats["strikeouts"] += 1
        make_out(state, batter, pitcher)
    elif result == "walk":
        handle_walk(state, batter)
        pitcher.stats["walks"] += 1
    elif result in ("single", "double", "triple", "homerun"):
        batter.stats["at_bats"] += 1
        pitcher.stats["hits"] += 1
        if result == "homerun":
            pitcher.stats["homeruns"] += 1
        handle_hit(state, batter, result)
    else:
        batter.stats["at_bats"] += 1
        defender = random.choice(batting_team.batters)
        error_rate = 0.025 - (defender.defense - 50) * 0.00025
        error_rate = clamp(error_rate, 0.005, 0.05)
        if random.random() < error_rate:
            handle_error(state, batter)
        else:
            make_out(state, batter, pitcher)

    return batting_index

def calculate_earned_runs(state):
    earned = 0
    for runner in state["scored_runners"]:
        if not runner.reached_by_error:
            earned += 1
    return earned

def play_half_inning(batting_team, fielding_team, pitcher, batting_index):
    state = {"bases": [None, None, None], "outs": 0, "runs": 0, "scored_runners": []}
    start_outs = pitcher.stats["outs_recorded"]

    while state["outs"] < 3:
        runner_on = state["bases"][1]
        if runner_on and runner_on.batter.speed >= 65:
            if random.random() < (runner_on.batter.speed - 60) * 0.015:
                runner_on.batter.stats["steal_attempts"] += 1
                if random.random() < 0.7:
                    state["bases"][2] = runner_on
                    state["bases"][1] = None
                    runner_on.batter.stats["steals"] += 1
                else:
                    state["bases"][1] = None
                    runner_on.batter.stats["caught_stealing"] += 1
                    state["outs"] += 1
        if state["outs"] >= 3:
            break

        batting_index = play_plate_appearance(batting_team, pitcher, state, batting_index)

    pitcher.stats["innings"] = pitcher.stats["outs_recorded"] / 3
    pitcher.stats["runs_allowed"] += state["runs"]
    pitcher.stats["earned_runs"] += calculate_earned_runs(state)
    return state["runs"], batting_index

def determine_pitcher_decision(winning_team, losing_team, winning_pitcher, losing_pitcher):
    if winning_pitcher is not None:
        winning_pitcher.stats["wins"] += 1
    if losing_pitcher is not None:
        losing_pitcher.stats["losses"] += 1

def play_game(home, away):
    home_pitcher = home.pitchers[0]
    away_pitcher = away.pitchers[0]

    home_score = 0
    away_score = 0
    home_batting_index = 0
    away_batting_index = 0

    for inning in range(1, MAX_INNINGS + 1):
        if should_replace_pitcher(home_pitcher):
            home_pitcher = choose_reliever(home, home_pitcher)
        runs, away_batting_index = play_half_inning(away, home, home_pitcher, away_batting_index)
        away_score += runs

        if inning >= 9 and home_score > away_score:
            break

        if should_replace_pitcher(away_pitcher):
            away_pitcher = choose_reliever(away, away_pitcher)
        runs, home_batting_index = play_half_inning(home, away, away_pitcher, home_batting_index)
        home_score += runs

        if inning >= 9 and home_score != away_score:
            break

    home.runs_for += home_score
    home.runs_against += away_score
    away.runs_for += away_score
    away.runs_against += home_score

    if home_score > away_score:
        home.wins += 1
        away.losses += 1
        determine_pitcher_decision(home, away, home_pitcher, away_pitcher)
    elif away_score > home_score:
        away.wins += 1
        home.losses += 1
        determine_pitcher_decision(away, home, away_pitcher, home_pitcher)
    else:
        home.draws += 1
        away.draws += 1

# ==========================================
# 2. カスタムCSSの定義
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
    .stApp { background-color: #f7f6f0; }
    .title-sub { font-size: 12px; color: #888; text-align: center; letter-spacing: 2px; margin-bottom: 0; }
    .title-main { font-size: 32px; font-weight: 900; text-align: center; margin-top: 0; margin-bottom: 24px; }
    .rule-box { background: transparent; border-top: 1px solid #ddd; padding-top: 16px; font-size: 14px; }
    .rule-item { border-bottom: 1px solid #eee; padding: 12px 0; display: flex; }
    .rule-num { color: #888; font-weight: bold; margin-right: 12px; }
    .disclaimer { font-size: 11px; color: #666; background: white; padding: 12px; border: 1px solid #ddd; margin-top: 24px; }

    .player-card {
        background: white; border-radius: 12px; padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 16px; border: 1px solid #eee;
    }
    .player-pos-badge { background: #1a5a5a; color: white; padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: bold; display: inline-block; margin-bottom: 8px;}
    .player-name { font-size: 28px; font-weight: 900; margin: 0 0 4px 0; color: #222;}
    .player-sub { font-size: 13px; color: #666; margin-bottom: 16px; }
    
    .attr-container { display: flex; justify-content: space-between; margin-top: 16px; gap: 4px;}
    .attr-box { border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 4px; text-align: center; flex: 1; background: #fafafa;}
    .attr-label { font-size: 10px; color: #666; margin-bottom: 2px;}
    .attr-grade { font-size: 22px; font-weight: 900; margin-bottom: 2px;}
    .attr-val { font-size: 11px; color: #888;}
    
    .grade-S { color: #e6b422; }
    .grade-A { color: #c93a3a; }
    .grade-B { color: #c25953; }
    .grade-C { color: #d48a35; }
    .grade-D { color: #3a82c9; }
    .grade-E, .grade-F, .grade-G { color: #666; }
    
    .status-bar { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #ddd; padding-bottom: 12px; margin-bottom: 16px;}
    .status-count { font-size: 24px; font-weight: bold; }
    .status-left { font-size: 13px; color: #666; }
    .pass-pill { background: #fbebeb; color: #b03535; padding: 6px 12px; border-radius: 16px; font-size: 13px; font-weight: bold; border: 1px solid #fad4d4;}

    div[data-baseweb="select"] { width: 56px !important; height: 56px !important; }
    div[data-baseweb="select"] > div {
        width: 56px !important; height: 56px !important; min-height: 56px !important;
        display: flex !important; align-items: center !important; justify-content: center !important;
        background-color: #f0f0f0 !important; border-radius: 8px !important; font-weight: bold !important; font-size: 18px !important;
    }

    div[data-testid="stHorizontalBlock"] { display: flex !important; flex-direction: row !important; align-items: center !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-of-type(1) { flex: 0 0 70px !important; width: 70px !important; min-width: 70px !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]:nth-of-type(2) { flex: 1 1 auto !important; width: calc(100% - 70px) !important; }
    </style>
    """, unsafe_allow_html=True)

def val_to_grade(val):
    if val >= 90: return "S", "grade-S"
    elif val >= 80: return "A", "grade-A"
    elif val >= 70: return "B", "grade-B"
    elif val >= 60: return "C", "grade-C"
    elif val >= 50: return "D", "grade-D"
    elif val >= 40: return "E", "grade-E"
    elif val >= 30: return "F", "grade-F"
    else: return "G", "grade-G"

# ==========================================
# 3. 初期化と画面管理
# ==========================================
st.set_page_config(page_title="野球チームメーカー", layout="centered", initial_sidebar_state="collapsed")
inject_custom_css()

@st.cache_data
def load_excel_pools():
    try:
        df_b = pd.read_excel("野手能力データ_最新.xlsx")
        batters_raw = []
        for _, row in df_b.iterrows():
            batters_raw.append({
                "name": row['選手名'], "team": row['チーム'],
                "meet": row['ミート'], "power": row['パワー'], "speed": row['走力'], "defense": row['守備力']
            })
        
        df_p = pd.read_excel("投手能力データ_最新.xlsx")
        pitchers_raw = []
        for _, row in df_p.iterrows():
            pitchers_raw.append({
                "name": row['選手名'], "team": row['チーム'],
                "control": row['制球'], "stamina": row['スタミナ'], "pitches": row['球種ランク']
            })
    except:
        batters_raw, pitchers_raw = [], []
    return batters_raw, pitchers_raw

if "screen" not in st.session_state:
    b_raw, p_raw = load_excel_pools()
    random.shuffle(b_raw)
    random.shuffle(p_raw)
    
    st.session_state.batters_raw_pool = b_raw
    st.session_state.pitchers_raw_pool = p_raw
    st.session_state.screen = "top"
    st.session_state.my_batters = []
    st.session_state.my_pitchers = []
    st.session_state.b_passes = 5
    st.session_state.p_passes = 8
    st.session_state.pool_idx = 0
    st.session_state.team_name = "マイチーム"

def change_screen(new_screen):
    st.session_state.screen = new_screen
    st.session_state.pool_idx = 0
    st.rerun()

draft_button_css = """
<style>
div[data-testid="column"]:nth-of-type(1) button {
    background-color: #b03535 !important; color: white !important;
    height: 60px !important; font-size: 18px !important; font-weight: bold !important; border-radius: 8px !important; border: none !important;
}
div[data-testid="column"]:nth-of-type(2) button {
    background-color: #2a6642 !important; color: white !important;
    height: 60px !important; font-size: 18px !important; font-weight: bold !important; border-radius: 8px !important; border: none !important;
}
</style>
"""

# --- ① トップ画面 ---
if st.session_state.screen == "top":
    st.markdown("<p class='title-sub'>BASEBALL TEAM BUILDER</p>", unsafe_allow_html=True)
    st.markdown("<h1 class='title-main'>野球チームメーカー</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 14px; margin-bottom: 40px;'>ランダムに現れる選手を取捨選択して、<br>24人のチームを作れ！</p>", unsafe_allow_html=True)
    
    html_top = """
<div class='rule-box'>
<div style='font-size: 12px; color: #666; margin-bottom: 8px;'>ルール</div>
<div class='rule-item'><span class='rule-num'>1</span>架空の選手がポジション関係なく完全ランダムで1人ずつ登場</div>
<div class='rule-item'><span class='rule-num'>2</span>できるのは<b>「取る」</b>か<b>「見送る」</b>だけ</div>
<div class='rule-item'><span class='rule-num'>3</span>まず<b>野手9人</b>（見送り5回まで）</div>
<div class='rule-item'><span class='rule-num'>4</span>つぎに<b>投手15人</b>（先発6人・救援9人をセットで選ぶ）</div>
<div class='rule-item'><span class='rule-num'>5</span>役割を決め、打順を組んで<b>143試合</b>を戦う</div>
<div class='rule-item'><span class='rule-num'>6</span>シーズン中は選手が急に伸びたり、不調に落ちたりする</div>
</div>
<div class='disclaimer'>
本サイトは日本野球機構（NPB）・各球団・選手本人とは関係のない非公式のファンサイトです。選手名・成績・能力値はすべて本ゲームのための架空のもので、実在の選手とは関係ありません。
</div>
"""
    st.markdown(html_top, unsafe_allow_html=True)
    st.write("")
    if st.button("ゲーム開始", use_container_width=True, type="primary"):
        change_screen("draft_batter")

# --- ② 野手を獲得 ---
elif st.session_state.screen == "draft_batter":
    st.markdown(draft_button_css, unsafe_allow_html=True)
    c_count = len(st.session_state.my_batters)
    html_status = f"""
<div class='status-bar'>
<div>
<div style='font-size: 12px; font-weight: bold;'>野手を獲得</div>
<span class='status-count'>{c_count} / 9</span> <span class='status-left'>あと{9 - c_count}人</span>
</div>
<div class='pass-pill'>見送り残り：{st.session_state.b_passes}回</div>
</div>
"""
    st.markdown(html_status, unsafe_allow_html=True)
    
    if c_count >= 9:
        st.success("野手9人が揃いました！")
        if st.button("投手の獲得へ進む", use_container_width=True, type="primary"):
            change_screen("draft_pitcher")
    else:
        p_raw = st.session_state.batters_raw_pool[st.session_state.pool_idx]
        m_grade, m_cls = val_to_grade(p_raw['meet'])
        p_grade, p_cls = val_to_grade(p_raw['power'])
        s_grade, s_cls = val_to_grade(p_raw['speed'])
        
        html_card = f"""
<div class='player-card'>
<div class='player-pos-badge'>野手</div>
<h2 class='player-name'>{p_raw['name']}</h2>
<div class='player-sub'>所属: {p_raw['team']}</div>
<div class='attr-container'>
    <div class='attr-box'><div class='attr-label'>ミート</div><div class='attr-grade {m_cls}'>{m_grade}</div><div class='attr-val'>{p_raw['meet']}</div></div>
    <div class='attr-box'><div class='attr-label'>パワー</div><div class='attr-grade {p_cls}'>{p_grade}</div><div class='attr-val'>{p_raw['power']}</div></div>
    <div class='attr-box'><div class='attr-label'>走力</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{p_raw['speed']}</div></div>
</div>
</div>
"""
        st.markdown(html_card, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"見送る (残り {st.session_state.b_passes} 回)", use_container_width=True, disabled=(st.session_state.b_passes <= 0)):
                st.session_state.b_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button("取る (チームに加える)", use_container_width=True, type="primary"):
                b_obj = Batter(
                    name=p_raw['name'], team_name=p_raw['team'],
                    contact=p_raw['meet'], power=p_raw['power'], speed=p_raw['speed'], defense=p_raw['defense']
                )
                st.session_state.my_batters.append(b_obj)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ③ 投手を獲得 ---
elif st.session_state.screen == "draft_pitcher":
    st.markdown(draft_button_css, unsafe_allow_html=True)
    c_count = len(st.session_state.my_pitchers)
    html_status = f"""
<div class='status-bar'>
<div>
<div style='font-size: 12px; font-weight: bold;'>投手を獲得</div>
<span class='status-count'>{c_count} / 15</span> <span class='status-left'>あと{15 - c_count}人</span>
</div>
<div class='pass-pill'>見送り残り：{st.session_state.p_passes}回</div>
</div>
"""
    st.markdown(html_status, unsafe_allow_html=True)
    
    if c_count >= 15:
        st.success("投手15人が揃いました！")
        if st.button("シーズン準備へ進む", use_container_width=True, type="primary"):
            change_screen("setup")
    else:
        p_raw = st.session_state.pitchers_raw_pool[st.session_state.pool_idx]
        c_grade, c_cls = val_to_grade(p_raw['control'])
        s_grade, s_cls = val_to_grade(p_raw['stamina'])
        
        html_card = f"""
<div class='player-card'>
<div class='player-pos-badge'>投手</div>
<h2 class='player-name'>{p_raw['name']}</h2>
<div class='player-sub'>所属: {p_raw['team']}</div>
<div class='attr-container'>
    <div class='attr-box'><div class='attr-label'>制球</div><div class='attr-grade {c_cls}'>{c_grade}</div><div class='attr-val'>{p_raw['control']}</div></div>
    <div class='attr-box'><div class='attr-label'>スタミナ</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{p_raw['stamina']}</div></div>
</div>
<div style='margin-top: 16px; font-size: 12px; color: #555; border-top: 1px dashed #ddd; padding-top: 12px;'>
    球種： <b>{p_raw['pitches']}</b>
</div>
</div>
"""
        st.markdown(html_card, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"見送る (残り {st.session_state.p_passes} 回)", use_container_width=True, disabled=(st.session_state.p_passes <= 0)):
                st.session_state.p_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button("取る (チームに加える)", use_container_width=True, type="primary"):
                p_obj = Pitcher(
                    name=p_raw['name'], team_name=p_raw['team'],
                    control=p_raw['control'], stamina=p_raw['stamina'], breaking_balls={"slider": "B"}
                )
                st.session_state.my_pitchers.append(p_obj)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ④ シーズン開始前 (打順・起用法セットアップ) ---
elif st.session_state.screen == "setup":
    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-bottom: 24px;'>打順・守備位置</h2>", unsafe_allow_html=True)
    
    st.session_state.team_name = st.text_input("チーム名", value=st.session_state.team_name, max_chars=12)
    positions_list = ["捕手", "一塁手", "二塁手", "三塁手", "遊撃手", "左翼手", "中堅手", "右翼手", "指名打者"]
    
    for idx, b in enumerate(st.session_state.my_batters):
        if not hasattr(b, 'temp_order') or b.temp_order is None:
            b.temp_order = idx + 1
        if not hasattr(b, 'temp_position'):
            b.temp_position = positions_list[idx % len(positions_list)]

    sorted_batters = sorted(st.session_state.my_batters, key=lambda x: x.temp_order)

    for i, batter in enumerate(sorted_batters):
        with st.container(border=True):
            col_ord, col_card = st.columns([1, 4])
            with col_ord:
                new_order = st.selectbox(
                    "打順選択", range(1, 10), index=batter.temp_order - 1, 
                    key=f"order_sel_{batter.name}", label_visibility="collapsed"
                )
                if new_order != batter.temp_order:
                    batter.temp_order = new_order
                    st.rerun()
            with col_card:
                st.markdown(f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{batter.name}</div><div style='font-size: 11px; color: #888; margin-bottom: 4px;'>所属: {batter.team_name}</div>", unsafe_allow_html=True)
                try:
                    pos_idx = positions_list.index(batter.temp_position)
                except ValueError:
                    pos_idx = 0
                new_pos = st.selectbox("守備位置選択", positions_list, index=pos_idx, label_visibility="collapsed", key=f"pos_{batter.name}")
                batter.temp_position = new_pos
                batter.position = new_pos

    st.session_state.my_batters = sorted_batters

    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-top: 32px; margin-bottom: 24px;'>投手の役割</h2>", unsafe_allow_html=True)
    roles_list = ["先発", "中継ぎ", "セットアッパー", "抑え"]
    
    for i, pitcher in enumerate(st.session_state.my_pitchers):
        with st.container(border=True):
            st.markdown(f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{pitcher.name}</div><div style='font-size: 11px; color: #888; margin-bottom: 4px;'>所属: {pitcher.team_name}</div>", unsafe_allow_html=True)
            def_index = 0 if i < 6 else 1
            pitcher.pitcher_role = st.selectbox("起用法選択", roles_list, index=def_index, label_visibility="collapsed", key=f"role_{i}")

    st.write("---")
    if st.button("🔥 開幕（143試合シミュレーション実行）", type="primary", use_container_width=True):
        # チームオブジェクトの作成
        my_team = Team(name=st.session_state.team_name, batters=st.session_state.my_batters, pitchers=st.session_state.my_pitchers)
        
        # 簡易的に対戦相手（CPUチーム）を生成
        cpu_batters = [Batter(f"CPU野手{i}", "CPU", 70, 70, 70, 70) for i in range(1, 10)]
        cpu_pitchers = [Pitcher(f"CPU投手{i}", "CPU", 70, 70, {"slider": "C"}) for i in range(1, 10)]
        cpu_team = Team(name="CPUライバルズ", batters=cpu_batters, pitchers=cpu_pitchers)

        teams = [my_team, cpu_team]
        for t in teams:
            t.reset_stats()

        # 143試合の実行
        games_to_play = SEASON_GAMES
        for _ in range(games_to_play):
            play_game(my_team, cpu_team)

        st.session_state.sim_my_team = my_team
        st.session_state.sim_cpu_team = cpu_team
        change_screen("result")

# --- ⑤ シーズン結果 (個人成績表示) ---
elif st.session_state.screen == "result":
    my_team = st.session_state.sim_my_team
    cpu_team = st.session_state.sim_cpu_team
    
    # 順位判定
    all_teams = sorted([my_team, cpu_team], key=lambda t: (t.wins, t.runs_for - t.runs_against), reverse=True)
    my_rank = all_teams.index(my_team) + 1

    st.markdown(f"<h1 style='text-align: center;'>{my_team.name}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='text-align: center; color: #b03535;'>最終順位： 第 {my_rank} 位</h2>", unsafe_allow_html=True)
    win_rate = my_team.wins / (my_team.wins + my_team.losses) if (my_team.wins + my_team.losses) > 0 else 0
    st.markdown(f"<p style='text-align: center; color: #666;'>143試合成績： {my_team.wins}勝 {my_team.losses}敗 {my_team.draws}分 (勝率 .{int(win_rate*1000):03d})</p>", unsafe_allow_html=True)
    st.write("---")
    
    tab1, tab2 = st.tabs(["⚾ 野手成績", "投手成績"])
    
    with tab1:
        st.subheader("野手 個人成績")
        batter_data = []
        for i, b in enumerate(my_team.batters):
            ab = b.stats['at_bats']
            avg = (b.stats['hits'] / ab) if ab > 0 else 0
            batter_data.append({
                "打順": f"{i+1}番",
                "守備": b.position,
                "選手名": b.name,
                "所属": b.team_name,
                "打率": f"{avg:.3f}",
                "安打": b.stats['hits'],
                "本塁打": b.stats['homeruns'],
                "打点": b.stats['rbi'],
                "盗塁": b.stats['steals']
            })
        st.dataframe(pd.DataFrame(batter_data), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("投手 個人成績")
        pitcher_data = []
        for p in my_team.pitchers:
            ip = p.stats['outs_recorded'] / 3
            era = (p.stats['earned_runs'] * 9 / ip) if ip > 0 else 0
            pitcher_data.append({
                "起用法": p.pitcher_role,
                "選手名": p.name,
                "所属": p.team_name,
                "防御率": f"{era:.2f}",
                "勝利": int(p.stats['wins']),
                "敗北": int(p.stats['losses']),
                "投球回": f"{ip:.1f}"
            })
        st.dataframe(pd.DataFrame(pitcher_data), use_container_width=True, hide_index=True)

    st.write("---")
    if st.button("🔄 最初からやり直す", use_container_width=True):
        st.session_state.clear()
        st.rerun()
