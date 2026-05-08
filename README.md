# quick_shell
个人常用shell

# Usage

## 安装 oh-my-zsh、zsh-autosuggestions、zsh-syntax-highlighting

自动安装 oh-my-zsh 及常用插件（zsh-autosuggestions、zsh-syntax-highlighting、autojump），支持 macOS / CentOS / Ubuntu。

**本地调用：**

```bash
bash ./quick_oh_my_zsh.sh
```

**远端调用：**

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/quick_oh_my_zsh.sh)"
```

---

## 合并 .bash_history 到 .zsh_history

将 `~/.bash_history` 合并到 `~/.zsh_history` 并去重，支持 macOS / CentOS / Ubuntu。

**本地调用：**

```bash
bash ./merge_bash_history_into_zsh_history.sh
```

**远端调用：**

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/merge_bash_history_into_zsh_history.sh)"
```

---

## daily

### fw-setup.sh

Debian 服务器防火墙一键修复、初始化与恢复脚本。会自动备份当前 `iptables` 规则，按指定端口放行 SSH / TCP / UDP，并开启 NAT 转发；支持从历史备份恢复。

**依赖：** Debian；root 权限；`iptables`、`iptables-persistent`、`netfilter-persistent`

| 选项 | 说明 |
|---|---|
| `-s, --ssh-port <port>` | SSH 端口，默认 `22` |
| `-t, --tcp-ports <list>` | 额外放行的 TCP 端口，逗号分隔，如 `80,443,8080` |
| `-u, --udp-ports <list>` | 额外放行的 UDP 端口，逗号分隔，如 `51820` |
| `-n, --nat-net <cidr>` | NAT 转发网段，默认 `192.168.90.0/24` |
| `-y, --all-yes` | 跳过确认提示，直接执行 |
| `--restore` | 从 `/root/iptables_backups` 中选择备份并恢复 |
| `-h, --help` | 显示帮助 |

**本地调用：**

```bash
sudo bash ./daily/fw-setup.sh -s 2222 -t 80,443,8080 -u 51820 -n 10.0.0.0/24
sudo bash ./daily/fw-setup.sh --restore
```

**远端调用：**

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/daily/fw-setup.sh) \
  -s 2222 -t 80,443,8080 -u 51820 -n 10.0.0.0/24

sudo bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/daily/fw-setup.sh) \
  --restore
```

---

## develop/MacOS

### prepare-colima-build-swap.sh

为 Apple Silicon 上的低内存 Colima VM 临时启用 swap，避免多架构 Docker 镜像发布时 `linux/amd64` 模拟构建因内存不足卡住或失败。默认在 Colima VM 内创建 `/swapfile-colima-build`，`cleanup` 会同时兼容清理旧路径 `/swapfile-open-design-build`。

**依赖：** macOS；Colima；Docker/Buildx 发布前已启动 Colima

| 命令 | 说明 |
|---|---|
| `ensure` | 内存低于 4GiB 且无 swap 时创建并启用 swap，默认命令 |
| `status` | 查看 Colima VM 内存与 swap 状态 |
| `cleanup` | 关闭并删除脚本创建的 swap 文件 |

| 环境变量 | 说明 |
|---|---|
| `COLIMA_BUILD_SWAP_SIZE` | swap 大小，默认 `4G` |
| `COLIMA_BUILD_SWAPFILE` | swap 文件路径，默认 `/swapfile-colima-build` |
| `COLIMA_BUILD_SWAP_MEMORY_THRESHOLD_KIB` | 低内存阈值，默认 `4194304`（4GiB） |
| `COLIMA_BIN` | 指定 Colima 可执行文件路径，默认优先 `/opt/homebrew/bin/colima` |

**本地调用：**

```bash
bash ./develop/MacOS/prepare-colima-build-swap.sh
# 执行你的 docker buildx / 镜像发布命令
bash ./develop/MacOS/prepare-colima-build-swap.sh cleanup
```

**安装为全局命令：**

```bash
sudo install -m 755 ./develop/MacOS/prepare-colima-build-swap.sh /usr/local/bin/prepare-colima-build-swap.sh
prepare-colima-build-swap.sh
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/MacOS/prepare-colima-build-swap.sh)
```

---

## develop/app

### appicon-magick.sh

使用 ImageMagick 移除图片背景，可选消除毛边，可选生成 macOS AppIcon.appiconset。

**依赖：** `brew install imagemagick`

| 选项 | 说明 |
|---|---|
| `-i <file>` | 输入图片路径（必填） |
| `-o <dir>` | 输出目录（必填） |
| `--fuzz <percent>` | 背景色容差，默认 15 |
| `--bg-color <color>` | 手动指定背景色，默认自动取左上角像素 |
| `--defringe <method>` | 毛边消除方案：`erode` / `smooth` / `decontam`（默认不启用） |
| `--defringe-radius <n>` | erode 方案腐蚀半径，默认 1 |
| `--mac-appicon` | 同时生成 macOS AppIcon.appiconset |
| `-h` | 显示帮助 |

**本地调用：**

```bash
bash ./develop/app/appicon-magick.sh -i icon.png -o ./output --defringe erode
bash ./develop/app/appicon-magick.sh -i icon.png -o ./output --mac-appicon
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/app/appicon-magick.sh) \
  -i icon.png -o ./output --defringe erode

bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/app/appicon-magick.sh) \
  -i icon.png -o ./output --mac-appicon
```

---

### gen-appicon.sh

从一张图片生成 macOS 或 iOS 的 AppIcon.appiconset 图标集（含 Contents.json）。

**依赖：** `brew install imagemagick`

| 选项 | 说明 |
|---|---|
| `-i <file>` | 输入图片路径（必填，建议 1024×1024 PNG） |
| `-o <dir>` | 输出目录（必填） |
| `--platform <p>` | 目标平台：`mac` 或 `ios`，默认 `mac` |
| `-h` | 显示帮助 |

**本地调用：**

```bash
bash ./develop/app/gen-appicon.sh -i icon.png -o ./output
bash ./develop/app/gen-appicon.sh -i icon.png -o ./output --platform ios
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/app/gen-appicon.sh) \
  -i icon.png -o ./output

bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/app/gen-appicon.sh) \
  -i icon.png -o ./output --platform ios
```

---

### create_pretty_dmg.sh

将 macOS .app 包打包成带精美安装背景的 DMG 文件。可自动读取 app 版本号/构建号附加到文件名。

**依赖：** Xcode Command Line Tools（`ditto`、`hdiutil`、`osascript`、`swift`）

| 选项 | 说明 |
|---|---|
| `--app-path PATH` | .app 包路径（必填） |
| `--dmg-name NAME` | DMG 文件名及挂载卷名的基础名称（必填） |
| `--append-version` | 读取 app 版本号并追加到名称，如 `_v1.2.3` |
| `--append-build` | 读取 app 构建号并追加到名称，如 `_26A5198a` |
| `--output-dir PATH` | DMG 输出目录，默认为当前目录 |
| `-h, --help` | 显示帮助 |

**本地调用：**

```bash
bash ./develop/app/create_pretty_dmg.sh \
  --app-path "./MyApp.app" \
  --dmg-name "MyApp" \
  --append-version \
  --append-build \
  --output-dir ./dist
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/app/create_pretty_dmg.sh) \
  --app-path "./MyApp.app" \
  --dmg-name "MyApp" \
  --append-version \
  --append-build \
  --output-dir ./dist
```

---

## develop/iOS

### check_binary.sh

检查 Mach-O 二进制（动态库/静态库）支持的平台和架构，支持 fat/thin 静态库、xcframework。

**依赖：** Xcode Command Line Tools（`vtool`、`lipo`、`ar`）

**本地调用：**

```bash
bash ./develop/iOS/check_binary.sh MyFramework.framework/MyFramework
bash ./develop/iOS/check_binary.sh libFoo.a
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/check_binary.sh) \
  MyFramework.framework/MyFramework

bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/check_binary.sh) \
  libFoo.a
```

---

### check_arch.py

精细检查 iOS 静态库（.a）或 Framework 中**每一个 .o 文件**的平台/架构，并生成汇总报告。

| 选项 | 说明 |
|---|---|
| `--lib` | .a 静态库 或 .framework 路径（必填） |
| `--arch` | 目标架构或平台（必填），如 `arm64`、`iphoneos`、`iphonesimulator` |
| `--output` | 报告输出路径，默认 `check_arch_report.txt` |

**本地调用：**

```bash
python3 ./develop/iOS/check_arch.py --lib libFoo.a --arch iphoneos
python3 ./develop/iOS/check_arch.py --lib MySDK.framework --arch arm64 --output report.txt
```

**远端调用：**

```bash
curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/check_arch.py \
  | python3 - --lib libFoo.a --arch iphoneos

curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/check_arch.py \
  | python3 - --lib MySDK.framework --arch arm64 --output report.txt
```

---

### find_symbol_in_libs.sh

在指定目录下递归查找 `.framework`、`.xcframework`、`.a` 中哪些库包含了目标符号。

| 选项 | 说明 |
|---|---|
| `-d, -dir <path>` | 要搜索的根目录（必填） |
| `-s, --symbol <sym>` | 要查找的符号名（必填） |
| `-v, --verbose` | 显示更多 nm 详情 |
| `-h, --help` | 显示帮助 |

**本地调用：**

```bash
bash ./develop/iOS/find_symbol_in_libs.sh -dir ~/Libs --symbol "_OBJC_CLASS_\$_MyClass"
bash ./develop/iOS/find_symbol_in_libs.sh -dir /path/to/Pods --symbol "my_function"
```

**远端调用：**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/find_symbol_in_libs.sh) \
  -dir ~/Libs --symbol "_OBJC_CLASS_\$_MyClass"

bash <(curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/iOS/find_symbol_in_libs.sh) \
  -dir /path/to/Pods --symbol "my_function"
```

---

## develop/python

### build_xcframework.py

将静态库（.a）、动态库（.dylib）或 framework 的多个平台切片打包为 XCFramework，自动整理头文件导入路径和 modulemap。支持单任务命令行模式和批量 JSON/YAML 配置模式。

**依赖：** Xcode（`xcodebuild`、`file`、`install_name_tool`）；YAML 模式需 `pip install pyyaml`

**单任务模式常用选项：**

| 选项 | 说明 |
|---|---|
| `--input PATH` | 输入切片路径（.a / .dylib / .framework），可重复指定多个切片 |
| `--headers-dir PATH` | 公共头文件根目录（.a/.dylib 输入时必填） |
| `--output PATH` | 输出 XCFramework 路径（必填） |
| `--module-name NAME` | 模块名，默认从输入名推导（自动去除 lib 前缀） |
| `--framework-name NAME` | framework 二进制名，默认同 module-name |
| `--umbrella-header NAME` | 伞头文件名，默认 `<module-name>.h` |
| `--modulemap PATH` | 自定义 modulemap 文件或 Modules 目录 |
| `--modulemap-mode` | `preserve`（默认，修复已有 modulemap）或 `generate`（重新生成） |
| `--external-module-import` | 将头文件引用重写为外部模块导入，格式 `prefix:module` |
| `--log-file PATH` | 头文件/modulemap 改写日志路径 |
| `--bundle-id-prefix` | bundle ID 前缀，默认 `com.codex.generated` |

**批量配置模式：**

| 选项 | 说明 |
|---|---|
| `--config FILE` | JSON 或 YAML 批量配置文件 |
| `--task-name NAME` | 只执行配置中指定名称的任务 |

**本地调用：**

```bash
python3 ./develop/python/build_xcframework.py \
  --input Demo/iphoneos/lib/libDemo.a \
  --input Demo/iphonesimulator/lib/libDemo.a \
  --input Demo/maccatalyst/lib/libDemo.a \
  --headers-dir Demo/include \
  --module-name DemoSDK \
  --output output/DemoSDK.xcframework

# 批量任务
python3 ./develop/python/build_xcframework.py --config build_tasks.yaml
```

**远端调用：**

```bash
curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/python/build_xcframework.py \
  | python3 - \
  --input Demo/iphoneos/lib/libDemo.a \
  --input Demo/iphonesimulator/lib/libDemo.a \
  --input Demo/maccatalyst/lib/libDemo.a \
  --headers-dir Demo/include \
  --module-name DemoSDK \
  --output output/DemoSDK.xcframework
```

---

### xcframework_import_fixer.py

扫描源代码目录，将 `#import "SomeHeader.h"` 替换为 `#import <LibName/SomeHeader.h>`（依据指定 xcframework 中的头文件路径）。支持预览（list）和直接修改（fix）两种模式。

| 选项 | 说明 |
|---|---|
| `--xcframework_path` | xcframework 路径（必填） |
| `--scan_dir` | 要扫描/修改的源代码目录（必填，递归） |
| `--action_type` | `list`（默认，仅预览）或 `fix`（直接修改文件） |

**本地调用：**

```bash
python3 ./develop/python/xcframework_import_fixer.py \
  --xcframework_path ./upnpx.xcframework \
  --scan_dir ./MyProject \
  --action_type list

python3 ./develop/python/xcframework_import_fixer.py \
  --xcframework_path ./upnpx.xcframework \
  --scan_dir ./MyProject \
  --action_type fix
```

**远端调用：**

```bash
curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/python/xcframework_import_fixer.py \
  | python3 - \
  --xcframework_path ./upnpx.xcframework \
  --scan_dir ./MyProject \
  --action_type list

curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/python/xcframework_import_fixer.py \
  | python3 - \
  --xcframework_path ./upnpx.xcframework \
  --scan_dir ./MyProject \
  --action_type fix
```

---

### quick_clone_proj.py

快速复制一个现有工程到新目录，并批量替换项目名、类名前缀等文本，同时重命名匹配的文件和目录。默认会跳过 `Pods`、`xcworkspace`、`build/outputs`、`iOS/build`、`.idea` 等目录。

| 选项 | 说明 |
|---|---|
| `--dir` | 源工程目录（必填） |
| `--destDir` | 新工程所在的父目录（必填） |
| `--destDirName` | 新工程目录名（必填） |
| `--oldWords` | 要替换的旧词列表，逗号分隔（必填） |
| `--newWords` | 对应的新词列表，逗号分隔，数量需与 `--oldWords` 一致（必填） |

**本地调用：**

```bash
python3 ./develop/python/quick_clone_proj.py \
  --dir ./OldProject \
  --destDir ~/Desktop \
  --destDirName NewProject \
  --oldWords OldProject,OLD \
  --newWords NewProject,NEW
```

**远端调用：**

```bash
curl -fsSL https://raw.githubusercontent.com/wangwanjie/quick_shell/main/develop/python/quick_clone_proj.py \
  | python3 - \
  --dir ./OldProject \
  --destDir ~/Desktop \
  --destDirName NewProject \
  --oldWords OldProject,OLD \
  --newWords NewProject,NEW
```
