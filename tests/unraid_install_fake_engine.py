"""Closed Docker/API simulation for the installer. MUST run in disposable tmpfs mounts."""

import fcntl
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    state_path = Path(os.environ["EMS_FAKE_ENGINE"])
    state = json.loads(state_path.read_bytes())
    mode, args = sys.argv[1], sys.argv[2:]

    def save():
        state_path.write_text(json.dumps(state))

    def find(name):
        return next(c for c in state["containers"].values() if c["Id"] == name or c["Name"] == "/"+name)

    if mode == "curl":
        assert args[-1].endswith("/containers/create?name=eos-pv-helper")
        assert not any(c["State"]["Running"] for c in state["containers"].values())
        if os.environ.get("EMS_FAIL_CREATE"):
            return 22
        payload = json.loads(Path(args[args.index("--data-binary")+1][1:]).read_bytes())
        original = state["containers"][state["old_id"]]
        target = {"Id": "2"*64, "Image": state["helper_id"], "Name": "/eos-pv-helper",
                  "Config": {k: v for k, v in payload.items() if k not in ("HostConfig", "NetworkingConfig")},
                  "HostConfig": payload["HostConfig"], "Mounts": original["Mounts"],
                  "State": {"Running": False, "Health": {"Status": "starting"}}}
        target["Config"]["Labels"]["org.eos.event-evidence-contract"] = "new-image-default"
        if os.environ.get("EMS_DRIFT_NEW_RUNTIME"):
            target["HostConfig"]["Memory"] = 1
        state["containers"][target["Id"]] = target
        state["events"].append("create")
        save()
        if os.environ.get("EMS_CREATE_ACK_LOST"):
            return 22
        print(json.dumps({"Id": target["Id"], "Warnings": []}))
        return 0
    assert args[:2] == ["--host", "unix:///var/run/docker.sock"]
    args = args[2:]
    verb = args[0]
    if verb == "inspect":
        target = find(args[-1])
        if "--format" not in args:
            print(json.dumps([target]))
        else:
            template = args[args.index("--format")+1]
            values = {"{{.Id}}": target["Id"], "{{.Image}}": target["Image"], "{{.Name}}": target["Name"],
                      "{{.State.Running}}": str(target["State"]["Running"]).lower(),
                      "{{.Config.Image}}": target["Config"]["Image"]}
            if template.startswith("{{index .Config.Labels"):
                print(target["Config"]["Labels"].get(template.split('"')[1], "<no value>"))
            else:
                print(values[template])
    elif verb == "image":
        print(state["helper_id"])
    elif verb == "load":
        state["events"].append("load")
        save()
        print("Loaded synthetic image")
    elif verb == "version":
        print("1.54")
    elif verb == "exec":
        target = find(args[2])
        assert target["State"]["Running"]
        return subprocess.run([sys.executable, *args[4:]], stdin=sys.stdin.buffer).returncode
    elif verb == "kill":
        assert args[1:3] == ["--signal", "TERM"]
        with Path(state["output"]).joinpath("sync.lock").open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                raise AssertionError("TERM must only be sent while the installer holds the exclusive sync lock")
        find(args[-1])["State"]["Running"] = False
        state["events"].append("term-outside-dispatch")
        if os.environ.get("EMS_CHANGE_CONFIG_ON_STOP"):
            with Path(state["config"]).open("ab") as handle:
                handle.write(b'\noperator_change = "keep"\n')
        save()
    elif verb == "wait":
        assert not find(args[-1])["State"]["Running"]
        print(0)
    elif verb == "rename":
        find(args[1])["Name"] = "/"+args[2]
        state["events"].append("rename")
        save()
    elif verb == "start":
        target = find(args[1])
        if os.environ.get("EMS_FAIL_START") and target["Id"] != state["old_id"]:
            return 1
        shutil.copyfile(state["config"], "/app/config.toml")
        target["State"]["Running"] = True
        state["events"].append("start-old" if target["Id"] == state["old_id"] else "start-new")
        save()
        print(target["Id"])
    elif verb == "rm":
        target = find(args[1])
        assert target["Id"] != state["old_id"] and not target["State"]["Running"]
        del state["containers"][target["Id"]]
        state["events"].append("remove-new")
        save()
    else:
        raise AssertionError("Unexpected migration operation")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StopIteration:
        raise SystemExit(1) from None
