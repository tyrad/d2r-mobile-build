# Native macOS build

Open **Actions → Build macOS → Run workflow**. The workflow uses the maintained upstream build logic and defaults to source release `v1.0.16`. Set `source_ref` to a different upstream release when updating. The prepared input URL and checksum manifest default to the configuration published by `jiayx/d2r-mobile-build`.

Successful builds publish both Apple silicon variants to this repository's Releases:

- `*-macos26.zip`: macOS 26 and newer.
- `*-macos15.zip`: macOS 15–25.

Extract the ZIP. Copy the two files in `Mac Resource Metadata/data` (`build_manifest.psv` and the hidden `.build.config`) into the existing `D2R Mobile Resources/data` directory. On first launch, select the whole `D2R Mobile Resources` folder.

These standard packages use ad hoc signing and do **not** enable iCloud save synchronization. A paid developer account alone does not enable synchronization: both apps must contain the sync implementation and use valid iCloud entitlements and provisioning for the same accessible container. Existing unsigned or ad hoc packages do not gain that capability merely by installing a newer standard build.

Upstream instructions: https://github.com/jiayx/d2r-mobile-build/blob/main/README.zh-CN.md
