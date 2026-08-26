import re


def test_application_serves_all_rendered_static_assets():
    from goldmonitor.application import app

    static_endpoints = [
        rule.endpoint
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/static/")
    ]
    assert app.static_folder is None
    assert static_endpoints == ["static_files"]

    client = app.test_client()
    index_response = client.get("/")
    assert index_response.status_code == 200

    asset_paths = set(
        re.findall(
            r'(?:href|src)="(/static/[^\"]+)"',
            index_response.get_data(as_text=True),
        )
    )
    assert "/static/app.css" in asset_paths
    assert any(path.startswith("/static/app.js?") for path in asset_paths)
    assert any(path.startswith("/static/vendor/chart.umd.min.js?") for path in asset_paths)
    assert any(path.startswith("/static/vendor/socket.io.min.js?") for path in asset_paths)
    assert "cdn.jsdelivr.net" not in index_response.get_data(as_text=True)
    assert "cdn.socket.io" not in index_response.get_data(as_text=True)

    failures = {}
    for path in sorted(asset_paths):
        response = client.get(path)
        if response.status_code != 200:
            failures[path] = response.status_code

    assert failures == {}
    assert client.get("/static/app.css").mimetype == "text/css"
    assert "javascript" in client.get("/static/app.js").mimetype
