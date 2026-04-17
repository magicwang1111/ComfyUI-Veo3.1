# ComfyUI-Veo3.1

`ComfyUI-Veo3.1` is a small ComfyUI custom node pack for generating Veo 3.1 videos through either AIHubMix's unified video API or Google's native Gemini Developer API.

It exposes three nodes under the `ComfyUI-Veo3.1` category:

- `ComfyUI-Veo3.1 Text-to-Video`
- `ComfyUI-Veo3.1 Image-to-Video`
- `ComfyUI-Veo3.1 Preview Video`

## What It Supports

- Model switching inside the text node: `veo-3.1-lite-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`
- Model switching inside the image node: `veo-3.1-lite-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`
- AIHubMix relay mode through `https://aihubmix.com`
- Google native mode through `https://generativelanguage.googleapis.com/v1beta`
- A standalone `Preview Video` node for explicit playback and saving
- Saving finished MP4 files into ComfyUI output
- Remote preview when `save_output` is disabled

## Current API Notes

- `seconds` is limited to `4`, `6`, or `8` for text-to-video.
- Image-to-video is fixed to `8` seconds.
- `size` is intentionally limited to `720p`, `1080p`, and `4k`.
- The plugin does not expose a portrait/landscape toggle in v1.
- When using Google native Veo, `1080p` and `4k` text-to-video require `8` seconds per the official Gemini API documentation.
- The text and image nodes now use a single `model` dropdown instead of separate nodes per model.
- Generation nodes no longer display inline previews. Connect their `url` output to `ComfyUI-Veo3.1 Preview Video`.
- On April 17, 2026, AIHubMix Veo 3.1 image-to-video probes still failed with the upstream error `` `inlineData` isn't supported by this model `` on both `https://aihubmix.com/v1/videos` and `https://aihubmix.com/gemini/v1beta`. The plugin now surfaces that limitation with a clearer error message instead of dumping the raw gateway trace.
- As of April 17, 2026, AIHubMix's public Video Gen docs list `veo-3.1-generate-preview` and `veo-3.1-fast-generate-preview`, but do not list `veo-3.1-lite-generate-preview`. The dropdown still includes Lite so you can use it against Google native Veo directly, but AIHubMix relay support for Lite may lag behind.

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

- `VEO_API_KEY`
- `VEO_BASE_URL`
- `VEO_POLL_INTERVAL`
- `VEO_REQUEST_TIMEOUT`
- `AIHUBMIX_API_KEY`
- `AIHUBMIX_BASE_URL`
- `AIHUBMIX_POLL_INTERVAL`
- `AIHUBMIX_REQUEST_TIMEOUT`
- `GOOGLE_API_KEY`
- `GEMINI_API_KEY`

Priority:

1. `config.local.json`
2. Environment variables

`base_url` decides which backend the plugin uses:

- `https://aihubmix.com` or `https://aihubmix.com/v1`
  Uses AIHubMix relay mode with `Authorization: Bearer ...`
- `https://generativelanguage.googleapis.com` or `https://generativelanguage.googleapis.com/v1beta`
  Uses Google's native Gemini Developer API with `x-goog-api-key: ...`

The plugin auto-detects the provider from `base_url`, so the node interface stays the same.

Google native example:

```json
{
  "api_key": "YOUR_GOOGLE_API_KEY",
  "base_url": "https://generativelanguage.googleapis.com/v1beta",
  "poll_interval": 15.0,
  "request_timeout": 60
}
```

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

- `model`: `veo-3.1-lite-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`
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

- `model`: `veo-3.1-lite-generate-preview`, `veo-3.1-fast-generate-preview`, `veo-3.1-generate-preview`
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

- Image nodes always send `seconds = "8"` to the backend.
- In AIHubMix mode, `url` returns `/v1/videos/{video_id}/content`.
- In Google native mode, `url` returns the generated video download URI from the completed operation.
- `file_path` is only populated when `save_output` is enabled.
- To preview the generated video inside ComfyUI, connect `url` to `ComfyUI-Veo3.1 Preview Video`.

### Preview Video Node

Inputs:

- `video_url`
- `filename_prefix`
- `save_output`

Outputs:

- `file_path`

Notes:

- Use this node when you want a dedicated preview widget in the workflow, similar to the Kling wrapper.
- With `save_output=false`, it previews the remote URL directly.
- With `save_output=true`, it downloads the MP4 to ComfyUI output first, then previews the local file.

## Examples

Two example workflow JSON files live in [examples/](./examples):

- [01_comfyui_veo31_text_workflow.json](./examples/01_comfyui_veo31_text_workflow.json)
- [02_comfyui_veo31_image_workflow.json](./examples/02_comfyui_veo31_image_workflow.json)

See [examples/README.md](./examples/README.md) for a quick description of each one.

## References

- [AIHubMix Video Gen documentation (CN)](https://docs.aihubmix.com/cn/api/Video-Gen)
- [AIHubMix Video Gen documentation (EN)](https://docs.aihubmix.com/en/api/Video-Gen)
- [Generate videos with Veo 3.1 in Gemini API](https://ai.google.dev/gemini-api/docs/video)
- [Gemini API pricing for Veo 3.1](https://ai.google.dev/gemini-api/docs/pricing)
