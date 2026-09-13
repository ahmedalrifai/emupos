## ADDED Requirements

### Requirement: Semantic versioning

The emupos package SHALL be versioned `MAJOR.MINOR.PATCH` following Semantic Versioning. From `1.0.0` onward, breaking changes SHALL be released only in a new major version. Before `1.0.0`, a breaking change SHALL be released only in a new minor version, never in a patch release. Release versions SHALL be derived from merged pull request titles: a `fix` SHALL produce a patch release, a `feat` SHALL produce a minor release, and a breaking change (marked with `!` or a `BREAKING CHANGE` footer) SHALL produce a minor release before `1.0.0` and a major release from `1.0.0` onward.

#### Scenario: Fix only

- **GIVEN** the last release is `0.Y.Z` and only `fix:` pull requests were merged since
- **WHEN** the next release is prepared
- **THEN** its version is `0.Y.(Z+1)`

#### Scenario: Breaking change before 1.0

- **GIVEN** the last release is `0.Y.Z` and a pull request titled `feat(config)!: rename receipts_dir` was merged since
- **WHEN** the next release is prepared
- **THEN** its version is `0.(Y+1).0`

#### Scenario: Breaking change after 1.0

- **GIVEN** the last release is `X.Y.Z` with `X` at least 1, and a breaking pull request was merged since
- **WHEN** the next release is prepared
- **THEN** its version is `(X+1).0.0`

### Requirement: Changelog

The repository SHALL contain `CHANGELOG.md` with one section per released version, generated from merged pull request titles and grouped by change type. Every breaking change SHALL be listed under the `⚠ BREAKING CHANGES` heading in the section of the release that contains it. Dropping support for a Python version SHALL be listed as a breaking change.

#### Scenario: Breaking change is listed

- **GIVEN** a release contains the merged pull request `feat(config)!: rename receipts_dir`
- **WHEN** the release is published
- **THEN** that release's section of `CHANGELOG.md` lists the change under `⚠ BREAKING CHANGES`

#### Scenario: Python version dropped

- **GIVEN** a release stops supporting a Python version
- **WHEN** the release is published
- **THEN** its `CHANGELOG.md` section lists the dropped Python version under `⚠ BREAKING CHANGES`

### Requirement: Single source for the package version

The package version SHALL be defined in exactly one place, `pyproject.toml`. `emupos --version`, the `version` field of `GET /api/v1/health`, and the metadata of the published distributions SHALL all report that version.

#### Scenario: Versions agree

- **GIVEN** `pyproject.toml` declares version `X.Y.Z` and that build is installed
- **WHEN** the user runs `emupos --version` and requests `GET /api/v1/health` from a running simulator
- **THEN** the command prints `emupos X.Y.Z` and the health response has `"version": "X.Y.Z"`

### Requirement: Conventional Commits pull request titles

Every pull request title SHALL follow the Conventional Commits format, and a required status check SHALL fail for a pull request whose title does not. Pull requests SHALL be squash-merged so that each title becomes one commit on the main branch.

#### Scenario: Non-conforming title

- **WHEN** a pull request is opened with the title `Added tare support`
- **THEN** the title check fails and the pull request is not mergeable

#### Scenario: Conforming title

- **WHEN** a pull request is opened with the title `feat(scale): add tare support`
- **THEN** the title check passes

### Requirement: Release pull request

An automatically maintained release pull request SHALL stay open while unreleased changes exist on the main branch. It SHALL bump the version in `pyproject.toml` and add the next release's section to `CHANGELOG.md`. Merging it SHALL create the git tag `vX.Y.Z` matching the new version. No other action SHALL be needed to start a release.

#### Scenario: Release pull request follows merges

- **GIVEN** a `feat:` pull request was merged after the last release
- **WHEN** the release pull request is updated
- **THEN** it proposes the next version in `pyproject.toml` and a `CHANGELOG.md` section that lists the merged change

#### Scenario: Merging tags the release

- **WHEN** a maintainer merges the release pull request that sets version `X.Y.Z`
- **THEN** the tag `vX.Y.Z` is created on the merge commit

### Requirement: Tag-triggered build

Pushing a tag `vX.Y.Z` SHALL start the release workflow, which SHALL build one wheel and one source distribution from the tagged commit. The workflow SHALL fail before publishing anything when the tag's version differs from the version in `pyproject.toml`.

#### Scenario: Build from tag

- **WHEN** the tag `vX.Y.Z` is pushed
- **THEN** the release workflow produces `emupos-X.Y.Z-py3-none-any.whl` and `emupos-X.Y.Z.tar.gz`

#### Scenario: Tag and version disagree

- **GIVEN** `pyproject.toml` at the tagged commit declares a version other than `X.Y.Z`
- **WHEN** the tag `vX.Y.Z` is pushed
- **THEN** the release workflow fails and nothing is published

### Requirement: Cross-platform smoke test gates publishing

Before publishing, the release workflow SHALL install the built wheel, not the source tree, on Windows, macOS and Linux, and on each SHALL verify that `emupos --version` prints the tag's version, that `emupos doctor --json` outputs a valid JSON report, and that a fixture ESC/POS job sent to a simulated printer produces the expected receipt text. If any of these checks fails on any operating system, nothing SHALL be published to PyPI and no GitHub Release SHALL be created.

#### Scenario: All platforms pass

- **GIVEN** the built wheel passes every smoke check on Windows, macOS and Linux
- **WHEN** the smoke test jobs finish
- **THEN** the publish step runs

#### Scenario: One platform fails

- **GIVEN** the installed wheel fails to start on Windows
- **WHEN** the smoke test jobs finish
- **THEN** the release is not published to PyPI and no GitHub Release is created

### Requirement: Trusted publishing with attestations

The release workflow SHALL publish the wheel and source distribution to PyPI using PyPI Trusted Publishing, without any long-lived PyPI token stored in the repository or its secrets, and SHALL publish attestations for both files. A published version SHALL NOT be overwritten; a broken release SHALL be yanked on PyPI and superseded by a patch release.

#### Scenario: No stored token

- **WHEN** the repository's secrets and workflow files are inspected
- **THEN** they contain no PyPI API token

#### Scenario: Attestations published

- **WHEN** version `X.Y.Z` is published
- **THEN** PyPI shows an attestation for `emupos-X.Y.Z-py3-none-any.whl` and for `emupos-X.Y.Z.tar.gz` linked to the release workflow run

### Requirement: GitHub Release

After publishing to PyPI, the release workflow SHALL create a GitHub Release for the tag `vX.Y.Z` whose notes are that version's section of `CHANGELOG.md`.

#### Scenario: Release notes from changelog

- **WHEN** version `X.Y.Z` has been published to PyPI
- **THEN** a GitHub Release named for `vX.Y.Z` exists and its notes match the `X.Y.Z` section of `CHANGELOG.md`

### Requirement: Distribution shape and licensing

emupos SHALL be distributed as a single pure-Python `py3-none-any` wheel plus a source distribution. Operating-system-specific runtime dependencies SHALL be declared with environment markers, so that installing emupos on one operating system SHALL NOT install another operating system's dependencies. The wheel SHALL NOT contain test files or test fixtures. Both distributions SHALL include the Apache-2.0 `LICENSE` and the `NOTICE` file. Continuous integration SHALL fail when any runtime dependency is licensed under GPL, LGPL or AGPL.

#### Scenario: No macOS dependency on Linux

- **WHEN** `pip install emupos` runs on Linux
- **THEN** no package that emupos requires only on macOS is installed

#### Scenario: Wheel contents

- **WHEN** the built wheel is listed
- **THEN** it contains `LICENSE` and `NOTICE` and no `test_*.py` files

#### Scenario: Copyleft dependency rejected

- **GIVEN** a pull request adds a runtime dependency licensed under LGPL-3.0
- **WHEN** continuous integration runs
- **THEN** the licence check fails

### Requirement: Python support policy

The package SHALL declare `requires-python = ">=3.13"`. Continuous integration SHALL run the test suite on Python 3.13 and 3.14 on each of Windows, macOS and Linux. Support for a Python version SHALL be dropped only in a release whose changelog lists it as a breaking change.

#### Scenario: Unsupported interpreter

- **WHEN** a user runs `pip install emupos` with Python 3.12
- **THEN** the installer refuses to install emupos because it requires Python 3.13 or newer

#### Scenario: CI matrix

- **WHEN** continuous integration runs for a pull request
- **THEN** tests run on Python 3.13 and 3.14 on Windows, macOS and Linux, and a failure in any combination fails the check

### Requirement: Independent API and configuration schema versions

The control API version (the `/api/v1` base path) and the configuration schema version (the `schema` integer) SHALL be versioned independently of the package version and of each other. A package release SHALL NOT change the API base path unless it makes a breaking API change, and SHALL NOT change the supported configuration schema version unless it makes an incompatible configuration change. A configuration file declaring a newer schema than the installed emupos supports SHALL be rejected as defined by the configuration capability.

#### Scenario: Package release without API change

- **GIVEN** a minor release adds a CLI option and changes no API behaviour
- **WHEN** the release is installed
- **THEN** the API is still served under `/api/v1` and `GET /api/v1/health` reports `"api_version": 1`

### Requirement: Documented installation methods

`README.md` SHALL document installing emupos with `uv tool install emupos` as the recommended method, and also with `uvx emupos`, `pipx install emupos` and `pip install emupos`. The documentation SHALL include per-operating-system setup guides for the external prerequisites: com0com for serial devices on Windows, Accessibility permission for keyboard-wedge scanning on macOS, and X11 with libXtst for keyboard-wedge scanning on Linux.

#### Scenario: Recommended install

- **GIVEN** a machine with uv installed and no Python 3.13
- **WHEN** the user runs `uv tool install emupos` as documented
- **THEN** `emupos --version` succeeds afterwards

#### Scenario: Prerequisite guides

- **WHEN** a reader opens the documentation
- **THEN** it links a Windows serial guide covering com0com, a macOS Accessibility guide, and a Linux X11 guide covering libXtst
