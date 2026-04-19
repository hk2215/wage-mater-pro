import flet as ft
import time
import threading
import json
import os
from datetime import datetime

# データを保存するファイル名
DATA_FILE = "time_wage_data.json"

# ==========================================
# 1. データベース（JSONファイル）の読み書き機能
# ==========================================
def load_db():
    default_db = {
        "settings": {
            "base_wage": 1200.0, 
            "target_amount": 5000.0,
            # ★ 加算枠をリスト形式に変更（何個でも追加可能に）
            "bonuses": [
                {"start": "18:00", "end": "20:00", "amt": 20.0},
                {"start": "20:00", "end": "22:00", "amt": 30.0}
            ]
        },
        "state": {
            "running": False, 
            "last_time": None, 
            "accumulated_seconds": 0.0, 
            "accumulated_earned": 0.0
        },
        "logs": {}
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded_db = json.load(f)
                
                # 古いバージョンの設定データ（b1_start等）がある場合、新しいリスト形式に自動変換
                loaded_settings = loaded_db.get("settings", {})
                if "b1_start" in loaded_settings:
                    bonuses = []
                    if loaded_settings.get("b1_start"):
                        bonuses.append({"start": loaded_settings["b1_start"], "end": loaded_settings["b1_end"], "amt": loaded_settings.get("b1_amt", 0)})
                    if loaded_settings.get("b2_start"):
                        bonuses.append({"start": loaded_settings["b2_start"], "end": loaded_settings["b2_end"], "amt": loaded_settings.get("b2_amt", 0)})
                    loaded_settings["bonuses"] = bonuses
                    # 古いキーを削除
                    for key in ["b1_start", "b1_end", "b1_amt", "b2_start", "b2_end", "b2_amt"]:
                        loaded_settings.pop(key, None)

                default_db["settings"].update(loaded_settings)
                default_db["state"].update(loaded_db.get("state", {}))
                default_db["logs"] = loaded_db.get("logs", {})
                return default_db
        except Exception:
            pass
    return default_db

def save_db(db):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存エラー: {e}")

# ==========================================
# 2. メインアプリ
# ==========================================
def main(page: ft.Page):
    page.title = "時給メーター Pro"
    page.theme_mode = ft.ThemeMode.LIGHT

    db = load_db()
    settings = db["settings"]
    state = db["state"]
    logs = db["logs"]

    def show_msg(msg):
        snack = ft.SnackBar(content=ft.Text(msg))
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # --- UIパーツ ---
    amount_text = ft.Text("¥ 0", size=65, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800)
    timer_text = ft.Text("00:00:00", size=20, color=ft.Colors.GREY_700)
    current_wage_text = ft.Text("現在の時給: ¥ ---", size=14, color=ft.Colors.ORANGE_600, weight=ft.FontWeight.BOLD)
    progress_ring = ft.ProgressRing(value=0, width=250, height=250, stroke_width=10, color=ft.Colors.BLUE)

    btn_start = ft.Button("開始", icon=ft.Icons.PLAY_ARROW, disabled=state["running"], style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE))
    btn_pause = ft.Button("一時停止", icon=ft.Icons.PAUSE, disabled=not state["running"], style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_500, color=ft.Colors.WHITE))
    btn_finish = ft.Button("勤務終了（記録）", icon=ft.Icons.SAVE, width=220, height=50)

    # --- 時給計算ロジック ---
    def get_parsed_bonuses():
        parsed = []
        for b in settings.get("bonuses", []):
            if b.get("start") and b.get("end") and b.get("amt", 0) > 0:
                try:
                    st = datetime.strptime(b["start"], "%H:%M").time()
                    et = datetime.strptime(b["end"], "%H:%M").time()
                    parsed.append((st, et, float(b["amt"])))
                except ValueError:
                    pass
        return parsed

    def get_wage_at_time(check_time, base, parsed_bonuses):
        wage = base
        for st, et, amt in parsed_bonuses:
            if st <= et:
                if st <= check_time <= et:
                    wage += amt
            else:
                if check_time >= st or check_time <= et:
                    wage += amt
        return wage

    def add_earned_time(now_t):
        if state.get("last_time") is None:
            return
        delta = now_t - state["last_time"]
        if delta <= 0:
            return
            
        base = settings["base_wage"]
        bonuses = get_parsed_bonuses()
        
        start_ts = state["last_time"]
        total_add = 0.0
        for i in range(int(delta)):
            current_time = datetime.fromtimestamp(start_ts + i).time()
            wage = get_wage_at_time(current_time, base, bonuses)
            total_add += (wage / 3600)
            
        rem = delta - int(delta)
        total_add += (base / 3600) * rem
        
        state["accumulated_earned"] += total_add
        state["accumulated_seconds"] += delta
        state["last_time"] = now_t

    # --- ロジック ---
    def toggle_timer(is_start):
        now_t = time.time()
        if is_start:
            state["last_time"] = now_t
        else:
            add_earned_time(now_t)
            state["last_time"] = None
            
        state["running"] = is_start
        save_db(db) 
        btn_start.disabled = is_start
        btn_pause.disabled = not is_start
        page.update()

    btn_start.on_click = lambda e: toggle_timer(True)
    btn_pause.on_click = lambda e: toggle_timer(False)

    def finish_session(e):
        if state["running"]:
            add_earned_time(time.time())
            
        earned = state["accumulated_earned"]
        if earned > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            logs[today] = logs.get(today, 0) + int(earned)
        
        state.update({"running": False, "last_time": None, "accumulated_seconds": 0.0, "accumulated_earned": 0.0})
        save_db(db)
        
        btn_start.disabled = False
        btn_pause.disabled = True
        show_msg("本日の収入を記録しました！お疲れ様です。")
        page.update()

    btn_finish.on_click = finish_session

    def clear_logs(e):
        db["logs"] = {}
        logs.clear()
        save_db(db)
        show_msg("履歴を削除しました")
        page.run_task(page.push_route, "/")

    # --- タイマースレッド ---
    def update_timer():
        while True:
            if state["running"]:
                add_earned_time(time.time())

            if page.route == "/" or page.route == "":
                earned = state["accumulated_earned"]
                amount_text.value = f"¥ {int(earned)}"
                
                total_sec = state["accumulated_seconds"]
                hrs, rem = divmod(int(total_sec), 3600)
                mins, secs = divmod(rem, 60)
                timer_text.value = f"{hrs:02d}:{mins:02d}:{secs:02d}"
                
                current_time = datetime.now().time()
                current_wage = get_wage_at_time(current_time, settings["base_wage"], get_parsed_bonuses())
                current_wage_text.value = f"現在の時給: ¥ {int(current_wage):,}"
                
                target = settings["target_amount"]
                progress_ring.value = min(earned / target, 1.0) if target > 0 else 0
                
                try:
                    page.update()
                except Exception:
                    pass
                
            time.sleep(1)

    # --- 設定メニュー (Drawer) 動的構築 ---
    wage_input = ft.TextField(label="基本時給 (円)", value=str(int(settings["base_wage"])), keyboard_type=ft.KeyboardType.NUMBER)
    target_input = ft.TextField(label="1日の目標金額 (円)", value=str(int(settings["target_amount"])), keyboard_type=ft.KeyboardType.NUMBER)
    
    # 動的に追加・削除されるUIパーツを管理するリスト
    bonus_ui_items = []
    bonus_list_column = ft.Column(spacing=15)

    def create_time_btn(default_time):
        t_text = ft.Text(default_time, size=16, weight=ft.FontWeight.BOLD)
        def on_time_picked(e):
            if e.control.value:
                t_text.value = e.control.value.strftime("%H:%M")
                page.update()
        picker = ft.TimePicker(confirm_text="決定", cancel_text="キャンセル", error_invalid_text="時間が無効です", on_change=on_time_picked)
        page.overlay.append(picker)
        def show_picker(e):
            picker.open = True
            page.update()
        btn = ft.TextButton(
            content=ft.Row([ft.Icon(ft.Icons.ACCESS_TIME, size=18, color=ft.Colors.BLUE_600), t_text], spacing=5),
            on_click=show_picker, style=ft.ButtonStyle(padding=5)
        )
        return btn, t_text

    def add_bonus_row(start_val="18:00", end_val="20:00", amt_val=0.0):
        btn_start, txt_start = create_time_btn(start_val)
        btn_end, txt_end = create_time_btn(end_val)
        tf_amt = ft.TextField(label="加算額(円)", value=str(int(amt_val)), width=100, keyboard_type=ft.KeyboardType.NUMBER)
        
        item = {
            "btn_start": btn_start, "txt_start": txt_start,
            "btn_end": btn_end, "txt_end": txt_end,
            "tf_amt": tf_amt
        }
        bonus_ui_items.append(item)
        refresh_bonus_ui()

    def delete_bonus_row(item):
        if item in bonus_ui_items:
            bonus_ui_items.remove(item)
            refresh_bonus_ui()

    def refresh_bonus_ui():
        bonus_list_column.controls.clear()
        for i, item in enumerate(bonus_ui_items):
            header = ft.Row([
                ft.Text(f"時間帯加算 {i+1}", size=16, weight=ft.FontWeight.BOLD),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=ft.Colors.RED_400, on_click=lambda e, it=item: delete_bonus_row(it))
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            
            row_times = ft.Row([item["btn_start"], ft.Text("〜"), item["btn_end"]])
            row_amt = ft.Row([item["tf_amt"], ft.Text("円アップ")])
            
            card = ft.Container(
                content=ft.Column([header, row_times, row_amt], spacing=5),
                padding=10, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8
            )
            bonus_list_column.controls.append(card)
        
        if page.route:  # 初期化時以外は画面を更新する
            page.update()

    # 起動時にデータベースのリストからUIを復元
    for b in settings.get("bonuses", []):
        add_bonus_row(b.get("start", "18:00"), b.get("end", "20:00"), b.get("amt", 0.0))

    btn_add_bonus = ft.TextButton("＋ 新しい加算枠を追加", icon=ft.Icons.ADD, on_click=lambda e: add_bonus_row())

    def save_settings(e):
        try:
            settings["base_wage"] = float(wage_input.value)
            settings["target_amount"] = float(target_input.value)
            
            # UIの入力内容から新しいリストを作成して保存
            settings["bonuses"] = []
            for item in bonus_ui_items:
                amt = float(item["tf_amt"].value) if item["tf_amt"].value else 0.0
                settings["bonuses"].append({
                    "start": item["txt_start"].value,
                    "end": item["txt_end"].value,
                    "amt": amt
                })
            
            save_db(db)
            page.run_task(page.close_drawer)
            show_msg("設定を保存しました")
            page.update()
        except ValueError:
            show_msg("正しい数値を入力してください")

    my_drawer = ft.NavigationDrawer(
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text("各種設定", size=22, weight=ft.FontWeight.BOLD),
                    wage_input,
                    target_input,
                    ft.Divider(),
                    bonus_list_column, # 動的リスト
                    btn_add_bonus,
                    ft.Divider(),
                    ft.Button("設定を保存", on_click=save_settings, style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)),
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                padding=20, expand=True
            )
        ]
    )

    # --- スワイプとルーティング ---
    def swipe_to_calendar(e):
        dx = e.local_delta.x if hasattr(e, "local_delta") else getattr(e, "delta_x", 0)
        if dx > 15:
            page.run_task(page.push_route, "/calendar")

    def swipe_to_home(e):
        dx = e.local_delta.x if hasattr(e, "local_delta") else getattr(e, "delta_x", 0)
        if dx < -15:
            page.run_task(page.push_route, "/")

    def route_change(route_event=None):
        page.views.clear()
        
        history_items = [
            ft.ListTile(
                leading=ft.Icon(ft.Icons.ATTACH_MONEY),
                title=ft.Text(f"{date}", weight=ft.FontWeight.BOLD), 
                subtitle=ft.Text(f"合計: ¥{amt:,}", color=ft.Colors.BLUE)
            )
            for date, amt in sorted(logs.items(), reverse=True)
        ]
        if not history_items:
            history_items.append(ft.Text("まだ記録がありません", color=ft.Colors.GREY_500))

        page.views.append(
            ft.View(
                route="/calendar",
                controls=[
                    ft.AppBar(title=ft.Text("収入履歴"), bgcolor=ft.Colors.BLUE_50),
                    ft.GestureDetector(
                        on_pan_update=swipe_to_home, 
                        expand=True,
                        content=ft.Container(
                            bgcolor=ft.Colors.TRANSPARENT,
                            content=ft.Column([
                                ft.Column(history_items, scroll=ft.ScrollMode.AUTO, expand=True),
                                ft.Divider(),
                                ft.TextButton("履歴をすべて削除", icon=ft.Icons.DELETE, on_click=clear_logs, icon_color=ft.Colors.RED, style=ft.ButtonStyle(color=ft.Colors.RED)),
                                ft.Text("← 左スワイプでホームへ戻る", color=ft.Colors.GREY_400, size=12)
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            expand=True, padding=20
                        )
                    )
                ]
            )
        )

        if page.route == "/" or page.route == "":
            page.views.append(
                ft.View(
                    route="/",
                    controls=[
                        ft.AppBar(title=ft.Text("ホーム"), leading=ft.IconButton(ft.Icons.MENU, on_click=lambda _: page.run_task(page.show_drawer))),
                        ft.GestureDetector(
                            on_pan_update=swipe_to_calendar,
                            expand=True,
                            content=ft.Container(
                                bgcolor=ft.Colors.TRANSPARENT,
                                content=ft.Column([
                                    ft.Text("本日の稼ぎ", size=18, color=ft.Colors.GREY_600),
                                    ft.Stack([
                                        progress_ring,
                                        ft.Container(
                                            content=ft.Column([amount_text, current_wage_text, timer_text], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=5),
                                            width=250, height=250, 
                                            alignment=ft.Alignment(0, 0)
                                        )
                                    ]),
                                    ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                                    ft.Row([btn_start, btn_pause], alignment=ft.MainAxisAlignment.CENTER, spacing=20),
                                    ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                                    btn_finish,
                                    ft.Text("右スワイプで履歴を確認 →", color=ft.Colors.GREY_400, size=12)
                                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                                expand=True, 
                                alignment=ft.Alignment(0, 0)
                            )
                        )
                    ],
                    drawer=my_drawer
                )
            )
            
        page.update()

    page.on_route_change = route_change
    page.route = page.route if page.route else "/"
    route_change()

    threading.Thread(target=update_timer, daemon=True).start()

if __name__ == "__main__":
    # Renderが指定するポート番号を読み込み、なければ8550を使う
    port = int(os.getenv("PORT", 8550))
    ft.run(main, host="0.0.0.0", port=port)