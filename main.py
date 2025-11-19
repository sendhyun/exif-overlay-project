"""
ctrl+f로 "#gpt"를 검색하시면 gpt 도움 받은 부분 찾으실 수 있습니다,
구현 원리도 같이 주석으로 달아놨습니다.
#f5f5f5 회색
할 일 : 멀티스레드 적용
"""
import os
import sys
import subprocess
import json
import ctypes
import itertools
import threading
from functools import partial
from tkinter import Tk,Button,Label,Frame,filedialog,messagebox,StringVar,simpledialog
from tkinter import font 

config_file = "config.json"
#컴퓨터에 이 패키지들이 없다면 설치해야함.
#참조 https://hwan001.co.kr/119
required = {"pillow": "PIL","piexif":"piexif"}
missing = []
for pkg,module in required.items():
    try:
        __import__(module)
    except ImportError:
        missing.append(pkg)
if missing:
    print(f"{', '.join(missing)} 설치")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

from PIL import Image,ImageTk
from exif_handler import add_exif_data,make_exif,read_exif

save_folder = None
path_label = None
preview_label = None
preview_container = None
download_button = None
title_label = None
control_frame = None
content_frame = None
body_frame = None
root_window = None
cur_preview_image = None
cur_preview_photo = None
cur_image_name = ""
cur_image_ext = ".jpg"
defo = "맑은 고딕"
button_font_configs = {}

#다운로드 저장 경로를 영구적으로 저장해야함.
def load_config():
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

#사진이름이 중복이면 덮어쓰기 되는 문제가 있음 (n)같은거 넣어서 해결해야할 듯함??
#ㄴ 해결함
def not_same(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for i in itertools.count(1):
        new_path = f"{base} ({i}){ext}"
        if not os.path.exists(new_path):
            return new_path

def set_save_folder():
    folder = filedialog.askdirectory(title="저장 폴더 선택")
    if folder:
        save_folder.set(folder)
        save_config({"save_folder": folder})
        messagebox.showinfo("저장 폴더 설정", f"저장 경로가 설정되었습니다:\n{folder}")

def open_save_folder():
    folder = save_folder.get()
    if os.path.exists(folder):
        os.startfile(folder)
    else:
        messagebox.showwarning("폴더가 존재하지 않습니다")

#gpt 도움 받은 부분, 창 크기를 변경할 때 tkinter가 심각할 정도로 끊기는 현상이 있었는데
#무거운 작업은 별도로 스레드를 할당해서 처리해 뼈대 프로그램에 영향이 없도록 처리했습니다.
def run_in_thread(fn, on_done=None):
    def task():
        try:
            result = fn()
            error = None
        except Exception as exc:
            result = None
            error = exc
        if on_done:
            if root_window:
                root_window.after(0, on_done, result, error)
            else:
                on_done(result, error)
    threading.Thread(target=task, daemon=True).start()

def draw_exif_info():
    global cur_preview_image, cur_image_name, cur_image_ext
    image_path = filedialog.askopenfilename(
        title="이미지 선택",
        filetypes=[("JPEG files", "*.jpg *.jpeg")],
    )
    if not image_path:
        return
    try:
        #폰트도 자동다운이 되는지?
        #11/19 - 안되는거같음
        font_path = r"C:\Windows\Fonts\RIDIBatang.otf"
        if not os.path.exists(font_path):
            font_path = r"C:\Windows\Fonts\malgun.ttf"
    except Exception:
        font_path = None
    exif_data = read_exif(image_path)
    metadata_inputs = None
    if not exif_data:
        required_fields = [
            ("camera_make", "카메라 제조사", "카메라 제조사를 입력하세요:"),
            ("camera_model", "기기 모델", "촬영 기기의 모델명을 입력하세요:"),
            ("lens_model", "렌즈 모델", "사용한 렌즈 모델을 입력하세요:"),
            ("aperture_value", "조리개 값", "조리개 값을 입력하세요:"),
            ("shutter_value", "셔터 속도", "셔터 속도를 입력하세요:"),
            ("iso_value", "ISO 값", "ISO 값을 입력하세요:"),
            ("datetime_value", "촬영일시", "촬영일시를 입력하세요:"),
        ]
        metadata_inputs = {}
        for key, title, prompt in required_fields:
            value = simpledialog.askstring(title, prompt)
            if not value:
                messagebox.showwarning("모든 정보를 입력해야 합니다.")
                return
            metadata_inputs[key] = value
    if preview_label:
        preview_label.config(image="", text="미리보기를 준비하는 중입니다...", fg="gray")
        preview_label.image = None
    enable_download(False) #미리보기가 있을때만 전달
    run_in_thread(
        partial(generate_preview, image_path, metadata_inputs, font_path),
        partial(apply_preview, image_path),
    )
    
def generate_preview(image_path, metadata_inputs, font_path):
    source = image_path
    if metadata_inputs:
        try:
            source = add_exif_data(
                image_path,
                metadata_inputs["camera_make"],
                metadata_inputs["camera_model"],
                metadata_inputs["lens_model"],
                metadata_inputs["aperture_value"],
                metadata_inputs["shutter_value"],
                metadata_inputs["iso_value"],
                metadata_inputs["datetime_value"],
            )
        except Exception as exc:
            raise RuntimeError(f"정보를 추가하는 중 오류가 발생했습니다.\n{exc}") from exc
    try:
        return make_exif(source, output_path=None, font_path=font_path)
    except Exception as exc:
        raise RuntimeError(f"미리보기를 만드는 중 문제가 발생했습니다.\n{exc}") from exc


def apply_preview(image_path, preview_img, error):
    global cur_preview_image, cur_image_name, cur_image_ext
    if error:
        messagebox.showerror("오류", str(error))
        if preview_label:
            preview_label.config(
                image="",
                text="여기에 미리보기가 표시됩니다.",
                fg="gray",
            )
            preview_label.image = None
        enable_download(False)
        return
    cur_preview_image = preview_img
    cur_image_name, cur_image_ext = os.path.splitext(os.path.basename(image_path))
    if cur_image_ext.lower() not in [".jpg", ".jpeg"]:
        cur_image_ext = ".jpg"
    enable_download(True)
    update_display()

def update_display(event=None):
    global cur_preview_photo
    if not preview_label or not preview_container:
        return

    if cur_preview_image is None:
        preview_label.config(
            image="",
            text="여기에 미리보기가 표시됩니다.",
            fg="gray",
        )
        preview_label.image = None
        enable_download(False)
        return

    width = preview_container.winfo_width()
    height = preview_container.winfo_height()
    if width <= 40 or height <= 40:
        return

    target_width = max(width - 40, 50)
    target_height = max(height - 40, 50)

    orig_w, orig_h = cur_preview_image.size
    if orig_w <= 0 or orig_h <= 0:
        return
    scale = min(target_width / orig_w, target_height / orig_h, 1)
    if scale < 1:
        new_size = (max(1, int(orig_w * scale)), max(1, int(orig_h * scale)))
        display = cur_preview_image.resize(new_size, Image.LANCZOS)
    else:
        display = cur_preview_image
    cur_preview_photo = ImageTk.PhotoImage(display)
    preview_label.config(image=cur_preview_photo, text="")
    preview_label.image = cur_preview_photo

def save_preview_image():
    target_folder = save_folder.get()
    os.makedirs(target_folder, exist_ok=True)
    base_name = cur_image_name or "result"
    ext = cur_image_ext if cur_image_ext.lower() in [".jpg", ".jpeg"] else ".jpg"
    save_path = os.path.join(target_folder, f"{base_name}_with_text{ext}")
    save_path = not_same(save_path)
    try:
        cur_preview_image.save(save_path, "JPEG")
        messagebox.showinfo("완료", f"이미지가 저장되었습니다.\n{save_path}")
    except Exception as exc:
        messagebox.showerror("저장 오류", str(exc))

def enable_download(enabled):
    state = "normal" if enabled else "disabled"
    if download_button:
        download_button.config(state=state)


def update_path(event=None):
    if path_label and event:
        path_label.config(wraplength=max(event.width - 20, 160))

def dynamic_button(button, *, min_size=10, max_size=16, weight="normal"):
    font_obj = font.Font(family=defo, size=max_size, weight=weight)
    button_font_configs[button] = {
        "font": font_obj,
        "min": min_size,
        "max": max_size,
    }
    button.config(font=font_obj)
    button.bind("<Configure>", lambda event, btn=button: sync_button_text(btn))
    sync_button_text(button)
    button.after_idle(lambda btn=button: sync_button_text(btn))

def sync_button_text(button):
    config = button_font_configs.get(button)
    if not config:
        return

    width = button.winfo_width()
    height = button.winfo_height()
    if width <= 1 or height <= 1:
        return

    target_size = max(config["min"], min(config["max"], int(height * 0.4)))
    config["font"].config(size=target_size)
    button.config(wraplength=max(width - 16, 40))

def main():
    global save_folder, path_label, preview_label, preview_container
    global download_button
    global title_label, controlsframe, root_window, content_frame, body_frame
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = Tk()
    root_window = root
    root.title("사진 정보 오버레이 프로그램")
    root.geometry("980x620")
    root.minsize(420, 360)
    root.tk.call("tk", "scaling", 1.4)
    root.state("zoomed")

    root.grid_rowconfigure(0, weight=0)
    root.grid_rowconfigure(1, weight=1)
    root.grid_rowconfigure(2, weight=0)
    root.grid_columnconfigure(0, weight=1)

    save_folder = StringVar()
    config = load_config()
    #config파일에 저장된 경로 불러오거나,output 폴더에 저장함
    default_folder = config.get("save_folder", os.path.join(os.getcwd(), "images", "output"))
    os.makedirs(default_folder, exist_ok=True)
    save_folder.set(default_folder)

    content = Frame(root, padx=30, pady=25)
    content.grid(row=1, column=0, sticky="nsew")
    content_frame = content
    content.grid_columnconfigure(0, weight=1)

    title_label = Label(content, text="사진 정보 오버레이 프로그램", font=("맑은 고딕", 14, "bold"))
    title_label.grid(row=0, column=0, sticky="n", pady=(0, 12))

    body_frame = Frame(content)
    body_frame.grid(row=1, column=0, sticky="nsew")
    content.grid_rowconfigure(1, weight=1)
    body_frame.grid_columnconfigure(0, weight=3, minsize=520)
    body_frame.grid_columnconfigure(1, weight=2, minsize=260)
    body_frame.grid_rowconfigure(0, weight=1)
    body_frame.grid_rowconfigure(1, weight=0)
    body_frame.grid_rowconfigure(2, weight=0)

    preview_container = Frame(body_frame, bd=1, relief="groove", bg="#f5f5f5")
    preview_container.grid(row=0, column=0, sticky="nsew", pady=(0, 18), padx=(0, 18))
    preview_container.grid_columnconfigure(0, weight=1)
    preview_container.grid_rowconfigure(0, weight=1)

    preview_label = Label(
        preview_container,
        text="여기에 미리보기가 표시됩니다.",
        fg="gray",
        bg="#f5f5f5",
        justify="center",
    )
    preview_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

    control_frame = Frame(body_frame, pady=10)
    control_frame.grid(row=0, column=1, rowspan=3, sticky="nsew")
    control_frame.grid_columnconfigure(0, weight=1)
    for idx in range(5):
        control_frame.grid_rowconfigure(idx, weight=1)

    btn_save_location = Button(
        control_frame,
        text="저장 폴더 설정",
        command=set_save_folder,
        height=2,
    )
    btn_save_location.grid(row=0, column=0, sticky="nsew", pady=6)
    dynamic_button(btn_save_location, min_size=9, max_size=16)

    btn_open_folder = Button(
        control_frame,
        text="저장 폴더 열기",
        command=open_save_folder,
        height=2,
    )
    btn_open_folder.grid(row=1, column=0, sticky="nsew", pady=6)
    dynamic_button(btn_open_folder, min_size=9, max_size=16)

    path_label = Label(
        control_frame,
        textvariable=save_folder,
        font=("맑은 고딕", 9),
        fg="gray",
        justify="center",
        wraplength=220,
    )
    path_label.grid(row=2, column=0, sticky="ew", pady=(2, 10))

    btn_generate = Button(
        control_frame,
        text="EXIF 텍스트 이미지 생성",
        command=draw_exif_info,
        height=3,
    )
    btn_generate.grid(row=3, column=0, sticky="nsew", pady=6)
    dynamic_button(btn_generate, min_size=9, max_size=15)

    download_button = Button(
        control_frame,
        text="다운로드",
        command=save_preview_image,
        state="disabled",
        height=2,
    )
    download_button.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
    dynamic_button(download_button, min_size=11, max_size=18, weight="bold")

    control_frame.bind("<Configure>", update_path)
    preview_container.bind("<Configure>", update_display)

    update_display()
    enable_download(False)
    root.mainloop()

if __name__ == "__main__":
    main()
