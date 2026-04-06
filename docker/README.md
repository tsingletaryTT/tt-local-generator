# Bundled Docker Images

This directory contains Docker images tracked via Git LFS.  Each `.tar.gz`
is the output of `docker save <image> | gzip -1 > <file>`.

## tt-media-inference-server-0.11.1-bac8b34.tar.gz

| Field   | Value |
|---------|-------|
| Image   | `ghcr.io/tenstorrent/tt-media-inference-server:0.11.1-bac8b34` |
| Digest  | `sha256:3fd30fdb904449d319adc4e2f426e1bcb785597fa2304cc834f1d745656679a8` |
| Built   | 2026-03-24 |
| Size    | ~29.7 GB uncompressed |
| Models  | Wan2.2-T2V-A14B-Diffusers (P150X4, P300X2), SDXL, Whisper |
| Status  | Validated on P300X2 (QB2) 2026-04-06 |

### Loading

```bash
docker load -i docker/tt-media-inference-server-0.11.1-bac8b34.tar.gz
```

### Bundling a new image

```bash
docker save ghcr.io/tenstorrent/tt-media-inference-server:<tag> \
  | gzip -1 > docker/tt-media-inference-server-<tag>.tar.gz
# Update .gitattributes if adding a different extension.
# Update vendor/VENDOR_SHA and re-run apply_patches.sh if upgrading.
```
