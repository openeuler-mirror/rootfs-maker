# rootfs制作方案

## 需求背景

在操作系统测试与镜像验证的流程中，测试人员通常需要对不同发行版的 ISO 镜像进行安装、修改和验证。例如，需要验证 ISO 是否能够正常安装、引导，或在系统环境中加入如 **lkp-tests** 等测试框架进行性能与稳定性测试。

然而当前的流程存在以下痛点：

1. **ISO 每次都需要完整安装，耗时长**： 安装一个 ISO 通常需要 10–30 分钟（甚至更久），测试人员在一次验证中需要重复安装多次，极其影响效率。
2. **QCOW2 虽然可用，但不便于快速修改内容**： QCOW2 镜像需要挂载或通过虚拟机启动后才能修改文件，例如加入 lkp-tests 或其他自定义文件，操作复杂、效率低。
3. **缺乏统一的 rootfs 制作方案**： 当前缺少一个能够统一处理 ISO、QCOW2、Docker 镜像的工具，导致不同来源的镜像需要不同工具链进行rootfs提取与处理，维护成本高。

因此，我们需要一个自动化、统一化的 **rootfs 制作程序**，用于快速从 ISO、QCOW2、Docker 等不同类型的镜像生成 rootfs，以提升测试人员的效率和镜像测试能力。



## 用户场景

该工具主要面向以下使用场景：

1. **ISO 镜像测试验证**：
   - 自动化安装 ISO（包括 deb 系列与 rpm 系列）
   - 无需人工干预即可得到安装后的 rootfs
   - 可用于 CI 自动化场景
2. **QCOW2 镜像内容验证与快速修改**：
   - 将 QCOW2 快速转换为 rootfs
   - rootfs 可直接修改、处理，再重新打包
3. **Docker 镜像内容再利用**：
   - 支持将 Docker 镜像转换为标准 rootfs 形式
   - 方便用于离线环境或进一步构建系统镜像
4. **系统测试流程集成**：
   - rootfs 中加入 lkp-tests、调试工具等
   - 用于性能测试、兼容性测试、安全测试等
5. **构建新镜像或固件时复用 rootfs**：
   - rootfs 可直接作为新系统的基础文件系统
   - 便于二次打包成 ISO、QCOW2、容器镜像等



## 业界方案

目前业界常见的 rootfs 生成方式包括：

1. **chroot/debootstrap/multistrap（Deb 系列）**
2. **mock / dnf --installroot / rpm-ostree（RPM 系列）**
3. **基于 Docker 导出文件系统**（docker export）
4. **vm_install → qcow2 → 挂载提取 rootfs**
5. **OpenStack / NeCTAR / image-factory 的自动化镜像构建脚本**（如 os-image-create.sh）

但这些方案往往只覆盖单一体系（例如只支持 deb，或只支持 qcow2），缺乏统一整合能力。本方案目标是构建一个 **可统一处理多种镜像来源的 rootfs 工具链**。



## 原型验证

### iso2qcow2

配置preseed.cfg 自动安装文件

```bash
root@Debian-12:/srv/preseed# cat /srv/preseed/preseed.cfg
# Minimal Preseed configuration
d-i debian-installer/locale string en_US
d-i keyboard-configuration/xkb-keymap select us
d-i console-setup/ask_detect boolean false
d-i console-setup/layoutcode string us

# Network
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string debian
d-i netcfg/get_domain string local

# Mirror
d-i mirror/country string manual
d-i mirror/http/hostname string deb.debian.org
d-i mirror/http/directory string /debian
d-i mirror/http/proxy string

# Clock
d-i clock-setup/utc boolean true
d-i time/zone string UTC

# Partitioning
d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

# User
d-i passwd/root-password password root
d-i passwd/root-password-again password root
d-i passwd/make-user boolean false

# Package selection
tasksel tasksel/first multiselect standard
d-i pkgsel/include string openssh-server

# Boot loader
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true
d-i finish-install/reboot_in_progress note

# Post-installation
d-i preseed/late_command string \
    in-target sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config; \
    in-target sed -i 's/PermitRootLogin no/PermitRootLogin yes/' /etc/ssh/sshd_config; \
    in-target apt-get clean;

root@Debian-12:/srv/preseed# python3 -m http.server 8000 &
```



安装依赖，并创建虚机安装iso

```bash
virt-install \
  --name debian-arm64 \
  --ram 4096 \
  --vcpus 4 \
  --disk path=/var/lib/libvirt/images/debian-12.qcow2,format=qcow2,size=10 \
  --cdrom /var/lib/libvirt/images/debian-12.12.0-arm64-DVD-1.iso \
  --network network=default,model=e1000 \
  --graphics none \
  --console pty,target_type=serial \
  --osinfo detect=on,require=off \
  --noautoconsole \
  --accelerate
  --wait -1  &
```

通过pexpect配置iso的grub，实现dvd iso的自动安装；（expect脚本跑总是失败，输入不到对应位置）

```python
import pexpect
import sys
import time


def auto_install_grub(vm_name, preseed_url):
    """
    自动配置GRUB启动参数以使用preseed文件进行自动化安装
    
    Args:
        vm_name: 虚拟机名称
        preseed_url: preseed文件的HTTP URL
    """
    cmd = f"virsh console {vm_name}"
    print(f"正在连接虚拟机: {cmd}")

    # spawn 启动进程
    child = pexpect.spawn(cmd)

    # [关键] 将所有输出实时打印到屏幕，方便调试 ANSI 乱码或状态
    child.logfile = sys.stdout.buffer

    # 设置较长的超时时间，防止启动慢导致脚本退出
    child.timeout = 300

    try:
        # ==========================================
        # 阶段 1: 等待 GRUB 菜单出现
        # 匹配特征文本: "Use the ^ and v keys to select"
        # ==========================================
        print("\n\n[状态] 等待 GRUB 菜单...")
        index = child.expect([
            r"Use the \^ and v keys to select",  # 匹配成功
            r"Press 'e' to edit",  # 另一种GRUB菜单格式
            r"Install",  # 直接显示Install选项
            pexpect.TIMEOUT,                     # 超时
            pexpect.EOF                          # 连接断开
        ])

        if index >= 3:  # TIMEOUT or EOF
            print("\n[错误] 未检测到 GRUB 菜单 (超时或连接关闭)")
            return False

        # 稍微缓冲一下，确保输入能被接收
        time.sleep(1)
        print("\n[动作] 检测到菜单，发送 'e' 进入编辑模式...")
        child.send('e')

        # ==========================================
        # 阶段 2: 等待编辑界面加载
        # 匹配特征文本: "Minimum Emacs-like screen editing is supported"
        # ==========================================
        print("\n[状态] 等待进入编辑模式...")
        index = child.expect([
            r"Minimum Emacs-like screen editing",
            r"linux",  # 直接看到linux行
            pexpect.TIMEOUT
        ])

        if index == 2:
            print("\n[错误] 未能进入编辑模式")
            return False
            
        print("\n[动作] 已进入编辑模式，开始导航...")
        time.sleep(1)

        # ==========================================
        # 阶段 3: 导航到 linux 行并追加参数
        # 使用 Emacs 快捷键比 ANSI 转义序列更可靠
        # ==========================================

        # 1. 向下移动找到 linux 行
        # 根据实际菜单位置，可能需要调整循环次数
        for i in range(3):
            child.sendcontrol('n')  # 发送 Ctrl+N (Next line)
            time.sleep(0.2)         # 给一点屏幕刷新时间

        # 2. 移动到行尾 (Ctrl+E)
        child.sendcontrol('e')      # 发送 Ctrl+E (End of line)
        time.sleep(0.5)

        # 3. 输入 Preseed 参数
        # 注意最前面的空格，防止和已有参数粘连
        params = f" auto=true priority=critical preseed/url={preseed_url} console=ttyS0"
        print(f"\n[动作] 输入参数: {params}")
        child.send(params)
        time.sleep(0.5)

        # ==========================================
        # 阶段 4: 启动 (Ctrl+X)
        # ==========================================
        print("\n[动作] 发送 Ctrl+X 启动系统...")
        child.sendcontrol('x') # 发送 Ctrl+X

        # ==========================================
        # 阶段 5: 等待安装开始
        # ==========================================
        print("\n[完成] GRUB配置完成，等待安装开始...")
        # 不调用interact()，让函数返回，主程序可以继续监控安装过程
        time.sleep(2)
        return True

    except Exception as e:
        print(f"\n[异常] 发生错误: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Debian/Ubuntu系统自动化安装脚本')
    parser.add_argument('vm_name', help='虚拟机名称')
    parser.add_argument('--preseed-url', required=True, help='Preseed文件的HTTP URL')
    
    args = parser.parse_args()
    auto_install_grub(args.vm_name, args.preseed_url)
```



### qcow2rootfs转rootfs

```sh
root@Debian-12:~# guestfish -i --ro -a  /var/lib/libvirt/images/debian-12.qcow2


Welcome to guestfish, the guest filesystem shell for
editing virtual machine filesystems and disk images.

Type: ‘help’ for help on commands
      ‘man’ to read the manual
      ‘quit’ to quit the shell
><fs> list-filesystems
/dev/sda1: vfat
/dev/sda2: ext4
/dev/sda3: swap
><fs> tar-out / /rootfs_temp.tar.gz compress:gzip numericowner:true xattrs:true selinux:true acls:true

><fs>
><fs> exit

root@Debian-12:~# ls /r
root/               rootfs_temp.tar.gz  run/
root@Debian-12:~# ls /r
root/               rootfs_temp.tar.gz  run/
root@Debian-12:~# ls -lh /rootfs_temp.tar.gz
-rw-r--r-- 1 root root 415M Nov 24 09:00 /rootfs_temp.tar.gz
```





## 实现方案

我当前要设计一个iso转rootfs，qcow2转rootfs，docker转rootfs的程序，其中iso转rootfs，需要真实安装，使用virt-install，同时支持deb和rpm两种格式，分别使用deb_expect.py 和rpm_expect.py来实现自动化设置preseed.cfg以及ks文件来实现；其中将iso2qcow2，qcow2rootfs，iso2rootfs，docker2rootfs个字写成一个文件，iso2rootfs调用iso2qcow2和qcow2rootfs，整体用python代码实现。生成的rootfs，提取他的kernel，并将剩下的内容打包成rootfs.cgz，cgz的压缩和解压使用两个函数放在lib中实现，是调用cpio和gzip来实现压缩的

### 1. 整体框架



### 2. ISO 转 rootfs

ISO → 自动安装 → 生成 qcow2 → 提取 rootfs

流程如下：

1. **virt-install 安装 ISO**
   - 支持 deb/ubuntu
   - 支持 rpm/centos/openEuler
2. **自动化安装配置**
   - deb 系列：使用 preseed.cfg，通过 deb_expect.py 注入
   - rpm 系列：使用 kickstart 文件，通过 rpm_expect.py 注入
3. **安装好的系统以 qcow2 形式存储**
4. **调用 qcow2rootfs 提取 rootfs**
5. **得到 rootfs.cgz**

### 3. qcow2 转 rootfs

qcow2 → 挂载 → rsync/rootfs copy → 打包

步骤：

1. qemu-nbd 挂载 qcow2
2. 找到 ROOT 分区并挂载
3. 将内容复制到指定目录作为 rootfs
4. 调用 cgz 压缩为 rootfs.cgz
5. 分离 kernel（/boot/vmlinuz-*）并单独输出

### 4. Docker 转 rootfs

docker image → docker export → rootfs

- 使用 `docker export` 获得文件系统内容
- 拆出 rootfs
- 按 rootfs 格式重新组织目录结构
- 输出 rootfs.cgz

### 5. rootfs.cgz 打包格式

使用 `cpio + gzip` 来实现，与内核 initramfs 格式一致。

cgz.py 提供两个函数：

```
def pack_to_cgz(src_dir, output_file):
    # 调用 cpio -o -H newc | gzip


def unpack_from_cgz(cgz_file, target_dir):
    # 调用 gzip -dc | cpio -idmv
```

### 6. 输出内容

每一次 rootfs 构建输出：

```
out/
├── kernel
├── initrd (optional)
└── rootfs.cgz
```

其中 kernel 来自 /boot 下的 vmlinuz 文件。



## 参考文档

https://github.com/NeCTAR-RC/nectar-images/blob/master/scripts/os-image-create.sh

https://gitee.com/weijihui/iso2qcow2

https://github.com/ionos-cloud/image-factory/blob/master/image-factory



