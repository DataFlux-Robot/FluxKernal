"""Include the canonical proof project and examples in built distributions."""
from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        assets = Path(self.build_lib) / "fluxkernel" / "_assets"
        sources = [root / "lean-toolchain", root / "lakefile.toml",
                   root / "scripts/verify_demo_bundle.py"]
        sources += sorted((root / "formal").rglob("*.lean"))
        sources += sorted((root / "examples").glob("*.fcad"))
        for source in sources:
            target = assets / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            copy2(source, target)


setup(cmdclass={"build_py": BuildPy})
