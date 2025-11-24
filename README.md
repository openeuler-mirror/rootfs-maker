# RootFS生成工具

本工具集用于将ISO与QCOW2镜像自动转换为rootfs目录，可提取Linux kernel并支持压缩为cgz格式。支持Debian/Ubuntu (deb系) 和 RHEL/CentOS/Fedora/OpenEuler (rpm系) 等主流发行版。

## 功能特性

- **ISO转rootfs**：通过真实virt-install安装，自动化应答配置（支持定制模板）
- **QCOW2转rootfs**：直接从QCOW2磁盘镜像提取完整rootfs
- **自动提取kernel**：从镜像自动查找并分离内核文件
- **CGZ压缩**：支持将rootfs目录打包为cpio+gzip格式（.cgz）

## 环境准备

### 快速开始

运行脚本自动初始化环境：

```bash
python3 setup.py
# 或
uv run python setup.py
```

setup脚本主要处理：

1. 检查/安装uv
2. 校验并提示缺失系统依赖（如virt-install、qemu-nbd）
3. 配置python虚拟环境
4. 安装python依赖

### 基础依赖

- Python 3.8+
- [`uv`](https://github.com/astral-sh/uv)（推荐的依赖管理器）
- `virt-install`（ISO转QCOW2虚拟化安装）
- `qemu-nbd`（QCOW2挂载，Linux下必需）
- `cpio`, `gzip`（rootfs cgz压缩）
- `libvirt`（虚拟化后端支持）
- `pexpect`（Linux自动化安装交互脚本）

#### 系统依赖安装

**Debian/Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y libvirt qemu-utils cpio gzip virt-install
```
**RHEL/CentOS/Fedora:**
```bash
sudo yum install -y libvirt qemu-img cpio gzip virt-install
```

#### Python依赖安装

推荐采用uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```
或传统方式：
```bash
pip install -r requirements.txt
```

## 项目结构

```
gen_rootfs/
├── src/
│   ├── iso2qcow2.py      # ISO转QCOW2镜像
│   ├── qcow2rootfs.py    # QCOW2提取rootfs
│   ├── iso2rootfs.py     # ISO转rootfs（一键集成）
│   ├── deb_expect.py     # debian/ubuntu自动化安装脚本
│   ├── rpm_expect.py     # rpm系自动化安装脚本
│   └── lib/
│       ├── __init__.py
│       └── cgz_utils.py  # cpio+gzip打包工具
├── templates/
│   ├── debian/preseed.cfg
│   ├── ubuntu/preseed.cfg
│   ├── openeuler/ks.ks
│   ├── centos/ks.ks
│   ├── rhel/ks.ks
│   └── fedora/ks.ks
├── demo/                 # 用例脚本
└── doc/                  # 文档
```

## 使用示例

### 1. ISO转rootfs（推荐入口，自动从ISO生成rootfs）

```bash
# 自动模板方式
./src/iso2rootfs.py -i debian-12.iso -o ./output

# 指定发行版模板
./src/iso2rootfs.py -i centos-7.iso -o ./output -d centos

# 自定义preseed或kickstart文件
./src/iso2rootfs.py -i debian.iso -o ./output -p custom-preseed.cfg
./src/iso2rootfs.py -i centos.iso -o ./output -k custom.ks

# 常用参数
./src/iso2rootfs.py \
    -i debian.iso \
    -o ./output \
    -d debian \
    -s 30G \
    -m 4096 \
    -c 4 \
    -t 7200
```

**主要参数说明**

- `-i, --iso`：ISO路径
- `-o, --output`：输出目录
- `-p, --preseed`：Deb系自动化配置（如需自定义）
- `-k, --kickstart`：RPM系自动化配置（如需自定义）
- `-d, --distribution`：指定发行版名（如debian, ubuntu, centos等）
- `-s, --size`：虚拟磁盘大小，默认20G
- `-m, --memory`：虚拟机内存MB，默认2048
- `-c, --vcpus`：虚拟机CPU核心数，默认2
- `-t, --timeout`：安装超时时间，默认3600
- `--kernel`：内核输出路径（默认output/kernel）
- `--no-cgz`：不生成cgz压缩包
- `--keep-qcow2`：保留虚拟磁盘(qcow2)中间文件

### 2. QCOW2转rootfs

将已有的qcow2快速提取为rootfs：

```bash
./src/qcow2rootfs.py -i vm.qcow2 -o ./output

# 增强示例
./src/qcow2rootfs.py -i vm.qcow2 -o ./output --kernel ./kernel --no-cgz
```

### 3. ISO转QCOW2（如仅需qcow2虚拟机磁盘）

```bash
./src/iso2qcow2.py -i debian.iso -o debian.qcow2 -p preseed.cfg
```

### 4. 独立CGZ压缩/解包

```bash
python3 src/lib/cgz_utils.py compress /path/to/rootfs output.cgz
python3 src/lib/cgz_utils.py extract rootfs.cgz /path/to/output
```

## 输出结构说明

标准输出内容如下：

```
output/
├── kernel          # 分离出的vmlinuz
├── rootfs/         # 完整根文件系统
│   ├── bin/
│   ├── etc/
│   └── ...
└── rootfs.cgz      # 压缩包（可选）
```

## 配置模板机制

所有安装自动化配置模板集中于`templates/`目录，支持定制和覆盖。

- **debian/ubuntu**: `preseed.cfg`
- **openeuler/centos/rhel/fedora**: `ks.ks` (kickstart)

#### 模板优先级（自动选择顺序）

1. 手动提供的`-p`或`-k`优先
2. 指定`-d`发行版
3. 自动识别ISO名称获得模板
4. 默认为debian或centos

## 工作流程简述

### ISO转rootfs

1. 分析ISO类型（deb/rpm）
2. 准备自动化配置文件，HTTP提供服务
3. 利用virt-install自动化安装，自动与GRUB/引导器交互
4. 获得QCOW2磁盘文件
5. 用qemu-nbd挂载，提取系统文件与kernel，构建输出（含cgz）

### QCOW2转rootfs

- 直接qemu-nbd挂载提取rootfs+kernel，压缩输出

### DVD/netinst差异

- netinst ISO：直接通过extra-args参数自动安装
- DVD ISO：需自动交互GRUB引导，插入配置URL参数

## 故障排查

### virt-install相关

- 检查libvirt服务与权限
- 建议root执行，或确保用户加入libvirt组

```bash
sudo systemctl status libvirt
sudo systemctl start libvirt
virsh net-list
```

### QCOW2挂载失败

- 检查qemu-nbd与nbd内核模块已加载

```bash
sudo modprobe nbd max_part=16
which qemu-nbd
```

### 安装超时

- 增加`-t`参数或提升虚拟机资源分配

## 常见注意事项

- 主要面向Linux，部分环节(macOS)不可用
- 某些操作须root权限
- ISO自动化安装须能访问本机HTTP服务
- 虚拟机磁盘/内存要足够，否则可能安装超时

## 开发与扩展参考

主要逻辑划分：

- `iso2qcow2.py`：ISO转QCOW2完整虚拟化安装自动化
- `qcow2rootfs.py`：QCOW2挂载提取
- `iso2rootfs.py`：上面两步的自动集成入口
- `lib/cgz_utils.py`：标准化cpio/gz打包

要拓展支持其它rootfs提取/转换，可参考上述结构编写新脚本。

## 许可证

[请填写具体许可证]

## 贡献

欢迎提出Issue、PR及建议！

