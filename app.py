import streamlit as st
import pandas as pd
import random

# ==========================================
# 0. カスタムCSSの定義（スクリーンショットのデザインを再現）
# ==========================================
def inject_custom_css():
    st.markdown("""
    <style>
    /* 全体の背景色をアプリに近いオフホワイトに */
    .stApp {
        background-color: #f7f6f0;
    }
    
    /* トップページのタイトル・ルール周り */
    .title-sub { font-size: 12px; color: #888; text-align: center; letter-spacing: 2px; margin-bottom: 0; }
    .title-main { font-size: 32px; font-weight: 900; text-align: center; margin-top: 0; margin-bottom: 24px; }
    .rule-box { background: transparent; border-top: 1px solid #ddd; padding-top: 16px; font-size: 14px; }
    .rule-item { border-bottom: 1px solid #eee; padding: 12px 0; display: flex; }
    .rule-num { color: #888; font-weight: bold; margin-right: 12px; }
    .disclaimer { font-size: 11px; color: #666; background: white; padding: 12px; border: 1px solid #ddd; margin-top: 24px; }

    /* 選手カードのデザイン */
    .player-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        margin-bottom: 16px;
        border: 1px solid #eee;
    }
    .player-pos-badge { background: #1a5a5a; color: white; padding: 4px 12px; border-radius: 16px; font-size: 12px; font-weight: bold; display: inline-block; margin-bottom: 8px;}
    .player-name { font-size: 28px; font-weight: 900; margin: 0 0 4px 0; color: #222;}
    .player-sub { font-size: 13px; color: #666; margin-bottom: 16px; }
    
    /* 1軍・2軍成績ボックス */
    .stats-row { background: #f9f9f6; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 8px; display: flex; align-items: center;}
    .stats-badge { background: #2a6642; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 12px; font-weight: bold;}
    .stats-badge-sub { background: #dcdcdc; color: #333; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 12px; font-weight: bold;}
    
    /* 能力値（ミート、パワー等）の四角いボックス */
    .attr-container { display: flex; justify-content: space-between; margin-top: 16px; gap: 4px;}
    .attr-box { border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 4px; text-align: center; flex: 1; background: #fafafa;}
    .attr-label { font-size: 10px; color: #666; margin-bottom: 2px;}
    .attr-grade { font-size: 22px; font-weight: 900; margin-bottom: 2px;}
    .attr-val { font-size: 11px; color: #888;}
    
    /* アルファベットの色分け */
    .grade-S { color: #e6b422; }
    .grade-A { color: #c93a3a; }
    .grade-B { color: #c25953; }
    .grade-C { color: #d48a35; }
    .grade-D { color: #3a82c9; }
    .grade-E, .grade-F, .grade-G { color: #666; }

    /* 見送り・取るボタンの配色オーバーライド */
    div[data-testid="column"]:nth-child(1) button {
        background-color: #b03535 !important;
        color: white !important;
        border: none !important;
        height: 60px;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
    }
    div[data-testid="column"]:nth-child(2) button {
        background-color: #2a6642 !important;
        color: white !important;
        border: none !important;
        height: 60px;
        font-size: 18px !important;
        font-weight: bold !important;
        border-radius: 8px !important;
    }
    
    /* ヘッダーのステータス表示 */
    .status-bar { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid #ddd; padding-bottom: 12px; margin-bottom: 16px;}
    .status-count { font-size: 24px; font-weight: bold; }
    .status-left { font-size: 13px; color: #666; }
    .pass-pill { background: #fbebeb; color: #b03535; padding: 6px 12px; border-radius: 16px; font-size: 13px; font-weight: bold; border: 1px solid #fad4d4;}

    /* リストアイテム（打順・起用法）のカード化 */
    .list-card { background: white; border: 1px solid #eee; border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.02);}
    .list-num { font-size: 20px; font-weight: bold; width: 40px; text-align: center; background: #f0f0f0; padding: 8px; border-radius: 6px; margin-right: 12px;}
    .list-info { flex: 1; }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 1. ユーティリティとデータモデル
# ==========================================
def val_to_grade(val):
    if val >= 90: return "S", "grade-S"
    elif val >= 80: return "A", "grade-A"
    elif val >= 70: return "B", "grade-B"
    elif val >= 60: return "C", "grade-C"
    elif val >= 50: return "D", "grade-D"
    elif val >= 40: return "E", "grade-E"
    elif val >= 30: return "F", "grade-F"
    else: return "G", "grade-G"

def generate_dummy_profile():
    prefs = ["東京都", "大阪府", "愛知県", "福岡県", "北海道", "広島県", "宮城県", "神奈川県"]
    return random.choice(prefs), random.randint(18, 38)

class Player:
    def __init__(self, name, team, role):
        self.name = name
        self.team = team
        self.role = role
        self.pref, self.age = generate_dummy_profile()

class Batter(Player):
    def __init__(self, name, team, meet, power, speed, defense):
        super().__init__(name, team, "野手")
        self.meet = meet
        self.power = power
        self.speed = speed
        self.defense = defense
        self.batting_order = None
        self.position = None
        self.stats = {"打率": 0.0, "本塁打": 0, "打点": 0}

class Pitcher(Player):
    def __init__(self, name, team, control, stamina, pitches):
        super().__init__(name, team, "投手")
        self.control = control
        self.stamina = stamina
        self.pitches = pitches
        self.pitcher_role = "中継ぎ"
        self.stats = {"防御率": 0.0, "勝利": 0, "敗北": 0}

@st.cache_data
def load_players():
    try:
        df_b = pd.read_excel("野手能力データ_最新.xlsx")
        batters = [Batter(row['選手名'], row['チーム'], row['ミート'], row['パワー'], row['走力'], row['守備力']) for _, row in df_b.iterrows()]
        
        df_p = pd.read_excel("投手能力データ_最新.xlsx")
        pitchers = [Pitcher(row['選手名'], row['チーム'], row['制球'], row['スタミナ'], row['球種ランク']) for _, row in df_p.iterrows()]
    except:
        st.error("Excelファイルが見つかりません。")
        batters, pitchers = [], []
    return batters, pitchers

# ==========================================
# 2. 初期化と画面管理
# ==========================================
st.set_page_config(page_title="野球チームメーカー", layout="centered", initial_sidebar_state="collapsed")
inject_custom_css()

if "screen" not in st.session_state:
    batters, pitchers = load_players()
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

def change_screen(new_screen):
    st.session_state.screen = new_screen
    st.session_state.pool_idx = 0
    st.rerun()

# ==========================================
# 3. 画面描画ロジック
# ==========================================

# --- ① トップ画面 ---
if st.session_state.screen == "top":
    st.markdown("<p class='title-sub'>BASEBALL TEAM BUILDER</p>", unsafe_allow_html=True)
    st.markdown("<h1 class='title-main'>野球チームメーカー</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 14px; margin-bottom: 40px;'>ランダムに現れる選手を取捨選択して、<br>24人のチームを作れ！</p>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class='rule-box'>
        <div style='font-size: 12px; color: #666; margin-bottom: 8px;'>ルール</div>
        <div class='rule-item'><span class='rule-num'>1</span>架空の選手がポジション関係なく完全ランダムで1人ずつ登場</div>
        <div class='rule-item'><span class='rule-num'>2</span>できるのは「<b>取る</b>」か「<b>見送る</b>」だけ</div>
        <div class='rule-item'><span class='rule-num'>3</span>まず<b>野手9人</b>（見送り5回まで）</div>
        <div class='rule-item'><span class='rule-num'>4</span>つぎに<b>投手15人</b>（先発6人・救援9人をセットで選ぶ）</div>
        <div class='rule-item'><span class='rule-num'>5</span>役割を決め、打順を組んで<b>143試合</b>を戦う</div>
        <div class='rule-item'><span class='rule-num'>6</span>シーズン中は選手が急に伸びたり、不調に落ちたりする</div>
    </div>
    
    <div class='disclaimer'>
        本サイトは日本野球機構（NPB）・各球団・選手本人とは関係のない非公式のファンサイトです。選手名・成績・能力値はすべて本ゲームのための架空のもので、実在の選手とは関係ありません。
    </div>
    """, unsafe_allow_html=True)
    
    st.write("")
    if st.button("ゲーム開始", use_container_width=True, type="primary"):
        change_screen("draft_batter")

# --- ② 野手を獲得 ---
elif st.session_state.screen == "draft_batter":
    c_count = len(st.session_state.my_batters)
    st.markdown(f"""
    <div class='status-bar'>
        <div>
            <div style='font-size: 12px; font-weight: bold;'>野手を獲得</div>
            <span class='status-count'>{c_count} / 9</span> <span class='status-left'>あと{9 - c_count}人</span>
        </div>
        <div class='pass-pill'>見送り残り：{st.session_state.b_passes}回</div>
    </div>
    """, unsafe_allow_html=True)
    
    if c_count >= 9:
        st.success("野手9人が揃いました！")
        if st.button("投手の獲得へ進む", use_container_width=True, type="primary"):
            change_screen("draft_pitcher")
    else:
        player = st.session_state.batters_pool[st.session_state.pool_idx]
        m_grade, m_cls = val_to_grade(player.meet)
        p_grade, p_cls = val_to_grade(player.power)
        s_grade, s_cls = val_to_grade(player.speed)
        
        # 選手カードUI
        st.markdown(f"""
        <div class='player-card'>
            <div class='player-pos-badge'>野手</div>
            <h2 class='player-name'>{player.name}</h2>
            <div class='player-sub'>{player.pref} {player.age}歳 <br>所属: {player.team}</div>
            
            <div class='stats-row'>
                <span class='stats-badge'>一軍</span> 打率 .249  本 0  点 5  OPS .646
            </div>
            <div class='stats-row'>
                <span class='stats-badge-sub'>二軍</span> 打率 .346  本 0  点 5  OPS .842
            </div>
            
            <div class='attr-container'>
                <div class='attr-box'><div class='attr-label'>ミート</div><div class='attr-grade {m_cls}'>{m_grade}</div><div class='attr-val'>{player.meet}</div></div>
                <div class='attr-box'><div class='attr-label'>パワー</div><div class='attr-grade {p_cls}'>{p_grade}</div><div class='attr-val'>{player.power}</div></div>
                <div class='attr-box'><div class='attr-label'>走力</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{player.speed}</div></div>
            </div>
            <div style='margin-top: 16px; font-size: 13px; color: #555; border-top: 1px dashed #ddd; padding-top: 12px;'>
                守れる所： <b>{player.defense}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"見送る\n残り {st.session_state.b_passes} 回", use_container_width=True, disabled=(st.session_state.b_passes <= 0)):
                st.session_state.b_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button(f"取る\nチームに加える", use_container_width=True):
                st.session_state.my_batters.append(player)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ③ 投手を獲得 ---
elif st.session_state.screen == "draft_pitcher":
    c_count = len(st.session_state.my_pitchers)
    st.markdown(f"""
    <div class='status-bar'>
        <div>
            <div style='font-size: 12px; font-weight: bold;'>投手を獲得</div>
            <span class='status-count'>{c_count} / 15</span> <span class='status-left'>あと{15 - c_count}人</span>
        </div>
        <div class='pass-pill'>見送り残り：{st.session_state.p_passes}回</div>
    </div>
    """, unsafe_allow_html=True)
    
    if c_count >= 15:
        st.success("投手15人が揃いました！")
        if st.button("シーズン準備へ進む", use_container_width=True, type="primary"):
            change_screen("setup")
    else:
        player = st.session_state.pitchers_pool[st.session_state.pool_idx]
        c_grade, c_cls = val_to_grade(player.control)
        s_grade, s_cls = val_to_grade(player.stamina)
        
        st.markdown(f"""
        <div class='player-card'>
            <div class='player-pos-badge'>投手</div>
            <h2 class='player-name'>{player.name}</h2>
            <div class='player-sub'>{player.pref} {player.age}歳 <br>所属: {player.team}</div>
            
            <div class='stats-row'>
                <span class='stats-badge'>一軍</span> 防御率 2.52  奪三振 32
            </div>
            
            <div class='attr-container'>
                <div class='attr-box'><div class='attr-label'>制球</div><div class='attr-grade {c_cls}'>{c_grade}</div><div class='attr-val'>{player.control}</div></div>
                <div class='attr-box'><div class='attr-label'>スタミナ</div><div class='attr-grade {s_cls}'>{s_grade}</div><div class='attr-val'>{player.stamina}</div></div>
            </div>
            <div style='margin-top: 16px; font-size: 12px; color: #555; border-top: 1px dashed #ddd; padding-top: 12px; line-height: 1.5;'>
                球種： <b>{player.pitches}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"見送る\n残り {st.session_state.p_passes} 回", use_container_width=True, disabled=(st.session_state.p_passes <= 0)):
                st.session_state.p_passes -= 1
                st.session_state.pool_idx += 1
                st.rerun()
        with col2:
            if st.button(f"取る\nチームに加える", use_container_width=True):
                st.session_state.my_pitchers.append(player)
                st.session_state.pool_idx += 1
                st.rerun()

# --- ④ シーズン開始前 (打順・起用法セットアップ) ---
elif st.session_state.screen == "setup":
    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-bottom: 24px;'>打順・守備位置</h2>", unsafe_allow_html=True)
    
    positions_list = ["捕手", "一塁手", "二塁手", "三塁手", "遊撃手", "左翼手", "中堅手", "右翼手", "指名打者"]
    
    for i, batter in enumerate(st.session_state.my_batters):
        st.markdown(f"""
        <div style='background: white; border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; align-items: center;'>
            <div style='font-size: 24px; font-weight: 900; width: 40px; text-align: center; background: #f0f0f0; border-radius: 4px; padding: 8px 0; margin-right: 16px;'>{i+1}<span style='font-size:10px; display:block; font-weight: normal;'>番</span></div>
            <div style='flex: 1;'>
                <div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{batter.name}</div>
                <div style='font-size: 11px; color: #888;'>{batter.pref}・{batter.age}歳</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # セレクトボックスはHTMLに埋め込めないので通常のStreamlitウィジェットで配置
        batter.position = st.selectbox(f"{batter.name}の守備位置", positions_list, index=i%9, label_visibility="collapsed", key=f"pos_{i}")

    st.markdown("<h2 style='font-size: 20px; font-weight: bold; margin-top: 32px; margin-bottom: 24px;'>投手の役割</h2>", unsafe_allow_html=True)
    roles_list = ["先発", "僅差", "ビハインド", "セットアッパー", "抑え"]
    
    for i, pitcher in enumerate(st.session_state.my_pitchers):
        st.markdown(f"""
        <div style='background: white; border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 8px;'>
            <div style='font-weight: bold; font-size: 16px; margin-bottom: 2px;'>{pitcher.name}</div>
            <div style='font-size: 11px; color: #888;'>{pitcher.pref}・{pitcher.age}歳</div>
        </div>
        """, unsafe_allow_html=True)
        def_index = 0 if i < 6 else (4 if i == 14 else 1)
        pitcher.pitcher_role = st.selectbox(f"{pitcher.name}の起用法", roles_list, index=def_index, label_visibility="collapsed", key=f"role_{i}")

    st.write("---")
    if st.button("開幕", type="primary", use_container_width=True):
        change_screen("result")

# --- ⑤ シーズン結果 (簡易版) ---
elif st.session_state.screen == "result":
    st.markdown("<h2 style='text-align: center;'>シーズン終了</h2>", unsafe_allow_html=True)
    st.write("143試合が終了しました（シミュレーション結果）。")
    
    if st.button("最初からやり直す", use_container_width=True):
        st.session_state.clear()
        st.rerun()
