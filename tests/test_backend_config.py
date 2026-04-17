import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import numpy


REPO_ROOT = Path(__file__).resolve().parents[1]
COMFYUI_ROOT = REPO_ROOT.parent.parent
if str(COMFYUI_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFYUI_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_fake_torch():
    if "torch" in sys.modules:
        return

    try:
        import torch  # noqa: F401
        return
    except ImportError:
        pass

    fake_torch = types.ModuleType("torch")

    class FakeTensor:
        def __init__(self, array):
            self._array = numpy.array(array, dtype=numpy.float32, copy=False)

        @property
        def ndim(self):
            return self._array.ndim

        def unsqueeze(self, axis):
            return FakeTensor(numpy.expand_dims(self._array, axis))

        def cpu(self):
            return self

        def numpy(self):
            return self._array

    fake_torch.Tensor = FakeTensor
    sys.modules["torch"] = fake_torch


_install_fake_torch()

veo_package = importlib.import_module("py")
veo_nodes = importlib.import_module("py.nodes")
client_module = importlib.import_module("py.api.client")
video_api = importlib.import_module("py.api.video")


ENV_KEYS = {
    "VEO_API_KEY": "",
    "VEO_BASE_URL": "",
    "VEO_POLL_INTERVAL": "",
    "VEO_REQUEST_TIMEOUT": "",
    "AIHUBMIX_API_KEY": "",
    "AIHUBMIX_BASE_URL": "",
    "AIHUBMIX_POLL_INTERVAL": "",
    "AIHUBMIX_REQUEST_TIMEOUT": "",
    "GOOGLE_API_KEY": "",
    "GEMINI_API_KEY": "",
}


class FakeResolvedClient:
    def __init__(self, api_key, timeout=60, base_url=None, poll_interval=15.0):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url
        self.poll_interval = poll_interval
        self.provider = client_module.Client.detect_provider(base_url)

    def absolute_url(self, path):
        if isinstance(path, str) and path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}{path}"

    def download_to_file(self, path, file_path):
        with open(file_path, "wb") as handle:
            handle.write(b"video-bytes")

    def close(self):
        pass


class FakeVideoClient(FakeResolvedClient):
    def __init__(self, responses, base_url="https://aihubmix.com"):
        super().__init__("fake-key", timeout=60, base_url=base_url, poll_interval=0.0)
        self._responses = list(responses)
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self._responses.pop(0)


class BackendConfigTests(unittest.TestCase):
    def test_node_mapping_contains_four_generation_nodes(self):
        self.assertEqual(len(veo_package.NODE_CLASS_MAPPINGS), 4)
        self.assertIn("ComfyUI-Veo3.1 veo-3.1-generate-preview (Text)", veo_package.NODE_CLASS_MAPPINGS)
        self.assertIn("ComfyUI-Veo3.1 veo-3.1-fast-generate-preview (Image)", veo_package.NODE_CLASS_MAPPINGS)

    def test_runtime_client_prefers_config_local_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            json_path = tmpdir_path / "config.local.json"

            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "json-key",
                        "base_url": "https://json.example.com/v1/",
                        "poll_interval": 12.5,
                        "request_timeout": 90,
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {**ENV_KEYS, "AIHUBMIX_API_KEY": "env-key", "AIHUBMIX_BASE_URL": "https://env.example.com"},
                clear=False,
            ):
                with mock.patch.object(veo_nodes, "CONFIG_JSON_PATH", json_path):
                    with mock.patch.object(veo_nodes, "Client", FakeResolvedClient):
                        client = veo_nodes._create_runtime_client()

            self.assertEqual(client.api_key, "json-key")
            self.assertEqual(client.timeout, 90)
            self.assertEqual(client.base_url, "https://json.example.com")
            self.assertEqual(client.poll_interval, 12.5)

    def test_runtime_client_uses_env_when_json_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "config.local.json"

            with mock.patch.dict(
                os.environ,
                {
                    **ENV_KEYS,
                    "AIHUBMIX_API_KEY": "env-key",
                    "AIHUBMIX_BASE_URL": "https://env.example.com/v1/",
                    "AIHUBMIX_POLL_INTERVAL": "20",
                    "AIHUBMIX_REQUEST_TIMEOUT": "75",
                },
                clear=False,
            ):
                with mock.patch.object(veo_nodes, "CONFIG_JSON_PATH", json_path):
                    with mock.patch.object(veo_nodes, "Client", FakeResolvedClient):
                        client = veo_nodes._create_runtime_client()

            self.assertEqual(client.api_key, "env-key")
            self.assertEqual(client.timeout, 75)
            self.assertEqual(client.base_url, "https://env.example.com")
            self.assertEqual(client.poll_interval, 20.0)

    def test_client_normalizes_base_url(self):
        client = client_module.Client("test-key", base_url="https://aihubmix.com/v1/")
        try:
            self.assertEqual(client.base_url, "https://aihubmix.com")
        finally:
            client.close()

    def test_client_normalizes_google_base_url_and_switches_provider(self):
        client = client_module.Client("test-key", base_url="https://generativelanguage.googleapis.com")
        try:
            self.assertEqual(client.base_url, "https://generativelanguage.googleapis.com/v1beta")
            self.assertEqual(client.provider, client_module.PROVIDER_GOOGLE)
            self.assertEqual(client._client.headers.get("x-goog-api-key"), "test-key")
        finally:
            client.close()

    def test_text_payload_contains_expected_fields(self):
        payload = video_api.build_text_video_payload(
            "veo-3.1-generate-preview",
            "A calm coastal scene.",
            "4",
            "720p",
        )
        self.assertEqual(payload["model"], "veo-3.1-generate-preview")
        self.assertEqual(payload["prompt"], "A calm coastal scene.")
        self.assertEqual(payload["seconds"], "4")
        self.assertEqual(payload["size"], "720p")
        self.assertNotIn("input_reference", payload)

    def test_google_text_payload_uses_instances_and_parameters(self):
        payload = video_api.build_text_video_payload(
            "veo-3.1-generate-preview",
            "A calm coastal scene.",
            "8",
            "1080p",
            provider=client_module.PROVIDER_GOOGLE,
        )
        self.assertEqual(payload["instances"][0]["prompt"], "A calm coastal scene.")
        self.assertEqual(payload["parameters"]["durationSeconds"], "8")
        self.assertEqual(payload["parameters"]["resolution"], "1080p")

    def test_google_text_payload_blocks_short_1080p_requests(self):
        with self.assertRaises(ValueError):
            video_api.build_text_video_payload(
                "veo-3.1-generate-preview",
                "A calm coastal scene.",
                "4",
                "1080p",
                provider=client_module.PROVIDER_GOOGLE,
            )

    def test_image_payload_forces_8_seconds(self):
        input_reference = video_api.build_input_reference_payload("ZmFrZS1iYXNlNjQ=")
        payload = video_api.build_image_video_payload(
            "veo-3.1-fast-generate-preview",
            "A paper lantern in motion.",
            "1080p",
            input_reference,
        )
        self.assertEqual(payload["seconds"], "8")
        self.assertEqual(payload["size"], "1080p")
        self.assertEqual(payload["input_reference"]["mime_type"], "image/jpeg")

    def test_google_image_payload_uses_inline_data(self):
        input_reference = video_api.build_input_reference_payload(
            "ZmFrZS1iYXNlNjQ=",
            provider=client_module.PROVIDER_GOOGLE,
        )
        payload = video_api.build_image_video_payload(
            "veo-3.1-fast-generate-preview",
            "A paper lantern in motion.",
            "720p",
            input_reference,
            provider=client_module.PROVIDER_GOOGLE,
        )
        self.assertEqual(payload["instances"][0]["image"]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(payload["parameters"]["durationSeconds"], "8")

    def test_wait_for_video_completion_polls_until_completed(self):
        client = FakeVideoClient(
            [
                {"id": "video-123", "status": "queued"},
                {"id": "video-123", "status": "running"},
                {"id": "video-123", "status": "completed"},
            ]
        )
        result = video_api.wait_for_video_completion(client, "video-123")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(client.calls), 3)

    def test_wait_for_google_operation_completion_polls_until_done(self):
        client = FakeVideoClient(
            [
                {"name": "operations/video-123", "done": False},
                {"name": "operations/video-123", "done": True, "response": {"generateVideoResponse": {"generatedSamples": [{"video": {"uri": "https://example.com/video.mp4"}}]}}},
            ],
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )
        result = video_api.wait_for_video_completion(client, "operations/video-123")
        self.assertTrue(result["done"])
        self.assertEqual(len(client.calls), 2)

    def test_google_result_url_uses_generated_video_uri(self):
        client = FakeVideoClient([], base_url="https://generativelanguage.googleapis.com/v1beta")
        task_info = {
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {"video": {"uri": "https://example.com/generated.mp4"}}
                    ]
                }
            }
        }
        self.assertEqual(
            video_api.extract_result_video_url(client, "operations/video-123", task_info),
            "https://example.com/generated.mp4",
        )

    def test_text_node_returns_remote_preview_url_when_save_disabled(self):
        fake_client = FakeVideoClient(
            [
                {"id": "video-123", "status": "in_progress"},
                {"id": "video-123", "status": "completed"},
            ]
        )

        @contextmanager
        def fake_runtime_client():
            yield fake_client

        with mock.patch.object(veo_nodes, "_runtime_client", fake_runtime_client):
            result = veo_nodes.Veo31TextNode().generate(
                "A calm coastal scene.",
                "4",
                "720p",
                "ComfyUI-Veo3.1",
                False,
            )

        self.assertEqual(
            result["ui"]["video_url"],
            ["https://aihubmix.com/v1/videos/video-123/content"],
        )
        self.assertEqual(
            result["result"],
            ("https://aihubmix.com/v1/videos/video-123/content", "video-123", ""),
        )

    def test_google_text_node_returns_generated_video_uri_when_save_disabled(self):
        fake_client = FakeVideoClient(
            [
                {"name": "operations/video-abc", "done": False},
                {
                    "name": "operations/video-abc",
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [
                                {"video": {"uri": "https://example.com/generated-google.mp4"}}
                            ]
                        }
                    },
                },
            ],
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )

        @contextmanager
        def fake_runtime_client():
            yield fake_client

        with mock.patch.object(veo_nodes, "_runtime_client", fake_runtime_client):
            result = veo_nodes.Veo31TextNode().generate(
                "A calm coastal scene.",
                "4",
                "720p",
                "ComfyUI-Veo3.1",
                False,
            )

        self.assertEqual(
            result["ui"]["video_url"],
            ["https://example.com/generated-google.mp4"],
        )
        self.assertEqual(
            result["result"],
            ("https://example.com/generated-google.mp4", "operations/video-abc", ""),
        )

    def test_text_node_saves_local_video_when_requested(self):
        fake_client = FakeVideoClient(
            [
                {"id": "video-999", "status": "in_progress"},
                {"id": "video-999", "status": "completed"},
            ]
        )

        @contextmanager
        def fake_runtime_client():
            yield fake_client

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            with mock.patch.object(veo_nodes, "_runtime_client", fake_runtime_client):
                with mock.patch.object(veo_nodes.folder_paths, "get_output_directory", return_value=str(tmpdir_path)):
                    with mock.patch.object(
                        veo_nodes.folder_paths,
                        "get_save_image_path",
                        return_value=(str(tmpdir_path), "ComfyUI-Veo3.1", 1, "", None),
                    ):
                        result = veo_nodes.Veo31TextNode().generate(
                            "A calm coastal scene.",
                            "4",
                            "720p",
                            "ComfyUI-Veo3.1",
                            True,
                        )

        self.assertEqual(
            result["ui"]["video_url"],
            ["/api/view?type=output&filename=ComfyUI-Veo3.1_00001_.mp4"],
        )
        self.assertEqual(
            result["result"][0],
            "https://aihubmix.com/v1/videos/video-999/content",
        )
        self.assertTrue(result["result"][2].endswith("ComfyUI-Veo3.1_00001_.mp4"))

    def test_examples_are_valid_json(self):
        examples_dir = REPO_ROOT / "examples"
        example_files = sorted(examples_dir.glob("*.json"))
        self.assertGreaterEqual(len(example_files), 2)

        for example_path in example_files:
            data = json.loads(example_path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)


if __name__ == "__main__":
    unittest.main()
