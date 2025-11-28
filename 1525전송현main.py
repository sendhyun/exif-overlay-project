"""
ctrl+f로 "#gpt"를 검색하시면 gpt 도움 받은 부분 찾으실 수 있습니다,
구현 원리도 같이 주석으로 달아놨습니다.
#f5f5f5 회색
할 일 : 멀티스레드 적용
"""

# https://github.com/sendhyun/exif-overlay-project
import os
import sys
import subprocess
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
import json
import ctypes
import itertools
import threading
from functools import partial
from io import BytesIO
from fractions import Fraction
from tkinter import Tk, Button, Label, Frame, filedialog, messagebox, StringVar, simpledialog, font
from PIL import Image, ImageTk, ImageDraw, ImageFont
import piexif
import requests
from io import BytesIO

def GetImageFromURL(url):
    response = requests.get(url)
    response.raise_for_status()
    return Image.open(BytesIO(response.content))

config_file = "config.json"

'''
#222222 검정색
#444444 흰색
11-06 최초 git-push
'''
logo_dir = os.path.join(os.path.dirname(__file__), "assets", "brands")
logo_map = {
    "apple": "apple.png",
    "samsung": "samsung.png",
    "sony": "sony.png",
    "canon": "canon.png",
    "nikon": "nikon.png",
}
default_logo = "default.png"
default_font = "malgun.ttf"
exif_fields = ("camera_make", "camera_model", "lens_model", "aperture_value", "shutter_value", "iso_value", "datetime_value")

def normal(value, *, to_bytes=False):  #텍스트 슬라이싱ㅇ
    if value is None:
        return None
    if isinstance(value, bytes) and not to_bytes:
        value = value.decode("utf-8", "ignore")
    text = str(value).strip()
    if not text:
        return None
    return text.encode("utf-8", "ignore") if to_bytes else text

def parse(value, mode):  #exif 데이터 값을 슬라이싱함 dict 나중에 사용 예정
    text = normal(value)
    if text is None:
        return None
    try:
        if mode == "fraction":
            if "/" in text:
                num, den = (int(part.strip()) for part in text.split("/", 1))
            else:
                frac = Fraction(text).limit_denominator(1000)
                num, den = frac.numerator, frac.denominator
            if den == 0:
                raise ZeroDivisionError
            return num, den
        number = int(text)
        if number <= 0:
            raise ValueError
        return number
    except (ValueError, ZeroDivisionError) as exc:
        msg = "ISO 값은 양수여야 합니다." if mode == "iso" else "유효한 숫자 또는 분수 형태로 입력하세요."
        raise ValueError(msg) from exc

def ratio(value): #exif 데이터가 튜플로 들어오는데, 숫자형태로 변경해줘야 나중에 쓸 수 있음
    if isinstance(value, tuple) and len(value) == 2:
        num, den = value
        if not isinstance(num, (int, float)) or not isinstance(den, (int, float)):
            return None
        if den == 0 or num < 0 or den < 0:
            return None
        return num / den
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    return None

def setting(info):  
    iso = info.get("ISOSpeedRatings")
    if isinstance(iso, (list, tuple)):
        iso = iso[0] if iso else None
    iso = int(iso) if isinstance(iso, (int, float)) and iso > 0 else None
    aperture = ratio(info.get("FNumber"))
    shutter = ratio(info.get("ExposureTime"))
    dt = normal(info.get("DateTimeOriginal"))
    values = {"aperture": aperture, "shutter": shutter, "iso": iso, "datetime": dt}
    shutter_text = None if not shutter else (f"노출 {shutter:.1f}초" if shutter >= 1 else f"노출 1/{max(int(round(1 / shutter)), 1)}초")
    canvas = {"aperture": f"조리개 f/{aperture:.1f}" if aperture else None, "shutter": shutter_text, "iso": f"ISO {iso}" if iso else None, "datetime": f"촬영일시 {dt}" if dt else None}
    return values, canvas

def load_font(font_path, size): 
    try:
        return ImageFont.truetype(font_path or default_font, size)
    except Exception:
        return ImageFont.load_default()

def text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)

def line_info(draw, texts, font, x, start_y, gap, upward=False):
    y = start_y
    for text in texts:
        if not text:
            continue
        _, h = text_size(draw, text, font)
        if upward:
            y -= h
            draw.text((x, y), text, fill="#222222", font=font)
            y -= gap
        else:
            draw.text((x, y), text, fill="#222222", font=font)
            y += h + gap

def load_logo(img, margin):#gpt 도움받은 부분,asset에 있는 logo 이미지 px값이 제각각이라서, 사진 하단 여백에 맞게 비율을 조정해서 불러왔어야 했습니다.
    try:
        make = normal(piexif.load(img.info.get("exif", b""))["0th"].get(piexif.ImageIFD.Make))
    except Exception:
        make = None
    filename = next((name for brand, name in logo_map.items() if make and brand in make.lower()), default_logo)
    url = f"https://raw.githubusercontent.com/sendhyun/exif-overlay-project/main/assets/brands/{filename}"
    try:
        logo = GetImageFromURL(url).convert("RGBA")
    except:
        return None
    max_h = max(margin - 40, 20)
    ratio = min(max_h / logo.height, 1.0)
    size = (int(logo.width * ratio), int(logo.height * ratio))
    return logo.resize(size, Image.LANCZOS)


EXIF_TAGS = {
    "camera_make": ("0th", piexif.ImageIFD.Make, lambda v: normal(v, to_bytes=True)), "camera_model": ("0th", piexif.ImageIFD.Model, lambda v: normal(v, to_bytes=True)), "lens_model": ("Exif", piexif.ExifIFD.LensModel, lambda v: normal(v, to_bytes=True)),
    "datetime_value": ("Exif", piexif.ExifIFD.DateTimeOriginal, lambda v: normal(v, to_bytes=True)), "aperture_value": ("Exif", piexif.ExifIFD.FNumber, lambda v: parse(v, "fraction")),
    "shutter_value": ("Exif", piexif.ExifIFD.ExposureTime, lambda v: parse(v, "fraction")), "iso_value": ("Exif", piexif.ExifIFD.ISOSpeedRatings, lambda v: parse(v, "iso")),
}

def load_image(image_source): 
    return (image_source, False) if isinstance(image_source, Image.Image) else (Image.open(image_source), True)

def apply_exif(img, metadata):  
    try:
        exif = piexif.load(img.info.get("exif", b""))
    except Exception:
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    data = metadata or {}
    for key, (section, tag, parser) in EXIF_TAGS.items():
        raw = data.get(key)
        if raw is None:
            continue
        value = parser(raw)
        if value is not None:
            exif[section][tag] = value
    exif_bytes = piexif.dump(exif)
    with BytesIO() as buffer:
        base = img if img.mode == "RGB" else img.convert("RGB")
        try:
            base.save(buffer, "jpeg")
        finally:
            if base is not img:
                base.close()
        jpeg_bytes = buffer.getvalue()
    merged = piexif.insert(exif_bytes, jpeg_bytes)
    output = BytesIO(merged)
    try:
        result = Image.open(output)
        result.load()
    finally:
        output.close()
    return result

def add_exif(image_path, save_path, camera_make, camera_model, lens_model, aperture_value, shutter_value, iso_value, datetime_value):  # JPEG 이미지에 EXIF 메타데이터를 추가 후 저장
    updated = add_exif_data(image_path, camera_make, camera_model, lens_model, aperture_value, shutter_value, iso_value, datetime_value)
    try:
        updated.save(save_path, "jpeg")
    finally:
        updated.close()

def add_exif_data(image_source, camera_make, camera_model, lens_model, aperture_value, shutter_value, iso_value, datetime_value):  # EXIF 메타데이터를 적용한 PIL Image 객체를 반환
    metadata = {field: locals()[field] for field in exif_fields}
    img, should_close = load_image(image_source)
    try:
        return apply_exif(img, metadata)
    finally:
        if should_close:
            img.close()

def read_exif(image_source):  # 사진의 exif 데이터를 받아옴. 나중에 딕셔너리 가져가서 합성 구현
    img,should_close = load_image(image_source)
    try:
        exif_bytes = img.info.get("exif")
        if not exif_bytes:
            return {}
        exif_dict = piexif.load(exif_bytes)
        return {meta["name"]: value for ifd, tags in exif_dict.items() if isinstance(tags, dict) for tag, value in tags.items() for meta in (piexif.TAGS.get(ifd, {}).get(tag),) if meta and "name" in meta}
    finally:
        if should_close:
            img.close()

def write_exif(img, font_path):  # 합성 이미지를 반환
    info = read_exif(img)
    source = img.copy()
    try:
        w, h = source.size
        margin = max(int(h * 0.15), 120)
        canvas = Image.new("RGB", (w, h + margin), "white")
        canvas.paste(source, (0, 0))
        draw = ImageDraw.Draw(canvas)
        logo = load_logo(img, margin)
        logo_x, logo_width = 40, 0
        if logo:
            logo_y = h + int((margin - logo.height) / 2)
            canvas.paste(logo, (logo_x, logo_y), mask=logo); logo_width = logo.width; logo.close()
        base_font = max(int(margin * 0.28), 24)
        model_font, lens_font, settings_font = [load_font(font_path, size) for size in (base_font, max(int(base_font * 0.45), 12), max(int(base_font * 0.27), 10))]
        model_text = normal(info.get("Model")) or "기종 정보 없음"
        lens_text = normal(info.get("LensModel"))
        _, text_map = setting(info)
        shutter_text, aperture_text, datetime_text = text_map["shutter"], text_map["aperture"], text_map["datetime"]
        iso_text = text_map["iso"]
        text_left = logo_x + logo_width + 30
        _, model_h = text_size(draw, model_text, model_font)
        lens_h = text_size(draw, lens_text, lens_font)[1] if lens_text else 0
        block_h = model_h + (lens_h + 12 if lens_text else 0)
        model_y = h + (margin - block_h) / 2 - 40
        draw.text((text_left, model_y), model_text, fill="black", font=model_font)
        if lens_text:
            draw.text((text_left, model_y + model_h + 42), lens_text, fill="#444444", font=lens_font)
        settings_x = max(text_left + 120, int(w * 0.65))
        gap = 10
        if iso_text:
            _, iso_h = text_size(draw, iso_text, settings_font)
            iso_y = h + (margin - iso_h) / 2
            draw.text((settings_x, iso_y), iso_text, fill="#222222", font=settings_font)
            line_info(draw, [shutter_text], settings_font, settings_x, iso_y - gap, gap, upward=True)
            line_info(draw, [aperture_text, datetime_text], settings_font, settings_x, iso_y + iso_h + gap, gap)
        else:
            line_info(draw, [shutter_text, aperture_text, datetime_text], settings_font, settings_x, h + max(int(margin * 0.1), 10), gap)
        if not any(text_map.values()) and not lens_text and model_text == "기종 정보 없음":
            fallback = "EXIF가 없습니다"
            fw, fh = text_size(draw, fallback, model_font)
            draw.text(((w - fw) // 2, h + (margin - fh) // 2), fallback, fill="gray", font=model_font)
        return canvas
    finally:
        source.close()

def make_exif(image_source, output_path=None, font_path=None):  # 하단 여백에 브랜드 로고 + exif 합성 내보냄
    img, should_close = load_image(image_source)
    try:
        composed = write_exif(img, font_path)
    finally:
        if should_close:
            img.close()
    if output_path:
        composed.save(output_path, "jpeg")
    return composed


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
    save_path = os.path.join(target_folder, f"{base_name}_edit_{ext}")
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
    global title_label,root_window, content_frame, body_frame
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
main()