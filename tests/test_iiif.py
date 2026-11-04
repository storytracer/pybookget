"""Tests for IIIF manifest parsing, page image URLs and fetch() (no network: httpx.MockTransport)."""

import asyncio

import httpx
import pytest

from pybookget.config import Config
from pybookget.formats.iiif import canvas_images, image_api_version, parse_iiif_manifest
from pybookget.http.client import create_client, fetch
from pybookget.models.iiif import IIIFService, label_text

V2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@id": "https://example.org/iiif/b1/manifest",
    "@type": "sc:Manifest",
    "label": [{"@value": "Flora", "@language": "en"}],
    "license": "https://creativecommons.org/publicdomain/mark/1.0/",
    "attribution": "Example Library",
    "sequences": [{"canvases": [
        {"@id": "https://example.org/iiif/b1/canvas/1", "label": "i", "images": [{"resource": {
            "@id": "https://example.org/images/b1-1.jpg", "width": 2000, "height": 3000,
            "service": {"@context": "http://iiif.io/api/image/2/context.json",
                        "@id": "https://example.org/iiif/image/b1-1/",
                        "profile": "http://iiif.io/api/image/2/level2.json"}}}]},
        {"@id": "https://example.org/iiif/b1/canvas/2", "label": "blank, no image", "images": []},
        {"@id": "https://example.org/iiif/b1/canvas/3", "label": "ii", "images": [{"resource": {
            "@id": "https://example.org/images/b1-3.jpg"}}]},
    ]}],
}

V3 = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "id": "https://example.org/iiif/b2/manifest",
    "type": "Manifest",
    "label": {"de": ["Flora"]},
    "rights": "http://creativecommons.org/publicdomain/mark/1.0/",
    "requiredStatement": {"label": {"en": ["Attribution"]}, "value": {"en": ["Example Library"]}},
    "items": [{"id": "https://example.org/iiif/b2/canvas/1", "type": "Canvas", "label": {"none": ["1r"]},
               "items": [{"type": "AnnotationPage", "items": [{"type": "Annotation", "body": {
                   "id": "https://example.org/iiif/image/b2-1/full/max/0/default.jpg", "type": "Image",
                   "service": [{"id": "https://example.org/iiif/image/b2-1", "type": "ImageService3",
                                "profile": "level1"}]}}]}]}],
}


def config(**kwargs) -> Config:
    c = Config(retry_wait_min=0, retry_wait_max=0, **kwargs)
    c.proxy = None
    return c


def test_v2_canvas_images_with_fallbacks_and_numbering():
    manifest = parse_iiif_manifest(V2)
    images = canvas_images(manifest, config())
    assert [(i.index, i.canvas.label, i.url, i.fallback_url) for i in images] == [
        (1, "i", "https://example.org/iiif/image/b1-1/full/full/0/default.jpg",
         "https://example.org/images/b1-1.jpg"),
        (2, "ii", "https://example.org/images/b1-3.jpg", None),  # no service: its own URL only
    ]
    assert (manifest.rights, manifest.required_statement) == (
        "https://creativecommons.org/publicdomain/mark/1.0/", "Example Library")


def test_v3_uses_max_and_the_config_parameters():
    manifest = parse_iiif_manifest(V3)
    [image] = canvas_images(manifest, config(iiif_quality="gray", iiif_format="png"))
    assert image.url == "https://example.org/iiif/image/b2-1/full/max/0/gray.png"
    assert image.canvas.label == "1r"  # a label without English
    assert (manifest.rights, manifest.required_statement) == (
        "http://creativecommons.org/publicdomain/mark/1.0/", "Example Library")


@pytest.mark.parametrize("service, version", [
    (IIIFService("s", type="ImageService3"), 3),
    (IIIFService("s", context="http://iiif.io/api/image/3/context.json"), 3),
    (IIIFService("s", profile="http://iiif.io/api/image/1/level1.json"), 2),
    (IIIFService("s"), 2),
    (None, 2),
])
def test_image_api_version(service, version):
    assert image_api_version(service) == version


@pytest.mark.parametrize("value, text", [
    ("Flora", "Flora"),
    ({"@value": "Flora", "@language": "la"}, "Flora"),
    ([{"@value": "Flora"}, "Band 1"], "Flora; Band 1"),
    ({"fr": ["Flore"], "en": ["Flora"]}, "Flora"),
    ({"none": ["1r"]}, "1r"),
    ({}, None),
    (None, None),
])
def test_label_text(value, text):
    assert label_text(value) == text


def run_fetch(cfg, handler, url, fallback_url=None):
    async def main():
        async with create_client(cfg, transport=httpx.MockTransport(handler)) as c:
            return await fetch(c, url, cfg, fallback_url=fallback_url)

    return asyncio.run(main())


def test_fetch_retries_then_falls_back_on_404():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/busy":
            return httpx.Response(503 if len(calls) == 1 else 404)
        return httpx.Response(200, content=b"jpeg")

    response = run_fetch(config(), handler, "https://example.org/busy", "https://example.org/direct")
    assert (response.content, str(response.url)) == (b"jpeg", "https://example.org/direct")
    assert calls == ["https://example.org/busy"] * 2 + ["https://example.org/direct"]


def test_fetch_without_fallback_raises_the_404():
    with pytest.raises(httpx.HTTPStatusError):
        run_fetch(config(), lambda r: httpx.Response(404), "https://example.org/missing")


def test_config_creates_no_folders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Config()
    assert list(tmp_path.iterdir()) == []
