#!/usr/bin/env bash
# start_animate.sh — Start the Wan2.2-Animate-14B character animation server.
#
# This script starts the same tt-media-server Docker image used for T2V/FLUX,
# but bind-mounts the modified server files from this repo over their container
# counterparts so that the Animate runner (TTWan22AnimateRunner) is available
# without rebuilding the image.
#
# Phase 1 note: TTWan22AnimateRunner uses the Diffusers WanAnimatePipeline on
# CPU or CUDA — it does NOT use Tenstorrent hardware yet.  The container CMD
# is overridden to upgrade diffusers >= 0.34.0 before starting uvicorn.
#
# Hardware note: Animate-14B requires a reference motion video + character image;
# it produces a video of the character mimicking the motion (animation mode) or
# the character replacing the person in the reference video (replacement mode).
#
# Usage:
#   ./start_animate.sh             # start server and tail its log
#   ./start_animate.sh --stop      # stop the running server container
#   ./start_animate.sh --gui       # start without interactive prompts or tail
#   ./start_animate.sh --help      # show this help

set -euo pipefail

REPO_DIR="$HOME/code/tt-inference-server"
HF_CACHE="$HOME/.cache/huggingface"
DOCKER_IMAGE="ghcr.io/tenstorrent/tt-media-inference-server:0.11.1-bac8b34"
MODEL="Wan2.2-Animate-14B-Diffusers"
DEVICE="p150x4"
LOG_DIR="$REPO_DIR/workflow_logs/docker_server"
LOG_GLOB="media_*_${MODEL}_server.log"

# Paths inside the container where the tt-media-server is installed
# (from Dockerfile: COPY "tt-media-server" "${TT_METAL_HOME}/server")
CONTAINER_HOME="/home/container_app_user"
CONTAINER_SERVER="${CONTAINER_HOME}/tt-metal/server"
CONTAINER_PYTHON_ENV="${CONTAINER_HOME}/tt-metal/python_env"

# Local tt-media-server directory to bind-mount into the container
MEDIA_SERVER_DIR="$REPO_DIR/tt-media-server"

# ── Parse flags ───────────────────────────────────────────────────────────────

GUI_MODE=0
for arg in "$@"; do
    case "$arg" in
        --help|-h)
            sed -n '2,21p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        --stop)
            RUNNING=$(docker ps --filter "ancestor=$DOCKER_IMAGE" --format "{{.ID}}" 2>/dev/null)
            if [[ -z "$RUNNING" ]]; then
                echo "No running server container found."
                exit 0
            fi
            echo "Stopping container(s): $RUNNING"
            echo "$RUNNING" | xargs docker stop
            echo "Server stopped."
            exit 0
            ;;
        --gui)
            GUI_MODE=1
            ;;
    esac
done

# ── Sanity checks ─────────────────────────────────────────────────────────────

if [[ ! -d "$REPO_DIR" ]]; then
    echo "ERROR: tt-inference-server not found at $REPO_DIR"
    exit 1
fi

HF_CACHE_DIR="$HF_CACHE/hub/models--Wan-AI--Wan2.2-Animate-14B-Diffusers"
if [[ ! -d "$HF_CACHE_DIR" ]]; then
    echo "WARNING: Animate-14B weights not found at $HF_CACHE_DIR"
    echo "         Pre-download with:"
    echo "           huggingface-cli download Wan-AI/Wan2.2-Animate-14B-Diffusers"
    echo "         (~30 GB)"
    if [[ $GUI_MODE -eq 1 ]]; then
        echo "         Continuing in GUI mode (weights will download inside container)."
    else
        read -rp "Continue anyway (weights will download inside container)? [y/N] " yn
        [[ "${yn,,}" == "y" ]] || exit 1
    fi
fi

# ── Check for running container ───────────────────────────────────────────────

EXISTING=$(docker ps --filter "ancestor=$DOCKER_IMAGE" --format "{{.ID}}" 2>/dev/null | head -1)
if [[ -n "$EXISTING" ]]; then
    echo "Server already running in container $EXISTING"
    if [[ $GUI_MODE -eq 1 ]]; then
        echo "Server is already up. Use the GUI health indicator to confirm readiness."
        exit 0
    fi
    LATEST_LOG=$(ls -t "$LOG_DIR"/$LOG_GLOB 2>/dev/null | head -1 || true)
    if [[ -n "$LATEST_LOG" ]]; then
        echo "Tailing log: $LATEST_LOG"
        echo "(Ctrl-C to stop tailing — server keeps running)"
        exec tail -f "$LATEST_LOG"
    else
        echo "  Logs: docker logs -f $EXISTING"
        echo "  Stop: docker stop $EXISTING"
    fi
    exit 0
fi

# ── Read JWT secret ────────────────────────────────────────────────────────────

JWT_SECRET=$(grep -E '^JWT_SECRET=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)
if [[ -z "$JWT_SECRET" ]]; then
    echo "ERROR: JWT_SECRET not found in $REPO_DIR/.env"
    exit 1
fi
AUTH_TOKEN=$(grep -E '^AUTHORIZATION_TOKEN=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)

# ── Launch ─────────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"
echo "Starting Wan2.2-Animate-14B server…"
echo "  Image:     $DOCKER_IMAGE"
echo "  HF cache:  $HF_CACHE  (bind-mounted read-only)"
echo "  Port:      8000"
echo "  Note:      Phase 1 — Diffusers CPU/CUDA path (no TT hardware)"
echo ""

# The container CMD is overridden to:
#   1. Upgrade diffusers to >= 0.34.0 (WanAnimatePipeline requires it)
#   2. Start uvicorn as normal
#
# Modified server files are bind-mounted read-only over the container's copies
# so the Animate runner is available without rebuilding the image.
docker run \
    --rm \
    --name tt-animate-server \
    -p 8000:8000 \
    -e MODEL="$MODEL" \
    -e DEVICE="$DEVICE" \
    -e JWT_SECRET="$JWT_SECRET" \
    ${AUTH_TOKEN:+-e AUTHORIZATION_TOKEN="$AUTH_TOKEN"} \
    -e MODEL_SOURCE=huggingface \
    -v "$HF_CACHE:/home/container_app_user/.cache/huggingface:ro" \
    --mount "type=bind,src=${MEDIA_SERVER_DIR}/config/constants.py,dst=${CONTAINER_SERVER}/config/constants.py,readonly" \
    --mount "type=bind,src=${MEDIA_SERVER_DIR}/domain/video_generate_request.py,dst=${CONTAINER_SERVER}/domain/video_generate_request.py,readonly" \
    --mount "type=bind,src=${MEDIA_SERVER_DIR}/tt_model_runners/dit_runners.py,dst=${CONTAINER_SERVER}/tt_model_runners/dit_runners.py,readonly" \
    --mount "type=bind,src=${MEDIA_SERVER_DIR}/tt_model_runners/video_runner.py,dst=${CONTAINER_SERVER}/tt_model_runners/video_runner.py,readonly" \
    --mount "type=bind,src=${MEDIA_SERVER_DIR}/tt_model_runners/runner_fabric.py,dst=${CONTAINER_SERVER}/tt_model_runners/runner_fabric.py,readonly" \
    "$DOCKER_IMAGE" \
    /bin/bash -c "
        source ${CONTAINER_PYTHON_ENV}/bin/activate
        echo '>>> Upgrading diffusers for WanAnimatePipeline support...'
        pip install -q 'diffusers>=0.34.0' || { echo 'WARNING: diffusers upgrade failed; trying anyway'; }
        echo '>>> Starting uvicorn...'
        cd ${CONTAINER_SERVER}
        source ./run_uvicorn.sh
    " &

DOCKER_PID=$!
echo "Docker container starting (PID: $DOCKER_PID)"
echo "Waiting for server to become ready…"
echo ""

if [[ $GUI_MODE -eq 1 ]]; then
    echo "Server started in Docker. GUI health check will detect when ready."
    exit 0
fi

# Tail docker logs in interactive mode
echo "Tailing container logs (Ctrl-C to stop tailing — server keeps running)"
sleep 2
docker logs -f tt-animate-server 2>/dev/null || wait "$DOCKER_PID"
