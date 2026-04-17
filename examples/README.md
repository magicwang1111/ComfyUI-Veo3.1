# Examples

This folder contains two small starter workflows for the Veo generation nodes plus the standalone preview node:

- `01_comfyui_veo31_text_workflow.json`
  Uses `ComfyUI-Veo3.1 veo-3.1-generate-preview (Text)` and pipes the returned `url` into `ComfyUI-Veo3.1 Preview Video`.

- `02_comfyui_veo31_image_workflow.json`
  Uses `LoadImage`, `ComfyUI-Veo3.1 veo-3.1-fast-generate-preview (Image)`, and `ComfyUI-Veo3.1 Preview Video`.

Prepare `config.local.json` first, then import the workflow you want to start from.
