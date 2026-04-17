import json
import time
import urllib.parse


TEXT_SECONDS_OPTIONS = ["4", "6", "8"]
SIZE_OPTIONS = ["720p", "1080p", "4k"]
DEFAULT_IMAGE_SECONDS = "8"
DEFAULT_IMAGE_REFERENCE_MIME_TYPE = "image/jpeg"

ACTIVE_VIDEO_STATUSES = {"queued", "pending", "running", "in_progress"}
FAILURE_VIDEO_STATUSES = {"failed", "error", "cancelled"}
COMPLETED_VIDEO_STATUS = "completed"


def _clean_prompt(prompt):
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string.")
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required.")
    return prompt


def _validate_seconds(seconds):
    normalized = str(seconds).strip()
    if normalized not in TEXT_SECONDS_OPTIONS:
        raise ValueError(f"seconds must be one of: {', '.join(TEXT_SECONDS_OPTIONS)}.")
    return normalized


def _validate_size(size):
    normalized = str(size).strip()
    if normalized not in SIZE_OPTIONS:
        raise ValueError(f"size must be one of: {', '.join(SIZE_OPTIONS)}.")
    return normalized


def build_input_reference_payload(base64_data, mime_type=DEFAULT_IMAGE_REFERENCE_MIME_TYPE):
    if not isinstance(base64_data, str) or not base64_data.strip():
        raise ValueError("input reference image data is required.")
    return {
        "mime_type": mime_type,
        "data": base64_data,
    }


def build_text_video_payload(model_name, prompt, seconds, size):
    return {
        "model": str(model_name).strip(),
        "prompt": _clean_prompt(prompt),
        "seconds": _validate_seconds(seconds),
        "size": _validate_size(size),
    }


def build_image_video_payload(model_name, prompt, size, input_reference):
    if not isinstance(input_reference, (dict, str)):
        raise ValueError("input_reference must be a dict or string.")

    return {
        "model": str(model_name).strip(),
        "prompt": _clean_prompt(prompt),
        "seconds": DEFAULT_IMAGE_SECONDS,
        "size": _validate_size(size),
        "input_reference": input_reference,
    }


def submit_video_generation(client, payload):
    return client.request("POST", "/v1/videos", json=payload)


def fetch_video_status(client, video_id):
    safe_video_id = urllib.parse.quote(str(video_id).strip(), safe="")
    return client.request("GET", f"/v1/videos/{safe_video_id}")


def video_content_path(video_id):
    safe_video_id = urllib.parse.quote(str(video_id).strip(), safe="")
    return f"/v1/videos/{safe_video_id}/content"


def describe_task_error(task_info):
    if not isinstance(task_info, dict):
        return "Unknown video task error."

    error_payload = task_info.get("error")
    if isinstance(error_payload, dict):
        return error_payload.get("message") or json.dumps(error_payload, ensure_ascii=False)
    if error_payload:
        return str(error_payload)

    status = task_info.get("status") or "unknown"
    return f"Video generation ended with status={status}."


def wait_for_video_completion(client, video_id):
    while True:
        task_info = fetch_video_status(client, video_id)
        status = str(task_info.get("status", "")).strip().lower()

        if status == COMPLETED_VIDEO_STATUS:
            return task_info

        if status in FAILURE_VIDEO_STATUSES:
            raise RuntimeError(describe_task_error(task_info))

        if status not in ACTIVE_VIDEO_STATUSES:
            raise RuntimeError(f"Unexpected video task status: {status or 'unknown'}.")

        time.sleep(client.poll_interval)
