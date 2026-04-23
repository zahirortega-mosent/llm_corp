FROM ghcr.io/open-webui/open-webui:main

USER root

ARG BRAND_NAME="Mosent Group"
ENV BRAND_NAME=${BRAND_NAME}
ENV WEBUI_NAME=${BRAND_NAME}

COPY patch_brand.py /tmp/patch_brand.py

RUN python /tmp/patch_brand.py && rm -f /tmp/patch_brand.py
