import streamlit as st
import pandas as pd
import random
from dataclasses import dataclass, field
from collections import defaultdict

# =========================================================
# 基本設定・定数
# =========================================================
GAMES_PER_SEASON = 143
MAX_INNINGS = 12
CHANGE_LEVEL = {
    "S": 100, "A": 85, "B": 70, "C": 55, "D": 40, "E": 25,
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

# =========================================================
# データクラス定義
# =========================================================
@dataclass
class Batter:
    name: str
    team: str
    contact: int
    power: int
    speed: int
    defense_str: str
    position: str = "捕手"
    temp_order: int = 1
    temp_position: str = "捕手"
    stats: dict = field(default_factory=lambda: defaultdict(int))

    def reset_stats(self):
        self.stats = defaultdict(int)

@dataclass
class Pitcher:
    name: str
    team: str
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

# =========================================================
# 投手能力計算
# =========================================================
def breaking_ball_value(pitcher):
    if not pitcher.breaking_balls:
        return 25
    values = [
        CHANGE_LEVEL[level] for level in pitcher.breaking_balls.values() if level in CHANGE_LEVEL
    ]
    if not values:
        return 25
    average = sum(values) / len(values)
    variety_bonus = min(len(values) - 1, 3) * 3
    return clamp(average + variety_bonus, 25, 100)

def pitcher_strength(pitcher):
    breaking = breaking_ball_value(pitcher)
    return pitcher.control * 0.55 + breaking * 0.45

# =========================================================
# 打者 vs 投手
# =========================================================
def batter_pitcher_matchup(batter, pitcher):
    p_strength = pitcher_strength(pitcher)
    contact_match = batter.contact - p_strength
    power_match = batter.power - p_strength
    return contact_match, power_match

def plate_appearance(batter, pitcher):
    contact_match, power_match = batter_pitcher_matchup(batter, pitcher)

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
    homerun = max(0.3, homerun)
    double = max(1.0, double)

    walk += (50 - pitcher.control) * 0.12
    breaking = breaking_ball_value(pitcher)
    strikeout += (breaking - 50) * 0.12
    triple += (batter.speed - 50) * 0.025

    strikeout = max(3, strikeout)
    walk = max(2, walk)
    single = max(5, single)
    double = max(1, double)
    triple = max(0.2, triple)
    homerun = max(0.3, homerun)
    out = max(10, out)

    probabilities = [
        ("strikeout", strikeout),
        ("walk", walk),
        ("single", single),
        ("double", double),
        ("triple", triple),
        ("homerun", homerun),
        ("out", out),
    ]
    return weighted_choice(probabilities)

# =========================================================
# 試合進行・イニング処理
# =========================================================
@dataclass
class GameState:
    bases: list = field(default_factory=lambda: [None, None, None])
    outs: int = 0
    runs: int = 0

def advance_runners(state, batter, bases_to_advance):
    old_bases = state.bases[:]
    state.bases = [None, None, None]
    scored_count = 0
    for base_index in range(2, -1, -1):
        runner = old_bases[base_index]
        if runner is None:
            continue
        new_base = base_index + bases_to_advance
        if new_base >= 3:
            state.runs += 1
            scored_count += 1
            runner.stats["runs"] += 1
        else:
            state.bases[new_base] = runner
    
    batter.stats["rbis"] += scored_count
    return scored_count

def handle_hit(state, batter, result):
    if result == "single":
        advance_runners(state, batter, 1)
        state.bases[0] = batter
        batter.stats["hits"] += 1
        batter.stats["singles"] += 1
    elif result == "double":
        advance_runners(state, batter, 2)
        state.bases[1] = batter
        batter.stats["hits"] += 1
        batter.stats["doubles"] += 1
    elif result == "triple":
        advance_runners(state, batter, 3)
        state.bases[2] = batter
        batter.stats["hits"] += 1
        batter.stats["triples"] += 1
    elif result == "homerun":
        scored_count = 0
        for i in range(3):
            runner = state.bases[i]
            if runner is not None:
                state.runs += 1
                scored_count += 1
                runner.stats["runs"] += 1
        state.bases = [None, None, None]
        state.runs += 1
        scored_count += 1
        
        batter.stats["hits"] += 1
        batter.stats["homeruns"] += 1
        batter.stats["runs"] += 1
        batter.stats["rbis"] += scored_count

def handle_walk(state, batter):
    batter.stats["walks"] += 1
    scored_count = 0
    if state.bases[0] is not None:
        if state.bases[1] is not None:
            if state.bases[2] is not None:
                runner = state.bases[2]
                if runner:
                    runner.stats["runs"] += 1
                    scored_count += 1
                state.runs += 1
                state.bases[2] = state.bases[1]
            state.bases[1] = state.bases[0]
        state.bases[0] = batter
    else:
        state.bases[0] = batter
    
    if scored_count > 0:
        batter.stats["rbis"] += scored_count

def play_half_inning(batting_team, pitcher, batting_index):
    state = GameState()
    while state.outs < 3:
        batter = batting_team.batters[batting_index % 9]
        batting_index += 1
        batter.stats["plate_appearances"] += 1

        result = plate_appearance(batter, pitcher)

        if result == "strikeout":
            batter.stats["strikeouts"] += 1
            batter.stats["at_bats"] += 1
            pitcher.stats["strikeouts"] += 1
            pitcher.stats["batters_faced"] += 1
            state.outs += 1
        elif result == "walk":
            handle_walk(state, batter)
            pitcher.stats["walks"] += 1
            pitcher.stats["batters_faced"] += 1
        elif result in ("single", "double", "triple", "homerun"):
            batter.stats["at_bats"] += 1
            handle_hit(state, batter, result)
            pitcher.stats["hits"] += 1
            pitcher.stats["batters_faced"] += 1
            if result == "homerun":
                pitcher.stats["homeruns"] += 1
        else:
            batter.stats["at_bats"] += 1
            batter.stats["outs"] += 1
            pitcher.stats["batters_faced"] += 1
            state.outs += 1
            
    pitcher.stats["innings"] += 1.0
    return state.runs, batting_index

# =========================================================
# 投手マネジメント（継投ロジック）
# =========================================================
class PitcherManager:
    def __init__(self, team):
        self.starters = [p for p in team.pitchers if p.pitcher_role == "先発"]
        self.setups = [p for p in team.pitchers if p.pitcher_role == "セットアッパー"]
        self.closers = [p for p in team.pitchers if p.pitcher_role == "抑え"]
        self.closes = [p for p in team.pitchers if p.pitcher_role == "僅差"]
        self.behinds = [p for p in team.pitchers if p.pitcher_role == "ビハインド"]
        
        if not self.starters:
            self.starters = team.pitchers[:1]
        if not self.setups:
            self.setups = team.pitchers[1:3] if len(team.pitchers) > 2 else team.pitchers
        if not self.closers:
            self.closers = team.pitchers[-1:]
            
        self.current_pitcher = random.choice(self.starters)
        self.innings_pitched_by_current = 0.0

    def get_pitcher(self, inning, my_score, opp_score):
        score_diff = my_score - opp_score
        
        starter_limit = max(3, int(self.current_pitcher.stamina / 14))
        is_tired = (self.current_pitcher.pitcher_role == "先発" and self.innings_pitched_by_current >= starter_limit)
        
        should_change = is_tired or (self.current_pitcher.pitcher_role == "先発" and inning >= 6)
        
        if should_change:
            if score_diff < 0 and self.behinds:
                self.current_pitcher = random.choice(self.behinds)
            elif inning >= 9 and 0 <= score_diff <= 3 and self.closers:
                self.current_pitcher = random.choice(self.closers)
            elif inning == 8 and abs(score_diff) <= 3 and self.setups:
                self.current_pitcher = random.choice(self.setups)
            elif abs(score_diff) <= 3 and self.closes:
                self.current_pitcher = random.choice(self.closes)
            elif self.setups:
                self.current_pitcher = random.choice(self.setups)
            elif self.closes:
                self.current_pitcher = random.choice(self.closes)
                
        return self.current_pitcher

    def add_inning(self):
        self.innings_pitched_by_current += 1.0

def play_game(home, away):
    home_mgr = PitcherManager(home)
    away_mgr = PitcherManager(away)

    home_score = 0
    away_score = 0
    home_batting_index = 0
    away_batting_index = 0

    for inning in range(1, MAX_INNINGS + 1):
        away_pitcher = home_mgr.get_pitcher(inning, home_score, away_score)
        away_runs, away_batting_index = play_half_inning(away, away_pitcher, away_batting_index)
        home_score += away_runs
        away_pitcher.stats["earned_runs"] += away_runs
        home_mgr.add_inning()

        if inning >= 9 and home_score > away_score:
            break

        home_pitcher = away_mgr.get_pitcher(inning, away_score, home_score)
        home_runs, home_batting_index = play_half_inning(home, home_pitcher, home_batting_index)
        away_score += home_runs
        home_pitcher.stats["earned_runs"] += home_runs
        away_mgr.add_inning()

        if inning >= 9 and home_score != away_score:
            break

    home.runs_for += home_score
    home.runs_against += away_score
    away.runs_for += away_score
    away.runs_against += home_score

    if home_score > away_score:
        home.wins += 1
        away.losses += 1
        home_mgr.current_pitcher.stats["wins"] += 1
        away_mgr.current_pitcher.stats["losses"] += 1
    elif away_score > home_score:
        away.wins += 1
        home.losses += 1
        away_mgr.current_pitcher.stats["wins"] += 1
        home_mgr.current_pitcher.stats["losses"] += 1
    else:
        home.draws += 1
        away.draws += 1

# =========================================================
# カスタムCSSの定義
# =========================================================
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
    
    .grade-S { color: #e6b422; } .grade-A { color: #c93a3a; } .grade-B { color: #c25953; }
    .grade-C { color: #d48a35; } .grade-D { color: #3a82c9; } .grade-E, .grade-F, .grade-G { color: #666; }
    
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

@st.cache_data
def load_pool_players():
    batters = []
    pitchers = []
    try:
        df_b = pd.read_excel("野手能力データ_最新.xlsx")
        for _, row in df_b.iterrows():
            batters.append(Batter(
                name=row['選手名'], team=row['チーム'],
                contact=row['ミート'], power=row['パワー'],
                speed=row['走力'], defense_str=str(row['守備力'])
            ))
            
        df_p = pd.read_excel("投手能力データ_最新.xlsx")
        for _, row in df_p.iterrows():
            bb = {}
            raw_bb = row.get('球種ランク', row.get('変化球', ''))
            if isinstance(raw_bb, str) and raw_bb.strip():
                parts = raw_bb.replace('，', ',').split(',')
                for p in parts:
                    if ':' in p:
                        k, v = p.split(':', 1)
                        bb[k.strip()] = v.strip()
                    elif ' ' in p:
                        k, v = p.split(' ', 1)
                        bb[k.strip()] = v.strip()
            elif isinstance(raw_bb, dict):
                bb = raw_bb

            pitchers.append(Pitcher(
                name=row['選手名'], team=row['チーム'],
                control=row['制球'], stamina=row['スタミナ'],
                breaking_balls=bb
            ))
    except Exception as e:
        family_names = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤", "吉田", "山田", "佐々木", "山口", "松本"]
        first_names = ["翔", "大輝", "蓮", "陽翔", "樹", "湊", "新", "朝陽", "悠真", "律", "結衣", "陽葵", "澪", "紬", "芽依"]
        teams = ["東京", "大阪", "名古屋", "福岡", "札幌", "仙台"]
        
        for i in range(80):
            name = f"{random.choice(family_names)}{random.choice(first_names)}"
            batters.append(Batter(
                name=name, team=random.choice(teams),
                contact=random.randint(40, 95),
                power=random.randint(30, 95),
                speed=random.randint(40, 90),
                defense_str="捕手・一塁手・外野手"
            ))
        for i in range(80):
            name = f"{random.choice(family_names)}{random.choice(first_names)}"
            bb_types = ["スライダー", "カーブ", "フォーク", "シュート", "チェンジアップ", "カットボール"]
            bb_grades = ["S", "A", "B", "C", "D"]
            bb = {}
            for _ in range(random.randint(2, 4)):
                t = random.choice(bb_types)
                if t not in bb:
                    bb[t] = random.choice(bb_grades)
            pitchers.append(Pitcher(
                name=name, team=random.choice(teams),
                control=random.randint(40, 95),
                stamina=random.randint(40, 95),
                breaking_balls=bb
            ))
    return batters, pitchers

# =========================================================
# 初期化と画面管理
# =========================================================
st.set_page_config(page_title="野球チームメーカー", layout="centered", initial_sidebar_state="collapsed")
inject_custom_css()

if "screen" not in st.session_state:
    batters, pitchers = load_pool_players()
    random.shuffle(batters)
    random.shuffle(pitchers)
    
    st.session_state.batters_pool = batters
    st.session_state.pitchers_pool = pitchers
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
本サイトは日本野球機構（NPB）・各球団・選手本人とは関係のない非公式のファンサイトです。
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
        st.success("野手9人が揃えました！")
        if st.button("投手の獲得へ進む", use_container_width=True, type="primary"):
            change_screen("draft_pitcher")
    else:
        player = st.session_state.batters_pool[st.session_state.pool_idx]
        m_grade, m_cls = val_to_grade(player.contact)
        p_grade, p_cls = val_to_grade(player.power)
        s_grade, s_cls = val_to_grade(player.speed)
        
        html_card = f"""
<div class='player-card'>
<div class='player-pos-badge'>野手</div>
<h2 class='player-name'>{player.name}</h2>
<div class='player-sub'>所属: {player.team}</div>
<div class='attr-container'>
    <div class='attr-box'><div class='attr-label'>ミート</div><div class='attr-grade {m_cls}'>{m_grade}</div><div class='attr-val'>{player.contact}</div></div>
    <div class='attr-box'><div class='attr-label'>パワー</div><div class='attr-grade {p_cls}'>{p_grade}</div><div class='attr-val'>{player.power}</div></div>
    <div class='attr-box'><div class='attr-label'>走力</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{player.speed}</div></div>
</div>
<div style='margin-top: 16px; font-size: 13px; color: #555; border-top: 1px dashed #ddd; padding-top: 12px;'>
    守れる所： <b>{player.defense_str}</b>
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
                st.session_state.my_batters.append(player)
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
        st.success("投手15人が揃えました！")
        if st.button("シーズン準備へ進む", use_container_width=True, type="primary"):
            change_screen("setup")
    else:
        player = st.session_state.pitchers_pool[st.session_state.pool_idx]
        c_grade, c_cls = val_to_grade(player.control)
        s_grade, s_cls = val_to_grade(player.stamina)
        
        bb_text = " / ".join([f"{k} {v}" for k, v in player.breaking_balls.items()]) if player.breaking_balls else "なし"
        
        html_card = f"""
<div class='player-card'>
<div class='player-pos-badge'>投手</div>
<h2 class='player-name'>{player.name}</h2>
<div class='player-sub'>所属: {player.team}</div>
<div class='attr-container'>
    <div class='attr-box'><div class='attr-label'>制球</div><div class='attr-grade {c_cls}'>{c_grade}</div><div class='attr-val'>{player.control}</div></div>
    <div class='attr-box'><div class='attr-label'>スタミナ</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{player.stamina}</div></div>
</div>
<div style='margin-top: 16px; font-size: 13px; color: #555; border-top: 1px dashed #ddd; padding-top: 12px;'>
    変化球： <b>{bb_text}</b>
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
                st.session_state.my_pitchers.append(player)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ④ シーズン開始前 (打順・起用法セットアップ) ---
elif st.session_state.screen == "setup":
    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-bottom: 24px;'>打順・守備位置</h2>", unsafe_allow_html=True)
    st.session_state.team_name = st.text_input("チーム名", value=st.session_state.team_name, max_chars=12)
    positions_list = ["捕手", "一塁手", "二塁手", "三塁手", "遊撃手", "左翼手", "中堅手", "右翼手", "指名打者"]
    
    # 初回初期化：打順1〜9を被りなく割り振り、守備位置も捕手〜右翼手等を被りなく割り振る
    for idx, b in enumerate(st.session_state.my_batters):
        if not hasattr(b, 'temp_order') or b.temp_order is None:
            b.temp_order = idx + 1
        if not hasattr(b, 'temp_position') or b.temp_position is None:
            b.temp_position = positions_list[idx % len(positions_list)]
            b.position = b.temp_position

    sorted_batters = sorted(st.session_state.my_batters, key=lambda x: x.temp_order)

    for i, batter in enumerate(sorted_batters):
        with st.container(border=True):
            col_ord, col_card = st.columns([1, 4])
            with col_ord:
                new_order = st.selectbox(
                    "打順選択", range(1, 10), index=batter.temp_order - 1, 
                    key=f"order_sel_{batter.name}", label_visibility="collapsed"
                )
                # 打順が変更された場合、他の選手とスワップ（入れ替え）する処理
                if new_order != batter.temp_order:
                    for other_b in st.session_state.my_batters:
                        if other_b != batter and other_b.temp_order == new_order:
                            other_b.temp_order = batter.temp_order
                            break
                    batter.temp_order = new_order
                    st.rerun()
            with col_card:
                st.markdown(f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{batter.name}</div><div style='font-size: 11px; color: #888; margin-bottom: 4px;'>所属: {batter.team}</div>", unsafe_allow_html=True)
                try:
                    pos_idx = positions_list.index(batter.temp_position)
                except ValueError:
                    pos_idx = 0
                new_pos = st.selectbox(
                    "守備位置選択", positions_list, index=pos_idx, 
                    label_visibility="collapsed", key=f"pos_{batter.name}"
                )
                batter.temp_position = new_pos
                batter.position = new_pos

    st.session_state.my_batters = sorted(st.session_state.my_batters, key=lambda x: x.temp_order)

    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-top: 32px; margin-bottom: 24px;'>投手の役割</h2>", unsafe_allow_html=True)
    roles_list = ["先発", "セットアッパー", "抑え", "僅差", "ビハインド"]
    
    for i, pitcher in enumerate(st.session_state.my_pitchers):
        with st.container(border=True):
            bb_text = " / ".join([f"{k} {v}" for k, v in pitcher.breaking_balls.items()]) if pitcher.breaking_balls else "なし"
            st.markdown(f"<div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{pitcher.name} <span style='font-size: 12px; font-weight: normal; color: #666;'>(変化球: {bb_text})</span></div><div style='font-size: 11px; color: #888; margin-bottom: 4px;'>所属: {pitcher.team}</div>", unsafe_allow_html=True)
            
            if i < 6:
                def_index = 0
            elif i < 9:
                def_index = 1
            elif i < 11:
                def_index = 2
            elif i < 13:
                def_index = 3
            else:
                def_index = 4
                
            pitcher.pitcher_role = st.selectbox("起用法選択", roles_list, index=def_index, label_visibility="collapsed", key=f"role_{i}")

    st.write("---")
    if st.button("🔥 開幕（143試合シミュレーション実行）", type="primary", use_container_width=True):
        my_team = Team(name=st.session_state.team_name, batters=st.session_state.my_batters, pitchers=st.session_state.my_pitchers)
        
        dummy_teams = []
        for t_idx in range(5):
            d_batters = [Batter(f"D{t_idx}_{i}", "CPU", 70, 70, 70, "捕手") for i in range(9)]
            d_pitchers = [
                Pitcher(f"D{t_idx}P{i}", "CPU", 70, 70, {"スライダー": "B"}, pitcher_role="先発" if i < 6 else ("セットアッパー" if i < 9 else ("抑え" if i < 11 else ("僅差" if i < 13 else "ビハインド"))))
                for i in range(15)
            ]
            dummy_teams.append(Team(name=f"CPUチーム{t_idx+1}", batters=d_batters, pitchers=d_pitchers))
            
        all_teams = [my_team] + dummy_teams
        
        for team in all_teams:
            team.reset_stats()
            
        n = len(all_teams)
        games_per_opponent = GAMES_PER_SEASON // (n - 1)
        
        for i in range(n):
            for j in range(i + 1, n):
                team_a = all_teams[i]
                team_b = all_teams[j]
                for g in range(games_per_opponent):
                    if g % 2 == 0:
                        play_game(team_a, team_b)
                    else:
                        play_game(team_b, team_a)
                    
        st.session_state.sim_my_team = my_team
        sorted_teams = sorted(all_teams, key=lambda t: (t.wins, t.runs_for - t.runs_against), reverse=True)
        st.session_state.sim_rank = sorted_teams.index(my_team) + 1
        
        change_screen("result")

# --- ⑤ シーズン結果 ---
elif st.session_state.screen == "result":
    t = st.session_state.sim_my_team
    st.markdown(f"<h1 style='text-align: center;'>{t.name}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='text-align: center; color: #b03535;'>最終順位： 第 {st.session_state.sim_rank} 位</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; color: #666;'>143試合成績： {t.wins}勝 {t.losses}敗 {t.draws}分 (得点 {t.runs_for} / 失点 {t.runs_against})</p>", unsafe_allow_html=True)
    st.write("---")
    
    tab1, tab2 = st.tabs(["⚾ 野手成績", "投手成績"])
    
    with tab1:
        st.subheader("野手 個人成績")
        batter_data = []
        for i, b in enumerate(t.batters):
            ab = b.stats["at_bats"]
            hits = b.stats["hits"]
            avg = (hits / ab) if ab > 0 else 0.0
            batter_data.append({
                "打順": f"{i+1}番",
                "守備": b.position,
                "選手名": b.name,
                "所属": b.team,
                "打率": f"{avg:.3f}",
                "打席": b.stats["plate_appearances"],
                "安打": hits,
                "本塁打": b.stats["homeruns"],
                "打点": b.stats["rbis"],
                "盗塁": b.stats["steals"]
            })
        st.dataframe(pd.DataFrame(batter_data), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("投手 個人成績")
        pitcher_data = []
        for p in t.pitchers:
             innings = p.stats["innings"]
             earned_runs = p.stats.get("earned_runs", 0)
             era_val = (earned_runs * 9 / innings) if innings > 0 else 0.0
             pitcher_data.append({
                "起用法": p.pitcher_role,
                "選手名": p.name,
                "所属": p.team,
                "防御率": f"{era_val:.2f}",
                "勝利": int(p.stats.get("wins", 0)),
                "敗北": int(p.stats.get("losses", 0)),
                "奪三振": int(p.stats.get("strikeouts", 0)),
                "投球回": int(innings)
            })
        st.dataframe(pd.DataFrame(pitcher_data), use_container_width=True, hide_index=True)

    st.write("---")
    if st.button("🔄 最初からやり直す", use_container_width=True):
        st.session_state.clear()
        st.rerun()
