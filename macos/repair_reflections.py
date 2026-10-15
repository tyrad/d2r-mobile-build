"""Recover omitted Mac reflection JSON from the same producer's paired MSL metadata.

The generator writes one shared reflection for macOS/iOS, changing only chain
identity and compiler-record fields. Never copy iOS Metal libraries to a Mac.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import urllib.request
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_lock(data):
    return dict(line.split("\t", 1) for line in data.decode().splitlines() if "\t" in line)


def chain_for(source, lock):
    gfx = source / "dm/gfx"
    path = gfx / "tools/dmsh_chain.lock"
    original = path.read_bytes()
    try:
        path.write_bytes(lock)
        spec = importlib.util.spec_from_file_location("paired_chain", gfx / "tools/dmsh_chain.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.version()
    finally:
        path.write_bytes(original)


def verify(directory, chain):
    libraries = list(directory.glob("*.metallib"))
    assert libraries, "No Metal libraries"
    for library in libraries:
        stem = library.stem
        base = stem[:-1] if stem.endswith("_bf") else stem
        path = directory / (base + ".json")
        assert path.is_file(), f"Missing reflection: {path.name}"
        data = json.loads(path.read_text())
        assert data["chain"] == chain and data["key"] == base and data["route"] == "B"
        assert data["entry"] and isinstance(data["bindings"], list)
        if stem.endswith("_bf"):
            assert isinstance(data.get("fetch"), dict), f"Missing fetch metadata: {base}"
    return len(libraries)


def repair(cache, source, ios_archive):
    info = json.loads((cache / "manifest.json").read_text())
    chain = info["shader_chain"]
    directory = cache / "msl" / ("b-" + chain)
    try:
        count = verify(directory, chain)
        return {"status": "already_complete", "libraries": count}
    except (AssertionError, KeyError, ValueError):
        assert not list(directory.glob("*.json")), "Refuse to mix an existing partial reflection set"
    with zipfile.ZipFile(ios_archive) as archive:
        ios = json.loads(archive.read("prepared.json"))
        assert ios["producer"]["source_commit"] == info["source_commit"], "Different producer sources"
        mac_lock = (cache / "shader-chain.lock").read_bytes()
        ios_lock = archive.read("shader-chain.lock")
        assert digest(ios_lock) == ios["files"]["shader-chain.lock"]["sha256"]
        assert parse_lock(mac_lock)["xlate_source"] == parse_lock(ios_lock)["xlate_source"], "Different translator source"
        ios_chain = ios["payload"]["shader_chain"]
        assert chain_for(source, mac_lock) == chain, "Mac generator inputs differ"
        assert chain_for(source, ios_lock) == ios_chain, "iOS generator inputs differ"
        payload = archive.read("source-payload.zip")
        assert digest(payload) == ios["files"]["source-payload.zip"]["sha256"]
    prefix = "Payload/DmIOS.app/msl/b-" + ios_chain + "/"
    staged = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if name.startswith(prefix) and name.endswith("_b.json"):
                metadata = json.loads(archive.read(name))
                stem = Path(name).stem
                assert metadata["chain"] == ios_chain and metadata["key"] == stem
                assert metadata["route"] == "B"
                metadata["chain"] = chain
                metadata["chain_metal"] = "xcrun -sdk macosx metal -c; xcrun -sdk macosx metallib"
                staged[stem + ".json"] = (json.dumps(metadata, ensure_ascii=False, indent=1) + "\n").encode()
    required = {p.with_suffix(".json").name for p in directory.glob("*_b.metallib")}
    assert required and required == set(staged), "Reflection keys do not exactly cover the Mac shaders"
    for name, data in staged.items():
        (directory / name).write_bytes(data)
        info["files"][(directory / name).relative_to(cache).as_posix()] = digest(data)
    count = verify(directory, chain)
    recovery = {"status": "recovered", "reflections": len(staged), "libraries": count,
                "producer_source": info["source_commit"], "mac_chain": chain,
                "reflection_source_chain": ios_chain, "ios_archive_sha256": digest(Path(ios_archive).read_bytes()),
                "note": "Shared reflection bindings preserved; macOS libraries unchanged. Generator inputs and translator source verified."}
    info["reflection_recovery"] = recovery
    (cache / "manifest.json").write_text(json.dumps(info, indent=2) + "\n")
    return recovery


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("cache", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--ios-archive", type=Path)
    args = parser.parse_args()
    if args.ios_archive:
        print(json.dumps(repair(args.cache, args.source, args.ios_archive), indent=2))
    else:
        with tempfile.TemporaryDirectory(prefix="mac-reflections-") as temporary:
            archive = Path(temporary) / "ios-prepared.zip"
            request = urllib.request.Request(os.environ["IOS_REFLECTION_INPUT_URL"], headers={"User-Agent": "D2R-Mac-reflection-repair"})
            with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as output:
                import shutil
                shutil.copyfileobj(response, output)
            assert digest(archive.read_bytes()) == os.environ["IOS_REFLECTION_INPUT_SHA256"], "Reference archive checksum mismatch"
            print(json.dumps(repair(args.cache, args.source, archive), indent=2))
