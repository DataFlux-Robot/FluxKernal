"""Dependency-free discovery for the asset API; execution requires the demo extra."""
import json
from pathlib import Path

def asset_schema(name):
    if name not in ('publish','query','instance'):raise ValueError('Unknown asset schema')
    return json.loads((Path(__file__).with_name('asset_schemas')/(name+'.json')).read_text())

def inline_schema(name):
    schema=asset_schema(name);definitions=schema.get('$defs',{})
    def expand(value):
        if isinstance(value,list):return [expand(v) for v in value]
        if not isinstance(value,dict):return value
        if '$ref' in value:return expand(definitions[value['$ref'].split('/')[-1]])
        return {k:expand(v) for k,v in value.items() if k!='$defs'}
    return expand(schema)
