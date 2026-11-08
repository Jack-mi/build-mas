import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_exported_schemas_match_owning_code():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("export_schemas", root / "scripts/export_schemas.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for name, schema in module.schemas().items():
        Draft202012Validator.check_schema(schema)
        assert json.loads((root / "src/build_mas/schemas" / f"{name}.schema.json").read_text()) == schema
