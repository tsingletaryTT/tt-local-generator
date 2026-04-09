# /etc/profile.d/tt-local-generator.sh
# Installed by the tt-local-generator package.
#
# Redirects the HuggingFace model cache to the shared system-wide location
# so that all users on the machine share a single copy of downloaded weights,
# and so that postinst scripts can populate the cache as root without needing
# to know which user's home directory to write into.
#
# /opt/tenstorrent/models/
#   hub/        ← HF model blobs (HF_HUB_CACHE)
#   tt-weights/ ← compiled TT tensor cache (TT_DIT_CACHE_DIR, Docker volume)
#   token       ← optional shared HF token (readable by docker group)
#
# To override for a specific session:
#   export HF_HOME=~/.cache/huggingface
#   unset HF_HUB_CACHE

export HF_HOME=/opt/tenstorrent/models
export HF_HUB_CACHE=/opt/tenstorrent/models/hub
