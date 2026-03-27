#!/usr/bin/env python3
"""
xcframework_import_fixer.py

将扫描目录内源文件中形如:
    #import "SomeHeader.h"
的导入，替换为:
    #import <LibName/relative/path/SomeHeader.h>
（前提是该头文件存在于指定的 xcframework 中）

用法:
    python xcframework_import_fixer.py \
        --xcframework_path /path/to/upnpx.xcframework \
        --scan_dir /path/to/your/project \
        --action_type list   # 或 fix
"""

import argparse
import os
import re
import sys
from pathlib import Path


# ──────────────────────────────────────────────
# 1. 从 xcframework 中提取头文件信息
# ──────────────────────────────────────────────

def find_headers_slice(xcframework_path: Path):
    """
    在 xcframework 中找到第一个可用的架构切片的 Headers 目录。
    支持两种目录结构：
      - ios-arm64/Headers/               (flat)
      - ios-arm64/SomeLib.framework/Headers/  (framework bundle)
    优先选取 ios-arm64。
    返回 (headers_dir: Path, lib_name: str | None)
    """
    preferred = ["ios-arm64", "ios-arm64_armv7", "ios-arm64-simulator"]

    candidates = []  # list of (slice_name, headers_dir, framework_name_or_None)

    for slice_dir in xcframework_path.iterdir():
        if not slice_dir.is_dir():
            continue

        # 情况 A：flat Headers
        flat_headers = slice_dir / "Headers"
        if flat_headers.exists():
            candidates.append((slice_dir.name, flat_headers, None))
            continue

        # 情况 B：*.framework/Headers
        for item in slice_dir.iterdir():
            if item.suffix == ".framework" and item.is_dir():
                fw_headers = item / "Headers"
                if fw_headers.exists():
                    candidates.append((slice_dir.name, fw_headers, item.stem))
                    break

    if not candidates:
        return None, None

    # 按偏好排序
    for pref in preferred:
        for slice_name, hdir, fw_name in candidates:
            if pref in slice_name:
                return hdir, fw_name

    # fallback
    _, hdir, fw_name = candidates[0]
    return hdir, fw_name


def resolve_lib_name(xcframework_path: Path, fw_name_from_bundle) -> str:
    """
    决定 #import <LibName/...> 中的 LibName。
    优先使用从 .framework bundle 推断的名字，否则用 xcframework 文件名。
    """
    if fw_name_from_bundle:
        return fw_name_from_bundle
    return xcframework_path.stem


def build_header_map(headers_dir: Path, lib_name: str) -> dict:
    header_map = {}
    for hfile in headers_dir.rglob("*.h"):
        relative = hfile.relative_to(headers_dir)  # 例如 KwaiSDK/KSApi.h
        parts = relative.parts

        # 如果第一层子目录名已经等于库名，直接用相对路径，不再拼接库名前缀
        if parts[0] == lib_name:
            import_path = relative.as_posix()           # KwaiSDK/KSApi.h
        else:
            import_path = f"{lib_name}/{relative.as_posix()}"  # upnpx/BasicUPnPService.h

        key = hfile.name
        header_map.setdefault(key, []).append(import_path)
    return header_map


# ──────────────────────────────────────────────
# 2. 扫描源文件并收集命中项
# ──────────────────────────────────────────────

SOURCE_EXTENSIONS = {".m", ".mm", ".h", ".hpp", ".cpp", ".c", ".swift"}

IMPORT_PATTERN = re.compile(
    r'^(\s*)#\s*(import|include)\s+"([^"]+\.h)"',
    re.MULTILINE,
)

# 新增：匹配 #import <KGStaticLibraries/xxx.h>
IMPORT_KGSTATIC_PATTERN = re.compile(
    r'^(\s*)#\s*(import|include)\s+<KGStaticLibraries/([^>]+\.h)>',
    re.MULTILINE,
)


def scan_file(filepath: Path, header_map: dict) -> list:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[WARN] 无法读取 {filepath}: {e}", file=sys.stderr)
        return []

    hits = []

    def process_match(m, header_name, original_line, line_no, indent):
        bare_name = Path(header_name).name
        if bare_name not in header_map:
            return
        candidates = header_map[bare_name]
        replacement_import_path = candidates[0]
        ambiguous = len(candidates) > 1
        new_line = f'{indent}#import <{replacement_import_path}>'
        hits.append({
            "line_no": line_no,
            "original": original_line,
            "replacement": new_line,
            "header_name": header_name,
            "import_path": replacement_import_path,
            "ambiguous": ambiguous,
            "ambiguous_candidates": candidates if ambiguous else [],
        })

    # 匹配 #import "xxx.h" / #include "xxx.h"
    for m in IMPORT_PATTERN.finditer(content):
        line_no = content[: m.start()].count("\n") + 1
        process_match(m, m.group(3), m.group(0), line_no, m.group(1))

    # 匹配 #import <KGStaticLibraries/xxx.h>
    for m in IMPORT_KGSTATIC_PATTERN.finditer(content):
        line_no = content[: m.start()].count("\n") + 1
        process_match(m, m.group(3), m.group(0), line_no, m.group(1))

    # 按行号排序，输出更整齐
    hits.sort(key=lambda x: x["line_no"])
    return hits




# ──────────────────────────────────────────────
# 3. 执行修改
# ──────────────────────────────────────────────

def fix_file(filepath: Path, header_map: dict) -> int:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[WARN] 无法读取 {filepath}: {e}", file=sys.stderr)
        return 0

    count = 0

    def replacer_quoted(m: re.Match) -> str:
        nonlocal count
        indent = m.group(1)
        header_name = m.group(3)
        bare_name = Path(header_name).name
        if bare_name not in header_map:
            return m.group(0)
        import_path = header_map[bare_name][0]
        count += 1
        return f"{indent}#import <{import_path}>"

    def replacer_kgstatic(m: re.Match) -> str:
        nonlocal count
        indent = m.group(1)
        header_name = m.group(3)  # 这里是 xxx.h 或 subdir/xxx.h
        bare_name = Path(header_name).name
        if bare_name not in header_map:
            return m.group(0)
        import_path = header_map[bare_name][0]
        count += 1
        return f"{indent}#import <{import_path}>"

    new_content = IMPORT_PATTERN.sub(replacer_quoted, content)
    new_content = IMPORT_KGSTATIC_PATTERN.sub(replacer_kgstatic, new_content)

    if count > 0:
        filepath.write_text(new_content, encoding="utf-8")
    return count





# ──────────────────────────────────────────────
# 4. 主流程
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="将 #import \"xxx.h\" 替换为 #import <LibName/xxx.h>（基于 xcframework）"
    )
    parser.add_argument(
        "--xcframework_path",
        required=True,
        help="xcframework 文件的路径，例如 /path/to/upnpx.xcframework",
    )
    parser.add_argument(
        "--scan_dir",
        required=True,
        help="要扫描/修改的源代码目录（递归）",
    )
    parser.add_argument(
        "--action_type",
        choices=["list", "fix"],
        default="list",
        help="list: 仅列出需要修改的导入（默认）；fix: 直接修改文件",
    )
    args = parser.parse_args()

    xcframework_path = Path(args.xcframework_path).expanduser().resolve()
    scan_dir = Path(args.scan_dir).expanduser().resolve()

    if not xcframework_path.exists():
        print(f"[ERROR] xcframework 路径不存在: {xcframework_path}", file=sys.stderr)
        sys.exit(1)
    if not scan_dir.exists():
        print(f"[ERROR] 扫描目录不存在: {scan_dir}", file=sys.stderr)
        sys.exit(1)

    # 步骤 1：找到 Headers 目录
    headers_dir, fw_name = find_headers_slice(xcframework_path)
    if headers_dir is None:
        print(f"[ERROR] 在 {xcframework_path} 中未找到任何 Headers 目录", file=sys.stderr)
        print("        支持的结构: ios-arm64/Headers/ 或 ios-arm64/Lib.framework/Headers/", file=sys.stderr)
        sys.exit(1)

    # 步骤 2：确定库名
    lib_name = resolve_lib_name(xcframework_path, fw_name)

    print(f"[INFO] xcframework  : {xcframework_path.name}")
    print(f"[INFO] 使用头文件切片 : {headers_dir.relative_to(xcframework_path)}")
    print(f"[INFO] 库名 (prefix) : {lib_name}")
    print(f"[INFO] 扫描目录      : {scan_dir}")
    print(f"[INFO] 操作类型      : {args.action_type}")
    print("─" * 60)

    # 步骤 3：建立头文件映射
    header_map = build_header_map(headers_dir, lib_name)
    print(f"[INFO] 共索引头文件数: {len(header_map)}")

    ambiguous_headers = {k: v for k, v in header_map.items() if len(v) > 1}
    if ambiguous_headers:
        print(f"[WARN] 以下头文件存在多个路径，将使用第一个:")
        for name, paths in ambiguous_headers.items():
            print(f"       {name} -> {paths}")
    print("─" * 60)

    # 步骤 4：遍历源文件
    total_files_with_hits = 0
    total_hits = 0
    total_fixed = 0

    # xcframework 自身的绝对路径，用于排除
    xcframework_real = xcframework_path.resolve()

    source_files = [
        f for f in scan_dir.rglob("*")
        if f.is_file()
        and f.suffix in SOURCE_EXTENSIONS
        and "Pods" not in f.parts                        # 跳过 Pods 目录
        and ".webp_build" not in f.parts                 # 跳过特定目录
        and "libwebp" not in f.parts                 # 跳过特定目录
        and not f.is_relative_to(xcframework_real)       # 跳过 xcframework 自身
    ]

    for filepath in sorted(source_files):
        if args.action_type == "list":
            hits = scan_file(filepath, header_map)
            if hits:
                total_files_with_hits += 1
                rel = filepath.relative_to(scan_dir)
                print(f"\n📄 {rel}")
                for h in hits:
                    ambig_note = (
                        f"  ⚠️  歧义候选: {h['ambiguous_candidates']}"
                        if h["ambiguous"]
                        else ""
                    )
                    print(f"  行 {h['line_no']:>4}: {h['original'].strip()}")
                    print(f"         -> {h['replacement'].strip()}{ambig_note}")
                    total_hits += 1
        else:
            count = fix_file(filepath, header_map)
            if count > 0:
                total_files_with_hits += 1
                total_fixed += count
                rel = filepath.relative_to(scan_dir)
                print(f"✅ 已修改 {count} 处  {rel}")

    print("\n" + "─" * 60)
    if args.action_type == "list":
        print(f"[DONE] 共发现 {total_hits} 处需要修改，涉及 {total_files_with_hits} 个文件。")
        if total_hits > 0:
            print("[HINT] 使用 --action_type fix 可直接修改所有文件。")
    else:
        print(f"[DONE] 共修改 {total_fixed} 处，涉及 {total_files_with_hits} 个文件。")


if __name__ == "__main__":
    main()
