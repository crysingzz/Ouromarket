"""Real Docker acceptance of fixed programs; never reads arbitrary native source.

Use --gvisor on the provisioned Linux sandbox host for the production policy.
Without it only built-in fixtures are permitted, explicitly marked in the report.
"""

import argparse
import json
import threading
from pathlib import Path

import httpx

from adaptive_alpha.domain import canonical
from adaptive_alpha.runner.contracts import ToolRequest
from adaptive_alpha.runner.docker import LABEL, OWNER, DockerRunner


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise SystemExit(reason)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, help="Local trusted Docker Engine Unix socket")
    parser.add_argument(
        "--image-id", required=True, help="Pinned sha256 image ID from the local build"
    )
    parser.add_argument("--gvisor", action="store_true")
    parser.add_argument("--output", default=".state/runner-acceptance.json")
    args = parser.parse_args()
    results = []
    report = {
        "profile": "runsc" if args.gvisor else "development-fixed-fixtures",
        "production_blocked_missing_gvisor": None,
        "capital_eligible": False,
        "acceptance_passed": False,
        "results": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    with httpx.Client(
        transport=httpx.HTTPTransport(uds=args.socket), base_url="http://docker", trust_env=False
    ) as client:
        runner = DockerRunner(client, args.image_id, development_fixtures=not args.gvisor)
        runner.recover()
        info = client.get("/v1.47/info").raise_for_status().json()
        production_blocked = "runsc" not in info.get("Runtimes", {})
        report["production_blocked_missing_gvisor"] = production_blocked
        save()
        if production_blocked:
            try:
                DockerRunner(client, args.image_id).run(ToolRequest(source="def run(p): return p"))
            except ValueError as exc:
                require(str(exc) == "GVISOR_REQUIRED", "Unexpected production refusal")
            else:
                raise SystemExit("Missing production runtime did not block execution")
        expected = {
            "echo": {"SUCCESS"},
            "boundaries": {"SUCCESS"},
            "timeout": {"TIMEOUT"},
            "output": {"OUTPUT_LIMIT"},
            "stderr": {"OUTPUT_LIMIT"},
            "invalid": {"INVALID_OUTPUT"},
            "failure": {"TOOL_FAILED"},
            "children": {"TIMEOUT"},
            "memory": {"RESOURCE_LIMIT", "TOOL_FAILED"},
            "workspace": {"SUCCESS"},
        }
        for fixture in [*expected, "workspace"]:
            result = runner.run_fixture(fixture)
            results.append({"fixture": fixture, **result})
            save()
            print(f"{fixture}: {result['status']}", flush=True)
            require(result["status"] in expected[fixture], f"Unexpected outcome: {fixture}")
            require(result["cleanup_confirmed"], "Container cleanup unconfirmed")
            if fixture == "boundaries":
                output = result["output"]
                require(output["uid"] == 65532, "Child did not drop privileges")
                require(len(output["denied"]) == 3, "Sensitive path was accessible")
                require(output["root_denied"], "Child could regain root")
                require(
                    output["capabilities"]
                    == {"CapEff": "0000000000000000", "CapPrm": "0000000000000000"},
                    "Child retained supervisor capabilities",
                )
                require(
                    output["readonly"]
                    and output["watchdog_protected"]
                    and output["network_denied"],
                    "Isolation boundary failed",
                )
            if fixture == "workspace":
                require(not result["output"]["previous_exists"], "Workspace leaked between jobs")
        cancel = threading.Event()
        timer = threading.Timer(1, cancel.set)
        timer.start()
        try:
            cancelled = runner.run_fixture("children", seconds=10, cancel=cancel)
        finally:
            timer.cancel()
        results.append({"fixture": "cancel-children", **cancelled})
        save()
        require(
            cancelled["status"] == "CANCELLED" and cancelled["cleanup_confirmed"], "Cancel failed"
        )
        remaining = (
            client.get(
                "/v1.47/containers/json",
                params={"all": "true", "filters": canonical({"label": [LABEL + "=" + OWNER]})},
            )
            .raise_for_status()
            .json()
        )
        own_ids = {item["id"] for item in results}
        require(
            not any(
                item.get("Labels", {}).get("org.ouromarket.runner.name") in own_ids
                for item in remaining
            ),
            "Acceptance containers remain after cleanup",
        )
    report["acceptance_passed"] = True
    save()
    print(f"Runner acceptance passed: {len(results)} jobs; {report['profile']}")


if __name__ == "__main__":
    main()
