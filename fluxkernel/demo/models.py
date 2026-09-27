from __future__ import annotations

import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Observation(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    source: Literal['visible', 'inferred', 'selected']


class Part(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')
    name: str = Field(min_length=1, max_length=100)
    group: str = Field(min_length=1, max_length=60)
    route: Literal['print', 'catalog', 'machine']
    shape: Literal['box', 'shell', 'frame', 'cylinder', 'tube', 'wing', 'fuselage', 'car_body', 'smooth_fuselage', 'smooth_car_body', 'fuselage_section', 'fuselage_nose', 'fuselage_tail']
    size: list[float] = Field(min_length=3, max_length=3)
    position: list[float] = Field(min_length=3, max_length=3)
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0], min_length=3, max_length=3)
    wall: float = Field(default=2.0, ge=0.4, le=1000)
    material: Literal['pla', 'petg', 'abs', 'aluminum', 'steel', 'catalog'] = 'petg'
    color: str = Field(default='#a8b9c7', pattern=r'^#[0-9a-fA-F]{6}$')
    catalog_ref: str = Field(default='', max_length=120)
    purpose: str = Field(default='', max_length=500)
    source: Literal['visible', 'inferred', 'selected'] = 'selected'

    @field_validator('size')
    @classmethod
    def valid_size(cls, value):
        if any(not 0.4 <= x <= 100000 for x in value):
            raise ValueError('all dimensions must be 0.4..100000 mm')
        return value

    @field_validator('position', 'rotation')
    @classmethod
    def valid_coords(cls, value):
        if any(not math.isfinite(x) or abs(x) > 100000 for x in value):
            raise ValueError('coordinates must be finite and bounded')
        return value

    @model_validator(mode='after')
    def consistent(self):
        if ((self.shape == 'tube' and 2*self.wall >= self.size[0]) or
            (self.shape == 'shell' and (2*self.wall >= min(self.size[:2]) or self.wall >= self.size[2])) or
            (self.shape == 'frame' and 2*self.wall >= min(self.size[:2])) or
            (self.shape in ('car_body','fuselage','smooth_car_body','smooth_fuselage','fuselage_section','fuselage_nose','fuselage_tail') and 12*self.wall >= min(self.size))):
            raise ValueError(f'{self.id}: wall must be less than half the smallest dimension')
        if self.shape in ('cylinder','tube') and self.size[0]!=self.size[1]:
            raise ValueError(f'{self.id}: cylinder/tube X and Y dimensions must be equal')
        if self.shape in ('car_body','fuselage','smooth_car_body','smooth_fuselage','fuselage_section','fuselage_nose','fuselage_tail') and self.size[0]<1.5*self.size[1]:
            raise ValueError(f'{self.id}: car_body/fuselage local X is length and must be at least 1.5 times local Y width; use rotation for a different world axis')
        if self.route == 'catalog' and not self.catalog_ref:
            raise ValueError(f'{self.id}: catalog route needs a specific catalog item')
        if self.route != 'catalog' and self.material == 'catalog':
            raise ValueError(f'{self.id}: fabricated part needs a material')
        return self


class Design(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    family: Literal['phone', 'car', 'aircraft', 'other']
    summary: str = Field(min_length=1, max_length=1000)
    observations: list[Observation] = Field(min_length=1, max_length=30)
    assumptions: list[str] = Field(min_length=1, max_length=25)
    requirements: list[str] = Field(min_length=1, max_length=20)
    parts: list[Part] = Field(min_length=3, max_length=64)
    unresolved: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique_parts(self):
        ids = [p.id for p in self.parts]
        if len(set(ids)) != len(ids):
            raise ValueError('part occurrence IDs must be unique')
        if any(i.startswith(('cell-','assembly-','seed-')) or i=='product' or i=='machine-cell' or i.endswith('-blank') for i in ids):
            raise ValueError('IDs cell-*, assembly-*, seed-*, *-blank, product and machine-cell are reserved')
        return self


class Request(StrictModel):
    brief: str = Field(default='根据图片设计外形相近、功能架构合理的可制造产品。', max_length=3000)
    equipment_depth: int = Field(default=1, ge=0, le=1)
    mode: Literal['live', 'reference', 'fixture', 'revision'] = 'live'
    reference: Literal['phone', 'car', 'aircraft'] | None = None
    visual_rounds: int = Field(default=3, ge=0, le=4)
    parent: str | None = Field(default=None, pattern=r'^[a-f0-9]{16}$')
