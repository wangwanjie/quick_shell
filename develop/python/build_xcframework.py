#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


HEADER_EXTENSIONS = {".h", ".hh", ".hpp", ".hxx"}
INCLUDE_PATTERN = re.compile(r'^(\s*#\s*(?:include|import)\s*)([<"])([^>"]+)([>"])(.*)$')
MODULE_DECL_PATTERN = re.compile(r'^(\s*(?:framework\s+module|module)\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*(?:\[[^\]]+\]\s*)?\{.*)$')
MODULEMAP_HEADER_PATTERN = re.compile(
    r'^(\s*(?:umbrella header|header|private header|textual header|exclude header)\s+")([^"]+)(".*)$'
)
SYSTEM_HEADERS = {
    "assert.h",
    "ctype.h",
    "float.h",
    "limits.h",
    "math.h",
    "pthread.h",
    "stdarg.h",
    "stdbool.h",
    "stddef.h",
    "stdint.h",
    "stdio.h",
    "stdlib.h",
    "string.h",
    "sys/types.h",
    "time.h",
    "unistd.h",
}
CPP_STANDARD_HEADERS = {
    "algorithm",
    "array",
    "deque",
    "functional",
    "list",
    "map",
    "memory",
    "set",
    "string",
    "unordered_map",
    "utility",
    "vector",
}


@dataclass(frozen=True)
class InputArtifact:
    source: Path
    kind: str
    binary: Path
    framework_name: str | None = None


@dataclass(frozen=True)
class HeaderCatalog:
    relative_paths: set[PurePosixPath]
    basename_map: dict[str, list[PurePosixPath]]
    lower_relative_map: dict[str, list[PurePosixPath]]
    lower_basename_map: dict[str, list[PurePosixPath]]

    @classmethod
    def build(cls, headers_dir: Path) -> HeaderCatalog:
        relative_paths: set[PurePosixPath] = set()
        basename_map: dict[str, list[PurePosixPath]] = {}
        lower_relative_map: dict[str, list[PurePosixPath]] = {}
        lower_basename_map: dict[str, list[PurePosixPath]] = {}
        for path in headers_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in HEADER_EXTENSIONS:
                continue
            if path.name.startswith("."):
                continue
            relative = PurePosixPath(path.relative_to(headers_dir).as_posix())
            relative_paths.add(relative)
            basename_map.setdefault(relative.name, []).append(relative)
            lower_relative_map.setdefault(relative.as_posix().lower(), []).append(relative)
            lower_basename_map.setdefault(relative.name.lower(), []).append(relative)
        return cls(
            relative_paths=relative_paths,
            basename_map=basename_map,
            lower_relative_map=lower_relative_map,
            lower_basename_map=lower_basename_map,
        )


@dataclass(frozen=True)
class BuildTask:
    name: str
    inputs: list[Path]
    headers_dir: Path | None
    module_name: str | None
    framework_name: str | None
    umbrella_header: str | None
    output: Path
    log_file: Path | None
    bundle_id_prefix: str
    modulemap: Path | None
    modulemap_mode: str
    external_module_imports: dict[str, str]
    umbrella_imports: list[str] | None


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def remove_if_exists(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def framework_binary_path(framework_dir: Path) -> Path:
    plist_path = framework_dir / "Info.plist"
    executable_name = None
    if plist_path.exists():
        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
        executable_name = info.get("CFBundleExecutable")
    if executable_name:
        candidate = framework_dir / executable_name
        if candidate.exists():
            return candidate

    default_candidate = framework_dir / framework_dir.stem
    if default_candidate.exists():
        return default_candidate

    files = [path for path in framework_dir.iterdir() if path.is_file() and path.name != "Info.plist"]
    if len(files) == 1:
        return files[0]
    raise FileNotFoundError(f"unable to locate framework binary in {framework_dir}")


def detect_binary_kind(binary_path: Path, *, framework: bool) -> str:
    file_output = capture(["file", str(binary_path)])
    if "current ar archive" in file_output or "static library" in file_output:
        return "static-framework" if framework else "static-library"
    if "dynamically linked shared library" in file_output:
        return "dynamic-framework" if framework else "dynamic-library"
    raise ValueError(f"unsupported binary type: {binary_path}")


def detect_input(path: Path) -> InputArtifact:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"input not found: {resolved}")

    if resolved.is_dir() and resolved.suffix == ".framework":
        framework_name = resolved.stem
        binary = framework_binary_path(resolved)
        return InputArtifact(
            source=resolved,
            kind=detect_binary_kind(binary, framework=True),
            binary=binary,
            framework_name=framework_name,
        )

    suffix = resolved.suffix.lower()
    if suffix == ".a":
        return InputArtifact(source=resolved, kind="static-library", binary=resolved)
    if suffix == ".dylib":
        return InputArtifact(source=resolved, kind="dynamic-library", binary=resolved)

    file_output = capture(["file", str(resolved)])
    if "current ar archive" in file_output or "static library" in file_output:
        return InputArtifact(source=resolved, kind="static-library", binary=resolved)
    if "dynamically linked shared library" in file_output:
        return InputArtifact(source=resolved, kind="dynamic-library", binary=resolved)
    raise ValueError(f"unsupported input: {resolved}")


def sanitize_module_name(name: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not sanitized:
        return "SDK"
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


def derive_module_name(task: BuildTask, inputs: list[InputArtifact]) -> str:
    if task.module_name:
        if sanitize_module_name(task.module_name) != task.module_name:
            raise ValueError(f"invalid module name: {task.module_name}")
        return task.module_name
    first = inputs[0]
    if first.source.suffix == ".framework":
        return sanitize_module_name(first.source.stem)
    name = first.source.stem
    return sanitize_module_name(name[3:] if name.startswith("lib") else name)


def derive_framework_name(task: BuildTask, module_name: str) -> str:
    return task.framework_name or module_name


def derive_headers_source(task: BuildTask, inputs: list[InputArtifact]) -> Path:
    if task.headers_dir:
        headers_dir = task.headers_dir.resolve()
        if not headers_dir.exists():
            raise FileNotFoundError(f"headers dir not found: {headers_dir}")
        return headers_dir

    first_framework = next((item for item in inputs if item.source.suffix == ".framework"), None)
    if first_framework is None:
        raise ValueError("`--headers-dir` is required when any input is not a framework")

    headers_dir = first_framework.source / "Headers"
    if not headers_dir.exists():
        raise FileNotFoundError(f"headers dir not found in framework: {headers_dir}")
    return headers_dir


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"unable to decode {path}")


def resolve_header_reference(
    include_path: str,
    *,
    current_header: PurePosixPath,
    catalog: HeaderCatalog,
    module_name: str,
) -> PurePosixPath | None:
    candidate = include_path.strip()
    if not candidate:
        return None

    candidates: list[PurePosixPath] = []
    if candidate.startswith(f"{module_name}/"):
        candidates.append(PurePosixPath(candidate[len(module_name) + 1 :]))
    if candidate.startswith("Headers/"):
        candidates.append(PurePosixPath(candidate[len("Headers/") :]))
    candidates.append(PurePosixPath(candidate))

    scoped = PurePosixPath(current_header.parent.as_posix(), candidate)
    scoped_parts: list[str] = []
    for part in scoped.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if scoped_parts:
                scoped_parts.pop()
            continue
        scoped_parts.append(part)
    if scoped_parts:
        candidates.append(PurePosixPath(*scoped_parts))

    for item in candidates:
        if item in catalog.relative_paths:
            return item
        lower_matches = catalog.lower_relative_map.get(item.as_posix().lower(), [])
        if len(lower_matches) == 1:
            return lower_matches[0]

    matches = catalog.basename_map.get(PurePosixPath(candidate).name, [])
    if len(matches) == 1:
        return matches[0]
    lower_matches = catalog.lower_basename_map.get(PurePosixPath(candidate).name.lower(), [])
    if len(lower_matches) == 1:
        return lower_matches[0]
    return None


def resolve_modulemap_header_reference(
    header_ref: str,
    *,
    catalog: HeaderCatalog,
    module_name: str,
) -> PurePosixPath | None:
    candidate = header_ref.strip()
    if not candidate:
        return None

    candidates: list[PurePosixPath] = []
    if candidate.startswith(f"{module_name}/"):
        candidates.append(PurePosixPath(candidate[len(module_name) + 1 :]))
    if candidate.startswith("Headers/"):
        candidates.append(PurePosixPath(candidate[len("Headers/") :]))
    candidates.append(PurePosixPath(candidate))

    for item in candidates:
        if item in catalog.relative_paths:
            return item
        lower_matches = catalog.lower_relative_map.get(item.as_posix().lower(), [])
        if len(lower_matches) == 1:
            return lower_matches[0]

    matches = catalog.basename_map.get(PurePosixPath(candidate).name, [])
    if len(matches) == 1:
        return matches[0]
    lower_matches = catalog.lower_basename_map.get(PurePosixPath(candidate).name.lower(), [])
    if len(lower_matches) == 1:
        return lower_matches[0]
    return None


def internal_include_path(target: PurePosixPath, current_header: PurePosixPath) -> str:
    target_parts = list(target.parent.parts)
    current_parts = list(current_header.parent.parts)

    common_length = 0
    for current_part, target_part in zip(current_parts, target_parts):
        if current_part != target_part:
            break
        common_length += 1

    upward = [".."] * (len(current_parts) - common_length)
    downward = target_parts[common_length:]
    relative_parts = upward + downward + [target.name]

    if not relative_parts:
        return target.name
    if len(relative_parts) == 1:
        return relative_parts[0]
    return "/".join(relative_parts)


def resolve_external_module_import(
    header_ref: str,
    external_module_imports: dict[str, str],
) -> tuple[str, str] | None:
    candidate = header_ref.strip()
    for prefix, module_name in external_module_imports.items():
        if candidate == prefix or candidate.startswith(f"{prefix}/"):
            return module_name, candidate
        short_name = prefix.split("/")[-1]
        if short_name.startswith("lib"):
            alias = f"{short_name[3:]}.h"
            if candidate == alias:
                return module_name, f"{prefix}/{candidate}"
    return None


def is_standard_header(ref: str) -> bool:
    candidate = ref.strip()
    return candidate in SYSTEM_HEADERS or candidate in CPP_STANDARD_HEADERS


def copy_headers_tree(source_headers_dir: Path, prepared_headers_dir: Path) -> None:
    if prepared_headers_dir.exists():
        shutil.rmtree(prepared_headers_dir)
    prepared_headers_dir.mkdir(parents=True)
    for path in sorted(source_headers_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in HEADER_EXTENSIONS:
            continue
        relative_path = path.relative_to(source_headers_dir)
        destination = prepared_headers_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def rewrite_header_imports(
    prepared_headers_dir: Path,
    module_name: str,
    external_module_imports: dict[str, str],
    log_entries: list[dict[str, object]],
    warnings: list[str],
) -> None:
    catalog = HeaderCatalog.build(prepared_headers_dir)
    for path in sorted(prepared_headers_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in HEADER_EXTENSIONS:
            continue
        relative_path = PurePosixPath(path.relative_to(prepared_headers_dir).as_posix())
        original_text, encoding = read_text_with_fallback(path)
        lines = original_text.splitlines(keepends=True)
        updated_lines: list[str] = []
        changed = False

        for index, line in enumerate(lines, start=1):
            match = INCLUDE_PATTERN.match(line.rstrip("\n"))
            if not match:
                updated_lines.append(line)
                continue

            prefix, opener, header_ref, _, suffix = match.groups()
            external_import = resolve_external_module_import(header_ref, external_module_imports)
            if external_import is not None:
                external_module_name, external_header_path = external_import
                new_line = f'#import <{external_module_name}/{external_header_path}>{suffix}'
                newline = "\n" if line.endswith("\n") else ""
                updated = new_line + newline
                updated_lines.append(updated)
                if updated != line:
                    changed = True
                    log_entries.append(
                        {
                            "type": "header",
                            "file": relative_path.as_posix(),
                            "line": index,
                            "old": line.rstrip("\n"),
                            "new": new_line,
                        }
                    )
                continue

            if opener == '"' and is_standard_header(header_ref):
                new_line = f"{prefix}<{header_ref}>{suffix}"
                newline = "\n" if line.endswith("\n") else ""
                updated = new_line + newline
                updated_lines.append(updated)
                if updated != line:
                    changed = True
                    log_entries.append(
                        {
                            "type": "header",
                            "file": relative_path.as_posix(),
                            "line": index,
                            "old": line.rstrip("\n"),
                            "new": new_line,
                        }
                    )
                continue

            resolved = resolve_header_reference(
                header_ref,
                current_header=relative_path,
                catalog=catalog,
                module_name=module_name,
            )

            if resolved is None:
                updated_lines.append(line)
                if opener == "<" and "/" in header_ref and not header_ref.startswith(f"{module_name}/"):
                    continue
                if opener == "<" and "/" not in header_ref and header_ref not in catalog.basename_map:
                    continue
                warnings.append(f"unresolved include in {relative_path}:{index}: {header_ref}")
                continue

            normalized_ref = internal_include_path(resolved, relative_path)
            new_line = f'{prefix}"{normalized_ref}"{suffix}'
            newline = "\n" if line.endswith("\n") else ""
            updated = new_line + newline
            updated_lines.append(updated)

            if updated != line:
                changed = True
                log_entries.append(
                    {
                        "type": "header",
                        "file": relative_path.as_posix(),
                        "line": index,
                        "old": line.rstrip("\n"),
                        "new": new_line,
                    }
                )

        if changed:
            path.write_text("".join(updated_lines), encoding=encoding)


def generate_umbrella_header(
    prepared_headers_dir: Path,
    umbrella_header_name: str,
    module_name: str,
    umbrella_imports: list[str] | None,
) -> None:
    imports: list[str] = []
    if umbrella_imports is not None:
        for relative_path in umbrella_imports:
            imports.append(f"#import <{module_name}/{relative_path}>\n")
    else:
        for path in sorted(prepared_headers_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in HEADER_EXTENSIONS:
                continue
            relative_path = path.relative_to(prepared_headers_dir).as_posix()
            if path.name == umbrella_header_name:
                continue
            imports.append(f"#import <{module_name}/{relative_path}>\n")
    umbrella_path = prepared_headers_dir / umbrella_header_name
    umbrella_path.write_text("".join(imports), encoding="utf-8")


def copy_modulemap_files(source_paths: list[Path], prepared_modules_dir: Path) -> list[Path]:
    prepared_modules_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source_path in source_paths:
        destination = prepared_modules_dir / source_path.name
        shutil.copy2(source_path, destination)
        copied.append(destination)
    return copied


def rewrite_modulemap_file(
    modulemap_path: Path,
    prepared_headers_dir: Path,
    module_name: str,
    umbrella_header_name: str,
    log_entries: list[dict[str, object]],
    warnings: list[str],
) -> None:
    catalog = HeaderCatalog.build(prepared_headers_dir)
    original_text, encoding = read_text_with_fallback(modulemap_path)
    lines = original_text.splitlines(keepends=True)
    updated_lines: list[str] = []
    changed = False
    saw_public_header_ref = False
    first_decl_index: int | None = None

    for index, line in enumerate(lines, start=1):
        raw = line.rstrip("\n")
        updated_raw = raw

        module_match = MODULE_DECL_PATTERN.match(updated_raw)
        if module_match and first_decl_index is None:
            prefix, old_name, suffix = module_match.groups()
            first_decl_index = len(updated_lines)
            if old_name != module_name:
                updated_raw = f"{prefix}{module_name}{suffix}"
                changed = True
                log_entries.append(
                    {
                        "type": "modulemap",
                        "file": modulemap_path.name,
                        "line": index,
                        "old": raw,
                        "new": updated_raw,
                    }
                )

        header_match = MODULEMAP_HEADER_PATTERN.match(updated_raw)
        if header_match:
            prefix, header_ref, suffix = header_match.groups()
            resolved = resolve_modulemap_header_reference(
                header_ref,
                catalog=catalog,
                module_name=module_name,
            )
            new_ref = header_ref
            if resolved is not None:
                new_ref = resolved.as_posix()
                saw_public_header_ref = True
            elif prefix.strip().startswith("umbrella header"):
                new_ref = umbrella_header_name
                saw_public_header_ref = True
                warnings.append(f"rewrote unresolved umbrella header in {modulemap_path.name}:{index} to {umbrella_header_name}")
            else:
                warnings.append(f"unresolved modulemap header in {modulemap_path.name}:{index}: {header_ref}")

            if new_ref != header_ref:
                updated_raw = f'{prefix}{new_ref}{suffix}'
                changed = True
                log_entries.append(
                    {
                        "type": "modulemap",
                        "file": modulemap_path.name,
                        "line": index,
                        "old": raw,
                        "new": updated_raw,
                    }
                )

        newline = "\n" if line.endswith("\n") else ""
        updated_lines.append(updated_raw + newline)

    if not saw_public_header_ref:
        insertion = f'  umbrella header "{umbrella_header_name}"\n'
        insert_at = first_decl_index + 1 if first_decl_index is not None else 0
        updated_lines.insert(insert_at, insertion)
        changed = True
        log_entries.append(
            {
                "type": "modulemap",
                "file": modulemap_path.name,
                "line": insert_at + 1,
                "old": "",
                "new": insertion.rstrip("\n"),
            }
        )

    if changed:
        modulemap_path.write_text("".join(updated_lines), encoding=encoding)


def generate_modulemap(prepared_modules_dir: Path, module_name: str, umbrella_header_name: str) -> None:
    prepared_modules_dir.mkdir(parents=True, exist_ok=True)
    modulemap_path = prepared_modules_dir / "module.modulemap"
    modulemap_path.write_text(
        (
            f"framework module {module_name} {{\n"
            f'  umbrella header "{umbrella_header_name}"\n'
            "  export *\n"
            "  module * { export * }\n"
            "}\n"
        ),
        encoding="utf-8",
    )


def discover_modulemap_files(task: BuildTask, headers_source: Path, inputs: list[InputArtifact]) -> list[Path]:
    candidate_files: list[Path] = []

    if task.modulemap:
        modulemap_path = task.modulemap.resolve()
        if not modulemap_path.exists():
            raise FileNotFoundError(f"modulemap path not found: {modulemap_path}")
        if modulemap_path.is_dir():
            candidate_files.extend(sorted(modulemap_path.glob("*.modulemap")))
        else:
            candidate_files.append(modulemap_path)
        return candidate_files

    candidate_dirs: list[Path] = []
    first_framework = next((item for item in inputs if item.source.suffix == ".framework"), None)
    if first_framework:
        candidate_dirs.append(first_framework.source / "Modules")
    candidate_dirs.append(headers_source / "Modules")
    candidate_dirs.append(headers_source.parent / "Modules")

    seen: set[Path] = set()
    for directory in candidate_dirs:
        resolved = directory.resolve()
        if resolved in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(resolved)
        files = sorted(resolved.glob("*.modulemap"))
        if files:
            candidate_files.extend(files)
            break

    return candidate_files


def prepare_modulemaps(
    source_modulemap_files: list[Path],
    prepared_headers_dir: Path,
    prepared_modules_dir: Path,
    module_name: str,
    umbrella_header_name: str,
    mode: str,
    log_entries: list[dict[str, object]],
    warnings: list[str],
) -> None:
    remove_if_exists(prepared_modules_dir)

    if mode == "preserve" and source_modulemap_files:
        copied = copy_modulemap_files(source_modulemap_files, prepared_modules_dir)
        for modulemap_path in copied:
            rewrite_modulemap_file(
                modulemap_path,
                prepared_headers_dir,
                module_name,
                umbrella_header_name,
                log_entries,
                warnings,
            )
        if not (prepared_modules_dir / "module.modulemap").exists():
            generate_modulemap(prepared_modules_dir, module_name, umbrella_header_name)
        return

    generate_modulemap(prepared_modules_dir, module_name, umbrella_header_name)


def prepare_headers_and_modules(
    source_headers_dir: Path,
    destination_root: Path,
    module_name: str,
    umbrella_header_name: str,
    source_modulemap_files: list[Path],
    modulemap_mode: str,
    external_module_imports: dict[str, str],
    umbrella_imports: list[str] | None,
    log_file: Path,
) -> tuple[Path, Path]:
    prepared_headers_dir = destination_root / "Headers"
    prepared_modules_dir = destination_root / "Modules"
    changes: list[dict[str, object]] = []
    warnings: list[str] = []

    copy_headers_tree(source_headers_dir, prepared_headers_dir)
    rewrite_header_imports(prepared_headers_dir, module_name, external_module_imports, changes, warnings)
    generate_umbrella_header(prepared_headers_dir, umbrella_header_name, module_name, umbrella_imports)
    prepare_modulemaps(
        source_modulemap_files,
        prepared_headers_dir,
        prepared_modules_dir,
        module_name,
        umbrella_header_name,
        modulemap_mode,
        changes,
        warnings,
    )

    log_payload = {
        "module_name": module_name,
        "source_headers_dir": str(source_headers_dir),
        "prepared_headers_dir": str(prepared_headers_dir),
        "modulemap_mode": modulemap_mode,
        "source_modulemap_files": [str(path) for path in source_modulemap_files],
        "external_module_imports": external_module_imports,
        "umbrella_imports": umbrella_imports,
        "changes": changes,
        "warnings": warnings,
    }
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(json.dumps(log_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return prepared_headers_dir, prepared_modules_dir


def write_framework_plist(plist_path: Path, framework_name: str, bundle_id: str, source_plist: Path | None) -> None:
    info: dict[str, object] = {}
    if source_plist and source_plist.exists():
        with source_plist.open("rb") as handle:
            info = plistlib.load(handle)

    info["CFBundlePackageType"] = "FMWK"
    info["CFBundleExecutable"] = framework_name
    info["CFBundleName"] = framework_name
    info["CFBundleIdentifier"] = bundle_id
    info.setdefault("CFBundleVersion", "1")
    info.setdefault("CFBundleShortVersionString", "1.0")

    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle, sort_keys=True)


def update_dynamic_install_name(binary_path: Path, framework_name: str) -> None:
    install_name = f"@rpath/{framework_name}.framework/{framework_name}"
    run(["install_name_tool", "-id", install_name, str(binary_path)])


def copy_prepared_headers(prepared_headers_dir: Path, prepared_modules_dir: Path, framework_dir: Path) -> None:
    headers_dir = framework_dir / "Headers"
    modules_dir = framework_dir / "Modules"
    remove_if_exists(headers_dir)
    remove_if_exists(modules_dir)
    shutil.copytree(prepared_headers_dir, headers_dir)
    shutil.copytree(prepared_modules_dir, modules_dir)


def normalize_framework_slice(
    artifact: InputArtifact,
    framework_dir: Path,
    framework_name: str,
    bundle_id: str,
    prepared_headers_dir: Path,
    prepared_modules_dir: Path,
) -> Path:
    shutil.copytree(artifact.source, framework_dir, symlinks=True)
    remove_if_exists(framework_dir / "_CodeSignature")

    source_binary = framework_binary_path(framework_dir)
    target_binary = framework_dir / framework_name
    if source_binary != target_binary:
        if target_binary.exists():
            target_binary.unlink()
        source_binary.rename(target_binary)

    copy_prepared_headers(prepared_headers_dir, prepared_modules_dir, framework_dir)
    write_framework_plist(framework_dir / "Info.plist", framework_name, bundle_id, artifact.source / "Info.plist")

    if artifact.kind == "dynamic-framework":
        update_dynamic_install_name(target_binary, framework_name)
    return framework_dir


def wrap_binary_as_framework(
    artifact: InputArtifact,
    framework_dir: Path,
    framework_name: str,
    bundle_id: str,
    prepared_headers_dir: Path,
    prepared_modules_dir: Path,
) -> Path:
    framework_dir.mkdir(parents=True, exist_ok=True)
    target_binary = framework_dir / framework_name
    shutil.copy2(artifact.binary, target_binary)
    copy_prepared_headers(prepared_headers_dir, prepared_modules_dir, framework_dir)
    write_framework_plist(framework_dir / "Info.plist", framework_name, bundle_id, None)

    if artifact.kind == "dynamic-library":
        update_dynamic_install_name(target_binary, framework_name)
    return framework_dir


def normalize_slice(
    artifact: InputArtifact,
    temp_root: Path,
    index: int,
    framework_name: str,
    bundle_id_prefix: str,
    prepared_headers_dir: Path,
    prepared_modules_dir: Path,
) -> Path:
    framework_dir = temp_root / f"slice_{index}" / f"{framework_name}.framework"
    bundle_id = f"{bundle_id_prefix}.{framework_name}".lower()

    if artifact.source.suffix == ".framework":
        return normalize_framework_slice(
            artifact,
            framework_dir,
            framework_name,
            bundle_id,
            prepared_headers_dir,
            prepared_modules_dir,
        )

    return wrap_binary_as_framework(
        artifact,
        framework_dir,
        framework_name,
        bundle_id,
        prepared_headers_dir,
        prepared_modules_dir,
    )


def build_xcframework(
    inputs: list[InputArtifact],
    output_path: Path,
    framework_name: str,
    prepared_headers_dir: Path,
    prepared_modules_dir: Path,
    bundle_id_prefix: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    remove_if_exists(output_path)

    with tempfile.TemporaryDirectory(prefix="xcframework_wrap_") as temp_dir:
        temp_root = Path(temp_dir)
        normalized_frameworks = [
            normalize_slice(
                artifact,
                temp_root,
                index,
                framework_name,
                bundle_id_prefix,
                prepared_headers_dir,
                prepared_modules_dir,
            )
            for index, artifact in enumerate(inputs, start=1)
        ]

        command = ["xcodebuild", "-create-xcframework"]
        for framework in normalized_frameworks:
            command.extend(["-framework", str(framework)])
        command.extend(["-output", str(output_path)])
        run(command)


def execute_task(task: BuildTask) -> tuple[Path, Path]:
    inputs = [detect_input(path) for path in task.inputs]
    module_name = derive_module_name(task, inputs)
    framework_name = derive_framework_name(task, module_name)
    umbrella_header_name = task.umbrella_header or f"{module_name}.h"
    headers_source = derive_headers_source(task, inputs)
    source_modulemap_files = discover_modulemap_files(task, headers_source, inputs)

    output_path = task.output.resolve()
    log_file = (task.log_file or output_path.with_name(f"{output_path.stem}.header-rewrite-log.json")).resolve()

    with tempfile.TemporaryDirectory(prefix="xcframework_headers_") as temp_dir:
        temp_root = Path(temp_dir)
        prepared_headers_dir, prepared_modules_dir = prepare_headers_and_modules(
            headers_source,
            temp_root,
            module_name,
            umbrella_header_name,
            source_modulemap_files,
            task.modulemap_mode,
            task.external_module_imports,
            task.umbrella_imports,
            log_file,
        )
        build_xcframework(
            inputs,
            output_path,
            framework_name,
            prepared_headers_dir,
            prepared_modules_dir,
            task.bundle_id_prefix,
        )

    return output_path, log_file


def load_config_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML is required to read YAML config files")
        return yaml.safe_load(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if yaml is None:
            raise RuntimeError("config is not valid JSON and PyYAML is unavailable for YAML parsing")
        return yaml.safe_load(text)


def resolve_path(value: str | None, base_dir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def ensure_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(f"`{field_name}` must be a string or string list")


def normalize_external_module_imports(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        normalized: dict[str, str] = {}
        for key, module_name in value.items():
            if not isinstance(key, str) or not isinstance(module_name, str):
                raise ValueError("`external_module_imports` keys and values must be strings")
            normalized[key.strip()] = module_name.strip()
        return normalized
    if isinstance(value, list):
        normalized = {}
        for item in value:
            if not isinstance(item, str) or ":" not in item:
                raise ValueError("list-form `external_module_imports` items must be `prefix:module` strings")
            prefix, module_name = item.split(":", 1)
            normalized[prefix.strip()] = module_name.strip()
        return normalized
    raise ValueError("`external_module_imports` must be an object or a list of `prefix:module` strings")


def normalize_optional_string_list(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    return ensure_string_list(value, field_name)


def task_from_mapping(raw_task: dict[str, Any], base_dir: Path, index: int) -> BuildTask:
    normalized = dict(raw_task)
    if "input" in normalized and "inputs" not in normalized:
        normalized["inputs"] = normalized["input"]

    inputs = [resolve_path(value, base_dir) for value in ensure_string_list(normalized.get("inputs"), "inputs")]
    if not inputs:
        raise ValueError("each task must provide at least one input")

    output = resolve_path(normalized.get("output"), base_dir)
    if output is None:
        raise ValueError("each task must provide `output`")

    modulemap_mode = normalized.get("modulemap_mode", "preserve")
    if modulemap_mode not in {"preserve", "generate"}:
        raise ValueError("`modulemap_mode` must be `preserve` or `generate`")

    name = normalized.get("name")
    if not name:
        name = output.stem

    return BuildTask(
        name=name,
        inputs=[path for path in inputs if path is not None],
        headers_dir=resolve_path(normalized.get("headers_dir"), base_dir),
        module_name=normalized.get("module_name"),
        framework_name=normalized.get("framework_name"),
        umbrella_header=normalized.get("umbrella_header"),
        output=output,
        log_file=resolve_path(normalized.get("log_file"), base_dir),
        bundle_id_prefix=normalized.get("bundle_id_prefix", "com.codex.generated"),
        modulemap=resolve_path(normalized.get("modulemap"), base_dir),
        modulemap_mode=modulemap_mode,
        external_module_imports=normalize_external_module_imports(normalized.get("external_module_imports")),
        umbrella_imports=normalize_optional_string_list(
            normalized["umbrella_imports"],
            "umbrella_imports",
        ) if "umbrella_imports" in normalized else None,
    )


def load_tasks_from_config(config_path: Path, selected_task_name: str | None) -> list[BuildTask]:
    document = load_config_document(config_path.resolve())
    if document is None:
        raise ValueError("config file is empty")

    if isinstance(document, list):
        defaults: dict[str, Any] = {}
        raw_tasks = document
    elif isinstance(document, dict):
        defaults = document.get("defaults", {})
        raw_tasks = document.get("tasks")
        if raw_tasks is None:
            raw_tasks = [document]
            defaults = {}
    else:
        raise ValueError("config root must be an object or array")

    if not isinstance(raw_tasks, list):
        raise ValueError("`tasks` must be a list")
    if defaults and not isinstance(defaults, dict):
        raise ValueError("`defaults` must be an object")

    tasks: list[BuildTask] = []
    for index, raw_task in enumerate(raw_tasks, start=1):
        if not isinstance(raw_task, dict):
            raise ValueError(f"task #{index} must be an object")
        merged = dict(defaults)
        merged.update(raw_task)
        tasks.append(task_from_mapping(merged, config_path.parent, index))

    if selected_task_name:
        tasks = [task for task in tasks if task.name == selected_task_name]
        if not tasks:
            raise ValueError(f"task not found in config: {selected_task_name}")

    return tasks


def task_from_args(args: argparse.Namespace) -> BuildTask:
    if not args.inputs:
        raise ValueError("single-task mode requires at least one `--input`")
    if not args.output:
        raise ValueError("single-task mode requires `--output`")
    if args.modulemap_mode not in {"preserve", "generate"}:
        raise ValueError("`--modulemap-mode` must be `preserve` or `generate`")

    return BuildTask(
        name=args.task_name or Path(args.output).stem,
        inputs=[Path(item).resolve() for item in args.inputs],
        headers_dir=args.headers_dir.resolve() if args.headers_dir else None,
        module_name=args.module_name,
        framework_name=args.framework_name,
        umbrella_header=args.umbrella_header,
        output=args.output.resolve(),
        log_file=args.log_file.resolve() if args.log_file else None,
        bundle_id_prefix=args.bundle_id_prefix,
        modulemap=args.modulemap.resolve() if args.modulemap else None,
        modulemap_mode=args.modulemap_mode,
        external_module_imports=normalize_external_module_imports(args.external_module_imports),
        umbrella_imports=normalize_optional_string_list(args.umbrella_imports, "umbrella_imports"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wrap static or dynamic libraries/frameworks and build XCFrameworks through `xcodebuild -create-xcframework -framework`.",
        epilog=(
            "Single task example:\n"
            "  python3 build_xcframework.py \\\n"
            "    --input Demo/iphoneos/lib/libDemo.a \\\n"
            "    --input Demo/iphonesimulator/lib/libDemo.a \\\n"
            "    --input Demo/maccatalyst/lib/libDemo.a \\\n"
            "    --headers-dir Demo/include \\\n"
            "    --module-name DemoSDK \\\n"
            "    --output output/DemoSDK.xcframework\n\n"
            "Batch config example:\n"
            "  python3 build_xcframework.py --config build_tasks.yaml\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=None, help="Batch config file in JSON or YAML.")
    parser.add_argument("--task-name", default=None, help="Optional task name. In config mode it filters to one task.")
    parser.add_argument("--input", dest="inputs", action="append", default=None, help="Input slice path. Supports `.a`, `.dylib`, or `.framework`. Repeat for each slice.")
    parser.add_argument("--headers-dir", type=Path, default=None, help="Public headers root. Required for `.a`/`.dylib` input. If omitted for pure framework input, the first framework's Headers directory is used.")
    parser.add_argument("--module-name", default=None, help="Module name used by imports and modulemap. Defaults to the first input name with a leading `lib` stripped.")
    parser.add_argument("--framework-name", default=None, help="Unified framework binary name used in every slice. Defaults to `module-name`.")
    parser.add_argument("--umbrella-header", default=None, help="Generated umbrella header file name. Defaults to `<module-name>.h`.")
    parser.add_argument("--modulemap", type=Path, default=None, help="Optional modulemap file or Modules directory. In preserve mode it is used as the source to copy and repair.")
    parser.add_argument("--modulemap-mode", default="preserve", help="`preserve` keeps and repairs existing modulemap files. `generate` always writes a new default modulemap.")
    parser.add_argument("--external-module-import", dest="external_module_imports", action="append", default=None, help="Rewrite matching includes to external module imports in `prefix:module` form. Example: `libavutil:ffmpeg`.")
    parser.add_argument("--umbrella-import", dest="umbrella_imports", action="append", default=None, help="Explicit header path to include from the generated umbrella header. Repeat as needed.")
    parser.add_argument("--output", type=Path, default=None, help="Output XCFramework path, for example `output/DemoSDK.xcframework`.")
    parser.add_argument("--log-file", type=Path, default=None, help="Header/modulemap rewrite log path. Defaults to a JSON file beside the output.")
    parser.add_argument("--bundle-id-prefix", default="com.codex.generated", help="Bundle identifier prefix used when normalizing framework slices.")
    return parser.parse_args()


def validate_environment() -> None:
    required_tools = ["xcodebuild", "file", "install_name_tool"]
    for tool in required_tools:
        if shutil.which(tool) is None:
            raise RuntimeError(f"required tool not found: {tool}")


def main() -> int:
    try:
        args = parse_args()
        validate_environment()

        if args.config:
            tasks = load_tasks_from_config(args.config, args.task_name)
        else:
            tasks = [task_from_args(args)]

        for task in tasks:
            output_path, log_file = execute_task(task)
            print(f"[{task.name}] {output_path}")
            print(f"[{task.name}] {log_file}")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"command failed: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode or 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
