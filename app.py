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

# --- 3. ドラフト（獲得/見送り）システムの実装 ---
def draft_phase(player_pool, target_roster_size=24):
    # 毎回異なる選手が登場するようにシャッフル
    random.shuffle(player_pool)
    my_team = []
    
    print(f"=== 新球団ドラフト開始（目標: {target_roster_size}名） ===")
    
    for player in player_pool:
        if len(my_team) >= target_roster_size:
            break
            
        print("-" * 40)
        print(f"【候補選手】 {player.name} （{player.team}）")
        
        if isinstance(player, Batter):
            print(f" [野手] ミート:{player.meet} | パワー:{player.power} | 走力:{player.speed}")
            print(f"        守備:{player.defense}")
        else:
            print(f" [投手] 制球:{player.control} | スタミナ:{player.stamina}")
            print(f"        球種:{player.pitches}")
            
        # プレイヤーに入力を促す（Webアプリ化する際はここの処理が画面上のボタンになります）
        while True:
            action = input("獲得しますか？ (y:獲得 / n:見送り) > ").strip().lower()
            if action in ['y', 'n']:
                break
                
        if action == 'y':
            my_team.append(player)
            print(f" ＞ {player.name} を獲得しました！ (現在: {len(my_team)}/{target_roster_size}名)")
        else:
            print(" ＞ 見送りました。")

    print("\n=== チーム編成完了 ===")
    print(f"【あなたのチームの所属選手（計{len(my_team)}名）】")
    for p in my_team:
        if isinstance(p, Batter):
            print(f" [野] {p.name}")
        else:
            print(f" [投] {p.name}")
            
    return my_team

# --- 実行部分 ---
if __name__ == "__main__":
    # 選手データを読み込み、ドラフトを開始する
    all_players = load_players()
    my_team = draft_phase(all_players, target_roster_size=24)
