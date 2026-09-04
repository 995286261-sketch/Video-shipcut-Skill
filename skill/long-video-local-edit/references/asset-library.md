# Asset Library

Use the bundled library only for reusable assets with a known license. Keep project-specific customer assets under that project's `外部资料/原始文件/<projectId>/brand/`; do not add them to this shared library.

## Layout

- `assets/asset-library/manifest.json`: inventory and global policy.
- `assets/asset-library/presets/`: production policies, not media files.
- `assets/asset-library/media/`: create only when registering a verified distributable asset.

## Register an Asset

Place the file below `media/`, then add an entry to `manifest.json`:

```json
{
  "assetId": "sfx-section-emphasis-001",
  "type": "sound-effect",
  "relativePath": "audio/sfx-section-emphasis-001.wav",
  "sha256": "UPPERCASE_SHA256",
  "license": "company-owned",
  "allowedUse": ["chapter-emphasis"],
  "tags": ["restrained", "editorial"],
  "durationMs": 320,
  "mix": {"targetGainDb": -18}
}
```

Use only `company-owned`, `user-authorized`, or `redistributable` for `license`. Record no item with an unknown license, a source/reference-video path, or an absolute path. Run `python scripts/validate_asset_library.py --manifest assets/asset-library/manifest.json` before adding a registered item to a render plan.

## Selection

Choose assets only from the active preset's allowlisted policy. Optional assets default to off. If no eligible asset exists, render without it and emit a warning; never substitute an arbitrary local file.
