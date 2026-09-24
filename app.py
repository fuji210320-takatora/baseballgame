import streamlit as st
import pandas as pd
import random
import io
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. データモデルの定義（成績・起用法の属性を追加）
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
        self.batting_order = None
        self.position = None
        self.stats = {"打率": 0.0, "本塁打": 0, "打点": 0, "盗塁": 0}

class Pitcher(Player):
    def __init__(self, name, team, control, stamina, pitches):
        super().__init__(name, team, "投手")
        self.control = control
        self.stamina = stamina
        self.pitches = pitches
        self.pitcher_role = "中継ぎ"
        self.stats = {"防御率": 0.0, "勝利": 0, "敗北": 0, "セーブ": 0, "ホールド": 0}

# ==========================================
# 2. Excelからのデータ読み込み
# ==========================================
@st.cache_data
def load_players():
    # 実際の環境にExcelファイルがある前提で読み込みます
    try:
        df_b = pd.read_excel("野手能力データ_最新.xlsx")
        batters = [Batter(row['選手名'], row['チーム'], row['ミート'], row['パワー'], row['走力'], row['守備力']) for _, row in df_b.iterrows()]
        
        df_p = pd.read_excel("投手能力データ_最新.xlsx")
        pitchers = [Pitcher(row['選手名'], row['チーム'], row['制球'], row['スタミナ'], row['球種ランク']) for _, row in df_p.iterrows()]
    except:
        # Excelが無い場合のフォールバック（テスト用）
        st.error("Excelファイルが見つかりません。")
        batters = []
        pitchers = []
        
    return batters, pitchers

# ==========================================
# 3. アプリの初期化と状態管理
# ==========================================
st.set_page_config(page_title="野球チームメーカー", page_icon="🏟", layout="wide")

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
    st.session_state.team_name = "マイチーム"

def change_screen(new_screen):
    st.session_state.screen = new_screen
    st.session_state.pool_idx = 0
    st.rerun()

# ==========================================
# 4. シミュレーション & 画像生成ロジック
# ==========================================
def simulate_season():
    for b in st.session_state.my_batters:
        base_avg = 0.200 + (b.meet / 100) * 0.120 + random.uniform(-0.03, 0.03)
        b.stats["打率"] = round(max(0.150, min(0.380, base_avg)), 3)
        b.stats["本塁打"] = int((b.power / 100) ** 2 * 40 + random.randint(0, 10))
        b.stats["打点"] = int(b.stats["本塁打"] * 2.5 + random.randint(20, 40))
        b.stats["盗塁"] = int((b.speed / 100) * 30 + random.randint(0, 5))

    for p in st.session_state.my_pitchers:
        base_era = 5.00 - (p.control / 100) * 2.5 + random.uniform(-0.5, 1.0)
        p.stats["防御率"] = round(max(1.00, min(8.00, base_era)), 2)
        
        if p.pitcher_role == "先発":
            p.stats["勝利"] = int((p.stamina / 100) * 15 + random.randint(0, 5))
            p.stats["敗北"] = int((100 - p.control) / 100 * 10 + random.randint(0, 5))
        elif p.pitcher_role == "抑え":
            p.stats["セーブ"] = int((p.control / 100) * 35 + random.randint(0, 10))
        else:
            p.stats["ホールド"] = int((p.control / 100) * 30 + random.randint(0, 10))

def generate_lineup_image():
    img = Image.new('RGB', (600, 700), color=(30, 40, 50))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("msgothic.ttc", 36)
        font_text = ImageFont.truetype("msgothic.ttc", 24)
    except:
        font_title = font_text = ImageFont.load_default()

    draw.text((20, 20), f"{st.session_state.team_name} - スターティングオーダー", font=font_title, fill=(255, 255, 255))
    starters = sorted([b for b in st.session_state.my_batters if b.batting_order], key=lambda x: x.batting_order)
    
    y_offset = 100
    for b in starters:
        text = f"{b.batting_order}番 [{b.position}] {b.name}"
        draw.text((40, y_offset), text, font=font_text, fill=(200, 230, 255))
        y_offset += 45
        
    y_offset += 20
    draw.line((40, y_offset, 560, y_offset), fill=(100, 100, 100), width=2)
    y_offset += 20
    
    sp = next((p for p in st.session_state.my_pitchers if p.pitcher_role == "先発"), None)
    sp_name = sp.name if sp else "未設定"
    draw.text((40, y_offset), f"先発投手: {sp_name}", font=font_text, fill=(255, 200, 200))
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ==========================================
# 5. UI（画面遷移）
# ==========================================

# --- ① トップ画面 ---
if st.session_state.screen == "top":
    st.markdown("<h1 style='text-align: center;'>野球チームメーカー</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>ランダムに現れる選手を取捨選択して、24人のチームを作れ！</p>", unsafe_allow_html=True)
    if st.button("⚾ ゲーム開始", use_container_width=True, type="primary"):
        change_screen("draft_batter")

# --- ② 野手を獲得 ---
elif st.session_state.screen == "draft_batter":
    st.subheader(f"野手を獲得 ({len(st.session_state.my_batters)} / 9)")
    st.progress(len(st.session_state.my_batters) / 9.0)
    st.write(f"見送り残り：**{st.session_state.b_passes}** 回")
    
    if len(st.session_state.my_batters) >= 9:
        st.success("野手9人が揃いました！次は投手を集めます。")
        if st.button("投手の獲得へ進む", use_container_width=True, type="primary"):
            change_screen("draft_pitcher")
    else:
        player = st.session_state.batters_pool[st.session_state.pool_idx]
        st.markdown(f"### {player.name} <span style='font-size: 0.6em; color: gray;'>({player.team})</span>", unsafe_allow_html=True)
        st.write(f"ミート: **{player.meet}** | パワー: **{player.power}** | 走力: **{player.speed}**")
        st.write(f"守備: {player.defense}")
        
        col1, col2 = st.columns(2)
        with col1:
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
    
    if len(st.session_state.my_pitchers) >= 15:
        st.success("投手15人が揃いました！24人のチームが完成です。")
        if st.button("シーズン準備へ進む", use_container_width=True, type="primary"):
            change_screen("setup")
    else:
        player = st.session_state.pitchers_pool[st.session_state.pool_idx]
        st.markdown(f"### {player.name} <span style='font-size: 0.6em; color: gray;'>({player.team})</span>", unsafe_allow_html=True)
        st.write(f"制球: **{player.control}** | スタミナ: **{player.stamina}**")
        st.write(f"球種: {player.pitches}")
        
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

# --- ④ シーズン開始前 (打順・起用法セットアップ) ---
elif st.session_state.screen == "setup":
    st.title("シーズン開始前: オーダーと起用法の決定")
    st.session_state.team_name = st.text_input("チーム名", value=st.session_state.team_name)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("打順・守備位置 (野手9名)")
        positions_list = ["捕", "一", "二", "三", "遊", "左", "中", "右", "指"]
        for i, batter in enumerate(st.session_state.my_batters):
            c_ord, c_pos, c_name = st.columns([2, 3, 5])
            with c_ord:
                batter.batting_order = st.selectbox(f"打順", range(1, 10), index=i, key=f"ord_{i}", label_visibility="collapsed")
            with c_pos:
                batter.position = st.selectbox("守備", positions_list, index=i, key=f"pos_{i}", label_visibility="collapsed")
            with c_name:
                st.write(f"**{batter.name}**")

    with col2:
        st.subheader("投手起用法 (投手15名)")
        roles_list = ["先発", "中継ぎ", "セットアッパー", "抑え"]
        for i, pitcher in enumerate(st.session_state.my_pitchers):
            c_role, c_name = st.columns([4, 6])
            with c_role:
                def_index = 0 if i < 6 else (3 if i == 14 else 1)
                pitcher.pitcher_role = st.selectbox("起用法", roles_list, index=def_index, key=f"role_{i}", label_visibility="collapsed")
            with c_name:
                st.write(f"**{pitcher.name}**")

    st.write("---")
    if st.button("🔥 143試合をシミュレーションして開幕", type="primary", use_container_width=True):
        simulate_season()
        change_screen("result")

# --- ⑤ 個人成績・画像化 結果画面 ---
elif st.session_state.screen == "result":
    st.title(f"{st.session_state.team_name} - シーズン結果")
    
    tab1, tab2, tab3 = st.tabs(["打撃成績", "投手成績", "オーダー画像化"])
    
    with tab1:
        st.subheader("野手 個人成績")
        batter_data = []
        for b in sorted(st.session_state.my_batters, key=lambda x: x.batting_order):
            row = {"打順": b.batting_order, "守備": b.position, "選手名": b.name}
            row.update(b.stats)
            batter_data.append(row)
        st.dataframe(pd.DataFrame(batter_data), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("投手 個人成績")
        pitcher_data = []
        for p in st.session_state.my_pitchers:
            row = {"起用法": p.pitcher_role, "選手名": p.name}
            row.update(p.stats)
            pitcher_data.append(row)
        st.dataframe(pd.DataFrame(pitcher_data), use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("スターティングオーダーの画像化")
        img_bytes = generate_lineup_image()
        st.image(img_bytes, caption="生成されたオーダー画像", width=400)
        st.download_button(
            label="📷 画像を保存 (ダウンロード)",
            data=img_bytes,
            file_name=f"{st.session_state.team_name}_order.png",
            mime="image/png",
            type="primary"
        )
        
    st.write("---")
    if st.button("🔄 最初からやり直す", use_container_width=True):
        st.session_state.clear()
        st.rerun()
