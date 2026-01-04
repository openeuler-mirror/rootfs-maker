# 使用指导
- 该脚本用于执行Jenkins调用iso2rootfs，并将产物归档给compass-ci执行机使用  
- 配置到jenkins的Configure -> Buid Steps -> Execute shell -> Command  
- timestamp变量来自于上游任务，或者定义在Jenkins的变量中，脚本中是直接使用的  


## 执行准备
 - 脚本的执行需要bash支持，第一行需要声明"#!/bin/bash"
 - 需要能访问外部网络clone代码仓
 - 默认已经存在iso文件，如果文件不存在需要下载添加
 - python脚本运行需要预先安装python3
### 当前shell需要配置的地方：
- 1.配置项：compass-ci服务器的ip；iso文件路径；结果目录路径
- 2.时间戳需要在jenkins变量中传递进来

## iso转rootfs脚本的参数 对应clone的代码仓脚本./src/iso2rootfs.py 
-i, --iso：ISO路径  
-o, --output：输出目录  
-p, --preseed：Deb系自动化配置（如需自定义）  
-k, --kickstart：RPM系自动化配置（如需自定义）  
-d, --distribution：指定发行版名（如debian, ubuntu, centos等）  
-s, --size：虚拟磁盘大小，默认20G  
-m, --memory：虚拟机内存MB，默认2048  
-c, --vcpus：虚拟机CPU核心数，默认2  
-t, --timeout：安装超时时间，默认3600  
--kernel：内核输出路径（默认output/kernel）  
--modules：modules输出路径   
--no-cgz：不生成cgz压缩包  
--keep-qcow2：保留虚拟磁盘(qcow2)中间文件  
--http-port： 启动http服务的端口，提供配置文件给虚拟机加载 默认8080  
--repo: 仓库镜像链接，将替换repo-config中的配置文件并复制到rootfs的相应目录下


```bash
#!/bin/bash

set -euo pipefail  # 开启严格模式：报错立即退出、未定义变量报错、管道错误传递

# 启动default网络（如果已经启动则忽略错误，但继续执行）
if ! virsh net-start default; then
    echo "警告：default网络启动失败（可能已经启动或不存在），继续执行..."
fi

# 设置default网络开机自动启动（如果已经设置则忽略错误，但继续执行）
if ! virsh net-autostart default; then
    echo "警告：default网络自动启动设置失败（可能已经设置），继续执行..."
fi

# ===================== 配置项:可修改部分=====================
# compass-ci服务器IP地址
TARGET_IP="172.168.177.42"
# ISO文件地址
ISO_FILE="/tmp/debian-12.11.0-arm64-DVD-1.iso"
# 本地rootfs输出目录
LOCAL_ROOTFS_DIR="/tmp/debian-arm64-rootfs"


# ===================== 配置项:禁止修改部分=====================
# 远程服务器OS文件基础目录
OS_BASE_DIR="/srv/os/debian/aarch64"
# 远程服务器initrd文件基础目录
INITRD_BASE_DIR="/srv/initrd/osimage/debian/aarch64"
# ===================== 函数定义 =====================

# 错误处理函数
error_exit() {
    echo "错误：$1" >&2
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

# 创建目录（提前检查并创建，避免权限问题）
echo "2. 创建工作目录"
sudo mkdir -p /c/ ${LOCAL_ROOTFS_DIR}/${timestamp} || error_exit "创建工作目录失败"
sudo chmod 775 /c/ || error_exit "修改/c/目录权限失败"
cd /c/ || error_exit "进入/c/目录失败"

# 定义仓库列表
REPOS=(
    "/c/rootfs-maker|https://gitcode.com/cicd-sig/rootfs-maker.git"
)

echo "3. 拉取/更新代码"
for item in "${REPOS[@]}"; do
    DIR="${item%%|*}"
    URL="${item##*|}"
    echo "处理仓库: $DIR"
    if [ -d "$DIR" ]; then
        echo "  拉取最新代码..."
        cd "$DIR" && git pull && cd - || error_exit "拉取$DIR代码失败"
    else
        echo "  克隆仓库..."
        git clone "$URL" "$DIR" || error_exit "克隆$URL到$DIR失败"
    fi
    echo "---"
done

cd /c/rootfs-maker || error_exit "进入rootfs-maker目录失败"

# 检查ISO文件是否存在
if [ ! -f "$ISO_FILE" ]; then
    error_exit "ISO文件不存在：$ISO_FILE，请先将ISO文件放到该路径！"
fi

echo "4. 执行ISO转换rootfs操作"
env LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 sudo ./src/iso2rootfs.py \
    -i "$ISO_FILE" \
    -o "${LOCAL_ROOTFS_DIR}/${timestamp}" \
    -d debian \
    -s 20 \
    -m 4096 \
    -c 24 \
    -t 7200 \
    --kernel "${LOCAL_ROOTFS_DIR}/${timestamp}/vmlinuz-${timestamp}" \
    --modules "${LOCAL_ROOTFS_DIR}/${timestamp}/modules-${timestamp}.cgz" \
    --http-port 8081 \
    --repo http://mirrors.huaweicloud.com || error_exit "ISO转换rootfs失败"

# 检查生成的文件是否存在
REQUIRED_FILES=(
    "${LOCAL_ROOTFS_DIR}/${timestamp}/vmlinuz-${timestamp}"
    "${LOCAL_ROOTFS_DIR}/${timestamp}/modules-${timestamp}.cgz"
    "${LOCAL_ROOTFS_DIR}/${timestamp}/rootfs.cgz"
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
ssh root@${TARGET_IP} "mkdir -p ${OS_BASE_DIR}/${timestamp}/boot/ ${INITRD_BASE_DIR}/${timestamp}/" || error_exit "创建远程目录失败"

# 同步内核文件并创建软链接
rsync -avz "${LOCAL_ROOTFS_DIR}/${timestamp}/vmlinuz-${timestamp}" root@${TARGET_IP}:${OS_BASE_DIR}/${timestamp}/boot/ || error_exit "同步vmlinuz失败"
ssh root@${TARGET_IP} "ln -sf ${OS_BASE_DIR}/${timestamp}/boot/vmlinuz-${timestamp} ${OS_BASE_DIR}/${timestamp}/boot/vmlinuz" || error_exit "创建vmlinuz软链接失败"

# 同步模块文件并创建软链接
rsync -avz "${LOCAL_ROOTFS_DIR}/${timestamp}/modules-${timestamp}.cgz" root@${TARGET_IP}:${OS_BASE_DIR}/${timestamp}/boot/ || error_exit "同步modules.cgz失败"
ssh root@${TARGET_IP} "ln -sf ${OS_BASE_DIR}/${timestamp}/boot/modules-${timestamp}.cgz ${OS_BASE_DIR}/${timestamp}/boot/modules.cgz" || error_exit "创建modules.cgz软链接失败"

# 同步rootfs文件并改名
rsync -avz "${LOCAL_ROOTFS_DIR}/${timestamp}/rootfs.cgz" root@${TARGET_IP}:${INITRD_BASE_DIR}/${timestamp}/ || error_exit "同步rootfs.cgz失败"
ssh root@${TARGET_IP} "mv -f ${INITRD_BASE_DIR}/${timestamp}/rootfs.cgz ${INITRD_BASE_DIR}/${timestamp}/current" || error_exit "重命名rootfs.cgz失败"

# 复制ipconfig文件
ssh root@${TARGET_IP} "cp -f /srv/ipconfig/run-ipconfig.cgz ${INITRD_BASE_DIR}/${timestamp}/" || error_exit "复制run-ipconfig.cgz失败"

echo "7. 任务执行完成！"
echo "时间戳：${timestamp}"
echo "远程服务器：${TARGET_IP}"
echo "产物路径：${OS_BASE_DIR}/${timestamp}/"
```