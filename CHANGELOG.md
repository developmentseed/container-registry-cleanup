# Changelog

## [0.2.3](https://github.com/developmentseed/container-registry-cleanup/compare/v0.2.2...v0.2.3) (2026-08-27)


### CI/CD

* bump actions/checkout from 7.0.0 to 7.0.1 ([#42](https://github.com/developmentseed/container-registry-cleanup/issues/42)) ([811207d](https://github.com/developmentseed/container-registry-cleanup/commit/811207dd8b6e3d517c5ad89523a8deb2121dc91f))
* bump actions/setup-python from 6.3.0 to 7.0.0 ([#43](https://github.com/developmentseed/container-registry-cleanup/issues/43)) ([096aed0](https://github.com/developmentseed/container-registry-cleanup/commit/096aed053d3e7766d1c5799e8d5ed87c584b20c1))
* bump astral-sh/setup-uv from 8.2.0 to 10.0.1 ([#44](https://github.com/developmentseed/container-registry-cleanup/issues/44)) ([addb420](https://github.com/developmentseed/container-registry-cleanup/commit/addb420e6f6254bc1604529bf69dad828c2234fa))
* bump zizmorcore/zizmor-action from 0.5.7 to 0.6.2 ([#45](https://github.com/developmentseed/container-registry-cleanup/issues/45)) ([463be19](https://github.com/developmentseed/container-registry-cleanup/commit/463be193c3c374b028346e246a864e2879faa9f5))

## [0.2.2](https://github.com/developmentseed/container-registry-cleanup/compare/v0.2.1...v0.2.2) (2026-08-25)


### Bug Fixes

* authenticate GHCR manifest fetches with an exchanged registry token ([#40](https://github.com/developmentseed/container-registry-cleanup/issues/40)) ([30d2004](https://github.com/developmentseed/container-registry-cleanup/commit/30d200439e3b47e8e79c7d7e68439e78369e4834))
* claude-pr-review.yml formatting. ([#41](https://github.com/developmentseed/container-registry-cleanup/issues/41)) ([39428a8](https://github.com/developmentseed/container-registry-cleanup/commit/39428a874e67eae75c10dd69bf9921170f3d84fd))


### CI/CD

* bump actions/checkout from 6.0.2 to 7.0.0 ([#37](https://github.com/developmentseed/container-registry-cleanup/issues/37)) ([81c419f](https://github.com/developmentseed/container-registry-cleanup/commit/81c419f60b483ec4a5bd44b6bf773a24d57d84d7))
* bump actions/setup-python from 6.2.0 to 6.3.0 ([#38](https://github.com/developmentseed/container-registry-cleanup/issues/38)) ([dddd915](https://github.com/developmentseed/container-registry-cleanup/commit/dddd915f8e4f680999f29b5edbc35f79744a42bf))
* bump astral-sh/setup-uv from 7.6.0 to 8.0.0 ([#21](https://github.com/developmentseed/container-registry-cleanup/issues/21)) ([4290c90](https://github.com/developmentseed/container-registry-cleanup/commit/4290c90a87cbfc5429ec328bb20168e46f2b4ac1))
* bump astral-sh/setup-uv from 8.0.0 to 8.2.0 ([#34](https://github.com/developmentseed/container-registry-cleanup/issues/34)) ([38dd4bc](https://github.com/developmentseed/container-registry-cleanup/commit/38dd4bc35e4fc71846a180071a01b6d3cfb448df))
* bump googleapis/release-please-action from 4.4.0 to 5.0.0 ([#26](https://github.com/developmentseed/container-registry-cleanup/issues/26)) ([878c65b](https://github.com/developmentseed/container-registry-cleanup/commit/878c65ba01b64ecfb5a4f0f7adceb5cbaf650eaa))
* bump zizmorcore/zizmor-action from 0.5.2 to 0.5.7 ([#39](https://github.com/developmentseed/container-registry-cleanup/issues/39)) ([09f6e07](https://github.com/developmentseed/container-registry-cleanup/commit/09f6e07f7f25eb8ceb2281d384918942e71f522b))
* enable zizmor, ruff and fix gha issues ([#19](https://github.com/developmentseed/container-registry-cleanup/issues/19)) ([1e15cc6](https://github.com/developmentseed/container-registry-cleanup/commit/1e15cc68e207e2f25a626532e8f5f3dc22eb6008))

## [0.2.1](https://github.com/developmentseed/container-registry-cleanup/compare/v0.2.0...v0.2.1) (2026-03-03)


### Bug Fixes

* OCI index-safe GHCR cleanup to prevent deleting manifests still reachable from tagged indexes. ([#17](https://github.com/developmentseed/container-registry-cleanup/issues/17)) ([fe699a4](https://github.com/developmentseed/container-registry-cleanup/commit/fe699a4daf4de04bb614b167d9b7495bf87d8917))

## [0.2.0](https://github.com/developmentseed/container-registry-cleanup/compare/v0.1.2...v0.2.0) (2026-01-30)


### Features

* added debug mode. ([#16](https://github.com/developmentseed/container-registry-cleanup/issues/16)) ([e9b0ffd](https://github.com/developmentseed/container-registry-cleanup/commit/e9b0ffd37d4d1a3abfb3893737a1ce5c477a5274))


### Bug Fixes

* dry-run summary for harbor. ([#13](https://github.com/developmentseed/container-registry-cleanup/issues/13)) ([9f200ad](https://github.com/developmentseed/container-registry-cleanup/commit/9f200addd344877b12206d6d3b008642ad0aa3c1))

## [0.1.2](https://github.com/developmentseed/container-registry-cleanup/compare/v0.1.1...v0.1.2) (2026-01-29)


### Bug Fixes

* dry-run summary. ([#11](https://github.com/developmentseed/container-registry-cleanup/issues/11)) ([06329fe](https://github.com/developmentseed/container-registry-cleanup/commit/06329fe583f75162718c84853fbe6ef112b8318a))

## [0.1.1](https://github.com/developmentseed/container-registry-cleanup/compare/v0.1.0...v0.1.1) (2026-01-29)


### Bug Fixes

* allowed python to find subpackages. ([#10](https://github.com/developmentseed/container-registry-cleanup/issues/10)) ([ca9b6a0](https://github.com/developmentseed/container-registry-cleanup/commit/ca9b6a083ba60e2ff480e536f5ea3c56ed178689))
* relied on github.action_path. ([#8](https://github.com/developmentseed/container-registry-cleanup/issues/8)) ([e2c683b](https://github.com/developmentseed/container-registry-cleanup/commit/e2c683b87c8a623099183e4e995896c7d0414ba9))

## [0.1.0](https://github.com/developmentseed/container-registry-cleanup/compare/v0.0.1...v0.1.0) (2026-01-29)


### Features

* added basic github action with ghcr registry. ([#2](https://github.com/developmentseed/container-registry-cleanup/issues/2)) ([a8994ba](https://github.com/developmentseed/container-registry-cleanup/commit/a8994bac114cbc896bded5076230a6b01dff34c9))
* added harbor registry client. ([#4](https://github.com/developmentseed/container-registry-cleanup/issues/4)) ([b327ea2](https://github.com/developmentseed/container-registry-cleanup/commit/b327ea29a92d7a0628f571e49cfeba79ea56b337))


### Bug Fixes

* GITHUB_STEP_SUMMARY as upper-case env var. ([#5](https://github.com/developmentseed/container-registry-cleanup/issues/5)) ([1555fd8](https://github.com/developmentseed/container-registry-cleanup/commit/1555fd8e67e3c9e6d69a59e6572383d636cc8f25))


### Chores

* added .gitgignore. ([e5480f7](https://github.com/developmentseed/container-registry-cleanup/commit/e5480f73b62a8bd49e86e11fa0eef18ad39de58a))
* added MIT license. ([a496a5a](https://github.com/developmentseed/container-registry-cleanup/commit/a496a5a80656d070db961cdf05e1db825ed0f4df))
* added python project structure. ([74b8403](https://github.com/developmentseed/container-registry-cleanup/commit/74b8403d6567319de265809cfb30abee85abd125))
* added python test structure. ([2889faa](https://github.com/developmentseed/container-registry-cleanup/commit/2889faa2df5bf007f7a2b144d556817c6d1220d4))
* added README.md ot release-please versioning. ([#7](https://github.com/developmentseed/container-registry-cleanup/issues/7)) ([f868915](https://github.com/developmentseed/container-registry-cleanup/commit/f8689151d6106c47fe1f95ade36d28ed929097ec))
* added release-please. ([f39b9cb](https://github.com/developmentseed/container-registry-cleanup/commit/f39b9cbec68fe3f88b58d8d1de95105a5ea75e9f))


### CI/CD

* added pytest and mypy. ([#3](https://github.com/developmentseed/container-registry-cleanup/issues/3)) ([d5a2aa6](https://github.com/developmentseed/container-registry-cleanup/commit/d5a2aa69d49e79c4657e0c788769f8c5d893b4bd))
* added workflow to run pre-commit. ([758bf86](https://github.com/developmentseed/container-registry-cleanup/commit/758bf86b342aab1794d11de1c87e56e6f0a99811))


### Tests

* added liniting and formatting checks with pre-commit. ([240cd74](https://github.com/developmentseed/container-registry-cleanup/commit/240cd741b6bcec400b86ac55b88e9c14c52b21fb))
