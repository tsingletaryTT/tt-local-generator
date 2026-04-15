#!/usr/bin/env bash
# bin/test_macos.sh — GStreamer + GTK4 video-playback diagnostic for macOS
#
# Run from the repo root:
#   ./bin/test_macos.sh
#
# What it checks:
#   1. Python + GObject introspection (gi) availability
#   2. GTK4 version
#   3. GStreamer elements required for MP4 / H.264 playback
#   4. GTK4 media backend (libmedia-gstreamer) — the bridge between Gtk.Video and GStreamer
#   5. GST_PLUGIN_PATH / GIO_MODULE_DIR environment variables
#   6. Homebrew prefix detection
#   7. Tries a minimal gst-launch-1.0 pipeline on a real video file (if available)
#
# Share the full output when reporting playback issues.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/test_macos.sh"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}OK${RESET}   $*"; }
warn() { echo -e "  ${YELLOW}WARN${RESET} $*"; }
fail() { echo -e "  ${RED}FAIL${RESET} $*"; }

echo "=== tt-local-generator macOS video diagnostic ==="
echo "Date: $(date)"
echo "OS:   $(sw_vers -productName 2>/dev/null) $(sw_vers -productVersion 2>/dev/null)"
echo "Arch: $(uname -m)"
echo ""

# ── 1. Homebrew prefix ────────────────────────────────────────────────────────
echo "[ 1 ] Homebrew prefix"
BREW_PREFIX=$(brew --prefix 2>/dev/null || true)
if [[ -z "$BREW_PREFIX" ]]; then
    fail "brew not found — install Homebrew: https://brew.sh"
    BREW_PREFIX="/opt/homebrew"   # assume Apple Silicon default
else
    ok "brew prefix: $BREW_PREFIX"
fi
echo ""

# ── 2. Python + gi ───────────────────────────────────────────────────────────
echo "[ 2 ] Python interpreter"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python3"
if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
    ok "using venv: $PYTHON"
else
    PYTHON=$(command -v python3 2>/dev/null || echo "")
    if [[ -z "$PYTHON" ]]; then
        fail "python3 not found — run: brew install python@3.12"
        exit 1
    fi
    warn "no .venv — using PATH python3: $PYTHON (run ./bin/setup_macos.sh for full setup)"
fi
echo "      $($PYTHON --version 2>&1)"
echo ""

echo "[ 3 ] GObject introspection (gi)"
if ! "$PYTHON" -c "import gi" 2>/dev/null; then
    fail "import gi failed — run: brew install pygobject3"
else
    ok "gi importable"
fi
echo ""

# ── 3. GStreamer Python bindings ──────────────────────────────────────────────
echo "[ 4 ] GStreamer Python bindings"
GST_OK=0
if "$PYTHON" -c "import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst" 2>/dev/null; then
    ok "gi.repository.Gst available"
    GST_OK=1
else
    fail "Gst 1.0 typelib missing — run: brew install gstreamer"
fi
echo ""

# ── 4. Required GStreamer elements ────────────────────────────────────────────
echo "[ 5 ] GStreamer elements (need: qtdemux + avdec_h264 for MP4/H.264)"

# Set GST_PLUGIN_PATH the same way tt-gen does so the check matches runtime.
for _prefix in "$BREW_PREFIX" "/opt/homebrew" "/usr/local"; do
    _gst_dir="$_prefix/lib/gstreamer-1.0"
    if [[ -d "$_gst_dir" ]]; then
        export GST_PLUGIN_PATH="${_gst_dir}${GST_PLUGIN_PATH:+:$GST_PLUGIN_PATH}"
        break
    fi
done

if [[ "$GST_OK" -eq 1 ]]; then
    "$PYTHON" - <<'PYEOF'
import os, sys
sys.path.insert(0, "app")
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

RED   = '\033[0;31m'; GREEN = '\033[0;32m'; RESET = '\033[0m'
YELLOW = '\033[1;33m'

elements = {
    'qtdemux':    'MP4 container demuxer (gst-plugins-good)',
    'avdec_h264': 'H.264 software decoder (gst-libav)',
    'playbin':    'High-level playback pipeline (gst-plugins-base)',
    'decodebin3': 'Auto-decoder (gst-plugins-base)',
    'fakesink':   'Null sink for testing (gst-plugins-base)',
}
all_ok = True
for elem, desc in elements.items():
    factory = Gst.ElementFactory.find(elem)
    if factory:
        print(f"  \033[0;32mOK\033[0m   {elem:18s}  {desc}")
    else:
        print(f"  \033[0;31mFAIL\033[0m {elem:18s}  {desc}")
        all_ok = False

if not all_ok:
    print()
    print("  Missing elements — run:")
    print("    brew install gst-plugins-base gst-plugins-good gst-libav")
else:
    print()
    print(f"  GST_PLUGIN_PATH: {os.environ.get('GST_PLUGIN_PATH','(not set)')}")
PYEOF
else
    warn "skipped (Gst not importable)"
fi
echo ""

# ── 5. GTK4 GStreamer media backend ───────────────────────────────────────────
echo "[ 6 ] GTK4 GStreamer media backend (libmedia-gstreamer)"
echo "      This is the bridge that lets Gtk.Video use GStreamer."
echo "      Without it, get_media_stream() always returns None."
echo ""

# Search common install locations.
MEDIA_BACKEND=$(find \
    "$BREW_PREFIX/lib/gtk-4.0" \
    "/opt/homebrew/lib/gtk-4.0" \
    "/usr/local/lib/gtk-4.0" \
    2>/dev/null \
    -name "libmedia-gstreamer*" 2>/dev/null | head -1 || true)

if [[ -n "$MEDIA_BACKEND" ]]; then
    ok "found: $MEDIA_BACKEND"
else
    fail "libmedia-gstreamer not found under $BREW_PREFIX/lib/gtk-4.0"
    echo ""
    echo "      This is the most common cause of inline video not working on macOS."
    echo "      The GTK4 Homebrew bottle may not include the GStreamer media backend."
    echo ""
    echo "      Fix options:"
    echo "        A) Install gtk4 from source with GStreamer support:"
    echo "           brew install gtk4 --with-gstreamer    (if the option exists)"
    echo ""
    echo "        B) Build gtk4 from source:"
    echo "           brew install --build-from-source gtk4"
    echo ""
    echo "        C) Check for the backend under a different path:"
    find / -name "libmedia-gstreamer*" 2>/dev/null | head -10 || true
fi
echo ""

# ── 6. GIO modules ───────────────────────────────────────────────────────────
echo "[ 7 ] GIO modules (GIO_MODULE_DIR)"
GIO_DIR=$(find "$BREW_PREFIX/lib/gio" "/opt/homebrew/lib/gio" "/usr/local/lib/gio" \
          2>/dev/null -maxdepth 2 -name "modules" -type d 2>/dev/null | head -1 || true)
if [[ -n "$GIO_DIR" ]]; then
    ok "GIO modules dir: $GIO_DIR"
    ls "$GIO_DIR"/*.dylib 2>/dev/null | while read f; do echo "      $(basename "$f")"; done
else
    warn "GIO modules dir not found (usually non-fatal)"
fi
echo ""

# ── 7. Environment variables ──────────────────────────────────────────────────
echo "[ 8 ] Runtime environment variables"
for k in GST_PLUGIN_PATH GST_PLUGIN_SCANNER GIO_MODULE_DIR GTK_PATH GTK_MODULES; do
    val="${!k:-}"
    if [[ -n "$val" ]]; then
        ok "$k=$val"
    else
        echo "      $k=(not set)"
    fi
done
echo ""

# ── 8. GTK4 version ──────────────────────────────────────────────────────────
echo "[ 9 ] GTK4 version"
if "$PYTHON" -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('     ', Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())" 2>/dev/null; then
    ok "(above)"
else
    fail "GTK4 not importable"
fi
echo ""

# ── 9. gst-launch smoke test ─────────────────────────────────────────────────
echo "[ 10 ] gst-launch-1.0 smoke test"
GST_LAUNCH=$(command -v gst-launch-1.0 2>/dev/null || echo "")
if [[ -z "$GST_LAUNCH" ]]; then
    warn "gst-launch-1.0 not in PATH (usually at $BREW_PREFIX/bin/gst-launch-1.0)"
    GST_LAUNCH="$BREW_PREFIX/bin/gst-launch-1.0"
fi

# Find a real video to test with.
VIDEOS_DIR="$HOME/.local/share/tt-video-gen/videos"
TEST_VIDEO=$(find "$VIDEOS_DIR" -name "*.mp4" 2>/dev/null | head -1 || true)

if [[ -z "$TEST_VIDEO" ]]; then
    warn "no MP4 found in $VIDEOS_DIR — skipping pipeline test"
else
    ok "test file: $TEST_VIDEO"
    echo "      Running: gst-launch-1.0 filesrc location=... ! qtdemux ! avdec_h264 ! fakesink"
    if timeout 10 "$GST_LAUNCH" \
        filesrc location="$TEST_VIDEO" \
        '!' qtdemux \
        '!' avdec_h264 \
        '!' fakesink 2>&1 | tail -5; then
        ok "gst-launch pipeline succeeded — GStreamer CAN decode this file"
    else
        fail "gst-launch pipeline failed — see output above"
        echo "      This means GStreamer is installed but cannot decode the MP4."
        echo "      Install: brew install gst-libav"
    fi
fi
echo ""

echo "=== Diagnostic complete ==="
echo ""
echo "Share the full output of this script when reporting playback issues."
