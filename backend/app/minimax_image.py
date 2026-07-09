import json
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.models import CreativePoint
from app.scenario_quality import unique_real_scenarios


@dataclass
class ImageResult:
    url: str
    prompt: str


def generate_point_image(point: CreativePoint, settings: Settings) -> ImageResult:
    if not settings.minimax_api_key:
        raise ValueError("还没有配置 MINIMAX_API_KEY，无法生成释义图")

    prompt = build_image_prompt(point)
    image_url = request_minimax_image(prompt, settings)
    saved_url = save_remote_image(image_url, point.id, settings)
    return ImageResult(url=saved_url, prompt=prompt)


def build_image_prompt(point: CreativePoint) -> str:
    scenarios = unique_real_scenarios(json.loads(point.application_scenarios_json or "[]"))
    scenario_text = ""
    if scenarios:
        first = scenarios[0]
        scenario_text = f"{first.get('name', '')}：{first.get('description', '')}"

    prompt = f"""
生成一张用于解释技术创意点的横版插画，风格真实、清爽、适合产品报告。
画面不要出现任何文字、字母、代码片段、水印或品牌标识。

创意点：{point.title}
大白话解释：{point.plain_explanation}
核心价值：{point.new_approach}
典型应用场景：{scenario_text}

画面应该像一个具体业务故事：有人正在处理复杂问题，系统用更聪明的方式把问题变简单。
重点表现“原本很麻烦，现在更省时、更清楚、更可靠”的价值。
构图要求：16:9，主体明确，细节真实，有技术感但不要科幻夸张。
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
    for key in ("image_urls", "images", "data"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
                if isinstance(item, dict):
                    url = item.get("url") or item.get("image_url")
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        return url
        if isinstance(value, dict):
            url = value.get("url") or value.get("image_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    return ""


def save_remote_image(image_url: str, point_id: int, settings: Settings) -> str:
    output_dir = settings.image_output_path
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = guess_suffix(image_url)
    filename = f"creative-point-{point_id}-{secrets.token_hex(8)}{suffix}"
    output_path = output_dir / filename

    request = urllib.request.Request(image_url, headers={"User-Agent": "sfqqyq-git-creative-distiller/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            output_path.write_bytes(response.read())
    except urllib.error.URLError as error:
        raise RuntimeError(f"图片下载失败：{error.reason}") from error

    return f"{settings.image_url_prefix.rstrip('/')}/{filename}"


def guess_suffix(image_url: str) -> str:
    path = Path(image_url.split("?", 1)[0])
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".png"
