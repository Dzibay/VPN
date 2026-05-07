"""HTML Swagger UI со встроенной OpenAPI-схемой (без отдельного URL /openapi.json)."""

from __future__ import annotations

import base64
import json
from html import escape
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import _html_safe_json, swagger_ui_default_parameters
from starlette.responses import HTMLResponse


def staff_swagger_ui_html(
    *,
    application: FastAPI,
    title: str,
    swagger_ui_parameters: dict[str, Any] | None = None,
    swagger_js_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    swagger_css_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    swagger_favicon_url: str = "https://fastapi.tiangolo.com/img/favicon.png",
    oauth2_redirect_url: str | None = None,
    init_oauth: dict[str, Any] | None = None,
) -> HTMLResponse:
    params = swagger_ui_default_parameters.copy()
    if swagger_ui_parameters:
        params.update(swagger_ui_parameters)

    schema = jsonable_encoder(application.openapi())
    raw = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    spec_b64 = base64.b64encode(raw).decode("ascii")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link type="text/css" rel="stylesheet" href="{swagger_css_url}">
    <link rel="shortcut icon" href="{swagger_favicon_url}">
    <title>{escape(title)}</title>
    </head>
    <body>
    <div id="swagger-ui">
    </div>
    <script src="{swagger_js_url}"></script>
    <script>
    const spec = JSON.parse(((b64) => {{
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    }})("{spec_b64}"));
    const ui = SwaggerUIBundle({{
        spec: spec,
    """

    for key, value in params.items():
        html += f"{_html_safe_json(key)}: {_html_safe_json(jsonable_encoder(value))},\n"

    if oauth2_redirect_url:
        html += f"oauth2RedirectUrl: window.location.origin + '{oauth2_redirect_url}',"

    html += """
    presets: [
        SwaggerUIBundle.presets.apis,
        SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
    })"""

    if init_oauth:
        html += f"""
        ui.initOAuth({_html_safe_json(jsonable_encoder(init_oauth))})
        """

    html += """
    </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
