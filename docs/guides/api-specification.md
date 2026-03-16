# API Specification

Auto-generated from the FastAPI application.
Rebuild with `just docs-openapi` or `uv run python scripts/export_openapi.py`.

<div id="swagger-ui"></div>

<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
document.addEventListener("DOMContentLoaded", function () {
    // Resolve openapi.json relative to the site root
    var base = document.querySelector('meta[name="generator"]') ? "" : "";
    SwaggerUIBundle({
        url: "../../openapi.json",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout",
        deepLinking: true,
        defaultModelsExpandDepth: 1,
        docExpansion: "list",
        supportedSubmitMethods: [],
    });
});
</script>
