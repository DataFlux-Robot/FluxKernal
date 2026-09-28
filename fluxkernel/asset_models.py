"""Typed contracts for portable, content-addressed design assets (demo extra)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,strict=True)

class Interval(Model):
    unit: str=Field(min_length=1,max_length=16)
    min: float
    max: float
    @model_validator(mode='after')
    def ordered(self):
        if self.min>self.max:raise ValueError('Interval must be ordered')
        return self

class Requirement(Interval):
    relation: Literal['covers','within']='covers'

class Query(Model):
    category: str=Field(min_length=1,max_length=80)
    requirements: dict[str,Requirement]=Field(default_factory=dict,max_length=64)
    interfaces: dict[str,str]=Field(default_factory=dict,max_length=32)

class Binding(Model):
    part: str
    field: str=Field(pattern=r'^(size|position)\.[012]$|^wall$')
    factor: float=1
    offset: float=0

class Parameter(Model):
    default: float
    min: float
    max: float
    bindings: list[Binding]=Field(min_length=1,max_length=32)
    @model_validator(mode='after')
    def ordered(self):
        if not self.min<=self.default<=self.max:raise ValueError('Parameter default must be within declared bounds')
        return self

class Measure(Model):
    part: str
    field: str=Field(pattern=r'^(size|position)\.[012]$|^wall$')
    unit: Literal['mm']='mm'

class Publish(Model):
    schema_version: Literal['fk-asset-publish-v1']='fk-asset-publish-v1'
    base_manifest_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    name: str=Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    version: str=Field(pattern=r'^\d+\.\d+\.\d+$')
    category: str=Field(min_length=1,max_length=80)
    kind: Literal['component','module','equipment']='module'
    description: str=Field(min_length=1,max_length=1500)
    parts: list[str]=Field(min_length=1,max_length=64)
    capabilities: dict[str,Interval]=Field(default_factory=dict,max_length=64)
    interfaces: dict[str,str]=Field(default_factory=dict,max_length=32)
    measures: dict[str,Measure]=Field(default_factory=dict,max_length=32)
    parameters: dict[str,Parameter]=Field(default_factory=dict,max_length=16)
    origin: list[float]=Field(default_factory=lambda:[0,0,0],min_length=3,max_length=3)

class Instance(Model):
    schema_version: Literal['fk-asset-instance-v1']='fk-asset-instance-v1'
    base_manifest_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    asset_sha256: str=Field(pattern=r'^[a-f0-9]{64}$')
    prefix: str=Field(pattern=r'^[a-z][a-z0-9_-]{0,15}$')
    query: Query
    parameters: dict[str,float]=Field(default_factory=dict,max_length=16)
    position: list[float]=Field(default_factory=lambda:[0,0,0],min_length=3,max_length=3)
    rotation: list[float]=Field(default_factory=lambda:[0,0,0],min_length=3,max_length=3)
    destination: Literal['product','equipment']='product'
    replace: dict[str,str]=Field(default_factory=dict,max_length=64,description='Optional source part ID to existing target part ID mapping; remaining parts are inserted with prefix')

# Static schemas keep MCP discovery dependency-free; runtime models are authoritative.
def write_schemas():
    import json
    from pathlib import Path
    root=Path(__file__).with_name('asset_schemas');root.mkdir(exist_ok=True)
    for name,model in [('publish',Publish),('query',Query),('instance',Instance)]:
        (root/(name+'.json')).write_text(json.dumps(model.model_json_schema(),indent=2)+'\n')

if __name__=='__main__':write_schemas()
