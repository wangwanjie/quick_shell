#!/bin/bash

# 判断操作系统类型，如果不是 macos、centos或者ubuntu，就退出
if [[ "$OSTYPE" != "darwin"* ]] && [[ "$OSTYPE" != "linux-gnu" ]]; then
    echo 'Error: This script only supports MacOS, CentOS and Ubuntu.' >&2
    exit 1
fi

# 判断操作系统类型，是否安装了 zsh，如果没安装，就退出
if ! [ -x "$(command -v zsh)" ]; then
    echo 'Error: zsh is not installed.' >&2
    exit 1
fi

# 判断是否存在 .bash_history 文件，如果不存在，就退出
if ! [ -f ~/.bash_history ]; then
    echo 'Error: ~/.bash_history does not exist.' >&2
    exit 1
fi

# 判断是否存在 .zsh_history 文件，如果不存在，就创建
if ! [ -f ~/.zsh_history ]; then
    touch ~/.zsh_history
fi

# 合并 .bash_history 到 .zsh_history，并做去重处理，相同命令内容的只保留一个，忽略时间戳
cat ~/.bash_history | sort -u -t ':' -k 2 | cut -d ';' -f 2- >> ~/.zsh_history

# 检查 .zsh_history 文件是否有重复的命令，如果有，就删除
awk -F ';' '!a[$2]++' ~/.zsh_history > ~/.zsh_history.tmp

# 检查 .zsh_history 文件是否有写法错误，如果有，就修正
sed -i -e 's/\\:/:/g' ~/.zsh_history.tmp