import streamlit as st
import pandas as pd
import random
import time

# ==========================================
# 1. データモデルと読み込み処理
# ==========================================
class Player:
    def __init__(self, name, team, role):
        self.name = name
        self.team = team
        self.role = role

class Batter(Player):
    def __init__(self, name, team, meet, power, speed, defense):
        super().__init__(name, team, "野手")
        self.meet = meet
        self.power = power
        self.speed = speed
        self.defense = defense

class Pitcher(Player):
    def __init__(self, name, team, control, stamina, pitches):
        super().__init__(name, team, "投手")
        self.control = control
        self.stamina = stamina
        self.pitches = pitches

def load_players():
    # 野手データの読み込み
    df_b = pd.read_excel("野手能力データ_最新.xlsx")
    batters = [Batter(row['選手名'], row['チーム'], row['ミート'], row['パワー'], row['走力'], row['守備力']) for _, row in df_b.iterrows()]
    
    # 投手データの読み込み
    df_p = pd.read_excel("投手能力データ_最新.xlsx")
    pitchers = [Pitcher(row['選手名'], row['チーム'], row['制球'], row['スタミナ'], row['球種ランク']) for _, row in df_p.iterrows()]
    
    return batters, pitchers

# ==========================================
# 2. アプリの初期化と状態管理 (Session State)
# ==========================================
st.set_page_config(page_title="野球チームメーカー", page_icon="🏟", layout="centered")

if "screen" not in st.session_state:
    batters, pitchers = load_players()
    random.shuffle(batters)
    random.shuffle(pitchers)
    
    st.session_state.batters_pool = batters
    st.session_state.pitchers_pool = pitchers
    
    # 状態変数の初期化
    st.session_state.screen = "top"           # 現在の画面
    st.session_state.my_batters = []          # 獲得した野手 (目標9人)
    st.session_state.my_pitchers = []         # 獲得した投手 (目標15人)
    st.session_state.b_passes = 5             # 野手の見送り残り回数
    st.session_state.p_passes = 8             # 投手の見送り残り回数 (独自設定)
    st.session_state.pool_idx = 0             # プールの参照インデックス
    st.session_state.team_name = "マイチーム"

# 画面遷移用のヘルパー関数
def change_screen(new_screen):
    st.session_state.screen = new_screen
    st.session_state.pool_idx = 0
    st.rerun()

# ==========================================
# 3. 各画面（スクリーン）の描画ロジック
# ==========================================

# --- ① トップ画面 ---
if st.session_state.screen == "top":
    st.markdown("<h4 style='text-align: center; color: gray;'>BASEBALL TEAM BUILDER</h4>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>野球チームメーカー</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>ランダムに現れる選手を取捨選択して、24人のチームを作れ！</p>", unsafe_allow_html=True)
    
    st.write("### ルール")
    st.markdown("""
    1. **架空の選手**が完全ランダムで1人ずつ登場
    2. できるのは「**取る**」か「**見送る**」だけ
    3. まず**野手9人**（見送り5回まで）
    4. つぎに**投手15人**
    5. チーム名とリーグを決めて**143試合**を自動シミュレーション
    """)
    
    st.write("---")
    if st.button("⚾ ゲーム開始", use_container_width=True, type="primary"):
        change_screen("draft_batter")

# --- ② 野手を獲得 ---
elif st.session_state.screen == "draft_batter":
    st.subheader(f"野手を獲得 ({len(st.session_state.my_batters)} / 9)")
    st.progress(len(st.session_state.my_batters) / 9.0)
    st.write(f"見送り残り：**{st.session_state.b_passes}** 回")
    st.write("---")
    
    if len(st.session_state.my_batters) >= 9:
        st.success("野手9人が揃いました！次は投手を集めます。")
        if st.button("投手の獲得へ進む", use_container_width=True, type="primary"):
            change_screen("draft_pitcher")
    else:
        player = st.session_state.batters_pool[st.session_state.pool_idx]
        
        st.markdown(f"### {player.name} <span style='font-size: 0.6em; color: gray;'>({player.team})</span>", unsafe_allow_html=True)
        st.write(f"ミート: **{player.meet}** | パワー: **{player.power}** | 走力: **{player.speed}**")
        st.write(f"守備: {player.defense}")
        st.write("---")
        
        col1, col2 = st.columns(2)
        with col1:
            # 見送りボタン（残り回数が0なら無効化）
            if st.button("❌ 見送る", use_container_width=True, disabled=(st.session_state.b_passes <= 0)):
                st.session_state.b_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button("⭕ 取る", use_container_width=True, type="primary"):
                st.session_state.my_batters.append(player)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ③ 投手を獲得 ---
elif st.session_state.screen == "draft_pitcher":
    st.subheader(f"投手を獲得 ({len(st.session_state.my_pitchers)} / 15)")
    st.progress(len(st.session_state.my_pitchers) / 15.0)
    st.write(f"見送り残り：**{st.session_state.p_passes}** 回")
    st.write("---")
    
    if len(st.session_state.my_pitchers) >= 15:
        st.success("投手15人が揃いました！24人のチームが完成です。")
        if st.button("シーズン準備へ進む", use_container_width=True, type="primary"):
            change_screen("season_setup")
    else:
        player = st.session_state.pitchers_pool[st.session_state.pool_idx]
        
        st.markdown(f"### {player.name} <span style='font-size: 0.6em; color: gray;'>({player.team})</span>", unsafe_allow_html=True)
        st.write(f"制球: **{player.control}** | スタミナ: **{player.stamina}**")
        st.write(f"球種: {player.pitches}")
        st.write("---")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("❌ 見送る", use_container_width=True, disabled=(st.session_state.p_passes <= 0)):
                st.session_state.p_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button("⭕ 取る", use_container_width=True, type="primary"):
                st.session_state.my_pitchers.append(player)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ④ シーズン開始前 ---
elif st.session_state.screen == "season_setup":
    st.markdown("### SEASON SETUP\n# シーズン開始前")
    
    st.session_state.team_name = st.text_input("チーム名", value=st.session_state.team_name, max_chars=12)
    league = st.radio("所属リーグを選ぶ", ["セ・リーグ", "パ・リーグ"], horizontal=True)
    
    with st.expander("獲得したメンバーを確認 (24名)", expanded=False):
        st.write("**【野手 9名】**")
        for b in st.session_state.my_batters:
            st.write(f"・ {b.name} ({b.team})")
        st.write("**【投手 15名】**")
        for p in st.session_state.my_pitchers:
            st.write(f"・ {p.name} ({p.team})")

    st.write("---")
    if st.button("🔥 143試合を開幕する", use_container_width=True, type="primary"):
        with st.spinner("ペナントレースをシミュレーション中..."):
            time.sleep(2) # 演出用の待機
        change_screen("season_result")

# --- ⑤ シーズン結果 ---
elif st.session_state.screen == "season_result":
    st.markdown(f"### {st.session_state.team_name} のシーズン結果")
    st.write("143試合のペナントレースが終了しました！")
    
    # 簡易的な勝敗シミュレーション（能力値の平均から勝率を微調整する擬似ロジック）
    avg_meet = sum([b.meet for b in st.session_state.my_batters]) / 9
    avg_control = sum([p.control for p in st.session_state.my_pitchers]) / 15
    team_power = (avg_meet + avg_control) / 2
    
    # 基準勝率を5割（71勝）とし、チーム力に応じて乱数を加味
    base_wins = int(71 + (team_power - 60) * 1.5 + random.randint(-10, 10))
    wins = max(30, min(110, base_wins))
    losses = 143 - wins
    win_rate = wins / 143

    # 順位判定
    rank = 6
    if win_rate > 0.58: rank = 1
    elif win_rate > 0.53: rank = 2
    elif win_rate > 0.50: rank = 3
    elif win_rate > 0.45: rank = 4
    elif win_rate > 0.40: rank = 5
    
    col1, col2, col3 = st.columns(3)
    col1.metric("最終順位", f"{rank} 位")
    col2.metric("勝利", f"{wins} 勝")
    col3.metric("敗北", f"{losses} 敗")
    
    st.write("---")
    if st.button("🔄 最初からやり直す", use_container_width=True):
        st.session_state.clear()
        st.rerun()
