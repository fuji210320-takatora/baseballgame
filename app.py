import streamlit as st
import pandas as pd
import random

# --- 1. データモデル（クラス）の定義 ---
class Player:
    def __init__(self, name, team):
        self.name = name
        self.team = team

class Batter(Player):
    def __init__(self, name, team, plate_appearances, meet, power, speed, defense):
        super().__init__(name, team)
        self.plate_appearances = plate_appearances
        self.meet = meet
        self.power = power
        self.speed = speed
        self.defense = defense

class Pitcher(Player):
    def __init__(self, name, team, control, stamina, pitches):
        super().__init__(name, team)
        self.control = control
        self.stamina = stamina
        self.pitches = pitches

# --- 2. Excelファイルからのデータ読み込み ---
@st.cache_data # 毎回Excelを読み込まないよう高速化
def load_players():
    # 野手データの読み込み
    df_batter = pd.read_excel("野手能力データ_最新.xlsx")
    batters_list = []
    for _, row in df_batter.iterrows():
        batters_list.append(Batter(
            name=row['選手名'],
            team=row['チーム'],
            plate_appearances=row['打席数'],
            meet=row['ミート'],
            power=row['パワー'],
            speed=row['走力'],
            defense=row['守備力']
        ))

    # 投手データの読み込み
    df_pitcher = pd.read_excel("投手能力データ_最新.xlsx")
    pitchers_list = []
    for _, row in df_pitcher.iterrows():
        pitchers_list.append(Pitcher(
            name=row['選手名'],
            team=row['チーム'],
            control=row['制球'],
            stamina=row['スタミナ'],
            pitches=row['球種ランク']
        ))
        
    return batters_list + pitchers_list

# --- 3. Streamlitでの画面構築と状態管理 ---
st.title("野球チームメーカー（開発中）")

# 初回のみ実行される初期化処理（ページをリロードしてもデータを保持する）
if "initialized" not in st.session_state:
    st.session_state.all_players = load_players()
    random.shuffle(st.session_state.all_players) # 選手をシャッフル
    st.session_state.my_team = []
    st.session_state.current_index = 0
    st.session_state.initialized = True

target_roster_size = 24

# 進行状況のチェック
if len(st.session_state.my_team) >= target_roster_size:
    # 24人集まった場合の画面
    st.success(f"チーム編成完了！ {target_roster_size}名の選手が集まりました。")
    st.subheader("【獲得選手一覧】")
    for p in st.session_state.my_team:
        if isinstance(p, Batter):
            st.write(f"⚾ [野] {p.name} ({p.team})")
        else:
            st.write(f"⚾ [投] {p.name} ({p.team})")
            
elif st.session_state.current_index >= len(st.session_state.all_players):
    st.error("候補選手がいなくなりました。")
    
else:
    # ドラフト継続中の画面
    player = st.session_state.all_players[st.session_state.current_index]
    
    st.subheader("現在の候補選手")
    st.markdown(f"### **{player.name}** （{player.team}）")
    
    # 選手の能力表示
    if isinstance(player, Batter):
        st.write("**[野手]**")
        st.write(f"ミート: **{player.meet}** | パワー: **{player.power}** | 走力: **{player.speed}**")
        st.write(f"守備: {player.defense}")
    else:
        st.write("**[投手]**")
        st.write(f"制球: **{player.control}** | スタミナ: **{player.stamina}**")
        st.write(f"球種: {player.pitches}")
        
    st.progress(len(st.session_state.my_team) / target_roster_size)
    st.write(f"現在の獲得人数: **{len(st.session_state.my_team)} / {target_roster_size} 名**")

    st.write("---")
    
    # ボタンの配置
    col1, col2 = st.columns(2)
    with col1:
        # 獲得ボタンが押されたらチームに追加し、次の選手へ
        if st.button("⭕ 獲得する", use_container_width=True):
            st.session_state.my_team.append(player)
            st.session_state.current_index += 1
            st.rerun() # 画面を再読み込みして更新
            
    with col2:
        # 見送りボタンが押されたらチームには追加せず、次の選手へ
        if st.button("❌ 見送る", use_container_width=True):
            st.session_state.current_index += 1
            st.rerun()
