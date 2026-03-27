#!/usr/bin/env python3
"""
check_arch.py — 检查 iOS 静态库 (.a) 或 Framework 中所有 .o 文件的平台/架构。

用法:
  python3 check_arch.py --lib <path> --arch <target> [--output <report.txt>]

示例:
  python3 check_arch.py --lib libFoo.a --arch iphoneos
  python3 check_arch.py --lib MySDK.framework --arch arm64 --output report.txt
"""

import argparse
import os
import re
import subprocess
import sys
import shutil
import tempfile

PLATFORM_MAP = {
    "iphoneos":        "IOS",
    "ios":             "IOS",
    "iphonesimulator": "IOSSIMULATOR",
    "simulator":       "IOSSIMULATOR",
    "macos":           "MACOSX",
    "macosx":          "MACOSX",
    "maccatalyst":     "MACCATALYST",
    "tvos":            "TVOS",
    "watchos":         "WATCHOS",
    "xros":            "XROS",
    "visionos":        "XROS",
}

AR_MAGIC     = b"!<arch>\n"
AR_HDR_SIZE  = 60
AR_END_CHARS = b"\x60\n"
TERMINAL_MAX = 10   # 终端最多显示条数


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def get_archs(path):
    stdout, _, rc = run(["lipo", "-info", path])
    if rc != 0:
        return None
    m = re.search(r"(?:are:|architecture:)\s+(.+)$", stdout)
    return set(m.group(1).strip().split()) if m else None


def get_platforms(path):
    stdout, _, rc = run(["vtool", "-show-build", path])
    if rc == 0:
        hits = re.findall(r"platform\s+(\w+)", stdout, re.IGNORECASE)
        return set(p.upper() for p in hits) if hits else None
    stdout, _, rc = run(["otool", "-l", path])
    if rc != 0:
        return None
    result = set()
    num_map = {
        "1": "MACOSX", "2": "IOS", "6": "TVOS",
        "7": "IOSSIMULATOR", "11": "MACCATALYST",
        "12": "IOSSIMULATOR", "13": "TVOSSIMULATOR",
        "14": "WATCHOS", "15": "WATCHOSSIMULATOR",
    }
    for p in re.findall(r"platform\s+(\d+)", stdout, re.IGNORECASE):
        result.add(num_map.get(p, f"PLATFORM_{p}"))
    if "LC_VERSION_MIN_IPHONEOS" in stdout:
        result.add("IOS")
    if "LC_VERSION_MIN_IPHONESIMULATOR" in stdout:
        result.add("IOSSIMULATOR")
    return result if result else None


# ─── 纯 Python ar 解析器 ──────────────────────────────────────────────────────

def _read_ar_header(f):
    hdr = f.read(AR_HDR_SIZE)
    if not hdr or len(hdr) < AR_HDR_SIZE:
        return None
    if hdr[58:60] != AR_END_CHARS:
        return None
    raw_name = hdr[0:16].decode("ascii", errors="replace")
    try:
        size = int(hdr[48:58].decode("ascii", errors="replace").strip())
    except ValueError:
        return None
    return raw_name, size


def extract_from_a_python(lib_path, tmpdir):
    results      = []
    name_counter = {}
    gnu_names    = {}

    try:
        f = open(lib_path, "rb")
    except OSError as e:
        print(f"  ❌ 无法打开文件: {e}")
        return []

    with f:
        if f.read(8) != AR_MAGIC:
            print("  ❌ 不是有效的 ar 归档文件")
            return []

        # 第一遍：读取 GNU ar 长名表 (//)
        saved = f.tell()
        while True:
            entry = _read_ar_header(f)
            if entry is None:
                break
            raw_name, size = entry
            data = f.read(size)
            if size % 2 != 0:
                f.read(1)
            if raw_name.rstrip() == "//":
                offset = 0
                for line in data.decode("ascii", errors="replace").split("\n"):
                    gnu_names[offset] = line.rstrip("/\r")
                    offset += len(line) + 1
                break
        f.seek(saved)

        # 第二遍：提取所有 .o 成员
        while True:
            entry = _read_ar_header(f)
            if entry is None:
                break
            raw_name, size = entry
            data = f.read(size)
            if size % 2 != 0:
                f.read(1)

            name = raw_name.rstrip()

            if name.startswith("#1/"):           # BSD ar 长名
                try:
                    nlen = int(name[3:].strip())
                except ValueError:
                    continue
                actual = data[:nlen].rstrip(b"\x00").decode("ascii", errors="replace")
                data   = data[nlen:]
            elif re.match(r"^/\d+", name):       # GNU ar 长名引用
                off    = int(name[1:].strip())
                actual = gnu_names.get(off, name).rstrip("/")
            elif name in ("", "/", "//", "__.SYMDEF", "__.SYMDEF SORTED",
                          "__.SYMDEF64", "__.SYMDEF64 SORTED"):
                continue
            else:
                actual = name.rstrip("/")

            if not actual.endswith(".o"):
                continue

            name_counter[actual] = name_counter.get(actual, 0) + 1
            idx = name_counter[actual]
            display  = actual if idx == 1 else f"{actual} (#{idx})"
            out_name = actual if idx == 1 else f"{actual[:-2]}_{idx}.o"
            out_path = os.path.join(tmpdir, out_name)

            try:
                with open(out_path, "wb") as out:
                    out.write(data)
                results.append((display, out_path))
            except OSError as e:
                print(f"  ⚠️  写入 {out_name} 失败: {e}")

    return results


# ─── Framework 查找 ───────────────────────────────────────────────────────────

def find_framework_binary(fw_path):
    fw_name   = os.path.splitext(os.path.basename(fw_path))[0]
    candidate = os.path.join(fw_path, fw_name)
    if os.path.isfile(candidate):
        return candidate
    skip = {".h", ".modulemap", ".swiftinterface", ".swiftdoc",
            ".plist", ".nib", ".storyboardc", ".strings", ".png"}
    for root, dirs, files in os.walk(fw_path):
        dirs[:] = [d for d in dirs if d not in ("Headers", "Modules", "_CodeSignature")]
        for fname in files:
            if os.path.splitext(fname)[1].lower() in skip:
                continue
            full = os.path.join(root, fname)
            out, _, rc = run(["file", full])
            if rc == 0 and ("Mach-O" in out or "archive" in out):
                return full
    return None


# ─── 检查单文件 ───────────────────────────────────────────────────────────────

def check_file(path, target, is_platform):
    if is_platform:
        platforms = get_platforms(path)
        if not platforms:
            return None, "无法获取平台信息"
        key  = PLATFORM_MAP.get(target.lower(), target.upper())
        info = f"平台: {', '.join(sorted(platforms))}"
        if key not in platforms:
            return False, f"❌ 不含目标平台 | {info}"
        if len(platforms) > 1:
            return False, f"⚠️  含多个平台   | {info}"
        return True, info
    else:
        archs = get_archs(path)
        if archs is None:
            return None, "无法获取架构信息"
        info = f"架构: {', '.join(sorted(archs))}"
        if target not in archs:
            return False, f"❌ 不含目标架构 | {info}"
        if len(archs) > 1:
            return False, f"⚠️  含多个架构   | {info}"
        return True, info


# ─── 双通道输出 ───────────────────────────────────────────────────────────────

class DualOutput:
    """同时写入终端和文件，终端对不符合条目限制最多显示 TERMINAL_MAX 条。"""

    def __init__(self, file_path):
        self.file   = open(file_path, "w", encoding="utf-8") if file_path else None
        self._term_mismatch_count = 0   # 已在终端打印的不符合条目数
        self._suppress_term       = False

    def _write_file(self, text):
        if self.file:
            self.file.write(text + "\n")

    def println(self, text="", is_mismatch=False):
        """is_mismatch=True 的行受 TERMINAL_MAX 限制"""
        self._write_file(text)
        if is_mismatch:
            if self._term_mismatch_count < TERMINAL_MAX:
                print(text)
                self._term_mismatch_count += 1
                if self._term_mismatch_count == TERMINAL_MAX:
                    print(f"  … 仅显示前 {TERMINAL_MAX} 条，完整列表见报告文件")
        else:
            print(text)

    def close(self):
        if self.file:
            self.file.close()


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="检查 iOS 静态库 / Framework 中所有 .o 文件的平台架构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--lib",    required=True,
                        help=".a 静态库 或 .framework 路径")
    parser.add_argument("--arch",   required=True,
                        help="目标架构或平台，如 arm64 / iphoneos / iphonesimulator")
    parser.add_argument("--output", default="check_arch_report.txt",
                        help="汇总报告输出路径（默认: check_arch_report.txt）")
    args = parser.parse_args()

    lib_path = os.path.abspath(args.lib)
    target   = args.arch.strip()
    out_path = args.output

    if not os.path.exists(lib_path):
        print(f"❌ 路径不存在: {lib_path}")
        sys.exit(1)

    is_platform  = target.lower() in PLATFORM_MAP
    target_label = (
        f"平台 [{PLATFORM_MAP[target.lower()]}]"
        if is_platform else f"架构 [{target}]"
    )

    dual = DualOutput(out_path)

    dual.println("=" * 66)
    dual.println(f"  📦 文件  : {lib_path}")
    dual.println(f"  🎯 目标  : {target_label}")
    if out_path:
        dual.println(f"  📄 报告  : {os.path.abspath(out_path)}")
    dual.println("=" * 66)

    tmpdir  = tempfile.mkdtemp(prefix="check_arch_")
    o_files = []

    try:
        ext = os.path.splitext(lib_path)[1].lower()

        if ext == ".a":
            dual.println("\n📂 正在解析静态库（Python ar 解析器）...")
            o_files = extract_from_a_python(lib_path, tmpdir)
            dual.println(f"   共发现 {len(o_files)} 个 .o 条目\n")

        elif ext == ".framework":
            binary = find_framework_binary(lib_path)
            if not binary:
                dual.println("❌ 无法在 Framework 中找到二进制文件")
                sys.exit(1)
            dual.println(f"\n📂 Framework 二进制: {binary}")
            if binary.endswith(".a"):
                o_files = extract_from_a_python(binary, tmpdir)
                dual.println(f"   共发现 {len(o_files)} 个 .o 条目\n")
            else:
                o_files = [(os.path.basename(binary), binary)]
                dual.println()
        else:
            o_files = [(os.path.basename(lib_path), lib_path)]
            dual.println()

        if not o_files:
            dual.println("⚠️  未发现任何 .o 文件，退出。")
            sys.exit(0)

        mismatch, errors, ok_count = [], [], 0

        for name, path in sorted(o_files, key=lambda x: x[0]):
            ok, info = check_file(path, target, is_platform)
            if ok is None:
                errors.append((name, info))
                dual.println(f"  ⚠️  {name:<52}  {info}", is_mismatch=True)
            elif not ok:
                mismatch.append((name, info))
                dual.println(f"  ✗  {name:<52}  {info}", is_mismatch=True)
            else:
                ok_count += 1

        total = len(o_files)

        # ── 汇总 ──
        dual.println()
        dual.println("=" * 66)
        dual.println("  📊 检查汇总")
        dual.println("=" * 66)
        dual.println(f"  总计 .o 文件     : {total}")
        dual.println(f"  ✅ 仅含目标       : {ok_count}")
        dual.println(f"  ✗  不符合目标     : {len(mismatch)}")
        dual.println(f"  ⚠️  无法检查       : {len(errors)}")

        # 完整列表（写入文件 + 终端超限提示已在 DualOutput 处理）
        if mismatch:
            dual.println(f"\n  📋 不符合目标的文件列表 ({len(mismatch)} 个):")
            for name, info in mismatch:
                dual.println(f"    - {name}")
                dual.println(f"        {info}")

        if errors:
            dual.println(f"\n  ⚠️  无法检查的文件列表 ({len(errors)} 个):")
            for name, info in errors:
                dual.println(f"    - {name}: {info}")

        dual.println("=" * 66)

        if out_path:
            print(f"\n  💾 完整报告已保存至: {os.path.abspath(out_path)}")

        dual.close()
        sys.exit(1 if mismatch else 0)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
