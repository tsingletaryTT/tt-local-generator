#!/usr/bin/env bash
# apply_patches.sh — Apply tt-local-generator patches to a tt-inference-server checkout.
#
# What this does:
#   1. Copies patches/tt_dit/ into <tt-inference-server>/patches/tt_dit/ so the
#      hotpatched DiT pipeline files are available for bind-mounting by run.py.
#
#   2. Inserts the tt_dit hotpatch block into
#      <tt-inference-server>/workflows/run_docker_server.py if it is not already
#      present.  The block teaches run_docker_server.py to bind-mount any .py files
#      under patches/tt_dit/ over the corresponding paths inside the container.
#
# Usage:
#   ./apply_patches.sh                        # uses ~/code/tt-inference-server
#   ./apply_patches.sh /path/to/tt-inference-server
#   ./apply_patches.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PATCHES_SRC="$REPO_ROOT/patches"

# ── Args ─────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,12p' "$0" | sed 's/^# \?//'
    exit 0
fi

# Default: prefer vendor/ inside the repo (portable), fall back to dev checkout.
_DEFAULT_INFER="$REPO_ROOT/vendor/tt-inference-server"
[[ -d "$_DEFAULT_INFER" ]] || _DEFAULT_INFER="$HOME/code/tt-inference-server"
TT_INFER="${1:-$_DEFAULT_INFER}"

if [[ ! -d "$TT_INFER" ]]; then
    echo "ERROR: tt-inference-server not found at $TT_INFER"
    echo "Usage: $0 [/path/to/tt-inference-server]"
    exit 1
fi

RDS="$TT_INFER/workflows/run_docker_server.py"
if [[ ! -f "$RDS" ]]; then
    echo "ERROR: $RDS not found — is $TT_INFER a valid tt-inference-server checkout?"
    exit 1
fi

echo "Applying patches to: $TT_INFER"
echo ""

# ── Step 1: Copy patches/tt_dit/ ─────────────────────────────────────────────

TT_DIT_DST="$TT_INFER/patches/tt_dit"
TT_DIT_SRC="$PATCHES_SRC/tt_dit"

echo "1. Copying $TT_DIT_SRC → $TT_DIT_DST"

# Walk each file so we can back up existing ones individually.
find "$TT_DIT_SRC" -name "*.py" | while read -r src_file; do
    rel="${src_file#$TT_DIT_SRC/}"
    dst_file="$TT_DIT_DST/$rel"
    dst_dir="$(dirname "$dst_file")"
    mkdir -p "$dst_dir"

    if [[ -f "$dst_file" ]]; then
        if diff -q "$src_file" "$dst_file" > /dev/null 2>&1; then
            echo "   unchanged: patches/tt_dit/$rel"
        else
            backup="${dst_file}.bak"
            cp "$dst_file" "$backup"
            echo "   updated:   patches/tt_dit/$rel  (backup: ${backup#$TT_INFER/})"
            cp "$src_file" "$dst_file"
        fi
    else
        echo "   created:   patches/tt_dit/$rel"
        cp "$src_file" "$dst_file"
    fi
done

echo ""

# ── Step 2: Patch run_docker_server.py ───────────────────────────────────────

echo "2. Patching $RDS"

# The block we need to insert (must match exactly what run_docker_server.py expects).
# Insertion point: immediately before "    for key, value in docker_env_vars.items():"
TT_DIT_BLOCK='    # Apply media-server tt_dit hotpatches: files under patches/tt_dit/ are
    # bind-mounted at their relative paths inside ~/tt-metal/models/tt_dit/.
    # Used to patch DiT pipeline code (e.g. mesh-shape assertions in pipeline_mochi.py)
    # for hardware topologies not yet in the released image.  Only active in dev_mode.
    if runtime_config.dev_mode:
        tt_dit_patches_dir = Path(repo_root_path) / "patches" / "tt_dit"
        if tt_dit_patches_dir.is_dir():
            for patch_file in sorted(tt_dit_patches_dir.rglob("*.py")):
                rel = patch_file.relative_to(tt_dit_patches_dir)
                dst = f"{user_home_path}/tt-metal/models/tt_dit/{rel}"
                docker_command += [
                    "--mount", f"type=bind,src={patch_file},dst={dst},readonly",
                ]
                logger.info(f"Hotpatch (tt_dit): {rel} -> {dst}")'

python3 - "$RDS" "$TT_DIT_BLOCK" <<'PYEOF'
import sys, shutil, pathlib, textwrap

rds_path = pathlib.Path(sys.argv[1])
block = sys.argv[2]

text = rds_path.read_text()

# Idempotency check — skip if the block is already present.
if "tt_dit_patches_dir" in text:
    print("   already patched — nothing to do")
    sys.exit(0)

# Anchor: the line that immediately follows where the block should live.
ANCHOR = "    for key, value in docker_env_vars.items():"

if ANCHOR not in text:
    print(f"ERROR: could not find insertion anchor in {rds_path}")
    print(f"  Expected to find: {ANCHOR!r}")
    print("  The file may have changed upstream.  Apply the block manually.")
    sys.exit(1)

# Back up before modifying.
backup = rds_path.with_suffix(".py.bak")
shutil.copy2(rds_path, backup)
print(f"   backup: {backup.name}")

# Insert the block (plus a trailing blank line) before the anchor.
new_text = text.replace(ANCHOR, block + "\n\n" + ANCHOR, 1)
rds_path.write_text(new_text)
print("   inserted tt_dit hotpatch block ✓")
PYEOF

echo ""

# ── Step 3: Copy patches/media_server_config/ ────────────────────────────────

MSC_SRC="$PATCHES_SRC/media_server_config"
MSC_DST="$TT_INFER/patches/media_server_config"

echo "3. Copying $MSC_SRC → $MSC_DST"

find "$MSC_SRC" -name "*.py" | while read -r src_file; do
    rel="${src_file#$MSC_SRC/}"
    dst_file="$MSC_DST/$rel"
    dst_dir="$(dirname "$dst_file")"
    mkdir -p "$dst_dir"

    if [[ -f "$dst_file" ]]; then
        if diff -q "$src_file" "$dst_file" > /dev/null 2>&1; then
            echo "   unchanged: patches/media_server_config/$rel"
        else
            backup="${dst_file}.bak"
            cp "$dst_file" "$backup"
            echo "   updated:   patches/media_server_config/$rel  (backup: ${backup#$TT_INFER/})"
            cp "$src_file" "$dst_file"
        fi
    else
        echo "   created:   patches/media_server_config/$rel"
        cp "$src_file" "$dst_file"
    fi
done

echo ""

# ── Step 4: Insert media_server_config bind-mount block ───────────────────────

echo "4. Patching $RDS (media_server_config)"

# Unconditional (no dev_mode guard): these config overrides must work with the
# production image startup used by start_wan.sh.  Files under
# patches/media_server_config/ mirror the container's ~/tt-metal/server/ tree
# and are bind-mounted over the corresponding paths at container start.
MSC_BLOCK='    # Apply media-server config patches: .py files under patches/media_server_config/
    # mirror ~/tt-metal/server/ inside the container and are bind-mounted at startup.
    # Unlike dev_mode hotpatches this block is unconditional — it works with the
    # production image (no --dev-mode flag required).  Use this for config overrides
    # such as per-device timeouts that are missing from the upstream image.
    _media_config_patches_dir = Path(repo_root_path) / "patches" / "media_server_config"
    if _media_config_patches_dir.is_dir():
        for _patch_file in sorted(_media_config_patches_dir.rglob("*.py")):
            _rel = _patch_file.relative_to(_media_config_patches_dir)
            _dst = f"{user_home_path}/tt-metal/server/{_rel}"
            docker_command += [
                "--mount", f"type=bind,src={_patch_file},dst={_dst},readonly",
            ]
            logger.info(f"Config patch (media_server_config): {_rel} -> {_dst}")'

python3 - "$RDS" "$MSC_BLOCK" <<'PYEOF'
import sys, shutil, pathlib

rds_path = pathlib.Path(sys.argv[1])
block = sys.argv[2]

text = rds_path.read_text()

if "_media_config_patches_dir" in text:
    print("   already patched — nothing to do")
    sys.exit(0)

ANCHOR = "    for key, value in docker_env_vars.items():"

if ANCHOR not in text:
    print(f"ERROR: could not find insertion anchor in {rds_path}")
    sys.exit(1)

backup = rds_path.with_suffix(".py.bak")
shutil.copy2(rds_path, backup)
print(f"   backup: {backup.name}")

new_text = text.replace(ANCHOR, block + "\n\n" + ANCHOR, 1)
rds_path.write_text(new_text)
print("   inserted media_server_config bind-mount block ✓")
PYEOF

echo ""
# ── Step 5: Insert HF_HOME bind-mount block ───────────────────────────────────

echo "5. Patching $RDS (HF_HOME mount)"

# When the model loading code calls from_pretrained("Wan-AI/Wan2.2-...") with the
# HF repo ID (not a local path), the HF library resolves it via HF_HOME.  Without
# setting HF_HOME inside the container, the library defaults to the container's own
# empty ~/.cache/huggingface, causing a download attempt or offline-mode failure.
# This block mounts the full host HF cache directory and sets HF_HOME so that the
# cached model (118 GB) is found by repo ID without any network access.
HF_HOME_BLOCK='    # Mount the full host HF cache as HF_HOME inside the container.
    # Model loading code calls from_pretrained("Wan-AI/Wan2.2-T2V-A14B-Diffusers")
    # with the HF repo ID; the HF library resolves this via HF_HOME.  Without this,
    # HF defaults to the empty container cache and tries to download, or fails offline.
    if setup_config and getattr(setup_config, "host_hf_cache", None):
        _hf_home_dst = f"{user_home_path}/hf_home_cache"
        docker_command += [
            "--mount", f"type=bind,src={setup_config.host_hf_cache},dst={_hf_home_dst},readonly",
        ]
        docker_env_vars["HF_HOME"] = _hf_home_dst
        logger.info(f"HF_HOME mount: {setup_config.host_hf_cache} -> {_hf_home_dst}")'

python3 - "$RDS" "$HF_HOME_BLOCK" <<'PYEOF'
import sys, shutil, pathlib

rds_path = pathlib.Path(sys.argv[1])
block = sys.argv[2]

text = rds_path.read_text()

if "hf_home_cache" in text:
    print("   already patched — nothing to do")
    sys.exit(0)

ANCHOR = "    for key, value in docker_env_vars.items():"

if ANCHOR not in text:
    print(f"ERROR: could not find insertion anchor in {rds_path}")
    sys.exit(1)

backup = rds_path.with_suffix(".py.bak")
shutil.copy2(rds_path, backup)
print(f"   backup: {backup.name}")

new_text = text.replace(ANCHOR, block + "\n\n" + ANCHOR, 1)
rds_path.write_text(new_text)
print("   inserted HF_HOME bind-mount block ✓")
PYEOF

echo ""

# ── Step 6: Inject SkyReels into model_spec.py ───────────────────────────────

MODEL_SPEC="$TT_INFER/workflows/model_spec.py"
echo "6. Patching $MODEL_SPEC (SkyReels ModelSpecTemplate)"

python3 - "$MODEL_SPEC" <<'PYEOF'
import sys, shutil, pathlib

p = pathlib.Path(sys.argv[1])
text = p.read_text()

MARKER = "Skywork/SkyReels-V2-DF-1.3B-540P-Diffusers"
if MARKER in text:
    print("   already patched — nothing to do")
    sys.exit(0)

# Insertion anchor: last entry before image_templates comment.
ANCHOR = "]\n\n# =============================================================================\n# image_templates"
if ANCHOR not in text:
    print(f"ERROR: could not find insertion anchor in {p}")
    sys.exit(1)

SKYREELS_ENTRY = """\
    # SkyReels-V2-DF-1.3B-540P — Blackhole (P150X4) only.
    # Weights: ~12GB.  540P = 480x272 native res.
    ModelSpecTemplate(
        weights=["Skywork/SkyReels-V2-DF-1.3B-540P-Diffusers"],
        tt_metal_commit="555f240",
        impl=tt_transformers_impl,
        min_disk_gb=20,
        min_ram_gb=16,
        model_type=ModelType.VIDEO,
        inference_engine=InferenceEngine.MEDIA.value,
        device_model_specs=[
            DeviceModelSpec(
                device=DeviceTypes.P150X4,
                max_concurrency=1,
                max_context=64 * 1024,
                default_impl=True,
            ),
            DeviceModelSpec(
                device=DeviceTypes.P300X2,
                max_concurrency=1,
                max_context=64 * 1024,
                default_impl=True,
            ),
        ],
        status=ModelStatusTypes.COMPLETE,
    ),
"""

backup = p.with_suffix(".py.bak")
shutil.copy2(p, backup)
new_text = text.replace(ANCHOR, SKYREELS_ENTRY + ANCHOR, 1)
p.write_text(new_text)
print(f"   inserted SkyReels ModelSpecTemplate ✓  (backup: {backup.name})")
PYEOF

echo ""
echo "Done. You can now run start_mochi.sh (or any media-server model with --dev-mode)"
echo "and the patches/tt_dit/ files will be bind-mounted automatically."
echo ""
echo "patches/media_server_config/ overrides are applied on every start_wan.sh launch"
echo "(no --dev-mode required)."
