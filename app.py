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
        # 起用法・成績用
        self.batting_order = None
        self.position = None
        self.stats = {"打率": 0.0, "本塁打": 0, "打点": 0, "盗塁": 0}

class Pitcher(Player):
    def __init__(self, name, team, control, stamina, pitches):
        super().__init__(name, team, "投手")
        self.control = control
        self.stamina = stamina
        self.pitches = pitches
        # 起用法・成績用
        self.pitcher_role = "中継ぎ" # デフォルト
        self.stats = {"防御率": 0.0, "勝利": 0, "敗北": 0, "セーブ": 0, "ホールド": 0}

# ==========================================
# 2. 初期化と画面遷移
# ==========================================
st.set_page_config(page_title="野球チームメーカー", layout="wide")

if "screen" not in st.session_state:
    # デバッグ用に仮の選手データを生成（実際のExcel読み込みに差し替えてください）
    st.session_state.my_batters = [Batter(f"野手{i}", "架空", random.randint(40,90), random.randint(40,90), random.randint(40,90), "外") for i in range(1, 10)]
    st.session_state.my_pitchers = [Pitcher(f"投手{i}", "架空", random.randint(40,90), random.randint(40,90), "直球") for i in range(1, 16)]
    
    st.session_state.screen = "setup" # ドラフトを省略し、直接セットアップ画面へ
    st.session_state.team_name = "マイチーム"

def change_screen(new_screen):
    st.session_state.screen = new_screen
    st.rerun()

# ==========================================
# 3. シミュレーションロジック
# ==========================================
def simulate_season():
    # 野手の成績生成（能力値に基づく簡易計算）
    for b in st.session_state.my_batters:
        base_avg = 0.200 + (b.meet / 100) * 0.120 + random.uniform(-0.03, 0.03)
        b.stats["打率"] = round(max(0.150, min(0.380, base_avg)), 3)
        b.stats["本塁打"] = int((b.power / 100) ** 2 * 40 + random.randint(0, 10))
        b.stats["打点"] = int(b.stats["本塁打"] * 2.5 + random.randint(20, 40))
        b.stats["盗塁"] = int((b.speed / 100) * 30 + random.randint(0, 5))

    # 投手の成績生成
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

# ==========================================
# 4. オーダー画像生成ロジック (Pillow)
# ==========================================
def generate_lineup_image():
    # 800x600のキャンバスを作成
    img = Image.new('RGB', (600, 700), color=(30, 40, 50))
    draw = ImageDraw.Draw(img)
    
    # フォントの設定（環境に合わせてパスを変更するか、デフォルトフォントを使用）
    try:
        # WindowsやMacの標準日本語フォントを指定
        font_title = ImageFont.truetype("msgothic.ttc", 36)
        font_text = ImageFont.truetype("msgothic.ttc", 24)
    except:
        font_title = font_text = ImageFont.load_default()

    draw.text((20, 20), f"{st.session_state.team_name} - スターティングオーダー", font=font_title, fill=(255, 255, 255))
    
    # 打順でソート
    starters = sorted([b for b in st.session_state.my_batters if b.batting_order], key=lambda x: x.batting_order)
    
    y_offset = 100
    for b in starters:
        text = f"{b.batting_order}番 [{b.position}] {b.name}"
        draw.text((40, y_offset), text, font=font_text, fill=(200, 230, 255))
        y_offset += 45
        
    y_offset += 20
    draw.line((40, y_offset, 560, y_offset), fill=(100, 100, 100), width=2)
    y_offset += 20
    
    # 先発投手を1名抽出
    sp = next((p for p in st.session_state.my_pitchers if p.pitcher_role == "先発"), None)
    sp_name = sp.name if sp else "未設定"
    draw.text((40, y_offset), f"先発投手: {sp_name}", font=font_text, fill=(255, 200, 200))
    
    # 画像をメモリ上のバイナリに変換
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ==========================================
# 5. UI描画
# ==========================================

# --- 打順・起用法セットアップ画面 ---
if st.session_state.screen == "setup":
    st.title("シーズン開始前: オーダーと起用法の決定")
    st.session_state.team_name = st.text_input("チーム名", value=st.session_state.team_name)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("打順・守備位置 (野手9名)")
        positions_list = ["捕", "一", "二", "三", "遊", "左", "中", "右", "指"]
        
        for i, batter in enumerate(st.session_state.my_batters):
            c_ord, c_pos, c_name = st.columns([2, 3, 5])
            with c_ord:
                # 1〜9番を割り当て
                batter.batting_order = st.selectbox(f"打順", range(1, 10), index=i, key=f"ord_{i}", label_visibility="collapsed")
            with c_pos:
                # 守備位置を割り当て
                batter.position = st.selectbox("守備", positions_list, index=i, key=f"pos_{i}", label_visibility="collapsed")
            with c_name:
                st.write(f"**{batter.name}** (ミート:{batter.meet} パワー:{batter.power})")

    with col2:
        st.subheader("投手起用法 (投手15名)")
        roles_list = ["先発", "中継ぎ", "セットアッパー", "抑え"]
        
        for i, pitcher in enumerate(st.session_state.my_pitchers):
            c_role, c_name = st.columns([4, 6])
            with c_role:
                # 先発を6人、抑えを1人に自動割り当て（初期値）
                def_index = 0 if i < 6 else (3 if i == 14 else 1)
                pitcher.pitcher_role = st.selectbox("起用法", roles_list, index=def_index, key=f"role_{i}", label_visibility="collapsed")
            with c_name:
                st.write(f"**{pitcher.name}** (制球:{pitcher.control} スタミナ:{pitcher.stamina})")

    st.write("---")
    if st.button("🔥 143試合をシミュレーションして開幕", type="primary", use_container_width=True):
        simulate_season()
        change_screen("result")

# --- 個人成績・画像化 結果画面 ---
elif st.session_state.screen == "result":
    st.title(f"{st.session_state.team_name} - シーズン結果")
    
    tab1, tab2, tab3 = st.tabs(["打撃成績", "投手成績", "オーダー画像化"])
    
    with tab1:
        st.subheader("野手 個人成績")
        # DataFrame化してテーブル表示
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
    if st.button("戻る", use_container_width=True):
        change_screen("setup")
