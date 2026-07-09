import json
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import CreativePoint
from app.scenario_quality import unique_real_scenarios


@dataclass
class ImageResult:
    url: str
    prompt: str


def generate_point_image(point: CreativePoint, settings: Settings, prompt: str) -> ImageResult:
    if not settings.minimax_api_key:
        raise ValueError("还没有配置 MINIMAX_API_KEY，无法生成释义图")

    image_url = request_minimax_image(prompt, settings)
    saved_url = save_remote_image(image_url, point, settings)
    return ImageResult(url=saved_url, prompt=prompt)


def build_image_prompt(point: CreativePoint) -> str:
    scenarios = unique_real_scenarios(json.loads(point.application_scenarios_json or "[]"))
    scenario_text = ""
    if scenarios:
        first = scenarios[0]
        scenario_text = f"{first.get('name', '')}：{first.get('description', '')}"
    title = chinese_label_text(point.title)

    prompt = f"""
生成一张用于解释技术创意点的横版卡通插画，风格轻松、活泼、明亮，像产品科普漫画，不要严肃架构图。
画面本身不要出现任何文字、字母、拼音、代码、小字说明、水印或品牌标识，中文标题和标签会由系统后期添加。

创意点：{title}
大白话解释：{point.plain_explanation}
核心价值：{point.new_approach}
典型应用场景：{scenario_text}

画面应该像一个具体业务小故事：左侧是工作人员被复杂流程和很多连接线搞得头大，右侧是一个可爱的系统助手把任务交给隔离服务处理，界面变得清楚、省心、可靠。
重点表现“原本很麻烦，现在更省时、更清楚、更可靠”的价值。
构图要求：16:9，主体明确，人物表情友好，色彩温暖，有一点技术感但不要科幻夸张，不要深色压抑背景。
""".strip()
    return re.sub(r"\s+", " ", prompt)[:1800]


def request_minimax_image(prompt: str, settings: Settings) -> str:
    endpoint = settings.minimax_api_base_url.rstrip("/") + "/image_generation"
    payload = {
        "model": settings.minimax_image_model,
        "prompt": prompt,
        "aspect_ratio": settings.minimax_image_aspect_ratio,
        "n": 1,
        "response_format": "url",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {settings.minimax_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"MiniMax 生成失败：HTTP {error.code} {body[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"MiniMax 连接失败：{error.reason}") from error

    image_url = extract_image_url(response_data)
    if not image_url:
        raise RuntimeError(f"MiniMax 没有返回图片地址：{json.dumps(response_data, ensure_ascii=False)[:300]}")
    return image_url


def extract_image_url(data: dict) -> str:
    nested_url = find_url(data)
    if nested_url:
        return nested_url
    return ""


def find_url(value) -> str:
    if isinstance(value, str):
        return value if value.startswith(("http://", "https://")) else ""
    if isinstance(value, list):
        for item in value:
            url = find_url(item)
            if url:
                return url
    if isinstance(value, dict):
        for key in ("url", "image_url"):
            url = value.get(key)
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
        for item in value.values():
            url = find_url(item)
            if url:
                return url
    return ""


def save_remote_image(image_url: str, point: CreativePoint, settings: Settings) -> str:
    output_dir = settings.image_output_path
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = guess_suffix(image_url)
    filename = f"creative-point-{point.id}-{secrets.token_hex(8)}{suffix}"
    output_path = output_dir / filename

    request = urllib.request.Request(image_url, headers={"User-Agent": "sfqqyq-git-creative-distiller/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())
    except urllib.error.URLError as error:
        raise RuntimeError(f"图片下载失败：{error.reason}") from error

    add_chinese_overlay(output_path, point)
    return f"{settings.image_url_prefix.rstrip('/')}/{filename}"


def add_chinese_overlay(image_path: Path, point: CreativePoint) -> None:
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    band_height = max(150, int(height * 0.20))
    canvas = Image.new("RGB", (width, height + band_height), "#fff7ea")
    canvas.paste(image, (0, 0))

    draw = ImageDraw.Draw(canvas)
    title_font = load_chinese_font(max(28, width // 36))
    label_font = load_chinese_font(max(20, width // 54))
    small_font = load_chinese_font(max(18, width // 64))

    padding = max(28, width // 45)
    y = height + max(18, band_height // 8)
    title = shorten_text(f"创意点：{chinese_label_text(point.title)}", 34)
    draw.text((padding, y), title, fill="#1f2933", font=title_font)

    labels = [
        "旧办法：流程容易缠在一起",
        "新办法：隔离服务来处理",
        "价值：更安全、更省心",
    ]
    x = padding
    y += max(44, band_height // 3)
    for label in labels:
        text_width = int(draw.textlength(label, font=label_font))
        chip_width = text_width + 34
        if x + chip_width > width - padding:
            x = padding
            y += 44
        draw.rounded_rectangle(
            (x, y, x + chip_width, y + 34),
            radius=17,
            fill="#ffffff",
            outline="#f0c56a",
            width=2,
        )
        draw.text((x + 17, y + 4), label, fill="#7a4b00", font=label_font)
        x += chip_width + 14

    hint = "系统生成的卡通释义图，中文说明由后端叠加，避免模型生成乱码文字。"
    draw.text((padding, height + band_height - 34), hint, fill="#8a6f45", font=small_font)
    canvas.save(image_path, quality=92)


def load_chinese_font(size: int):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for item in candidates:
        try:
            if Path(item).exists():
                return ImageFont.truetype(item, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def shorten_text(value: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def chinese_label_text(value: str) -> str:
    replacements = {
        "Execution API": "执行接口",
        "API": "接口",
        "Worker": "工作节点",
        "LLM": "大模型",
        "Git": "代码仓库",
        "SQL": "数据库语句",
        "UI": "界面",
    }
    text = str(value or "")
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def guess_suffix(image_url: str) -> str:
    path = Path(image_url.split("?", 1)[0])
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".png"
