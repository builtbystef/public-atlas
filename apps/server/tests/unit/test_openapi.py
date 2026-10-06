import json

from public_atlas.openapi import main, schema_json


def test_schema_json_matches_app():
    schema = json.loads(schema_json())
    assert schema["openapi"].startswith("3.1")
    assert "/health" in schema["paths"]


def test_main_writes_file(tmp_path):
    out = tmp_path / "openapi.json"
    main(["-o", str(out)])
    assert out.read_text() == schema_json()


def test_main_writes_stdout(capsys):
    main([])
    assert capsys.readouterr().out == schema_json()
