## 1. The image

- [x] 1.1 Add `.dockerignore` so the build context stays small. Written as an allowlist (`*`, then `!dist/*.whl` and `!docker/emupos.yaml`) rather than the denylist first sketched: the image needs exactly two files, and an allowlist cannot go stale as the repository grows.
- [x] 1.2 Add `Dockerfile`: `python:3.13-slim`, a non-root user (uid 10001), `WORKDIR /emupos`, `pip install --no-cache-dir` of the wheel copied in from the build context, `COPY docker/emupos.yaml /emupos/emupos.yaml` owned by that user, `PYTHONUNBUFFERED=1` so `docker logs` shows events live, `EXPOSE 8765 9100 9200`, `CMD ["emupos", "run"]` (design D1, D2). The wheel is copied with `dist/*.whl` rather than an `ARG WHEEL`, so `docker build .` works with no argument after `uv build`.
- [x] 1.3 Add `docker/emupos.yaml`: `api: { host: 0.0.0.0 }`, printer `front` on `tcp: { host: 0.0.0.0, port: 9100 }`, scanner `lane1` with `mode: keyboard` and `typed_by: client`, and no serial device at all (design D3, D3a). A Toledo scale on TCP was written first and removed: the protocol worked through a published port, but TCP is not how that scale attaches, so it would have looked like scale coverage while testing none of a POS's serial code.
- [x] 1.4 Build locally and check by hand: done on macOS with Docker 29.6.2. The container starts with no arguments; health answers from the host through `-p 127.0.0.1:18765:8765`; `docker exec … emupos devices` lists front and lane1 as "typed by the client"; no libX11 or libXtst in the image; `whoami` is `emupos`. Also confirmed that a pty device configured inside the container is not openable from the host (design D3a).
- [x] 1.5 Check that `openspec`-independent validation passes for the bundled file: `emupos config validate docker/emupos.yaml`.

## 2. Release workflow

- [x] 2.1 In `.github/workflows/release.yml`, add a job that runs after the PyPI publish job and downloads the wheel artefact the smoke tests used (design D1).
- [x] 2.2 In that job, build the image for the runner's architecture only and run `.github/scripts/image_smoke_test.py` from the runner: health endpoint through a published port, the fixture ESC/POS job to the published printer port with its expected receipt text, and the container's user is not root (design D7). Verified locally against `emupos:candidate`.
- [x] 2.3 Set up QEMU and Buildx, then build and push `linux/amd64,linux/arm64` with `docker/build-push-action`, tagged `X.Y.Z`, and `latest` only for a non-prerelease tag (design D5, D6).
- [x] 2.4 Use a `DOCKERHUB_TOKEN` repository secret scoped to the image repository, with `DOCKERHUB_USERNAME`. Fail the job with a clear message when either is missing.
- [x] 2.5 The job cannot run when the publish job failed (`if: needs.publish-pypi.result == 'success'`), and a `docker manifest inspect` step fails it before pushing when the version's tag already exists. Proving both against the real registry is task 4.2.

## 3. Documentation

- [x] 3.1 Add `docs/docker.md`: the `docker run` line with `-p 127.0.0.1:…`, mounting your own `emupos.yaml` and a receipts volume, why the bundled configuration binds `0.0.0.0` and why the startup warning about non-loopback binding is expected here, that pty serial ports do not cross the boundary, that keyboard scans are typed by the machine running `emupos scan`, and `docker exec … emupos devices` for the non-typing commands.
- [x] 3.2 `README.md`: Docker in the installation methods, linking `docs/docker.md`, with `X.Y.Z` pinned in the compose example and `latest` only in the one-line try-it command.
- [x] 3.3 `docs/automation.md`: a compose snippet running emupos beside a POS in CI, using TCP connections only and a serial scanner — CI has no operator to type a client-typed scan, which is what the page already says about keyboard scanners.

## 4. Before the first release (the maintainer's, not this change's)

- [ ] 4.1 Create the Docker Hub repository and issue a scoped access token; store `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` as repository secrets (design D6, open question).
- [ ] 4.2 Run the workflow once against a test tag or a scratch repository to prove the push path before a real release depends on it.
