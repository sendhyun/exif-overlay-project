import os
from io import BytesIO
from fractions import Fraction
import piexif
from PIL import Image, ImageDraw, ImageFont
'''
#222222 검정색
#444444 흰색
'''
logo_dir = os.path.join(os.path.dirname(__file__), "assets", "brands")
logo_map = {"apple": "apple.png", "samsung": "samsung.png", "sony": "sony.png", "canon": "canon.png", "nikon": "nikon.png"}
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

def load_logo(img, margin): #gpt 도움받은 부분,asset에 있는 logo 이미지 px값이 제각각이라서, 사진 하단 여백에 맞게 비율을 조정해서 불러왔어야 했습니다.
    try:
        make = normal(piexif.load(img.info.get("exif", b""))["0th"].get(piexif.ImageIFD.Make))
    except Exception:
        make = None
    filename = next((path for brand, path in logo_map.items() if make and brand in make.lower()), default_logo)
    try:
        logo = Image.open(os.path.join(logo_dir, filename)).convert("RGBA")
    except Exception:
        return None
    max_h = max(margin - 40, 20)
    ratio = min(max_h / logo.height, 1.0)
    size = (int(logo.width * ratio), int(logo.height * ratio))
    if min(size) <= 0:
        logo.close()
        return None
    resized = logo.resize(size, Image.LANCZOS)
    logo.close()
    return resized

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
