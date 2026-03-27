#!/usr/bin/env bash
#
# find_symbol_in_libs.sh - 在指定目录下遍历查找 framework、xcframework、.a 库中
# 哪些库包含（定义或引用）了指定符号
#
# 用法: find_symbol_in_libs.sh -dir /path/to/search --symbol "symbol_name"
#
# 安装到 /usr/local/bin 后可在任意目录使用:
#   sudo cp "$(dirname "$0")/find_symbol_in_libs.sh" /usr/local/bin/
# 或: sudo cp /path/to/find_symbol_in_libs.sh /usr/local/bin/
#

set -e

SCRIPT_NAME="find_symbol_in_libs.sh"
SEARCH_DIR=""
SYMBOL=""
VERBOSE=0

usage() {
    cat <<EOF
用法: $SCRIPT_NAME -dir <目录> --symbol <符号名> [选项]

选项:
  -d, -dir <path>     要搜索的根目录（必填）
  -s, --symbol <sym>  要查找的符号名（必填）
  -v, --verbose       显示更多信息（对每个库执行 nm 时的详情）
  -h, --help          显示此帮助

示例:
  $SCRIPT_NAME -dir ~/Libs --symbol "_OBJC_CLASS_\\\$_MyClass"
  $SCRIPT_NAME -dir /path/to/Pods --symbol "my_function"
EOF
    exit 0
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|-dir)
            SEARCH_DIR="$2"
            shift 2
            ;;
        -s|--symbol)
            SYMBOL="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "未知参数: $1" >&2
            usage
            ;;
    esac
done

if [[ -z "$SEARCH_DIR" || -z "$SYMBOL" ]]; then
    echo "错误: 必须指定 -dir 和 --symbol" >&2
    usage
fi

if [[ ! -d "$SEARCH_DIR" ]]; then
    echo "错误: 目录不存在: $SEARCH_DIR" >&2
    exit 1
fi

# 对单个二进制/静态库执行 nm，若包含目标符号则打印路径并返回 0
check_file() {
    local file="$1"
    local label="$2"
    if [[ ! -f "$file" ]]; then
        return 1
    fi
    # nm 可能对非目标文件报错，忽略 stderr
    local out
    out=$(nm -g "$file" 2>/dev/null | grep -w -- "$SYMBOL") || true
    if [[ -n "$out" ]]; then
        echo "----------------------------------------"
        echo "库: $label"
        echo "路径: $file"
        echo "符号匹配:"
        echo "$out"
        return 0
    fi
    return 1
}

# 递归找 .framework 里的主二进制（macOS: Framework.framework/FrameworkName 或 Versions/A/FrameworkName）
framework_binary() {
    local fw_root="$1"
    local name
    name=$(basename "$fw_root" .framework)
    if [[ -f "$fw_root/$name" ]]; then
        echo "$fw_root/$name"
        return
    fi
    if [[ -f "$fw_root/Versions/A/$name" ]]; then
        echo "$fw_root/Versions/A/$name"
        return
    fi
    return 1
}

# 搜索 .framework
search_frameworks() {
    while IFS= read -r -d '' fw; do
        local bin
        bin=$(framework_binary "$fw") || continue
        if check_file "$bin" "$fw"; then
            found=1
        fi
    done < <(find "$SEARCH_DIR" -type d -name "*.framework" -print0 2>/dev/null)
}

# 搜索 .xcframework 内各 slice 的 framework 和 .a
search_xcframeworks() {
    while IFS= read -r -d '' xc; do
        # 遍历 xcframework 内各架构目录（如 ios-arm64、ios-arm64_x86_64-simulator 等）
        for variant in "$xc"/*/; do
            [[ -d "$variant" ]] || continue
            # 该 slice 下可能有一个或多个 .framework
            for fw in "$variant"/*.framework; do
                [[ -d "$fw" ]] || continue
                local bin
                bin=$(framework_binary "$fw") || true
                if [[ -n "$bin" && -f "$bin" ]]; then
                    if check_file "$bin" "$xc ($variant)"; then
                        found=1
                    fi
                fi
            done
            # 有的 slice 直接是 .a 静态库
            for static in "$variant"/*.a; do
                [[ -f "$static" ]] || continue
                if check_file "$static" "$xc ($static)"; then
                    found=1
                fi
            done
        done
    done < <(find "$SEARCH_DIR" -type d -name "*.xcframework" -print0 2>/dev/null)
}

# 搜索 .a 静态库
search_static_libs() {
    while IFS= read -r -d '' a; do
        if check_file "$a" "$a"; then
            found=1
        fi
    done < <(find "$SEARCH_DIR" -type f -name "*.a" -print0 2>/dev/null)
}

found=0
echo "在目录 $SEARCH_DIR 中查找符号: $SYMBOL"
echo ""

search_frameworks
search_xcframeworks
search_static_libs

if [[ $found -eq 0 ]]; then
    echo "未在任何 framework / xcframework / .a 中找到符号: $SYMBOL"
    exit 1
fi
exit 0
