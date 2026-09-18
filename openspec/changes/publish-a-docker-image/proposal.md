## Why

Running emupos next to a POS that is already containerised means installing Python and the prerequisites on every developer's machine, or writing a Dockerfile per project. An official image makes `docker run` the whole setup.

The container defaults are wrong for a container in two ways that both look like "emupos is broken":

- `api.host` and every `tcp` connection's `host` default to `127.0.0.1`, which in a container is the *container's* loopback. Docker publishes ports to the container's `eth0`, so `-p 9100:9100` connection-refuses and the POS cannot reach the printer at all.
- A `serial: { pty: true }` port and its link are paths inside the container's filesystem, so the POS on the host cannot open them.

An image that ships a container-shaped configuration removes both, and `typed_by: client` (see the `type-scans-on-the-client` change) removes the third problem — the keyboard scanner.

## What Changes

- **A `Dockerfile` in the repository** builds an image that runs `emupos run`:
  - `python:3.13-slim` base, the release's own wheel installed into it, running as a non-root user;
  - `WORKDIR /emupos` with a bundled `/emupos/emupos.yaml`, so `emupos run` finds a configuration by the rule it already uses, and mounting a file over it is the way to use your own;
  - no X11 libraries: a container never types, so keyboard scanners in the bundled configuration are `typed_by: client`.
- **The bundled configuration is container-shaped**: `api: { host: 0.0.0.0 }`, a printer on `tcp: { host: 0.0.0.0, port: 9100 }`, a scale on TCP, a keyboard scanner with `typed_by: client`, and no `pty: true` anywhere.
- **The release workflow publishes the image to Docker Hub** for `linux/amd64` and `linux/arm64`, from the same wheel the cross-platform smoke tests passed, after the PyPI publish. Tags: `X.Y.Z` and `latest`.
- **A smoke check on the built image** before pushing: the container starts, `GET /api/v1/health` answers from the host through a published port, and a fixture ESC/POS job sent to the published printer port produces the expected receipt text. A failure stops the push.
- **Documentation:**
  - `docs/docker.md`: the `docker run` line, mounting your own configuration and a receipts volume, why the bundled configuration binds `0.0.0.0` and why publishing to `127.0.0.1:PORT:PORT` keeps it private, what does not cross the container boundary (pty serial ports), and that keyboard scans are typed by the machine running `emupos scan`.
  - `README.md`: Docker in the installation methods, linking that page.
  - `docs/automation.md`: a compose snippet for running emupos beside a POS in CI.

## Non-goals

- **Publishing to any registry other than Docker Hub.** GHCR would need no stored credential and is a natural follow-up, not part of this change.
- **Image signing, SBOM and provenance attestations.** The PyPI artefacts keep their attestations; the image gets them in a later change if it needs them.
- **X11 inside the container.** Typing from a container onto a Linux host's desktop is possible by mounting the X socket and the auth cookie, but it works on no other host operating system. The image stays without X libraries, and keyboard scans are the client's job.
- **A Windows container.**
- **Changing any default in the code.** `127.0.0.1` stays the default everywhere; only the bundled configuration file differs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `release-and-versioning`: a new requirement for the container image (what it contains, how it is built, its tags and when it is pushed), a new requirement for the image smoke check that gates the push, and `Documented installation methods` gains Docker.

## Impact

- New: `Dockerfile`, `docker/emupos.yaml` (the bundled configuration), `.dockerignore`, `docs/docker.md`.
- `.github/workflows/release.yml`: a build-and-push job after the publish job, using `docker/build-push-action` with `linux/amd64,linux/arm64`.
- `README.md`, `docs/automation.md`.
- **Dependencies:** no new Python dependency. A new repository secret holds a scoped Docker Hub access token, and a Docker Hub repository has to exist before the first release.
- **Order:** lands after `type-scans-on-the-client`, because the bundled configuration sets `typed_by: client`. If it lands first, the bundled scanner is `mode: serial` until that change arrives.
- **Compatibility:** additive. No existing command, configuration or default changes.
