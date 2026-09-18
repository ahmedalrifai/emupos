## Context

emupos is a pure-Python `py3-none-any` wheel published to PyPI by a tag-triggered workflow that first installs and smoke-tests the wheel on Windows, macOS and Linux (`release-and-versioning`). There is no container image today, and nothing in the repository describes running emupos in one.

Three defaults decide the shape of a container image:

- `ApiSettings.host` and `TcpConnection.host` both default to `127.0.0.1` (`src/emupos/config.py`), which `device-connections` and `control-api` pin as required behaviour. In a container that is the container's own loopback, and Docker publishes to `eth0`.
- `emupos run` reads `--config PATH`, and otherwise `emupos.yaml` in the current working directory (`configuration`, "Configuration file discovery"). There is no environment variable, and this change does not add one.
- A `serial: { pty: true }` port lives in the container's filesystem, so it is invisible to a POS on the host.

The keyboard scanner is handled by the separate `type-scans-on-the-client` change; this one assumes `typed_by` exists.

## Goals / Non-Goals

**Goals:**

- `docker run` with two published ports is a working emupos, without reading anything first.
- The image contains exactly the bytes PyPI got, and is pushed only after the same gates.
- Using your own configuration is one `-v`.
- Nothing about the non-container defaults changes.

**Non-Goals:**

- Other registries, signing, SBOMs, X11 in the container, Windows containers.
- A configuration environment variable or a new CLI flag.

## Decisions

### D1. The image installs the release's own wheel

The workflow already builds one wheel and smoke-tests it on three operating systems before publishing. The image job takes that same artefact and `pip install`s it, rather than building from the source tree again (which could differ) or installing from PyPI (which would wait on propagation and could, in principle, fetch something else). The image is therefore the tested bytes, and the build needs no network access to an index.

### D2. Configuration by the rule that already exists

`WORKDIR /emupos` and a bundled `/emupos/emupos.yaml`. `emupos run` with no arguments then finds it, exactly as it does on a developer's machine, and using your own configuration is `-v ./emupos.yaml:/emupos/emupos.yaml:ro`. Alternatives considered:

- an `EMUPOS_CONFIG` environment variable — a new way to find a file, for no gain over a bind mount;
- `CMD ["emupos", "run", "--config", "/etc/emupos/emupos.yaml"]` — the same thing with a longer path and a `CMD` users must repeat when they override it;
- shipping no configuration and requiring a mount — fails the "works without reading anything first" goal.

### D3. The bundled configuration binds `0.0.0.0`, and the documentation publishes to loopback

`0.0.0.0` inside the container is what makes `-p` work at all. It is not a weaker default than `127.0.0.1` on a host, because the container's network namespace holds nothing else; what decides exposure is the publish flag, so the documentation always shows:

```
docker run -p 127.0.0.1:9100:9100 -p 127.0.0.1:8765:8765 …
```

`emupos run` prints its "any machine able to reach that address is able to control the devices" warning on every start, as `control-api` requires. `docs/docker.md` explains why it appears and what makes it untrue here, so it is not mistaken for a misconfiguration.

The bundled configuration uses TCP for every device and no `pty: true`, because a pty and its link do not cross the container boundary.

### D4. No X11 libraries in the image

A container cannot reach the host's window server on macOS or Windows at all, and on Linux only by mounting `/tmp/.X11-unix` and the `XAUTHORITY` cookie into it. Supporting that would mean carrying libX11 and libXtst in every pull for a case that works on one host operating system. The bundled configuration uses `typed_by: client` instead, so the keystrokes come from the machine running `emupos scan`, and the image stays small and X-free.

The CLI is in the image regardless, so `docker exec <container> emupos devices` and the other non-typing commands work without installing anything on the host.

### D5. Multi-architecture, two platforms

`linux/amd64` and `linux/arm64`, built with `docker/build-push-action` and QEMU. The wheel is `py3-none-any`, so the only per-architecture content is the base image; the build stays cheap. arm64 is not optional — Apple Silicon is the common developer machine here, and an amd64-only image runs under emulation with a warning on every start.

### D6. Docker Hub, with a scoped access token, after PyPI

Docker Hub has no equivalent of PyPI Trusted Publishing, so this is the repository's first stored publishing credential: a scoped access token with write access to one repository, held as a repository secret. `release-and-versioning`'s "no stored token" requirement is about PyPI and stays true.

The image job runs after the PyPI publish job and depends on the same smoke-test gates, so a release either produces both artefacts or neither is reached. Tags are `X.Y.Z` and `latest`; `latest` moves only on a non-prerelease tag.

### D7. The image is smoke-tested before it is pushed

Building an image that starts is not evidence that a POS can reach it — the loopback default is exactly the failure that a build-only check misses. The job therefore runs the built image with published ports and, from the runner (not from inside the container), checks `GET /api/v1/health` and sends a fixture ESC/POS job to the published printer port, asserting the receipt text. This reuses the fixture the wheel's smoke test already uses.

## Risks / Trade-offs

- **A long-lived Docker Hub token in repository secrets** → scoped to one repository with write-only access, rotated on schedule; it cannot publish to PyPI or push to the repository.
- **`latest` moves under users** → the documentation pins `X.Y.Z` in every compose example, and `latest` appears only in the one-line "try it" command.
- **Docker Hub anonymous pull rate limits** in CI → documented; GHCR as a second registry is the follow-up if it bites.
- **The bundled configuration drifts from the starter configuration** `emupos config init` writes → they answer different questions (a container with TCP everywhere, versus a developer machine with pty ports), so they are deliberately different files; the tasks include a check that both stay valid.
- **QEMU-built arm64 image is only smoke-tested on amd64** → the runner is amd64, so the arm64 image is built but not started. Accepted: the only per-architecture content is the base image.

## Migration Plan

Additive. The first release after this change publishes the first image; nothing existing changes. Rolling back is removing the image job — published tags stay, and no other artefact depends on them.

## Open Questions

- The Docker Hub namespace and repository name (`emupos/emupos`, or a personal namespace) has to be created before the first tagged release, and the token issued for it.
