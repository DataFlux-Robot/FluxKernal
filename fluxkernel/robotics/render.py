"""Render native MJCF projections at their source rest configuration."""


def render(bundle, output, *, focus_body=None, caption="native rest pose, no policy"):
    import os

    os.environ.setdefault("MUJOCO_GL", "egl")
    import mujoco as mj
    from PIL import Image, ImageDraw
    from pathlib import Path

    root = Path(bundle)
    model = mj.MjModel.from_xml_path(str(root / "robot.xml"))
    model.vis.headlight.ambient[:] = [0.45, 0.45, 0.45]
    model.vis.headlight.diffuse[:] = [0.8, 0.8, 0.8]
    data = mj.MjData(model)
    mj.mj_forward(model, data)
    canvas = Image.new("RGB", (1024, 816), (25, 29, 35))
    draw = ImageDraw.Draw(canvas)
    opt = mj.MjvOption()
    opt.geomgroup[3] = 0
    cameras = [
        ("Perspective", 135, -20),
        ("-Y view", 90, 0),
        ("+X view", 180, 0),
        ("Top", 90, -90),
    ]
    with mj.Renderer(model, height=384, width=512) as renderer:
        for i, (label, azimuth, elevation) in enumerate(cameras):
            camera = mj.MjvCamera()
            camera.lookat[:] = model.stat.center
            camera.distance = model.stat.extent * 1.25
            if focus_body:
                body = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, focus_body)
                if body < 0:
                    raise ValueError("Unknown focus body")
                camera.lookat[:] = data.xpos[body]
                camera.lookat[2] += 0.025
                camera.distance = 0.24
            camera.azimuth = azimuth
            camera.elevation = elevation
            renderer.update_scene(data, camera=camera, scene_option=opt)
            frame = Image.fromarray(renderer.render())
            x = (i % 2) * 512
            y = (i // 2) * 408
            canvas.paste(frame, (x, y))
            draw.text(
                (x + 12, y + 387),
                label + " | " + caption,
                (220, 230, 240),
            )
    canvas.save(output)


def render_step(path, output):
    """Read the primary STEP independently, validate it, then render its geometry."""
    import tempfile
    from pathlib import Path
    import xml.etree.ElementTree as ET
    import build123d as b
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from ..solvers.feature3d import _props

    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError("STEP read failed")
    reader.TransferRoots()
    shape = b.Shape.cast(reader.OneShape())
    if not shape.is_valid or len(shape.solids()) != 1:
        raise ValueError("STEP must contain one valid solid")
    vertices, faces = shape.tessellate(0.08, 0.1)
    with tempfile.TemporaryDirectory(prefix="fk-part-view-") as directory:
        root = Path(directory)
        lines = ["v " + " ".join(str(float(x) / 1000) for x in v) for v in vertices]
        lines += ["f " + " ".join(str(i + 1) for i in f) for f in faces]
        (root / "part.obj").write_text("\n".join(lines) + "\n")
        xml = ET.Element("mujoco")
        # MuJoCo's default world extent dwarfs a millimetre-scale single part.
        # Set the framing from the independently imported STEP bounds.
        bounds = shape.bounding_box()
        center = [(float(a) + float(b)) / 2000 for a, b in zip(bounds.min, bounds.max)]
        extent = max(float(x) for x in bounds.size) / 1000
        ET.SubElement(xml, "statistic", center=" ".join(map(str, center)), extent=str(max(extent, 0.001)))
        asset = ET.SubElement(xml, "asset")
        ET.SubElement(asset, "mesh", name="part", file="part.obj")
        world = ET.SubElement(xml, "worldbody")
        ET.SubElement(world, "geom", type="mesh", mesh="part", rgba=".65 .75 .85 1")
        ET.ElementTree(xml).write(root / "robot.xml")
        render(root, output, caption="primary STEP reconstruction")
    properties = _props(shape.wrapped)
    vp = GProp_GProps()
    error = BRepGProp.VolumePropertiesGK_s(shape.wrapped, vp, 1e-8, False, True, False, False)
    if error < 0:
        raise ValueError("Adaptive STEP mass integration failed")
    moments = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, moments)
    properties.update(volume_mm3=vp.Mass(), com=[moments.CentreOfMass().X(), moments.CentreOfMass().Y(), moments.CentreOfMass().Z()])
    return {
        "accepted": True,
        "solids": 1,
        **properties,
        "scope": "Independent STEP read, B-rep validity, solid count, volume, COM and bounds",
    }
