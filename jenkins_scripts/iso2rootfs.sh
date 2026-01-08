#!/bin/bash

# Jenkins shell中先进行代码下载，然后执行这个脚本
#sudo mkdir -p /c/
#sudo chmod 775 /c/ || error_exit "修改/c/目录权限失败"
#cd /c/ || error_exit "进入/c/目录失败"
#REPOS=(
#    "/c/rootfs-maker|https://gitcode.com/cicd-sig/rootfs-maker.git"
#)
#
#echo "3. 拉取/更新代码"
#for item in "${REPOS[@]}"; do
#    DIR="${item%%|*}"
#    URL="${item##*|}"
#    echo "处理仓库: $DIR"
#    if [ -d "$DIR" ]; then
#        echo "  拉取最新代码..."
#        cd "$DIR" && git pull && cd - || error_exit "拉取$DIR代码失败"
#    else
#        echo "  克隆仓库..."
#        git clone "$URL" "$DIR" || error_exit "克隆$URL到$DIR失败"
#    fi
#    echo "---"
#done
# cd /c/rootfs-maker/jenkins_scripts
# bash -x iso2rootfs.sh

set -eo pipefail  # 开启严格模式：报错立即退出、未定义变量报错、管道错误传递

# ==================== 由Jenkins Pipeline生成的环境变量==============
BRANCH=${BRANCH-"master"}

TIMESTAMP=${TIMESTAMP-"202512111800"}

# ===================== Jenkins配置项:可修改部分=====================
# compass-ci服务器IP地址
TARGET_IP=${TARGET_IP-"10.232.168.215"}
# 架构
ARCH=${ARCH-"arm64"}
# ISO名称
ISO_NAME=${ISO_NAME-"byted-debian-12.10.b1-arm64-DVD-1.iso"}
# ISO本地目录
ISO_DIR=${ISO_DIR-"/data01/Jenkins_workspace/ISO"}
# ISO服务器地址
ISO_FILE_SERVER=${ISO_FILE_SERVER-"http://os-cicd.byted.org/fileserver"}
# 本地rootfs输出目录
LOCAL_ROOTFS_DIR=${LOCAL_ROOTFS_DIR-"/data01/debian-arm64-rootfs"}


# ===================== 配置项:禁止修改部分=====================

ISO_DIR="${ISO_DIR}/${TIMESTAMP}"
ISO_FILE_SERVER="${ISO_FILE_SERVER}/${BRANCH}/${TIMESTAMP}/iso/${ARCH}"
# ISO本地目录
ISO_FILE="${ISO_DIR}/${ISO_NAME}"

if [ "${ARCH}" = "arm64" ];then
# 远程服务器OS文件基础目录
  OS_BASE_DIR="/srv/os/debian/aarch64"
# 远程服务器initrd文件基础目录
  INITRD_BASE_DIR="/srv/initrd/osimage/debian/aarch64"
elif [ "${ARCH}" = "amd64" ];then
  OS_BASE_DIR="/srv/os/debian/x86_64"
  INITRD_BASE_DIR="/srv/initrd/osimage/debian/x86_64"
fi
# ===================== 函数定义 =====================

# 错误处理函数
error_exit() {
    echo "error：$1" >&2
    exit 1
}

# 检查SSH免密登录
check_ssh_auth() {
    echo "检查与 ${TARGET_IP} 的SSH免密登录..."
    if ! ssh -o BatchMode=yes -o ConnectTimeout=5 root@${TARGET_IP} "echo ok" >/dev/null 2>&1; then
        error_exit "未配置与 ${TARGET_IP} 的SSH免密登录，请先配置后再执行脚本！"
    fi
}

# ===================== 主流程 =====================
echo "1. 安装依赖"
sudo apt-get update || error_exit "更新软件源失败"
sudo apt-get install -y \
    git \
    libvirt-daemon-system \
    libvirt-clients \
    qemu-system \
    qemu-utils \
    cpio \
    gzip \
    virtinst \
    bridge-utils \
    ebtables \
    dnsmasq-base \
    libguestfs-tools \
    virt-viewer \
    virt-manager \
    python3-pexpect || error_exit "安装依赖失败"

echo "2. 检查default网络"
# 启动default网络（如果已经启动则忽略错误，但继续执行）
if ! virsh net-start default; then
    echo "警告：default网络启动失败（可能已经启动或不存在），继续执行..."
fi

# 设置default网络开机自动启动（如果已经设置则忽略错误，但继续执行）
if ! virsh net-autostart default; then
    echo "警告：default网络自动启动设置失败（可能已经设置），继续执行..."
fi

echo "3. 检查ISO文件"
if [ ! -f "$ISO_FILE" ]; then
    echo "ISO文件不存在：$ISO_FILE，尝试先下载"
    mkdir -p ${ISO_DIR} && cd ${ISO_DIR}
    wget ${ISO_FILE_SERVER}/${ISO_NAME} && cd -
    if [ ! -f "$ISO_FILE" ]; then
        error_exit "ISO文件不存在，请先将ISO文件手动放到该路径！"
    fi
fi

echo "4. 执行ISO转换rootfs操作"
sudo rm -rf ${LOCAL_ROOTFS_DIR}/${TIMESTAMP}
sudo mkdir -p ${LOCAL_ROOTFS_DIR}/${TIMESTAMP} || error_exit "创建本地rootfs目录失败"
cd /c/rootfs-maker || error_exit "进入rootfs-maker目录失败"

python_args=()
if [ -n "$REPO" ]; then
    python_args+=("--repo" "$REPO")
fi

env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 sudo python3 -u ./src/iso2rootfs.py \
    -i "$ISO_FILE" \
    -o "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}" \
    -d debian \
    -s 20 \
    -m 4096 \
    -c 24 \
    -t 7200 \
    --kernel "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/vmlinuz-${TIMESTAMP}" \
    --modules "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/modules-${TIMESTAMP}.cgz" \
    --http-port 8081 \
    "${python_args[@]}" || error_exit "ISO转换rootfs失败"

# 检查生成的文件是否存在
REQUIRED_FILES=(
    "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/vmlinuz-${TIMESTAMP}"
    "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/modules-${TIMESTAMP}.cgz"
    "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/rootfs.cgz"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        error_exit "转换产物缺失：$file，请检查iso2rootfs.py执行日志！"
    fi
done

echo "5. 检查远程服务器SSH连接"
check_ssh_auth

echo "6. 归档产物到指定远程目录"
# 创建远程目录
ssh root@${TARGET_IP} "mkdir -p ${OS_BASE_DIR}/${TIMESTAMP}/boot/ ${INITRD_BASE_DIR}/${TIMESTAMP}/" || error_exit "创建远程目录失败"

# 同步内核文件并创建软链接
rsync -avz "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/vmlinuz-${TIMESTAMP}" root@${TARGET_IP}:${OS_BASE_DIR}/${TIMESTAMP}/boot/ || error_exit "同步vmlinuz失败"
ssh root@${TARGET_IP} "ln -sf ${OS_BASE_DIR}/${TIMESTAMP}/boot/vmlinuz-${TIMESTAMP} ${OS_BASE_DIR}/${TIMESTAMP}/boot/vmlinuz" || error_exit "创建vmlinuz软链接失败"

# 同步模块文件并创建软链接
rsync -avz "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/modules-${TIMESTAMP}.cgz" root@${TARGET_IP}:${OS_BASE_DIR}/${TIMESTAMP}/boot/ || error_exit "同步modules.cgz失败"
ssh root@${TARGET_IP} "ln -sf ${OS_BASE_DIR}/${TIMESTAMP}/boot/modules-${TIMESTAMP}.cgz ${OS_BASE_DIR}/${TIMESTAMP}/boot/modules.cgz" || error_exit "创建modules.cgz软链接失败"

# 同步rootfs文件并改名
rsync -avz "${LOCAL_ROOTFS_DIR}/${TIMESTAMP}/rootfs.cgz" root@${TARGET_IP}:${INITRD_BASE_DIR}/${TIMESTAMP}/ || error_exit "同步rootfs.cgz失败"
ssh root@${TARGET_IP} "mv -f ${INITRD_BASE_DIR}/${TIMESTAMP}/rootfs.cgz ${INITRD_BASE_DIR}/${TIMESTAMP}/current" || error_exit "重命名rootfs.cgz失败"

# 复制ipconfig文件
ssh root@${TARGET_IP} "cp -f /srv/ipconfig/run-ipconfig.cgz ${INITRD_BASE_DIR}/${TIMESTAMP}/" || error_exit "复制run-ipconfig.cgz失败"

echo "7.job finished!"
echo "the timestamp:${TIMESTAMP}"
echo "the compass-ci Server:${TARGET_IP}"
echo "rootfs dir:${OS_BASE_DIR}/${TIMESTAMP}"