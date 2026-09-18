## 1. The image

- [ ] 1.1 Add `.dockerignore` excluding `.git`, `receipts/`, `openspec/`, `spikes/`, `docs/` and the virtual environment, so the build context stays small.
- [ ] 1.2 Add `Dockerfile`: `python:3.13-slim`, a non-root user, `WORKDIR /emupos`, `pip install --no-cache-dir` of the wheel copied in from the build context (`ARG WHEEL`), `COPY docker/emupos.yaml /emupos/emupos.yaml`, `EXPOSE 8765 9100`, `CMD ["emupos", "run"]` (design D1, D2).
- [ ] 1.3 Add `docker/emupos.yaml`: `api: { host: 0.0.0.0 }`, printer `front` on `tcp: { host: 0.0.0.0, port: 9100 }`, scale `deli` on TCP, scanner `lane1` with `mode: keyboard` and `typed_by: client`, and no `pty: true` (design D3).
- [ ] 1.4 Build locally and check by hand: the container starts with no arguments; `curl http://127.0.0.1:8765/api/v1/health` answers from the host through `-p 127.0.0.1:8765:8765`; `docker exec … emupos devices` lists the devices; the image has no libX11 or libXtst; the process is not root.
- [ ] 1.5 Check that `openspec`-independent validation passes for the bundled file: `emupos config validate docker/emupos.yaml`.

## 2. Release workflow

- [ ] 2.1 In `.github/workflows/release.yml`, add a job that runs after the PyPI publish job and downloads the wheel artefact the smoke tests used (design D1).
- [ ] 2.2 In that job, build the image for the runner's architecture only and run the image smoke check from the runner: health endpoint through a published port, then the fixture ESC/POS job to the published printer port with its expected receipt text (design D7).
- [ ] 2.3 Set up QEMU and Buildx, then build and push `linux/amd64,linux/arm64` with `docker/build-push-action`, tagged `X.Y.Z`, and `latest` only for a non-prerelease tag (design D4, D6).
- [ ] 2.4 Use a `DOCKERHUB_TOKEN` repository secret scoped to the image repository, with `DOCKERHUB_USERNAME`. Fail the job with a clear message when either is missing.
- [ ] 2.5 Confirm the job cannot run when the publish job failed, and that it never overwrites an existing `X.Y.Z` tag.

## 3. Documentation

- [ ] 3.1 Add `docs/docker.md`: the `docker run` line with `-p 127.0.0.1:…`, mounting your own `emupos.yaml` and a receipts volume, why the bundled configuration binds `0.0.0.0` and why the startup warning about non-loopback binding is expected here, that pty serial ports do not cross the boundary, that keyboard scans are typed by the machine running `emupos scan`, and `docker exec … emupos devices` for the non-typing commands.
- [ ] 3.2 `README.md`: Docker in the installation methods, linking `docs/docker.md`, with `X.Y.Z` pinned in the compose example and `latest` only in the one-line try-it command.
- [ ] 3.3 `docs/automation.md`: a compose snippet running emupos beside a POS in CI, using TCP connections only and `mode: serial` for the scanner — CI has no operator to type a client-typed scan, which is what the page already says about keyboard scanners.

## 4. Before the first release

- [ ] 4.1 Create the Docker Hub repository and issue a scoped access token; store `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` as repository secrets (design D6, open question).
- [ ] 4.2 Run the workflow once against a test tag or a scratch repository to prove the push path before a real release depends on it.
