from pathlib import Path
import json
from fluxkernel.robotics.part_geometry import generate
def gen_step():
    return generate(json.loads(Path(__file__).with_name("recipe.json").read_text()))
