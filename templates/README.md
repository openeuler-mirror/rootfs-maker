# 配置文件模板

本目录包含各种Linux发行版的自动化安装配置文件模板。

## 目录结构

```
templates/
├── debian/
│   └── preseed.cfg      # Debian Preseed配置
├── ubuntu/
│   └── preseed.cfg      # Ubuntu Preseed配置
├── openeuler/
│   └── ks.ks            # OpenEuler Kickstart配置
├── centos/
│   └── ks.ks            # CentOS Kickstart配置
├── rhel/
│   └── ks.ks            # RHEL Kickstart配置
└── fedora/
    └── ks.ks            # Fedora Kickstart配置
```

## 使用方式

### 自动选择模板

工具会根据ISO文件名自动检测发行版并选择对应的模板：

```bash
# 自动检测为debian，使用 templates/debian/preseed.cfg
./src/iso2rootfs.py -i debian-12.iso -o ./output

# 自动检测为openeuler，使用 templates/openeuler/ks.ks
./src/iso2rootfs.py -i openeuler-22.03.iso -o ./output
```

### 手动指定发行版

如果自动检测失败，可以使用 `-d` 参数手动指定：

```bash
./src/iso2rootfs.py -i my-iso.iso -o ./output -d openeuler
```

### 使用自定义配置

如果需要使用自定义配置，可以通过 `-p` 或 `-k` 参数指定：

```bash
# 使用自定义preseed文件（会覆盖模板）
./src/iso2rootfs.py -i debian.iso -o ./output -p /path/to/custom-preseed.cfg

# 使用自定义kickstart文件（会覆盖模板）
./src/iso2rootfs.py -i centos.iso -o ./output -k /path/to/custom-ks.ks
```

## 配置文件说明

### Preseed文件（Debian/Ubuntu）

Preseed文件用于Debian和Ubuntu系统的自动化安装，主要配置项包括：

- **本地化设置**: 语言、键盘布局
- **网络配置**: 主机名、域名
- **镜像源**: 软件包镜像服务器
- **分区设置**: 自动分区方案
- **用户设置**: root密码、用户创建
- **软件包选择**: 要安装的软件包
- **后置脚本**: 安装后的配置命令

### Kickstart文件（RPM系列）

Kickstart文件用于RHEL、CentOS、Fedora、OpenEuler等RPM系列系统的自动化安装，主要配置项包括：

- **系统语言**: 语言和键盘设置
- **认证**: root密码、认证方式
- **安全**: SELinux、防火墙设置
- **网络**: 网络配置
- **分区**: 磁盘分区方案
- **软件包**: 要安装的软件包组
- **后置脚本**: 安装后的配置命令

## 自定义模板

你可以根据需要编辑这些模板文件来自定义安装行为：

1. **修改默认配置**: 编辑对应的模板文件
2. **添加新发行版**: 创建新的目录和配置文件
3. **版本特定配置**: 可以为不同版本创建子目录

### 示例：添加新发行版模板

```bash
# 创建新发行版目录
mkdir -p templates/rocky

# 创建kickstart配置文件
cat > templates/rocky/ks.ks << 'EOF'
# Rocky Linux Kickstart configuration
lang en_US.UTF-8
keyboard us
timezone UTC
rootpw --plaintext root
...
EOF
```

## 模板优先级

当运行转换工具时，配置文件的优先级如下：

1. **最高优先级**: 通过 `-p` 或 `-k` 参数提供的自定义配置文件
2. **次优先级**: 通过 `-d` 参数指定的发行版模板
3. **自动检测**: 从ISO文件名自动检测的发行版模板
4. **默认配置**: 如果以上都不满足，使用默认配置（debian或centos）

## 注意事项

1. **模板文件编码**: 所有模板文件使用UTF-8编码
2. **路径相对性**: 模板路径相对于项目根目录
3. **向后兼容**: 如果不提供配置文件，工具会回退到默认配置
4. **自定义覆盖**: 自定义配置文件会完全覆盖模板，不会合并

## 贡献

欢迎提交新的发行版模板或改进现有模板！

