# ComfyUI-Veo3.1

`ComfyUI-Veo3.1` is a small ComfyUI custom node pack for generating Veo 3.1 videos through AIHubMix's unified video API.

It exposes four output nodes under the `ComfyUI-Veo3.1` category:

- `ComfyUI-Veo3.1 veo-3.1-generate-preview (Text)`
- `ComfyUI-Veo3.1 veo-3.1-generate-preview (Image)`
- `ComfyUI-Veo3.1 veo-3.1-fast-generate-preview (Text)`
- `ComfyUI-Veo3.1 veo-3.1-fast-generate-preview (Image)`

## What It Supports

- Text-to-video for `veo-3.1-generate-preview`
- Image-to-video for `veo-3.1-generate-preview`
- Text-to-video for `veo-3.1-fast-generate-preview`
- Image-to-video for `veo-3.1-fast-generate-preview`
- Inline video preview on the generation node itself
- Saving finished MP4 files into ComfyUI output
- Remote preview when `save_output` is disabled

## Current API Notes

- `seconds` is limited to `4`, `6`, or `8` for text-to-video.
- Image-to-video is fixed to `8` seconds.
- `size` is intentionally limited to `720p`, `1080p`, and `4k`.
- The plugin does not expose a portrait/landscape toggle in v1.

Why the direction toggle is hidden:
- On April 17, 2026, live probes against `https://aihubmix.com/v1/videos` accepted both `aspect_ratio: "9:16"` and `ratio: "9:16"` with `size: "720p"`, but the completed outputs still rendered at `1280x720`.
- To avoid a misleading UI, this plugin currently keeps the interface to the fields that are confirmed to work end-to-end.

## Configuration

Create [config.local.json](./config.local.json) in the repository root. Use [config.example.json](./config.example.json) as the template.

```json
{
  "api_key": "",
  "base_url": "https://aihubmix.com",
  "poll_interval": 15.0,
  "request_timeout": 60
}
```

Supported environment variables:

- `AIHUBMIX_API_KEY`
- `AIHUBMIX_BASE_URL`
- `AIHUBMIX_POLL_INTERVAL`
- `AIHUBMIX_REQUEST_TIMEOUT`

Priority:

1. `config.local.json`
2. Environment variables

`base_url` accepts either `https://aihubmix.com` or `https://aihubmix.com/v1`. The plugin normalizes both forms to the same internal base URL.

## Installation

1. Place this folder under `ComfyUI/custom_nodes`.
2. Install Python dependencies:

   ```bash
   pip install -r ComfyUI/custom_nodes/ComfyUI-Veo3.1/requirements.txt
   ```

3. Add `config.local.json`.
4. Restart ComfyUI.

## Node Interfaces

### Text Nodes

Inputs:

- `prompt`
- `seconds`: `4`, `6`, `8`
- `size`: `720p`, `1080p`, `4k`
- `filename_prefix`
- `save_output`

Outputs:

- `url`
- `video_id`
- `file_path`

### Image Nodes

Inputs:

- `prompt`
- `image`
- `size`: `720p`, `1080p`, `4k`
- `filename_prefix`
- `save_output`

Outputs:

- `url`
- `video_id`
- `file_path`

Notes:

- Image nodes always send `seconds = "8"` to AIHubMix.
- `url` always returns the remote AIHubMix `/v1/videos/{video_id}/content` URL.
- `file_path` is only populated when `save_output` is enabled.

## Examples

Two example workflow JSON files live in [examples/](./examples):

- [01_comfyui_veo31_text_workflow.json](./examples/01_comfyui_veo31_text_workflow.json)
- [02_comfyui_veo31_image_workflow.json](./examples/02_comfyui_veo31_image_workflow.json)

See [examples/README.md](./examples/README.md) for a quick description of each one.

## References

- [AIHubMix Video Gen documentation (CN)](https://docs.aihubmix.com/cn/api/Video-Gen)
- [AIHubMix Video Gen documentation (EN)](https://docs.aihubmix.com/en/api/Video-Gen)
