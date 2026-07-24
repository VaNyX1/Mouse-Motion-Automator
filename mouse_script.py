import tkinter as tk
from tkinter import ttk
import pyautogui
import math
import threading
import time
import keyboard
import pystray
import random
import json
import os
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# Файл для сохранения настроек
SETTINGS_FILE = "settings.json"

# Настройки масштаба превью (1920x1080 -> 240x135)
SCALE = 8.0
PREVIEW_WIDTH = 240
PREVIEW_HEIGHT = 135

# Глобальные переменные управления
is_running = False
is_recording = False
mouse_thread = None
record_thread = None
preview_angle = 0
recorded_path = []

# По умолчанию центр - середина Full HD экрана
custom_center_x = 1920 // 2
custom_center_y = 1080 // 2

# Маппинг кнопок мыши
MOUSE_BUTTONS = {
    "ЛКМ (Левая)": "left",
    "ПКМ (Правая)": "right",
    "СКМ (Колесико)": "middle"
}


# --- ЛОГИКА СОХРАНЕНИЯ НАСТРОЕК ---
def save_settings():
    settings = {
        "shape": shape_var.get(),
        "radius": radius_slider.get(),
        "speed": speed_slider.get(),
        "noise": noise_var.get(),
        "infinite": loop_infinite_var.get(),
        "loops": loop_count_entry.get(),
        "mouse_btn": mouse_btn_var.get(),
        "start_key": start_hk_var.get(),
        "stop_key": stop_hk_var.get()
    }
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                shape_var.set(data.get("shape", "Круг"))
                radius_slider.set(data.get("radius", 250))
                speed_slider.set(data.get("speed", 70))
                noise_var.set(data.get("noise", False))
                loop_infinite_var.set(data.get("infinite", True))
                loop_count_entry.delete(0, tk.END)
                loop_count_entry.insert(0, data.get("loops", "5"))
                mouse_btn_var.set(data.get("mouse_btn", "ЛКМ (Левая)"))
                start_hk_var.set(data.get("start_key", "F9"))
                stop_hk_var.set(data.get("stop_key", "F10"))
                toggle_loop_entry()
        except Exception as e:
            print(f"Ошибка загрузки настроек: {e}")


# --- МАТЕМАТИКА ТРАЕКТОРИЙ ---
def get_trajectory():
    shape = shape_var.get()
    radius = radius_slider.get()
    cx = custom_center_x
    cy = custom_center_y
    points = []

    if shape == "Круг":
        for angle in range(0, 360, 5):
            rad = math.radians(angle)
            points.append((cx + int(radius * math.cos(rad)), cy + int(radius * math.sin(rad))))

    elif shape == "Квадрат":
        r = int(radius)
        for x in range(cx - r, cx + r, 15): points.append((x, cy - r))
        for y in range(cy - r, cy + r, 15): points.append((cx + r, y))
        for x in range(cx + r, cx - r, -15): points.append((x, cy + r))
        for y in range(cy + r, cy - r, -15): points.append((cx - r, y))

    elif shape == "Зигзаг":
        r = int(radius)
        for x in range(cx - r, cx + r, 15):
            y = cy - r // 2 if (x // 30) % 2 == 0 else cy + r // 2
            points.append((x, y))
        for x in range(cx + r, cx - r, -15):
            points.append((x, cy))

    elif shape == "Бесконечность":
        for angle in range(0, 360, 5):
            rad = math.radians(angle)
            x = cx + int(radius * math.sin(rad))
            y = cy + int(radius * math.sin(rad) * math.cos(rad))
            points.append((x, y))

    elif shape == "Горизонтальная линия":
        r = int(radius)
        for x in range(cx - r, cx + r, 15): points.append((x, cy))
        for x in range(cx + r, cx - r, -15): points.append((x, cy))

    elif shape == "Вертикальная линия":
        r = int(radius)
        for y in range(cy - r, cy + r, 15): points.append((cx, y))
        for y in range(cy + r, cy - r, -15): points.append((cx, y))

    elif shape == "Записанная":
        if recorded_path:
            points = recorded_path.copy()
        else:
            points = [(cx, cy)]

    return points


# --- ФУНКЦИЯ ДВИЖЕНИЯ МЫШИ ---
def mouse_loop():
    global is_running
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    trajectory = get_trajectory()
    btn = MOUSE_BUTTONS[mouse_btn_var.get()]

    infinite = loop_infinite_var.get()
    try:
        max_loops = int(loop_count_entry.get())
    except ValueError:
        max_loops = 1

    loop_counter = 0

    try:
        pyautogui.moveTo(trajectory[0][0], trajectory[0][1])
        time.sleep(0.1)
        pyautogui.mouseDown(button=btn)

        while is_running:
            if not infinite and loop_counter >= max_loops:
                break

            speed = speed_slider.get()
            delay = (101 - speed) / 2000.0

            for x, y in trajectory:
                if not is_running:
                    break

                if noise_var.get():
                    x += random.randint(-2, 2)
                    y += random.randint(-2, 2)

                pyautogui.moveTo(x, y, duration=0)
                if delay > 0:
                    time.sleep(delay)

            loop_counter += 1

    except pyautogui.FailSafeException:
        stop_script()
    finally:
        pyautogui.mouseUp(button=btn)
        stop_script()


# --- УПРАВЛЕНИЕ СТАРТ / СТОП ---
def start_script():
    global is_running, mouse_thread
    if not is_running and not is_recording:
        is_running = True
        status_label.config(text="Статус: ЗАПУЩЕН", foreground="#00FF00")
        mouse_thread = threading.Thread(target=mouse_loop, daemon=True)
        mouse_thread.start()


def stop_script():
    global is_running
    if is_running:
        is_running = False
        status_label.config(text="Статус: Остановлен", foreground="#FF3B30")


# --- ЗАПИСЬ ДВИЖЕНИЙ МЫШИ ---
def record_loop():
    global is_recording, recorded_path
    recorded_path = []

    for i in range(3, 0, -1):
        status_label.config(text=f"Запись через {i} сек...", foreground="#FFCC00")
        time.sleep(1)

    status_label.config(text="ЗАПИСЬ... (нажми Esc для финала)", foreground="#FFCC00")

    while is_recording:
        x, y = pyautogui.position()
        recorded_path.append((x, y))
        time.sleep(0.01)

        if keyboard.is_pressed('esc'):
            break

    is_recording = False
    shape_var.set("Записанная")
    status_label.config(text="Запись сохранена!", foreground="#007AFF")
    rec_btn.config(text="Записать траекторию")


def toggle_record():
    global is_recording, record_thread
    if is_running:
        return
    if not is_recording:
        is_recording = True
        rec_btn.config(text="ОСТАНОВИТЬ ЗАПИСЬ (Esc)")
        record_thread = threading.Thread(target=record_loop, daemon=True)
        record_thread.start()
    else:
        is_recording = False


# --- СВОЙ ЦЕНТР ---
def set_custom_center():
    global custom_center_x, custom_center_y
    status_label.config(text="Наведи мышь на новый центр...", foreground="#FFCC00")
    root.update()
    time.sleep(2)
    custom_center_x, custom_center_y = pyautogui.position()
    status_label.config(text=f"Центр задан: {custom_center_x}, {custom_center_y}", foreground="#007AFF")


# --- ВИЗУАЛИЗАЦИЯ И ПРЕДПРОСМОТР ---
def update_preview():
    global preview_angle

    speed = speed_slider.get()
    step = speed / 10.0
    preview_angle = (preview_angle + step) % 360

    cx = PREVIEW_WIDTH / 2
    cy = (PREVIEW_HEIGHT - 8) / 2

    points = get_trajectory()

    preview_points = []
    for x, y in points:
        px = cx + (x - custom_center_x) / SCALE
        py = cy + (y - custom_center_y) / SCALE
        preview_points.append((px, py))

    preview_canvas.delete("path")
    if len(preview_points) > 1:
        flat_points = [coord for pt in preview_points for coord in pt]
        preview_canvas.create_line(flat_points, fill="#FFFFFF", dash=(3, 3), tags="path")

    if preview_points:
        idx = int((preview_angle / 360.0) * (len(preview_points) - 1))
        tx, ty = preview_points[idx]
        preview_canvas.coords(preview_dot, tx - 3, ty - 3, tx + 3, ty + 3)

    root.after(16, update_preview)


# --- ГЛОБАЛЬНЫЙ МОНИТОРИНГ КЛАВИАТУРЫ ---
def global_key_monitor():
    while True:
        try:
            start_key = start_hk_var.get().lower()
            stop_key = stop_hk_var.get().lower()

            if keyboard.is_pressed(start_key):
                start_script()
            if keyboard.is_pressed(stop_key):
                stop_script()
        except:
            pass
        time.sleep(0.08)


# --- СИСТЕМНЫЙ ТРЕЙ ---
def create_tray_image():
    image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    d.ellipse((8, 8, 56, 56), fill=(0, 122, 255))
    return image


def withdraw_window():
    save_settings()
    root.withdraw()
    show_tray_icon()


def show_window(icon_obj, item_obj):
    global icon
    if icon:
        icon.stop()
    root.after(0, root.deiconify)


def exit_program(icon_obj=None, item_obj=None):
    save_settings()
    if icon:
        icon.stop()
    root.destroy()


def show_tray_icon():
    global icon
    menu = (item('Развернуть', show_window), item('Выход', exit_program))
    icon = pystray.Icon("mouse_sim", create_tray_image(), "Mouse Simulator", menu)
    threading.Thread(target=icon.run, daemon=True).start()


# --- ИНТЕРФЕЙС ---
root = tk.Tk()
root.title("Mouse Simulator Ultimate")
root.geometry("380x790")
root.configure(bg="#1C1C1E")
root.protocol('WM_DELETE_WINDOW', withdraw_window)

# --- ИСПРАВЛЕНИЕ ЦВЕТОВ WINDOWS OVERRIDE ---
root.option_add('*TCombobox*Listbox.background', '#2C2C2E')
root.option_add('*TCombobox*Listbox.foreground', '#FFFFFF')
root.option_add('*TCombobox*Listbox.selectBackground', '#007AFF')
root.option_add('*TCombobox*Listbox.selectForeground', '#FFFFFF')

style = ttk.Style()
style.theme_use('clam')
style.configure('.', background='#1C1C1E', foreground='#FFFFFF')
style.configure('TLabel', background='#1C1C1E', foreground='#FFFFFF')
style.configure('TButton', background='#2C2C2E', foreground='#FFFFFF', borderwidth=0, font=("Arial", 9, "bold"))
style.map('TButton', background=[('active', '#3A3A3C')])

style.configure('TCombobox',
                fieldbackground='#2C2C2E',
                background='#2C2C2E',
                foreground='#FFFFFF',
                arrowcolor='#FFFFFF')

style.map('TCombobox',
          fieldbackground=[('readonly', '#2C2C2E'), ('active', '#3A3A3C')],
          background=[('readonly', '#2C2C2E'), ('active', '#3A3A3C')],
          foreground=[('readonly', '#FFFFFF'), ('active', '#FFFFFF')])

# 1. Статус
status_label = ttk.Label(root, text="Статус: Остановлен", font=("Arial", 14, "bold"), foreground="#FF3B30")
status_label.pack(pady=10)

# 2. Монитор рабочего стола
ttk.Label(root, text="Монитор предпросмотра (Масштаб 1:8):", font=("Arial", 8, "bold"), foreground="#8E8E93").pack()
preview_frame = tk.Frame(root, bg="#0078D7", bd=2, relief="solid")
preview_frame.pack(pady=5)

preview_canvas = tk.Canvas(preview_frame, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, bg="#0078D7",
                           highlightthickness=0)
preview_canvas.pack()

# Рисуем рабочий стол Windows
preview_canvas.create_rectangle(0, PREVIEW_HEIGHT - 10, PREVIEW_WIDTH, PREVIEW_HEIGHT, fill="#101010", width=0)
preview_canvas.create_rectangle(5, PREVIEW_HEIGHT - 8, 12, PREVIEW_HEIGHT - 2, fill="#0078D7", width=0)  # Пуск
preview_canvas.create_rectangle(5, 5, 10, 10, fill="#FFD700", width=0)  # Папка

preview_dot = preview_canvas.create_oval(0, 0, 0, 0, fill="#FF453A", width=0)

# 3. Ползунки настроек
settings_frame = tk.LabelFrame(root, text=" Настройки траектории ", bg="#1C1C1E", fg="#8E8E93",
                               font=("Arial", 9, "bold"))
settings_frame.pack(fill="x", padx=20, pady=5)

ttk.Label(settings_frame, text="Форма движения:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
shape_var = tk.StringVar(value="Круг")
shape_menu = ttk.Combobox(settings_frame, textvariable=shape_var, width=18, state="readonly")
shape_menu['values'] = ("Круг", "Квадрат", "Зигзаг", "Бесконечность", "Горизонтальная линия", "Вертикальная линия",
                        "Записанная")
shape_menu.grid(row=0, column=1, padx=10, pady=5)

ttk.Label(settings_frame, text="Радиус (размер):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
radius_slider = ttk.Scale(settings_frame, from_=50, to=500, value=250, orient="horizontal")
radius_slider.grid(row=1, column=1, padx=10, pady=5, sticky="we")

ttk.Label(settings_frame, text="Скорость:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
speed_slider = ttk.Scale(settings_frame, from_=1, to=100, value=70, orient="horizontal")
speed_slider.grid(row=2, column=1, padx=10, pady=5, sticky="we")

# 4. Фичи: Шум, Центр, Лимит циклов
features_frame = tk.LabelFrame(root, text=" Дополнительные Фичи ", bg="#1C1C1E", fg="#8E8E93",
                               font=("Arial", 9, "bold"))
features_frame.pack(fill="x", padx=20, pady=5)

# Рандомизация
noise_var = tk.BooleanVar(value=False)
noise_cb = tk.Checkbutton(features_frame, text="Рандомизация (Анти-бот шум)", variable=noise_var,
                          bg="#1C1C1E", fg="#FFFFFF", selectcolor="#1C1C1E", activebackground="#1C1C1E",
                          activeforeground="#FFFFFF")
noise_cb.grid(row=0, column=0, columnspan=2, padx=10, pady=3, sticky="w")

# Кнопка Свой Центр
center_btn = ttk.Button(features_frame, text="Задать центр под курсором", command=set_custom_center)
center_btn.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="we")


# Лимит циклов
def toggle_loop_entry():
    if loop_infinite_var.get():
        loop_count_entry.config(state="disabled", bg="#1C1C1E", fg="#555555")
    else:
        loop_count_entry.config(state="normal", bg="#2C2C2E", fg="#FFFFFF")


loop_infinite_var = tk.BooleanVar(value=True)
loop_cb = tk.Checkbutton(features_frame, text="Бесконечные круги", variable=loop_infinite_var,
                         bg="#1C1C1E", fg="#FFFFFF", selectcolor="#1C1C1E", activebackground="#1C1C1E",
                         activeforeground="#FFFFFF",
                         command=toggle_loop_entry)
loop_cb.grid(row=2, column=0, padx=10, pady=3, sticky="w")

loop_count_entry = tk.Entry(
    features_frame,
    width=6,
    state="disabled",
    bg="#1C1C1E",
    fg="#555555",
    disabledbackground="#1C1C1E",
    disabledforeground="#555555",
    insertbackground="#FFFFFF",
    relief="solid",
    bd=1,
    justify="center",
    font=("Arial", 10, "bold")
)
loop_count_entry.insert(0, "5")
loop_count_entry.grid(row=2, column=1, padx=10, pady=3, sticky="w")

# 5. Мышь и Хоткеи
control_frame = tk.LabelFrame(root, text=" Кнопки и Управление ", bg="#1C1C1E", fg="#8E8E93", font=("Arial", 9, "bold"))
control_frame.pack(fill="x", padx=20, pady=5)

ttk.Label(control_frame, text="Кнопка мыши:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
mouse_btn_var = tk.StringVar(value="ЛКМ (Левая)")
mouse_menu = ttk.Combobox(control_frame, textvariable=mouse_btn_var, width=15, state="readonly")
mouse_menu['values'] = list(MOUSE_BUTTONS.keys())
mouse_menu.grid(row=0, column=1, padx=10, pady=5)

hotkeys_list = ["F9", "F10", "F11", "F12", "Delete", "Insert", "Home", "End", "Scroll Lock"]

ttk.Label(control_frame, text="Клавиша СТАРТ:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
start_hk_var = tk.StringVar(value="F9")
start_hk_menu = ttk.Combobox(control_frame, textvariable=start_hk_var, width=15, state="readonly")
start_hk_menu['values'] = hotkeys_list
start_hk_menu.grid(row=1, column=1, padx=10, pady=5)

ttk.Label(control_frame, text="Клавиша СТОП:").grid(row=2, column=0, padx=10, pady=5, sticky="w")
stop_hk_var = tk.StringVar(value="F10")
stop_hk_menu = ttk.Combobox(control_frame, textvariable=stop_hk_var, width=15, state="readonly")
stop_hk_menu['values'] = hotkeys_list
stop_hk_menu.grid(row=2, column=1, padx=10, pady=5)

# 6. Запись пути
rec_frame = tk.LabelFrame(root, text=" Запись своей траектории ", bg="#1C1C1E", fg="#8E8E93", font=("Arial", 9, "bold"))
rec_frame.pack(fill="x", padx=20, pady=5)

rec_btn = ttk.Button(rec_frame, text="Записать траекторию", padding=5, command=toggle_record)
rec_btn.pack(pady=8, fill="x", padx=20)

# 7. Запуск
start_btn = ttk.Button(root, text="ЗАПУСТИТЬ", padding=8, command=start_script)
start_btn.pack(pady=(10, 3), fill="x", padx=30)

stop_btn = ttk.Button(root, text="СТОП", padding=8, command=stop_script)
stop_btn.pack(pady=3, fill="x", padx=30)

footer = ttk.Label(root, text="Закрытие программы сворачивает её в трей", font=("Arial", 8), foreground="#8E8E93")
footer.pack(pady=10)

# Загружаем сохраненные настройки перед запуском интерфейса
load_settings()

# Фоновые потоки
threading.Thread(target=global_key_monitor, daemon=True).start()
update_preview()

root.mainloop()
