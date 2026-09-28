"""Auditable, bounded GLM-only robot accessory perception-action workflow."""

import hashlib
import json
import re
import shutil
import importlib.metadata
import time
import uuid
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictInt

from .part_geometry import Strict, Recipe
from .native import write, digest
from .bundle import verify, seal
from .attachment import zone, attach
from .render import render, render_step


class Review(Strict):
    recipe_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verdict: Literal["meets-brief", "needs-review"]
    findings: list[str] = Field(max_length=12)
    next_step: Literal["revise", "stop"]
    reason: str = Field(min_length=1, max_length=2000)


class Selection(Strict):
    selected_round: StrictInt | None
    reason: str = Field(min_length=1, max_length=2000)


def decode_response(text):
    """Transport-only decoding: a whole JSON object or exactly one JSON fence.

    Never change values, choose between objects or recover truncated JSON.
    """
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        fences = re.findall(r"```(?:json)?\s*\n(.*?)```", text, flags=re.S)
        if len(fences) != 1:
            raise ValueError(
                "Return exactly one JSON object, no prose; ambiguous response rejected"
            )
        value = json.loads(fences[0])
    if not isinstance(value, dict):
        raise ValueError("Expected one JSON object")
    return value


def run(
    parent,
    brief,
    output,
    rounds=3,
    *,
    target=None,
    require_proof=True,
    provider=None,
    config=None,
    deadline_s=1200,
):
    from ..demo import vision
    from ..demo.perception import model_json

    if type(rounds) is not int or not 1 <= rounds <= 3:
        raise ValueError("Pilot permits 1..3 candidate rounds")
    if not isinstance(brief, str) or not 1 <= len(brief) <= 6000:
        raise ValueError("Expected a bounded nonempty brief")
    cfg = dict(config or vision.model_config())
    if cfg.get("model") != "glm-5.3-flash":
        raise ValueError("Robot personalization requires glm-5.3-flash; no fallback")
    cfg["required_model"] = "glm-5.3-flash"
    parent = Path(parent).resolve()
    verify(parent, require_proof)
    contract = zone(parent, target)
    root = Path(output).expanduser().resolve() / ("robot-pal-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    skill = (
        Path(__file__).parents[1] / "demo/skills/robot-personalization/SKILL.md"
    ).read_text()
    (root / "skill.md").write_text(skill)
    write(root / "zone.json", contract)
    (root / "brief.txt").write_text(brief)
    workflow = {}
    for folder, names in [
        (
            "robotics",
            [
                "personalize",
                "attachment",
                "part_geometry",
                "render",
                "bundle",
                "native",
                "projection",
                "validation",
                "proof",
                "personalization_report",
            ],
        ),
        ("demo", ["perception", "vision"]),
    ]:
        for name in names:
            src = Path(__file__).parents[1] / folder / (name + ".py")
            dst = root / "workflow" / folder / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            workflow[str(dst.relative_to(root))] = hashlib.sha256(
                src.read_bytes()
            ).hexdigest()
    write(
        root / "workflow.json",
        {
            "sources": workflow,
            "versions": {
                name: importlib.metadata.version(name)
                for name in ["build123d", "mujoco", "numpy", "pydantic"]
            },
        },
    )
    render(parent, root / "baseline.png")
    render(parent, root / "baseline-head.png", focus_body=contract["parent_body"])

    # Provider injection is only a labeled test seam; CLI never exposes it.
    def wire_provider(*args):
        return model_json(*args, decoder=decode_response)

    ask = provider or wire_provider
    calls = []
    records = []
    eligible = {}
    feedback = []
    selected = None
    started = time.monotonic()
    report = {
        "schema": "fk-robot-pal-v1",
        "mode": "mock" if provider else "live",
        "model": cfg["model"],
        "parent_native_sha256": contract["parent_native_sha256"],
        "max_rounds": rounds,
        "max_provider_calls": 4 * rounds + 2,
        "selected_round": None,
        "status": "running",
        "deployment_ready": False,
        "interface_status": "unverified",
        "records": records,
        "calls": calls,
        "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
    }
    write(root / "run.json", report)

    def invoke(schema, label, prompt, images, directory):
        if len(calls) >= report["max_provider_calls"]:
            raise ValueError("Model call budget exhausted")
        if time.monotonic() - started > deadline_s:
            raise TimeoutError("Robot PAL deadline exceeded")
        return ask(
            cfg,
            skill + "\n" + label,
            prompt,
            images,
            schema,
            directory,
            label,
            lambda *args: None,
            calls,
        )

    def persist():
        report["elapsed_s"] = round(time.monotonic() - started, 2)
        report["model_calls"] = len(calls)
        write(root / "run.json", report)

    try:
        for i in range(rounds):
            directory = root / f"round-{i:02d}"
            directory.mkdir()
            record = {"round": i, "state": "proposing", "attempts": []}
            records.append(record)
            prompt = (
                "User brief: "
                + brief
                + "\nFrozen zone: "
                + json.dumps(contract, ensure_ascii=False)
                + "\nPrevious evidence: "
                + json.dumps(feedback, ensure_ascii=False)
            )
            images = [root / "baseline.png", root / "baseline-head.png"]
            if eligible:
                last = eligible[max(eligible)]
                images += [
                    Path(last["directory"]) / "views.png",
                    Path(last["directory"]) / "head.png",
                ]
            result = None
            recipe = None
            for attempt in range(2):
                raw = None
                try:
                    raw = invoke(
                        Recipe.model_json_schema(),
                        f"plan-{attempt}",
                        prompt,
                        images,
                        directory,
                    )
                    recipe = Recipe.model_validate(raw).model_dump()
                    write(directory / f"recipe-{attempt}.json", recipe)
                    candidate = attach(parent, recipe, directory, target)
                    write(directory / f"build-{attempt}.json", candidate)
                    if not candidate["accepted"] or (
                        require_proof and not candidate["proof_accepted"]
                    ):
                        raise ValueError(
                            "Candidate failed motion or required structural proof; "
                            + json.dumps(candidate)
                        )
                    bundle = Path(candidate["directory"])
                    render(bundle, bundle / "views.png")
                    render(bundle, bundle / "head.png", focus_body=contract["parent_body"])
                    cad_file = bundle / "cad" / candidate["part_body"] / "part.step"
                    step_check = render_step(cad_file, bundle / "part.png")
                    expected = json.loads(cad_file.with_name("properties.json").read_text())
                    write(bundle / "step-checks.json", step_check)
                    if abs(step_check["volume_mm3"] - expected["volume_mm3"]) > max(
                        1e-5, expected["volume_mm3"] * 1e-5
                    ):
                        raise ValueError(
                            f"STEP volume {step_check['volume_mm3']} differs from generating CAD {expected['volume_mm3']}"
                        )
                    seal(bundle)
                    result = candidate
                    break
                except (ValueError, KeyError) as e:
                    failure = {
                        "attempt": attempt, "state": "rejected", "error": str(e),
                        "proposed_recipe": raw,
                    }
                    record["attempts"].append(failure)
                    prompt += "\nRejected attempt: " + json.dumps(failure, ensure_ascii=False)
                    persist()
            if result is None:
                record["state"] = "rejected"
                feedback.append(record)
                persist()
                continue
            review_prompt = json.dumps(
                {
                    "brief": brief,
                    "recipe": recipe,
                    "recipe_sha256": digest(recipe),
                    "build": result,
                    "properties": json.loads(
                        cad_file.with_name("properties.json").read_text()
                    ),
                    "motion": json.loads((bundle / "motion-checks.json").read_text()),
                },
                ensure_ascii=False,
            )
            review = None
            for attempt in range(2):
                try:
                    review = Review.model_validate(
                        invoke(
                            Review.model_json_schema(),
                            f"review-{attempt}",
                            review_prompt,
                            [
                                root / "baseline.png",
                                bundle / "views.png",
                                bundle / "head.png",
                            ],
                            directory,
                        )
                    ).model_dump()
                    if review["recipe_sha256"] != digest(recipe):
                        raise ValueError("Review names a stale recipe")
                    break
                except ValueError as e:
                    review = None
                    review_prompt += "\nInvalid review: " + str(e)
            if review is None:
                raise ValueError("No valid model review")
            write(directory / "review.json", review)
            record.update(state="reviewed", candidate=result, review=review)
            eligible[i] = result
            feedback.append({"round": i, "recipe": recipe, "review": review})
            persist()
            if review["next_step"] == "stop":
                break
        options = [
            {"round": r["round"], "review": r["review"], "candidate": r["candidate"]}
            for r in records
            if r["state"] == "reviewed"
        ]
        if options:
            directory = root / "selection"
            directory.mkdir()
            prompt = json.dumps(
                {"brief": brief, "eligible": options}, ensure_ascii=False
            )
            images = [
                Path(eligible[i]["directory"]) / "views.png" for i in sorted(eligible)
            ]
            for attempt in range(2):
                try:
                    selection = Selection.model_validate(
                        invoke(
                            Selection.model_json_schema(),
                            f"select-{attempt}",
                            prompt,
                            images,
                            directory,
                        )
                    ).model_dump()
                    if (
                        selection["selected_round"] is not None
                        and selection["selected_round"] not in eligible
                    ):
                        raise ValueError(
                            "Selection must name a reviewed eligible round or null"
                        )
                    report["selection"] = selection
                    selected = selection["selected_round"]
                    break
                except ValueError as e:
                    prompt += "\nInvalid selection: " + str(e)
            else:
                raise ValueError("No valid model selection")
        if selected is not None:
            report["selected_round"] = selected
            report["result"] = eligible[selected]
            report["visual_status"] = next(
                r["review"]["verdict"] for r in records if r["round"] == selected
            )
            report["status"] = "prototype-needs-physical-validation"
        else:
            report["status"] = "needs-review"
    except Exception as e:
        report["status"] = "failed"
        report["error"] = str(e)
        persist()
        from .personalization_report import build_report
        build_report(root, report)
        seal(root)
        raise
    persist()
    from .personalization_report import build_report

    build_report(root, report)
    seal(root)
    return {
        **report,
        "directory": str(root),
        "accepted": selected is not None,
        "proof_accepted": eligible[selected]["proof_accepted"]
        if selected is not None
        else False,
    }
