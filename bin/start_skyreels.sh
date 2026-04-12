#!/usr/bin/env bash
# start_skyreels.sh — Start the SkyReels-V2-DF-1.3B-540P inference server on Blackhole.
#
# Target hardware: Tenstorrent Blackhole
#   P150X4  — 4× P150 cards, (1, 4) mesh  (recommended: pure 4-way TP)
#   P300X2  — 2× P300 cards, (2, 2) mesh  (QB2 machine)
#
# Uses:
#   - Docker image: ghcr.io/tenstorrent/tt-media-inference-server:0.11.1-bac8b34
#   - --dev-mode: required to bind-mount the tt_dit hotpatch (pipeline_skyreels.py)
#   - --host-hf-cache: mounts host HF cache (avoids 12 GB download inside container)
#
# Prerequisites:
#   1. Apply patches first: cd tt-local-generator && bin/apply_patches.sh
#   2. SkyReels weights downloaded: python3 skyreels-ttlang/inference/download_weights.py
#   3. tt-inference-server .env with JWT_SECRET
#
# Notes:
#   - Weight loading takes 15-30 min (3.5B params × 4 chips over PCIe to Blackhole).
#   - The server timeout is set to 3600s in ModelConfigs for SkyReels runners.
#   - The server prints "Application startup complete" when ready (~20-35 min first run).
#
# Usage:
#   ./start_skyreels.sh [--device p150x4|p300x2] [--stop] [--gui] [--help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer vendored tt-inference-server if present.
if [[ -d "$REPO_ROOT/vendor/tt-inference-server" ]]; then
    REPO_DIR="$REPO_ROOT/vendor/tt-inference-server"
else
    REPO_DIR="$HOME/code/tt-inference-server"
fi

HF_CACHE="$HOME/.cache/huggingface"
DOCKER_IMAGE="ghcr.io/tenstorrent/tt-media-inference-server:0.11.1-bac8b34"
LOG_DIR="$REPO_DIR/workflow_logs/docker_server"

# ── Parse flags ───────────────────────────────────────────────────────────────

DEVICE="p300x2"
GUI_MODE=0

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            sed -n '2,29p' "$0" | sed 's/^# \?//'
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
        --device)
            # Next arg is the device type
            shift
            DEVICE="${1:-p300x2}"
            ;;
        p150x4|p300x2)
            DEVICE="$arg"
            ;;
    esac
done

LOG_GLOB="media_*_SkyReels-V2-DF-1.3B-540P-Diffusers_${DEVICE}_server.log"

# ── Sanity checks ─────────────────────────────────────────────────────────────

if [[ ! -d "$REPO_DIR" ]]; then
    echo "ERROR: tt-inference-server not found at $REPO_DIR"
    echo "Run: bin/apply_patches.sh"
    exit 1
fi

if [[ ! -d "$HF_CACHE/hub/models--Skywork--SkyReels-V2-DF-1.3B-540P-Diffusers" ]]; then
    echo "WARNING: SkyReels weights not found in HF cache at $HF_CACHE"
    echo "         Run: python3 skyreels-ttlang/inference/download_weights.py"
    echo "         (12 GB download — needed before first run)"
    if [[ $GUI_MODE -eq 1 ]]; then
        echo "         Continuing in GUI mode (weights will download inside container — slow)."
    else
        read -rp "Continue anyway? [y/N] " yn
        [[ "${yn,,}" == "y" ]] || exit 1
    fi
fi

# Verify patches have been applied
if [[ ! -f "$REPO_DIR/patches/tt_dit/pipelines/skyreels_v2/pipeline_skyreels.py" ]]; then
    echo "ERROR: SkyReels tt_dit hotpatch not found."
    echo "       Run: bin/apply_patches.sh"
    exit 1
fi

# ── Check for running container ───────────────────────────────────────────────

EXISTING=$(docker ps --filter "ancestor=$DOCKER_IMAGE" --format "{{.ID}}" 2>/dev/null | head -1)
if [[ -n "$EXISTING" ]]; then
    echo "Server already running in container $EXISTING"
    if [[ $GUI_MODE -eq 1 ]]; then
        echo "Server is already up."
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

# ── Launch ────────────────────────────────────────────────────────────────────

echo "Starting SkyReels-V2-DF-1.3B-540P on $DEVICE …"
echo "  Repo:      $REPO_DIR"
echo "  Image:     $DOCKER_IMAGE"
echo "  HF cache:  $HF_CACHE  (bind-mounted read-only)"
echo "  Port:      8000"
echo "  Note:      Weight loading takes 15-30 min — server not ready until that completes."
echo ""

mkdir -p "$LOG_DIR"
START_TS=$(date +%s)
cd "$REPO_DIR"

JWT_SECRET=$(grep -E '^JWT_SECRET=' "$REPO_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'" || true)
if [[ -z "$JWT_SECRET" ]]; then
    echo "ERROR: JWT_SECRET not found in $REPO_DIR/.env"
    exit 1
fi

# --dev-mode is required: it activates the tt_dit hotpatch bind-mount mechanism
# that injects pipeline_skyreels.py into the container at startup.
MODEL_SOURCE=huggingface JWT_SECRET="$JWT_SECRET" python3 run.py \
    --model SkyReels-V2-DF-1.3B-540P-Diffusers \
    --workflow server \
    --tt-device "$DEVICE" \
    --impl tt-transformers \
    --engine media \
    --docker-server \
    --dev-mode \
    --override-docker-image "$DOCKER_IMAGE" \
    --host-hf-cache "$HF_CACHE" &
WORKFLOW_PID=$!

echo "Workflow PID: $WORKFLOW_PID"
echo "Waiting for log file to appear in $LOG_DIR …"
echo ""

wait "$WORKFLOW_PID"
WORKFLOW_EXIT=$?

if [[ $WORKFLOW_EXIT -ne 0 ]]; then
    echo "ERROR: Workflow process exited with code $WORKFLOW_EXIT."
    LATEST=$(ls -t "$LOG_DIR"/$LOG_GLOB 2>/dev/null | head -1 || true)
    [[ -n "$LATEST" ]] && { echo "Last log: $LATEST"; tail -50 "$LATEST"; }
    exit 1
fi

LOG_FILE=$(ls -t "$LOG_DIR"/$LOG_GLOB 2>/dev/null \
           | while read -r f; do
               mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
               [[ $mtime -ge $START_TS ]] && echo "$f" && break
             done)

if [[ -z "$LOG_FILE" ]]; then
    echo "WARNING: Could not find a new log file in $LOG_DIR"
    echo "  Check manually: docker logs -f \$(docker ps -lq)"
    exit 0
fi

echo "Log file: $LOG_FILE"
echo ""
echo "Tip: the server prints 'Application startup complete' when ready."
echo "     Weight loading takes 15-30 min on first start."
echo ""

if [[ $GUI_MODE -eq 1 ]]; then
    echo "Server started in Docker. GUI health check will detect when ready."
    exit 0
fi

echo "(Ctrl-C to stop tailing — server keeps running in Docker)"
tail -f "$LOG_FILE"
