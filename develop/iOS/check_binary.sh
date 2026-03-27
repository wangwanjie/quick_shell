#!/bin/bash
#
# check_binary.sh (v5 - 修正了 "archive" 和 "Mach-O" 的检查顺序)
#
# 一个用于检查 Mach-O 二进制文件（动态库或静态库）
# 支持的平台和架构的通用脚本。
#

# --- 配置 ---
set -e # 任何命令失败时立即退出

# --- 检查：参数 ---
if [ $# -eq 0 ]; then
    echo "Usage: $0 <path_to_binary_file>"
    echo "Example: $0 MyFramework.framework/MyFramework"
    exit 1
fi

# --- 检查：依赖 ---
if ! command -v vtool &> /dev/null || ! command -v lipo &> /dev/null || ! command -v ar &> /dev/null; then
    echo "Error: This script requires vtool, lipo, and ar."
    echo "Please make sure Xcode Command Line Tools are installed."
    exit 1
fi

# --- 路径处理 ---
TARGET_FILE="$1"
if [[ "$TARGET_FILE" != /* ]]; then
    TARGET_FILE="$(pwd)/$TARGET_FILE"
fi

if [ ! -f "$TARGET_FILE" ]; then
    echo "Error: File not found at $TARGET_FILE"
    exit 1
fi

echo "🔍 Analyzing: $TARGET_FILE"
echo "------------------------------------------------------"

# --- 临时工作目录 ---
TEMP_DIR=$(mktemp -d -t check_binary_XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT

# --- 核心逻辑：判断文件类型 ---
FILE_TYPE=$(file "$TARGET_FILE")

#
# !!!! 关键修复：检查顺序 !!!!
#
# 场景 1: 归档文件 (静态库, .a)
# *必须*最先检查这个，因为 "fat archive" 的 "file" 输出
# 可能同时包含 "Mach-O" 和 "archive"
#
if [[ "$FILE_TYPE" == *"archive"* ]]; then
    echo "File is a Static Library Archive (.a)."
    
    LIPO_INFO=$(lipo -info "$TARGET_FILE" 2>/dev/null)

    if [[ "$LIPO_INFO" == *"Architectures in the fat file"* ]]; then
        # 场景 1a: "Fat" 胖静态库 (包含多架构)
        echo "It's a 'fat' static library. Analyzing each architecture..."
        
        ARCHS=$(echo "$LIPO_INFO" | sed -n 's/.*are: \(.*\)$/\1/p')

        for ARCH in $ARCHS; do
            THIN_LIB_PATH="$TEMP_DIR/${ARCH}.a"
            lipo "$TARGET_FILE" -thin "$ARCH" -output "$THIN_LIB_PATH"
            
            FIRST_O_FILE_NAME=$(ar -t "$THIN_LIB_PATH" | grep '\.o$' | head -n 1)
            
            if [ -z "$FIRST_O_FILE_NAME" ]; then
                echo ""
                echo "--- Analyzing Arch: $ARCH ---"
                echo "Error: Could not find any .o files in the $ARCH archive."
                continue
            fi
            
            (
                cd "$TEMP_DIR"
                ar -x "$THIN_LIB_PATH" "$FIRST_O_FILE_NAME"
                echo ""
                echo "--- Analyzing Arch: $ARCH (Platform for '$FIRST_O_FILE_NAME') ---"
                vtool -show-build "$FIRST_O_FILE_NAME"
            )
        done

    else
        # 场景 1b: "Thin" 瘦静态库 (只包含单架构)
        echo "It's a 'thin' static library. Analyzing..."
        
        FIRST_O_FILE_NAME=$(ar -t "$TARGET_FILE" | grep '\.o$' | head -n 1)
        
        if [ -z "$FIRST_O_FILE_NAME" ]; then
            echo "Error: Could not find any .o files in the archive."
            exit 1
        fi
        
        (
            cd "$TEMP_DIR"
            ar -x "$TARGET_FILE" "$FIRST_O_FILE_NAME"
            echo ""
            echo "--- Analyzing (Platform for '$FIRST_O_FILE_NAME') ---"
            vtool -show-build "$FIRST_O_FILE_NAME"
        )
    fi

#
# 场景 2: Mach-O 文件 (动态库, 可执行文件, 或 .o 文件)
#
elif [[ "$FILE_TYPE" == *"Mach-O"* || "$FILE_TYPE" == *"mach-o"* ]]; then
    echo "File is a Mach-O (Dynamic Library / Executable / .o file)."
    echo "Running vtool directly:"
    echo ""
    vtool -show-build "$TARGET_FILE"

#
# 场景 3: 未知文件类型
#
else
    echo "Error: Unknown file type. Not a Mach-O or archive."
    echo "File type detected: $FILE_TYPE"
    exit 1
fi

echo "------------------------------------------------------"
echo "✅ Analysis complete."