"""Stage only a pinned OpenClacky gem, its runtime dependencies and Ruby stdlib.
Run on macOS after `gem install openclacky -v 1.5.3`. No ~/.clacky data is read.
"""
import json
import os
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".desktop-vendor" / "openclacky"
VERSION = "1.5.3"


def stage():
    ruby = os.getenv("STUDIO_BUILD_RUBY") or shutil.which("ruby")
    if not ruby:
        raise RuntimeError("Ruby runtime required to build")
    query = r'''require "json"; require "rbconfig"; require "rubygems"
seen={}; visit=lambda{|s| return if seen[s.full_name];seen[s.full_name]=s;s.runtime_dependencies.each{|d|visit.call(d.to_spec)}}
visit.call(Gem::Specification.find_by_name("openclacky", "= 1.5.3"))
puts JSON.generate({rubylib: RbConfig::CONFIG["rubylibdir"], archlib: RbConfig::CONFIG["archdir"], gems:seen.values.map{|s|{path:s.full_gem_path,spec:s.loaded_from,name:s.full_name,licenses:s.licenses}}})'''
    info = json.loads(subprocess.check_output([ruby, "-e", query], text=True))
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / "bin").mkdir(parents=True)
    shutil.copy2(ruby, DEST / "bin/ruby")
    shutil.copytree(info["rubylib"], DEST / "ruby-lib", symlinks=False)
    arch = Path(info["archlib"])
    shutil.copytree(arch, DEST / "ruby-lib" / arch.name, dirs_exist_ok=True, symlinks=False)
    for gem in info["gems"]:
        shutil.copytree(gem["path"], DEST / "gems/gems" / gem["name"], symlinks=False)
        target = DEST / "gems/specifications" / Path(gem["spec"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gem["spec"], target)
    # Ruby is copied as data, so relocate every non-system Mach-O dependency.
    native = DEST / "native"
    native.mkdir()
    queue = [p for p in DEST.rglob("*") if p.is_file() and (p.suffix in (".bundle", ".dylib") or p == DEST / "bin/ruby")]
    visited = set()
    while queue:
        binary = queue.pop()
        if binary in visited:
            continue
        visited.add(binary)
        result = subprocess.run(["otool", "-L", str(binary)], text=True, capture_output=True)
        if result.returncode:
            continue
        os.chmod(binary, 0o755)
        for line in result.stdout.splitlines()[1:]:
            dep = line.strip().split(" (", 1)[0]
            if not dep.startswith("/") or dep.startswith(("/usr/lib/", "/System/")):
                continue
            source = Path(dep)
            if not source.is_file():
                raise RuntimeError(f"Missing Ruby dependency {source.name}")
            target = native / source.name
            if not target.exists():
                shutil.copy2(source, target)
                queue.append(target)
            relative = os.path.relpath(target, binary.parent)
            subprocess.run(["install_name_tool", "-change", dep, "@loader_path/" + relative, str(binary)], check=True, capture_output=True)
        subprocess.run(["codesign", "--force", "--sign", "-", str(binary)], check=True, capture_output=True)
    manifest = {"project":"https://github.com/clacky-ai/openclacky", "version":VERSION, "gems":info["gems"]}
    # Do not retain build-machine absolute paths in the distribution manifest.
    for gem in manifest["gems"]:
        gem.pop("path"); gem.pop("spec")
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(DEST)


if __name__ == "__main__":
    stage()
