import base64
import io
import json
import os
import urllib.parse
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path

import folder_paths
import numpy
import PIL.Image
import torch

from .api import (
    Client,
    SIZE_OPTIONS,
    TEXT_SECONDS_OPTIONS,
    VideoAPIError,
    build_image_video_payload,
    build_input_reference_payload,
    build_text_video_payload,
    extract_result_video_url,
    extract_task_id,
    submit_video_generation,
    wait_for_video_completion,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_JSON_PATH = ROOT_DIR / "config.local.json"

NODE_PREFIX = "ComfyUI-Veo3.1"
NODE_CATEGORY = NODE_PREFIX
DEFAULT_FILENAME_PREFIX = NODE_PREFIX
DEFAULT_BASE_URL = "https://aihubmix.com"
DEFAULT_POLL_INTERVAL = 15.0
DEFAULT_REQUEST_TIMEOUT = 60


def _load_json_config():
    if not CONFIG_JSON_PATH.exists():
        return {}

    try:
        with CONFIG_JSON_PATH.open("r", encoding="utf-8") as handle:
            config_data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{CONFIG_JSON_PATH.name} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Failed to read {CONFIG_JSON_PATH.name}: {exc}") from exc

    if not isinstance(config_data, dict):
        raise ValueError(f"{CONFIG_JSON_PATH.name} must contain a top-level JSON object.")

    return config_data


def _json_value_present(config_data, key):
    if key not in config_data:
        return False

    value = config_data[key]
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _load_env_value(*keys):
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def _parse_request_timeout(value):
    if isinstance(value, bool):
        raise ValueError("request_timeout must be an integer.")

    if isinstance(value, int):
        timeout = value
    else:
        try:
            timeout = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("request_timeout must be an integer.") from exc

    if timeout < 5:
        raise ValueError("request_timeout must be greater than or equal to 5.")

    return timeout


def _parse_poll_interval(value):
    if isinstance(value, bool):
        raise ValueError("poll_interval must be a number.")

    if isinstance(value, (int, float)):
        interval = float(value)
    else:
        try:
            interval = float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("poll_interval must be a number.") from exc

    if interval <= 0:
        raise ValueError("poll_interval must be greater than 0.")

    return interval


def _normalize_base_url(value):
    normalized = str(value or "").strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3].rstrip("/")
    return normalized or DEFAULT_BASE_URL


def _resolve_api_key(config_data):
    if _json_value_present(config_data, "api_key"):
        return str(config_data["api_key"]).strip()

    env_value = _load_env_value("VEO_API_KEY", "AIHUBMIX_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    if env_value:
        return env_value

    raise ValueError(
        "An api_key is required. Add api_key to config.local.json or set VEO_API_KEY, "
        "AIHUBMIX_API_KEY, GOOGLE_API_KEY, or GEMINI_API_KEY."
    )


def _resolve_base_url(config_data):
    if _json_value_present(config_data, "base_url"):
        return _normalize_base_url(config_data["base_url"])

    env_value = _load_env_value("VEO_BASE_URL", "AIHUBMIX_BASE_URL")
    if env_value:
        return _normalize_base_url(env_value)

    return DEFAULT_BASE_URL


def _resolve_poll_interval(config_data):
    if _json_value_present(config_data, "poll_interval"):
        return _parse_poll_interval(config_data["poll_interval"])

    env_value = _load_env_value("VEO_POLL_INTERVAL", "AIHUBMIX_POLL_INTERVAL")
    if env_value:
        return _parse_poll_interval(env_value)

    return DEFAULT_POLL_INTERVAL


def _resolve_request_timeout(config_data):
    if _json_value_present(config_data, "request_timeout"):
        return _parse_request_timeout(config_data["request_timeout"])

    env_value = _load_env_value("VEO_REQUEST_TIMEOUT", "AIHUBMIX_REQUEST_TIMEOUT")
    if env_value:
        return _parse_request_timeout(env_value)

    return DEFAULT_REQUEST_TIMEOUT


def _create_runtime_client():
    config_data = _load_json_config()
    return Client(
        _resolve_api_key(config_data),
        timeout=_resolve_request_timeout(config_data),
        base_url=_resolve_base_url(config_data),
        poll_interval=_resolve_poll_interval(config_data),
    )


@contextmanager
def _runtime_client():
    client = _create_runtime_client()
    try:
        yield client
    finally:
        client.close()


def _raise_with_api_guidance(exc):
    if exc.status_code in {401, 403}:
        raise ValueError(
            f"The video API rejected the request with {exc.status_code}. "
            "Check api_key, base_url, billing, and model availability."
        ) from exc

    if exc.status_code == 429:
        raise ValueError("AIHubMix rate limit exceeded (429). Wait and retry.") from exc

    raise ValueError(str(exc)) from exc


def _tensor2images(tensor):
    np_imgs = numpy.clip(tensor.cpu().numpy() * 255.0, 0.0, 255.0).astype(numpy.uint8)
    return [PIL.Image.fromarray(np_img) for np_img in np_imgs]


def _encode_image(img):
    with io.BytesIO() as bytes_io:
        img.save(bytes_io, format="JPEG")
        return bytes_io.getvalue()


def _image_to_base64(image):
    if image is None:
        return None

    if isinstance(image, Iterable) and not isinstance(image, torch.Tensor):
        image = next(iter(image), None)

    if image is None:
        raise ValueError("image is required.")

    if isinstance(image, torch.Tensor) and image.ndim == 3:
        image = image.unsqueeze(0)

    pil_image = _tensor2images(image)[0]
    return base64.b64encode(_encode_image(pil_image)).decode("utf-8")


def _saved_result(filename, subfolder, folder_type):
    return {
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type,
    }


def _build_local_media_view_url(filename, subfolder, folder_type):
    query = [
        f"type={urllib.parse.quote(str(folder_type), safe='')}",
        f"filename={urllib.parse.quote(str(filename), safe='')}",
    ]
    if subfolder:
        query.append(f"subfolder={urllib.parse.quote(str(subfolder), safe='')}")
    return "/api/view?" + "&".join(query)


def _clean_prompt(prompt):
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string.")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required.")
    return prompt


def _submit_and_wait(client, model_name, payload):
    try:
        submission = submit_video_generation(client, model_name, payload)
    except VideoAPIError as exc:
        _raise_with_api_guidance(exc)

    task_id = extract_task_id(client, submission)

    try:
        task_info = wait_for_video_completion(client, task_id)
    except VideoAPIError as exc:
        _raise_with_api_guidance(exc)

    return task_id, task_info


def _build_video_result(client, task_id, task_info, filename_prefix, save_output):
    remote_video_url = extract_result_video_url(client, task_id, task_info)
    if not save_output:
        return {
            "ui": {"video_url": [remote_video_url]},
            "result": (remote_video_url, task_id, ""),
        }

    output_dir = folder_paths.get_output_directory()
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, output_dir)
    saved_name = f"{filename}_{counter:05}_.mp4"
    file_path = os.path.join(full_output_folder, saved_name)
    local_preview_url = _build_local_media_view_url(saved_name, subfolder, "output")

    client.download_to_file(remote_video_url, file_path)

    return {
        "ui": {
            "images": [_saved_result(saved_name, subfolder, "output")],
            "video_url": [local_preview_url],
            "animated": (True,),
        },
        "result": (remote_video_url, task_id, file_path),
    }


def _build_preview_result(video_url, filename_prefix, save_output):
    if isinstance(video_url, list):
        video_url = video_url[0] if video_url else ""

    video_url = str(video_url or "").strip()
    if not video_url:
        raise ValueError("video_url is required.")

    if not save_output:
        return {
            "ui": {"video_url": [video_url]},
            "result": ("",),
        }

    output_dir = folder_paths.get_output_directory()
    full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, output_dir)
    saved_name = f"{filename}_{counter:05}_.mp4"
    file_path = os.path.join(full_output_folder, saved_name)
    local_preview_url = _build_local_media_view_url(saved_name, subfolder, "output")

    with _runtime_client() as client:
        client.download_to_file(video_url, file_path)

    return {
        "ui": {
            "images": [_saved_result(saved_name, subfolder, "output")],
            "video_url": [local_preview_url],
            "animated": (True,),
        },
        "result": (file_path,),
    }


class _BaseVeoTextNode:
    MODEL_NAME = None
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("url", "video_id", "file_path")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    CATEGORY = NODE_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "seconds": (TEXT_SECONDS_OPTIONS, {"default": "4"}),
                "size": (SIZE_OPTIONS, {"default": "720p"}),
                "filename_prefix": ("STRING", {"default": DEFAULT_FILENAME_PREFIX}),
                "save_output": ("BOOLEAN", {"default": True}),
            }
        }

    def generate(self, prompt, seconds, size, filename_prefix=DEFAULT_FILENAME_PREFIX, save_output=True):
        with _runtime_client() as client:
            payload = build_text_video_payload(
                self.MODEL_NAME,
                _clean_prompt(prompt),
                seconds,
                size,
                provider=client.provider,
            )
            task_id, task_info = _submit_and_wait(client, self.MODEL_NAME, payload)
            print(f"[{NODE_PREFIX}] completed {self.MODEL_NAME} task_id={task_id}")
            return _build_video_result(client, task_id, task_info, filename_prefix, save_output)


class _BaseVeoImageNode:
    MODEL_NAME = None
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("url", "video_id", "file_path")
    FUNCTION = "generate"
    OUTPUT_NODE = True
    CATEGORY = NODE_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "image": ("IMAGE",),
                "size": (SIZE_OPTIONS, {"default": "720p"}),
                "filename_prefix": ("STRING", {"default": DEFAULT_FILENAME_PREFIX}),
                "save_output": ("BOOLEAN", {"default": True}),
            }
        }

    def generate(self, prompt, image, size, filename_prefix=DEFAULT_FILENAME_PREFIX, save_output=True):
        with _runtime_client() as client:
            image_reference = build_input_reference_payload(
                _image_to_base64(image),
                provider=client.provider,
            )
            payload = build_image_video_payload(
                self.MODEL_NAME,
                _clean_prompt(prompt),
                size,
                image_reference,
                provider=client.provider,
            )
            task_id, task_info = _submit_and_wait(client, self.MODEL_NAME, payload)
            print(f"[{NODE_PREFIX}] completed {self.MODEL_NAME} task_id={task_id}")
            return _build_video_result(client, task_id, task_info, filename_prefix, save_output)


class Veo31TextNode(_BaseVeoTextNode):
    MODEL_NAME = "veo-3.1-generate-preview"


class Veo31ImageNode(_BaseVeoImageNode):
    MODEL_NAME = "veo-3.1-generate-preview"


class Veo31FastTextNode(_BaseVeoTextNode):
    MODEL_NAME = "veo-3.1-fast-generate-preview"


class Veo31FastImageNode(_BaseVeoImageNode):
    MODEL_NAME = "veo-3.1-fast-generate-preview"


class PreviewVideoNode:
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = NODE_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {"forceInput": True}),
                "filename_prefix": ("STRING", {"default": DEFAULT_FILENAME_PREFIX}),
                "save_output": ("BOOLEAN", {"default": True}),
            }
        }

    def run(self, video_url, filename_prefix=DEFAULT_FILENAME_PREFIX, save_output=True):
        return _build_preview_result(video_url, filename_prefix, save_output)
