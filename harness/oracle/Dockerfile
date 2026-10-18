# Legacy oracle image for the Roboviva parity harness.
#
# Runs the UNMODIFIED Python 2 code from the repo root so we can record what it
# actually does. Nothing in this image is part of the shipped service.
#
# Debian bullseye rather than python:2.7-slim: that image is based on buster,
# whose apt repos have moved to archive.debian.org and would need sources
# rewriting to build at all. Bullseye still ships python2.7 as a real package.
#
# The RUN steps are split finer than they would normally be. Each apt group is
# its own layer so a build that is interrupted (texlive is ~1.5GB unpacked over
# a slow link) resumes from the last completed layer instead of starting over.
FROM debian:bullseye-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    SOURCE_DATE_EPOCH=0 \
    FORCE_SOURCE_DATE=1

# python2 runs the legacy code; python3 exists ONLY so PDF summaries are
# extracted with the same pypdf the py3 test suite uses, which keeps text
# extraction from skewing the comparison.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python2 python3 python3-pip ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# geometry, colortbl, amsmath, fancyhdr  (latex.py:167-182)
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-latex-base texlive-latex-recommended \
    && rm -rf /var/lib/apt/lists/*

# supertabular, lastpage
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

# helvet -- the sans font the whole sheet is set in (\sfdefault, latex.py:214)
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

# fourier (\danger), bbding (\Plus), ifsym[alpine] (\Mountain).
#
# Installed from a pre-fetched .deb rather than the network: it is a 513MB
# download that regularly outlives a single build attempt. Fetch it once with
#   harness/oracle/fetch_debs.sh
# The file is gitignored -- it is a build input, not a source artifact.
COPY .debcache/texlive-fonts-extra_2020.20210202-3_all.deb /tmp/
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         /tmp/texlive-fonts-extra_2020.20210202-3_all.deb \
    && rm -f /tmp/texlive-fonts-extra_2020.20210202-3_all.deb \
    && rm -rf /var/lib/apt/lists/*

# python2.7 has no bundled pip on bullseye; bootstrap the last one that works.
RUN curl -fsSL https://bootstrap.pypa.io/pip/2.7/get-pip.py -o /tmp/get-pip.py \
    && python2 /tmp/get-pip.py 'pip==20.3.4' 'setuptools==44.1.1' 'wheel==0.37.1' \
    && rm -f /tmp/get-pip.py

COPY requirements.txt /oracle/requirements.txt
RUN python2 -m pip install --no-cache-dir -r /oracle/requirements.txt

# Same pypdf on both sides of the PDF comparison.
RUN python3 -m pip install --no-cache-dir 'pypdf==3.17.4'

# Fail the build, not the first test run, if a LaTeX package is missing.
RUN set -eux; \
    for pkg in geometry colortbl supertabular amsmath helvet fourier bbding \
               ifsym fancyhdr lastpage; do \
      kpsewhich "$pkg.sty" >/dev/null || { echo "MISSING LaTeX package: $pkg"; exit 1; }; \
    done; \
    python2 -c "import flask, flask_shelve; print('py2 flask OK')"; \
    python3 -c "import pypdf; print('py3 pypdf OK')"; \
    echo "oracle image ready"

WORKDIR /repo
ENTRYPOINT ["/bin/bash"]
