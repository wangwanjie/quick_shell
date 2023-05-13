#!/bin/bash

# detect os mac or centos or ubuntu based, to install zsh first
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OSX
    brew install zsh
elif [[ "$OSTYPE" == "linux-gnu" ]]; then
    # Linux
    if [[ -f /etc/redhat-release ]]; then
        # CentOS
        sudo yum install zsh
    elif [[ -f /etc/lsb-release ]]; then
        # Ubuntu
        sudo apt-get install zsh
    fi
fi

# detect if zsh is installed, if not, exit
if ! [ -x "$(command -v zsh)" ]; then
    echo 'Error: zsh is not installed.' >&2
    exit 1
fi

# change default shell to zsh
chsh -s $(which zsh)

# 根据操作系统类型，安装 oh-my-zsh
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OSX
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
elif [[ "$OSTYPE" == "linux-gnu" ]]; then
    # Linux
    if [[ -f /etc/redhat-release ]]; then
        # CentOS
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
    elif [[ -f /etc/lsb-release ]]; then
        # Ubuntu
        sh -c "$(wget https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh -O -)"
    fi
fi

# 安装 zsh 插件
# 根据操作系统类型安装 zsh-autosuggestions ，并添加到 .zshrc
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OSX
    brew install zsh-autosuggestions
    echo "source /usr/local/share/zsh-autosuggestions/zsh-autosuggestions.zsh" >> ~/.zshrc
elif [[ "$OSTYPE" == "linux-gnu" ]]; then
    # Linux
    if [[ -f /etc/redhat-release ]]; then
        # CentOS
        git clone   https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/plugins/zsh-autosuggestions ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions
        echo "source ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh" >> ~/.zshrc
    elif [[ -f /etc/lsb-release ]]; then
        # Ubuntu
        git clone   https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/plugins/zsh-autosuggestions ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions
        echo "source ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh" >> ~/.zshrc
    fi
fi

# 根据操作系统类型安装 zsh-syntax-highlighting ，并添加到 .zshrc
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Mac OSX
    brew install zsh-syntax-highlighting
    echo "source /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" >> ~/.zshrc
elif [[ "$OSTYPE" == "linux-gnu" ]]; then
    # Linux
    if [[ -f /etc/redhat-release ]]; then
        # CentOS
        git clone https://raw.githubusercontent.com/zsh-users/zsh-syntax-highlighting.git ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting
        echo "source ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" >> ~/.zshrc
    elif [[ -f /etc/lsb-release ]]; then
        # Ubuntu
        git clone https://raw.githubusercontent.com/zsh-users/zsh-syntax-highlighting.git ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting
        echo "source ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" >> ~/.zshrc
    fi
fi

# 判断是否安装了 autojump，没有的话则安装
if ! [ -x "$(command -v autojump)" ]; then
    echo 'Error: autojump is not installed.' >&2
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # Mac OSX
        brew install autojump
    elif [[ "$OSTYPE" == "linux-gnu" ]]; then
        # Linux
        if [[ -f /etc/redhat-release ]]; then
            # CentOS
            sudo yum install autojump
        elif [[ -f /etc/lsb-release ]]; then
            # Ubuntu
            sudo apt-get install autojump
        fi
    fi
fi

# 判断 autojump 是否安装成功，如果安装成功，则添加到 .zshrc
if [ -x "$(command -v autojump)" ]; then
    echo 'autojump is installed.' >&2
    echo "[[ -s ~/.autojump/etc/profile.d/autojump.sh ]] && source ~/.autojump/etc/profile.d/autojump.sh" >> ~/.zshrc
fi
