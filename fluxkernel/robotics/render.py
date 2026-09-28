"""Render native MJCF projections at their source rest configuration."""


def render(bundle, output):
    import os

    os.environ.setdefault("MUJOCO_GL", "egl")
    import mujoco as mj
    from PIL import Image, ImageDraw
    from pathlib import Path

    root = Path(bundle)
    model = mj.MjModel.from_xml_path(str(root / "robot.xml"))
    data = mj.MjData(model)
    mj.mj_forward(model, data)
    canvas = Image.new("RGB", (1024, 816), (25, 29, 35))
    draw = ImageDraw.Draw(canvas)
    opt = mj.MjvOption()
    opt.geomgroup[3] = 0
    cameras = [
        ("Perspective", 135, -20),
        ("+Y view", 90, 0),
        ("+X view", 0, 0),
        ("Top", 90, -90),
    ]
    with mj.Renderer(model, height=384, width=512) as renderer:
        for i, (label, azimuth, elevation) in enumerate(cameras):
            camera = mj.MjvCamera()
            camera.lookat[:] = model.stat.center
            camera.distance = model.stat.extent * 1.25
            camera.azimuth = azimuth
            camera.elevation = elevation
            renderer.update_scene(data, camera=camera, scene_option=opt)
            frame = Image.fromarray(renderer.render())
            x = (i % 2) * 512
            y = (i // 2) * 408
            canvas.paste(frame, (x, y))
            draw.text(
                (x + 12, y + 387),
                label + " | native rest pose, no policy",
                (220, 230, 240),
            )
    canvas.save(output)
