# How to run Mochi-1-preview on QB2 (P300x2)

**Model:** `genmo/mochi-1-preview`  
**Hardware:** QB2 — 2× P300 cards = 4 Blackhole chips in a (2,2) mesh  
**Status:** Working as of 2026-04-02 with the hotpatches described below

---

## Prerequisites

### Weights (~133 GB)
```bash
huggingface-cli download genmo/mochi-1-preview
```
Weights land in `~/.cache/huggingface/hub/models--genmo--mochi-1-preview/`.

### Docker image
```
ghcr.io/tenstorrent/tt-media-inference-server:0.10.0-555f240
```
Pull it ahead of time to avoid timeout during startup:
```bash
docker pull ghcr.io/tenstorrent/tt-media-inference-server:0.10.0-555f240
```

> **Note on image versions**: The dev `model_spec.py` references `0.12.0-555f240` (not yet published) and `0.11.1-bac8b34` (published but has no Mochi support — container exits silently). Use `0.10.0-555f240` from `release_model_spec.json`.

---

## Why hotpatches are needed

The `0.10.0-555f240` image was released before P300x2 (Blackhole) was a supported topology for Mochi. Two bugs in `pipeline_mochi.py` inside the container prevent it from starting on a (2,2) mesh:

### Bug 1 — assertion excludes (2,2) mesh

`tt-metal/models/tt_dit/pipelines/mochi/pipeline_mochi.py`, line 302:
```python
# Original — blocks (2,2):
assert tuple(mesh_device.shape) in [(2, 4), (4, 8)]

# Fixed:
assert tuple(mesh_device.shape) in [(2, 2), (2, 4), (4, 8)]
```
The `default_config` dict in the same file already had a complete `(2,2)` entry — only the guard was wrong.

### Bug 2 — VAE parallel config produces a missing map key

With `vae_mesh_shape=(2,2)` the VAE ends up with `time_parallel.factor=2`, but `ResBlock.core_grid_y_map[768]` in `vae_mochi.py` only has entries for factors 4 and 8.

Fix: change `vae_mesh_shape` in the `(2,2)` config to `(1,4)`, which reshapes the 4-chip mesh into a linear (1×4) arrangement for the VAE pass and gives `time_parallel.factor=4` — already in the map.

```python
# Original:
(2, 2): { ..., "vae_mesh_shape": (2, 2), ... }

# Fixed:
(2, 2): { ..., "vae_mesh_shape": (1, 4), ... }
```

This mirrors the pattern used on Wormhole: a (2,4) WH mesh uses `vae_mesh_shape=(1,8)` for the same reason.

---

## What was changed in tt-inference-server

### 1. `patches/tt_dit/pipelines/mochi/pipeline_mochi.py` (new file)

A copy of `pipeline_mochi.py` from inside the container with both fixes applied. This file is bind-mounted over the container's original at runtime.

### 2. `workflows/run_docker_server.py` (modified)

A new hotpatch block was added that, when `--dev-mode` is active, mounts every `.py` file under `patches/tt_dit/` into the container at its relative path inside `~/tt-metal/models/tt_dit/`:

```python
# Applies media-server tt_dit hotpatches in dev_mode.
if runtime_config.dev_mode:
    tt_dit_patches_dir = Path(repo_root_path) / "patches" / "tt_dit"
    if tt_dit_patches_dir.is_dir():
        for patch_file in sorted(tt_dit_patches_dir.rglob("*.py")):
            rel = patch_file.relative_to(tt_dit_patches_dir)
            dst = f"{user_home_path}/tt-metal/models/tt_dit/{rel}"
            docker_command += ["--mount", f"type=bind,src={patch_file},dst={dst},readonly"]
```

This is analogous to the existing per-model `patches/<impl_id>/` mechanism used for LLM models (e.g., `patches/gpt_oss/`).

---

## Starting the server

```bash
cd ~/code/tt-local-generator
./start_mochi.sh          # start and tail the log
./start_mochi.sh --gui    # start without interactive prompts (for GUI/scripts)
./start_mochi.sh --stop   # stop the running container
```

Startup takes **~5–8 minutes** (transformer warmup runs 2 full inference steps).  
The log line `Application startup complete.` confirms the server is ready.

Log file location:
```
~/code/tt-inference-server/workflow_logs/docker_server/media_<timestamp>_mochi-1-preview_p300x2_server.log
```

Health check:
```bash
curl http://localhost:8000/tt-liveness
# → {"status":"alive","model_ready":true,...,"runner_in_use":"tt-mochi-1"}
```

---

## API

**Endpoint:** `POST /v1/videos/generations` (note: **"videos"** plural — unlike WAN's `/v1/video/`)

**Auth:** `Authorization: Bearer your-secret-key`  
The media server uses a plain `API_KEY` env var (not JWT like the LLM server). The container default is `"your-secret-key"` when `API_KEY` is not set.

### Submit a job

```bash
curl -X POST http://localhost:8000/v1/videos/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-key" \
  -d '{
    "prompt": "a cat playing with a ball of yarn",
    "num_inference_steps": 20
  }'
# → {"id": "<job-id>", "status": "queued", ...}
```

### Poll for completion

```bash
JOB_ID="<job-id>"
curl http://localhost:8000/v1/videos/generations/$JOB_ID \
  -H "Authorization: Bearer your-secret-key"
# → {"status": "in_progress" | "completed" | "failed", ...}
```

### Download the video

```bash
curl http://localhost:8000/v1/videos/generations/$JOB_ID/download \
  -H "Authorization: Bearer your-secret-key" \
  -o output.mp4
```

**Generation time:** ~7 minutes per 168-frame (≈7 s) 480×848 video with `num_inference_steps=20`.

---

## Do the changes affect other models?

**No.** The two modifications are isolated:

| Change | Scope |
|--------|-------|
| `patches/tt_dit/pipelines/mochi/pipeline_mochi.py` | Only mounted when `dev_mode` is active. Only overrides the Mochi-specific pipeline file; WAN and other media models use different pipeline files at different paths. |
| `run_docker_server.py` — `tt_dit` hotpatch block | Additive and gated on `dev_mode` + `patches/tt_dit/` directory existing. Does not change any existing logic. Only relevant for models launched with `--dev-mode` that have files in `patches/tt_dit/`. |

The existing per-model `patches/<impl_id>/` hotpatch mechanism (used by LLM models like `gpt_oss`) is untouched.

One thing to keep in mind: any `.py` file placed under `patches/tt_dit/` will be mounted into **all** media server containers launched in `dev_mode` (not just Mochi). Keep patches scoped to model-specific subdirectories (e.g., `patches/tt_dit/pipelines/mochi/`) to avoid unintended side-effects on WAN or other DiT-based models.
