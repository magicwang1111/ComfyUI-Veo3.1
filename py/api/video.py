import json
import time
import urllib.parse

from .client import PROVIDER_AIHUBMIX, PROVIDER_GOOGLE


TEXT_SECONDS_OPTIONS = ["4", "6", "8"]
SIZE_OPTIONS = ["720p", "1080p", "4k"]
MODEL_OPTIONS = [
    "veo-3.1-lite-generate-preview",
    "veo-3.1-fast-generate-preview",
    "veo-3.1-generate-preview",
]
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


def _validate_model_name(model_name):
    normalized = str(model_name).strip()
    if normalized not in MODEL_OPTIONS:
        raise ValueError(f"model must be one of: {', '.join(MODEL_OPTIONS)}.")
    return normalized


def _validate_google_resolution_duration(size, seconds):
    if size in {"1080p", "4k"} and str(seconds).strip() != DEFAULT_IMAGE_SECONDS:
        raise ValueError("Google native Veo requires duration_seconds=8 when resolution is 1080p or 4k.")


def build_input_reference_payload(
    base64_data,
    mime_type=DEFAULT_IMAGE_REFERENCE_MIME_TYPE,
    provider=PROVIDER_AIHUBMIX,
):
    if not isinstance(base64_data, str) or not base64_data.strip():
        raise ValueError("input reference image data is required.")
    if provider == PROVIDER_GOOGLE:
        return {
            "inlineData": {
                "mimeType": mime_type,
                "data": base64_data,
            }
        }
    return {
        "mime_type": mime_type,
        "data": base64_data,
    }


def build_text_video_payload(model_name, prompt, seconds, size, provider=PROVIDER_AIHUBMIX):
    validated_model = _validate_model_name(model_name)
    cleaned_prompt = _clean_prompt(prompt)
    validated_seconds = _validate_seconds(seconds)
    validated_size = _validate_size(size)

    if provider == PROVIDER_GOOGLE:
        _validate_google_resolution_duration(validated_size, validated_seconds)
        return {
            "instances": [
                {
                    "prompt": cleaned_prompt,
                }
            ],
            "parameters": {
                "durationSeconds": validated_seconds,
                "resolution": validated_size,
            },
        }

    return {
        "model": validated_model,
        "prompt": cleaned_prompt,
        "seconds": validated_seconds,
        "size": validated_size,
    }


def build_image_video_payload(model_name, prompt, size, input_reference, provider=PROVIDER_AIHUBMIX):
    if not isinstance(input_reference, (dict, str)):
        raise ValueError("input_reference must be a dict or string.")

    validated_model = _validate_model_name(model_name)
    cleaned_prompt = _clean_prompt(prompt)
    validated_size = _validate_size(size)

    if provider == PROVIDER_GOOGLE:
        return {
            "instances": [
                {
                    "prompt": cleaned_prompt,
                    "image": input_reference,
                }
            ],
            "parameters": {
                "durationSeconds": DEFAULT_IMAGE_SECONDS,
                "resolution": validated_size,
            },
        }

    return {
        "model": validated_model,
        "prompt": cleaned_prompt,
        "seconds": DEFAULT_IMAGE_SECONDS,
        "size": validated_size,
        "input_reference": input_reference,
    }


def submit_video_generation(client, model_name, payload):
    if client.provider == PROVIDER_GOOGLE:
        path = client.absolute_url(f"/models/{urllib.parse.quote(str(model_name).strip(), safe='-._')}:predictLongRunning")
        return client.request("POST", path, json=payload)
    return client.request("POST", "/v1/videos", json=payload)


def fetch_video_status(client, task_id):
    safe_task_id = str(task_id).strip()
    if client.provider == PROVIDER_GOOGLE:
        return client.request("GET", client.absolute_url(f"/{safe_task_id.lstrip('/')}"))
    safe_video_id = urllib.parse.quote(safe_task_id, safe="")
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

    google_error = task_info.get("error")
    if isinstance(google_error, dict):
        return google_error.get("message") or json.dumps(google_error, ensure_ascii=False)
    if google_error:
        return str(google_error)

    status = task_info.get("status") or "unknown"
    return f"Video generation ended with status={status}."


def wait_for_video_completion(client, task_id):
    while True:
        task_info = fetch_video_status(client, task_id)

        if client.provider == PROVIDER_GOOGLE:
            if task_info.get("done") is True:
                if task_info.get("error"):
                    raise RuntimeError(describe_task_error(task_info))
                return task_info
            time.sleep(client.poll_interval)
            continue

        status = str(task_info.get("status", "")).strip().lower()

        if status == COMPLETED_VIDEO_STATUS:
            return task_info

        if status in FAILURE_VIDEO_STATUSES:
            raise RuntimeError(describe_task_error(task_info))

        if status not in ACTIVE_VIDEO_STATUSES:
            raise RuntimeError(f"Unexpected video task status: {status or 'unknown'}.")

        time.sleep(client.poll_interval)


def extract_task_id(client, submission):
    key = "name" if client.provider == PROVIDER_GOOGLE else "id"
    task_id = str(submission.get(key) or "").strip()
    if not task_id:
        raise ValueError(f"Video API did not return a task identifier in `{key}`.")
    return task_id


def _extract_google_generated_video(task_info):
    response_payload = task_info.get("response") or {}
    if isinstance(response_payload.get("generateVideoResponse"), dict):
        response_payload = response_payload["generateVideoResponse"]

    generated_samples = response_payload.get("generatedSamples") or response_payload.get("generatedVideos") or []
    if not generated_samples:
        raise ValueError("Google native Veo response did not include generated video samples.")

    video_payload = generated_samples[0].get("video")
    if not isinstance(video_payload, dict):
        raise ValueError("Google native Veo response did not include a downloadable video payload.")

    video_uri = str(video_payload.get("uri") or "").strip()
    if not video_uri:
        raise ValueError("Google native Veo response did not include a video download URI.")

    return video_uri


def extract_result_video_url(client, task_id, task_info):
    if client.provider == PROVIDER_GOOGLE:
        return _extract_google_generated_video(task_info)
    return client.absolute_url(video_content_path(task_id))
