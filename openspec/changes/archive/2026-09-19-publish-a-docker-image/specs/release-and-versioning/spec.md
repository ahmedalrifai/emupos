## ADDED Requirements

### Requirement: Container image

The repository SHALL contain a `Dockerfile` that builds an image whose default command starts `emupos run`. The image SHALL install the same wheel the release workflow built and smoke-tested, SHALL run as a non-root user, and SHALL NOT contain X11 libraries, because a container does not type keystrokes.

The image SHALL set its working directory to `/emupos` and SHALL contain a `/emupos/emupos.yaml` that is usable in a container without editing: the control API and every device connection bound to `0.0.0.0`, and every keyboard scanner set to `typed_by: client`. Mounting a file over `/emupos/emupos.yaml` SHALL be sufficient to use a different configuration, with no environment variable and no command-line argument.

The bundled configuration SHALL contain only devices whose wiring inside a container is the wiring of the real hardware, and SHALL NOT substitute TCP for a device that speaks a serial protocol, because a POS testing against such a stand-in would exercise none of its serial code. A pseudo-terminal created inside a container cannot be opened from the host, so the documentation SHALL state that serial devices need emupos running on the host.

#### Scenario: Starts with no arguments

- **WHEN** the image is run with no command and no mounted configuration
- **THEN** the simulator starts the devices of the bundled configuration and serves the control API

#### Scenario: Reachable from the host

- **WHEN** the image is run with the control API and printer ports published
- **THEN** a client on the host reaches `GET /api/v1/health` and the printer's TCP port

#### Scenario: Own configuration by bind mount

- **GIVEN** a valid configuration file on the host
- **WHEN** the image is run with that file mounted at `/emupos/emupos.yaml`
- **THEN** the simulator starts that file's devices

#### Scenario: No serial stand-in

- **WHEN** the bundled configuration is read
- **THEN** it defines no device whose real hardware speaks a serial protocol
- **AND** the documentation states that serial devices need emupos on the host

#### Scenario: No X11 libraries

- **WHEN** the image's installed packages are listed
- **THEN** they include neither libX11 nor libXtst

#### Scenario: Not root

- **WHEN** a command is run in the container
- **THEN** its user is not `root`

### Requirement: Container image smoke check gates the push

Before pushing any image tag, the release workflow SHALL start the built image with its ports published and SHALL verify, from outside the container, that `GET /api/v1/health` answers and that a fixture ESC/POS job sent to the published printer port produces the expected receipt text. If either check fails, no image tag SHALL be pushed.

#### Scenario: Image smoke check passes

- **GIVEN** the built image answers the health endpoint and produces the expected receipt
- **WHEN** the smoke check finishes
- **THEN** the push step runs

#### Scenario: Image unreachable from outside

- **GIVEN** the built image's control API is not reachable from the host through its published port
- **WHEN** the smoke check finishes
- **THEN** no image tag is pushed

### Requirement: Container image publishing

After publishing to PyPI, the release workflow SHALL push the image to Docker Hub for `linux/amd64` and `linux/arm64`, tagged `X.Y.Z` and, for a release that is not a prerelease, `latest`. The credential SHALL be an access token scoped to that one image repository, held as a repository secret. A pushed tag `X.Y.Z` SHALL NOT be overwritten.

#### Scenario: Tags pushed

- **WHEN** version `X.Y.Z` has been published to PyPI
- **THEN** Docker Hub serves `X.Y.Z` and `latest` for `linux/amd64` and `linux/arm64`

#### Scenario: PyPI publish failed

- **GIVEN** the publish to PyPI did not succeed
- **WHEN** the workflow finishes
- **THEN** no image tag was pushed

#### Scenario: Token scope

- **WHEN** the repository's secrets are inspected
- **THEN** the only registry credential is an access token for the image repository, and it has no access to PyPI or to the source repository

## MODIFIED Requirements

### Requirement: Documented installation methods

`README.md` SHALL document installing emupos with `uv tool install emupos` as the recommended method, and also with `uvx emupos`, `pipx install emupos` and `pip install emupos`, and SHALL document running the published container image as an alternative that needs no Python on the machine. The documentation SHALL include per-operating-system setup guides for the external prerequisites: com0com for serial devices on Windows, Accessibility permission for keyboard-wedge scanning on macOS, and X11 with libXtst for keyboard-wedge scanning on Linux. It SHALL include a Docker guide stating which ports to publish, that publishing to `127.0.0.1` keeps the control API private, that pseudo-terminal serial ports do not cross the container boundary, and that keyboard-mode scans are typed by the machine that runs `emupos scan`.

#### Scenario: Recommended install

- **GIVEN** a machine with uv installed and no Python 3.13
- **WHEN** the user runs `uv tool install emupos` as documented
- **THEN** `emupos --version` succeeds afterwards

#### Scenario: Prerequisite guides

- **WHEN** a reader opens the documentation
- **THEN** it links a Windows serial guide covering com0com, a macOS Accessibility guide, and a Linux X11 guide covering libXtst

#### Scenario: Docker guide

- **WHEN** a reader opens the Docker guide
- **THEN** it gives a `docker run` command publishing the control API and printer ports to `127.0.0.1`, shows how to mount a configuration file, and states that pseudo-terminal serial ports are not reachable from the host
