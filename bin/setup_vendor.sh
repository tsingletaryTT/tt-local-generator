#!/usr/bin/env bash
# setup_vendor.sh — Clone or verify vendor/tt-inference-server at the pinned SHA.
#
# Manages the vendored shallow clone of tt-inference-server so that all scripts
# in tt-local-generator use a known-good, patched copy of the server tree instead
# of whatever happens to be on the PATH or in ~/code.
#
# This script NEVER touches ~/code/tt-inference-server.
#
# Usage:
#   ./setup_vendor.sh                    # clone or verify; no-op if already correct
#   ./setup_vendor.sh --check            # exit 0 if vendor/ is at pinned SHA, else 1
#   ./setup_vendor.sh --update <sha>     # write new SHA to VENDOR_SHA and re-clone
#   ./setup_vendor.sh --force            # re-clone even if already at correct SHA
#   ./setup_vendor.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VENDOR_DIR="$REPO_ROOT/vendor"
VENDOR_SHA_FILE="$VENDOR_DIR/VENDOR_SHA"
CLONE_DST="$VENDOR_DIR/tt-inference-server"
UPSTREAM="https://github.com/tenstorrent/tt-inference-server.git"

# ── Helpers ───────────────────────────────────────────────────────────────────

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "  $*"; }
ok()   { echo "  ✓ $*"; }

# ── Args ─────────────────────────────────────────────────────────────────────

CHECK_ONLY=0
FORCE=0
UPDATE_SHA=""

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            sed -n '2,11p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        --check)
            CHECK_ONLY=1 ;;
        --force)
            FORCE=1 ;;
        --update)
            # next arg is the new SHA — handled below
            ;;
        *)
            # If previous arg was --update this is the SHA value
            if [[ "${PREV_ARG:-}" == "--update" ]]; then
                UPDATE_SHA="$arg"
            fi ;;
    esac
    PREV_ARG="$arg"
done

# Handle --update <sha>
if [[ " $* " == *" --update "* && -z "$UPDATE_SHA" ]]; then
    die "--update requires a SHA argument, e.g.: --update abc1234"
fi

# ── Read / update VENDOR_SHA ──────────────────────────────────────────────────

mkdir -p "$VENDOR_DIR"

if [[ -n "$UPDATE_SHA" ]]; then
    echo "$UPDATE_SHA" > "$VENDOR_SHA_FILE"
    echo "Updated VENDOR_SHA → $UPDATE_SHA"
    FORCE=1
fi

if [[ ! -f "$VENDOR_SHA_FILE" ]]; then
    die "VENDOR_SHA file not found at $VENDOR_SHA_FILE — cannot determine which commit to pin."
fi

WANT_SHA=$(cat "$VENDOR_SHA_FILE" | tr -d '[:space:]')
[[ -z "$WANT_SHA" ]] && die "VENDOR_SHA is empty."

# ── Check current state ───────────────────────────────────────────────────────

current_sha() {
    git -C "$CLONE_DST" rev-parse HEAD 2>/dev/null || echo ""
}

if [[ -d "$CLONE_DST/.git" ]]; then
    HAVE_SHA=$(current_sha)
    SHORT_HAVE="${HAVE_SHA:0:7}"
    SHORT_WANT="${WANT_SHA:0:7}"

    if [[ "$HAVE_SHA" == "$WANT_SHA"* || "$WANT_SHA" == "$HAVE_SHA"* ]]; then
        if [[ $FORCE -eq 0 ]]; then
            ok "vendor/tt-inference-server already at $SHORT_WANT — nothing to do."
            exit 0
        else
            info "Forcing re-clone (--force)."
        fi
    else
        if [[ $CHECK_ONLY -eq 1 ]]; then
            echo "MISMATCH: vendor/tt-inference-server is at $SHORT_HAVE, want $SHORT_WANT"
            exit 1
        fi
        echo "vendor/tt-inference-server is at $SHORT_HAVE, need $SHORT_WANT — updating."
    fi
elif [[ -d "$CLONE_DST" && ! -d "$CLONE_DST/.git" ]]; then
    die "$CLONE_DST exists but is not a git repo. Remove it and re-run."
else
    if [[ $CHECK_ONLY -eq 1 ]]; then
        echo "MISSING: vendor/tt-inference-server not found (want $SHORT_WANT)"
        exit 1
    fi
    echo "vendor/tt-inference-server not found — cloning at $SHORT_WANT."
fi

# ── Clone (or re-clone) at the exact pinned SHA ───────────────────────────────
#
# Strategy: init an empty repo, add the remote, fetch only the one object we
# want (--depth 1 on a specific SHA), then checkout.  This avoids downloading
# the default branch HEAD when it differs from our pinned SHA.

if [[ -d "$CLONE_DST" ]]; then
    info "Removing existing $CLONE_DST …"
    rm -rf "$CLONE_DST"
fi

echo ""
echo "Fetching $UPSTREAM"
echo "at commit $WANT_SHA …"
echo "(this is a shallow clone — only the pinned commit, no history)"
echo ""

mkdir -p "$CLONE_DST"
git -C "$CLONE_DST" init -q
git -C "$CLONE_DST" remote add origin "$UPSTREAM"

# GitHub allows fetching a specific SHA from a public repo.
# --depth 1 keeps it to the single commit tree (no ancestry).
git -C "$CLONE_DST" fetch --depth 1 origin "$WANT_SHA"
git -C "$CLONE_DST" checkout FETCH_HEAD
git -C "$CLONE_DST" config advice.detachedHead false

ACTUAL_SHA=$(current_sha)
if [[ "$ACTUAL_SHA" != "$WANT_SHA"* && "$WANT_SHA" != "$ACTUAL_SHA"* ]]; then
    die "SHA mismatch after clone: got $ACTUAL_SHA, expected $WANT_SHA"
fi

echo ""
ok "vendor/tt-inference-server @ ${WANT_SHA:0:7} is ready."
echo ""
echo "Next: run ./bin/apply_patches.sh to apply QB2 hotpatches."
