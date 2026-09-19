# emupos in a container: the simulated devices and the control API, with no desktop of its own.
#
# Built from the wheel the release workflow already smoke-tested on three operating systems,
# never from the source tree, so the image holds exactly what PyPI holds. See docs/docker.md.
FROM python:3.13-slim

# No X11 libraries: a container cannot reach the host's window server, so keyboard scans are
# typed by whoever runs `emupos scan` (`typed_by: client` in the bundled configuration).
RUN useradd --create-home --uid 10001 emupos

COPY dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# `emupos run` reads `emupos.yaml` from the working directory, so replacing the bundled
# configuration is one bind mount: -v ./emupos.yaml:/emupos/emupos.yaml:ro
COPY docker/emupos.yaml /emupos/emupos.yaml
RUN chown -R emupos:emupos /emupos

USER emupos
WORKDIR /emupos
ENV PYTHONUNBUFFERED=1
EXPOSE 8765 9100
CMD ["emupos", "run"]
