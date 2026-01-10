#!/usr/bin/env python3
"""
ISO转QCOW2工具
使用virt-install进行真实安装，支持Debian/Ubuntu (deb) 和 RHEL/CentOS/Fedora (rpm)
"""

import argparse
import logging.config
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# 添加lib目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from lib.http_server import get_host_ip, start_http_server, check_firewall_status, check_http_server_accessible
from lib.deb_expect import auto_install_grub as deb_auto_install_grub
from lib.rpm_expect import auto_install_grub as rpm_auto_install_grub

if not logging.getLogger().hasHandlers():
    os.makedirs('logs', exist_ok=True)
    logger_config = os.path.join(str(Path(__file__).parent.parent), 'config','logger.conf')
    print(f"logger_config: {logger_config}")
    logging.config.fileConfig(logger_config, encoding="utf-8")

logger = logging.getLogger("common")

def detect_iso_type(iso_path):
    """
    检测ISO类型（deb或rpm）
    
    Returns:
        'deb' 或 'rpm' 或 None
    """
    mount_point = None
    try:
        # 创建临时挂载点
        mount_point = tempfile.mkdtemp(prefix='iso_mount_')
        
        # 挂载ISO
        subprocess.run(
            ['mount', '-o', 'ro,loop', iso_path, mount_point],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 检查Debian/Ubuntu特征
        mount_path = Path(mount_point)
        if (mount_path / 'dists').exists() or \
           (mount_path / 'pool').exists() or \
           (mount_path / 'install.amd').exists() or \
           (mount_path / 'install.netboot').exists() or \
           (mount_path / 'install').exists():
            return 'deb'
        
        # 检查RHEL/CentOS/Fedora特征
        if (mount_path / 'Packages').exists() or \
           (mount_path / 'repodata').exists() or \
           (mount_path / 'images').exists() or \
           (mount_path / 'BaseOS').exists():
            return 'rpm'
        
        return None
    
    except Exception as e:
        logger.warning(f"警告: 无法检测ISO类型: {e}")
        return None
    
    finally:
        if mount_point:
            try:
                subprocess.run(['umount', mount_point], check=False)
                os.rmdir(mount_point)
            except Exception:
                pass


def is_dvd_iso(iso_path):
    """
    检测是否为DVD ISO（无法使用extra-args的ISO）
    
    Returns:
        True 如果是DVD ISO，False 如果是netinst ISO
    """
    mount_point = None
    try:
        # 创建临时挂载点
        mount_point = tempfile.mkdtemp(prefix='iso_mount_')
        
        # 挂载ISO
        subprocess.run(
            ['mount', '-o', 'ro,loop', iso_path, mount_point],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        mount_path = Path(mount_point)
        
        # DVD ISO的特征：
        # - Debian/Ubuntu: 有dists或pool目录，但没有install.netboot
        # - RPM: 有Packages目录（完整DVD），而不是只有images/pxeboot
        
        # Debian/Ubuntu DVD检测
        if (mount_path / 'dists').exists() or (mount_path / 'pool').exists():
            # 如果有install.netboot，通常是netinst
            if not (mount_path / 'install.netboot').exists():
                return True
        
        # RPM DVD检测
        if (mount_path / 'Packages').exists():
            # 如果有完整的Packages目录，通常是DVD
            return True
        
        # 如果文件名包含DVD字样，也认为是DVD
        iso_name = Path(iso_path).name.lower()
        if 'dvd' in iso_name:
            return True
        
        return False
    
    except Exception as e:
        logger.warning(f"警告: 无法检测ISO类型: {e}")
        # 默认假设是netinst，可以使用extra-args
        return False
    
    finally:
        if mount_point:
            try:
                subprocess.run(['umount', mount_point], check=False)
                os.rmdir(mount_point)
            except Exception:
                pass




def get_template_dir():
    """获取模板目录路径"""
    script_dir = Path(__file__).parent
    template_dir = script_dir.parent / 'templates'
    return template_dir


def detect_distribution(iso_path):
    """
    从ISO文件名或内容检测发行版名称
    
    Returns:
        发行版名称 (debian, ubuntu, openeuler, centos, rhel, fedora) 或 None
    """
    iso_name = Path(iso_path).name.lower()
    
    # 从文件名检测
    if 'debian' in iso_name:
        return 'debian'
    elif 'ubuntu' in iso_name:
        return 'ubuntu'
    elif 'openeuler' in iso_name or 'open-euler' in iso_name:
        return 'openeuler'
    elif 'centos' in iso_name:
        return 'centos'
    elif 'rhel' in iso_name or 'redhat' in iso_name or 'red-hat' in iso_name:
        return 'rhel'
    elif 'fedora' in iso_name:
        return 'fedora'
    
    return None


def load_template_config(distribution, iso_type):
    """
    从模板目录加载配置文件
    
    Args:
        distribution: 发行版名称 (debian, ubuntu, openeuler, centos, rhel, fedora)
        iso_type: ISO类型 ('deb' 或 'rpm')
    
    Returns:
        配置文件内容字符串，如果模板不存在则返回None
    """
    template_dir = get_template_dir()
    
    if iso_type == 'deb':
        # deb系统使用preseed.cfg
        if distribution is None:
            # 默认使用debian模板
            distribution = 'debian'
        template_file = template_dir / distribution / 'preseed.cfg'
    else:
        # rpm系统使用ks.ks
        if distribution is None:
            # 默认使用centos模板
            distribution = 'centos'
        template_file = template_dir / distribution / 'ks.ks'
    
    if template_file.exists():
        with open(template_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    return None


def generate_from_template(output_path, distribution, iso_type):
    """
    从模板生成配置文件
    
    Args:
        output_path: 输出文件路径
        distribution: 发行版名称
        iso_type: ISO类型 ('deb' 或 'rpm')
    
    Raises:
        FileNotFoundError: 如果模板文件不存在
    """
    template_content = load_template_config(distribution, iso_type)
    if not template_content:
        template_dir = get_template_dir()
        if iso_type == 'deb':
            template_file = template_dir / distribution / 'preseed.cfg'
        else:
            template_file = template_dir / distribution / 'ks.ks'
        raise FileNotFoundError(
            f"模板文件不存在: {template_file}\n"
            f"请确保 templates/{distribution}/ 目录下有对应的配置文件，"
            f"或使用 -p/-k 参数提供自定义配置文件"
        )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template_content)


def iso2qcow2(iso_path, output_qcow2, preseed_file=None, ks_file=None,
              disk_size='20G', memory=2048, vcpus=2, timeout=3600,
              vm_name=None, distribution=None, http_port=8080):
    """
    将ISO转换为QCOW2镜像
    
    Args:
        iso_path: ISO文件路径
        output_qcow2: 输出QCOW2文件路径
        preseed_file: Preseed文件路径（Debian/Ubuntu）
        ks_file: Kickstart文件路径（RHEL/CentOS/Fedora）
        disk_size: 磁盘大小
        memory: 内存大小（MB）
        vcpus: CPU核心数
        timeout: 安装超时时间（秒）
        vm_name: 虚拟机名称（如果为None则自动生成）
    """
    iso_path = Path(iso_path).resolve()
    if not iso_path.exists():
        raise FileNotFoundError(f"ISO文件不存在: {iso_path}")
    
    output_qcow2 = Path(output_qcow2).resolve()
    output_qcow2.parent.mkdir(parents=True, exist_ok=True)
    
    # 检测ISO类型
    iso_type = detect_iso_type(str(iso_path))
    if iso_type is None:
        logger.warning("警告: 无法自动检测ISO类型，尝试使用提供的配置文件")
        if preseed_file:
            iso_type = 'deb'
        elif ks_file:
            iso_type = 'rpm'
        else:
            raise ValueError("无法确定ISO类型，请提供preseed或kickstart文件")
    
    logger.info(f"检测到ISO类型: {iso_type}")
    
    # 检测发行版（如果未指定）
    if distribution is None:
        distribution = detect_distribution(str(iso_path))
        if distribution:
            logger.info(f"检测到发行版: {distribution}")
    
    # 生成虚拟机名称
    if vm_name is None:
        vm_name = f"iso2qcow2_{int(time.time())}"
    
    # 创建临时目录用于HTTP服务器
    temp_dir = tempfile.mkdtemp(prefix='iso2qcow2_')
    http_server = None

    def remove_fd(vm_name):
        vm_file = "/var/lib/libvirt/qemu/nvram/" + vm_name + "_VARS.fd"
        if os.path.exists(vm_file):
            os.remove(vm_file)
            logger.info(f"成功删除文件：{vm_file}")
        else:
            logger.warning(f"{vm_file}文件不存在")

    def ensure_vm_stopped(vm_name, max_retries=5, shutdown_timeout=30):
        """
        确保虚拟机已停止，先尝试优雅关机，失败后强制销毁。
        返回True如果虚拟机已停止或不存在，否则返回False。
        """
        
        for attempt in range(max_retries):
            # 检查虚拟机状态
            try:
                result = subprocess.run(
                    ['virsh', 'domstate', vm_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                state = result.stdout.strip()
            except subprocess.TimeoutExpired:
                logger.info(f"检查虚拟机状态超时，尝试关闭...")
                state = 'unknown'
            except Exception as e:
                # 虚拟机可能不存在（已销毁或未定义）
                logger.warning(f"无法获取虚拟机状态（可能不存在）: {e}")
                break  # 视为已停止
            
            if state in ('shut off', 'shutdown', 'in shutdown'):
                logger.info(f"虚拟机 {vm_name} 已停止")
                break
            elif state in ('running', 'idle', 'paused', 'blocked'):
                if attempt == 0:
                    logger.info(f"虚拟机 {vm_name} 状态为 {state}，尝试优雅关机...")
                    subprocess.run(['virsh', 'shutdown', vm_name], check=False)
                else:
                    logger.info(f"虚拟机 {vm_name} 状态仍为 {state}，等待 {shutdown_timeout} 秒...")
                
                # 等待关机
                wait_start = time.time()
                grace_flag = False
                while time.time() - wait_start < shutdown_timeout:
                    time.sleep(2)
                    try:
                        result = subprocess.run(
                            ['virsh', 'domstate', vm_name],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if 'shut off' in result.stdout:
                            logger.info(f"虚拟机 {vm_name} 已优雅关机")
                            grace_flag = True
                            break
                    except Exception:
                        pass
                
                # 超时后强制销毁
                if not grace_flag:
                    logger.info(f"优雅关机超时，尝试强制销毁...")
                    subprocess.run(['virsh', 'destroy', vm_name], check=False)
                    # 继续循环，下一次迭代将检查状态
                else:
                    break

            else:
                # 其他状态（如 'crashed', 'pmsuspended'）也尝试销毁
                logger.info(f"虚拟机 {vm_name} 状态为 {state}，尝试强制销毁...")
                subprocess.run(['virsh', 'destroy', vm_name], check=False)
        
        # 最终检查
        try:
            result = subprocess.run(
                ['virsh', 'domstate', vm_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            logger.info(f"关闭虚拟机 {vm_name}最终检查输出:{result.stdout} ")
            if 'shut off' in result.stdout:
                logger.info(f"虚拟机 {vm_name} 最终已停止")
            remove_fd(vm_name)
            subprocess.run(['virsh', 'undefine', vm_name, '--nvram'], check=False, capture_output=True)
            return True
        except Exception:
            pass
        
        logger.warning(f"警告: 无法确保虚拟机 {vm_name} 停止")
        return False

    try:
        # 设置配置文件
        if iso_type == 'deb':
            if preseed_file:
                shutil.copy(preseed_file, Path(temp_dir) / 'preseed.cfg')
                logger.info(f"使用提供的preseed文件: {preseed_file}")
            else:
                # 如果没有指定发行版，尝试使用debian作为默认
                if distribution is None:
                    distribution = 'debian'
                    logger.info(f"未检测到发行版，使用默认模板: templates/{distribution}/preseed.cfg")
                else:
                    logger.info(f"使用模板: templates/{distribution}/preseed.cfg")
                generate_from_template(Path(temp_dir) / 'preseed.cfg', distribution, 'deb')
            config_url = f"http://{get_host_ip()}:{http_port}/preseed.cfg"
        else:  # rpm
            if ks_file:
                # 保持原始文件名，但如果是.ks结尾则直接使用
                ks_filename = Path(ks_file).name
                if not ks_filename.endswith('.ks'):
                    ks_filename = 'ks.ks'
                shutil.copy(ks_file, Path(temp_dir) / ks_filename)
                logger.info(f"使用提供的kickstart文件: {ks_file}")
                config_url = f"http://{get_host_ip()}:{http_port}/{ks_filename}"
            else:
                # 如果没有指定发行版，尝试使用centos作为默认
                if distribution is None:
                    distribution = 'centos'
                    logger.info(f"未检测到发行版，使用默认模板: templates/{distribution}/ks.ks")
                else:
                    logger.info(f"使用模板: templates/{distribution}/ks.ks")
                generate_from_template(Path(temp_dir) / 'ks.ks', distribution, 'rpm')
                config_url = f"http://{get_host_ip()}:{http_port}/ks.ks"
        
        # 启动HTTP服务器
        logger.info(f"启动HTTP服务器在端口{http_port}...")
        http_server, http_thread = start_http_server(temp_dir, port=http_port)
        
        # 验证HTTP服务器可访问性
        host_ip = get_host_ip()
        config_filename = 'preseed.cfg' if iso_type == 'deb' else 'ks.ks'
        
        # 检查防火墙状态
        check_firewall_status(http_port)
        
        if not check_http_server_accessible(host_ip, http_port, config_filename):
            logger.warning(f"警告: HTTP服务器可能无法从虚拟机访问")
            logger.info(f"请确保防火墙允许端口{http_port}，或使用以下命令临时开放端口:")
            logger.info(f"  sudo firewall-cmd --add-port={http_port}/tcp --permanent && sudo firewall-cmd --reload  # firewalld")
            logger.info(f"  sudo ufw allow {http_port}/tcp               # ufw")
            logger.info(f"  sudo iptables -A INPUT -p tcp --dport {http_port} -j ACCEPT  # iptables")
            logger.info(f"或者尝试使用不同的端口: --http-port 参数")
        
        logger.info(f"配置文件URL: {config_url}")
        
        # 检测是否为DVD ISO
        is_dvd = is_dvd_iso(str(iso_path))
        if is_dvd:
            logger.info("检测到DVD ISO，将使用expect脚本配置GRUB（不支持extra-args）")
        else:
            logger.info("检测到netinst ISO，可以使用extra-args")
        
        # 构建virt-install命令
        virt_install_cmd = [
            'virt-install',
            '--name', vm_name,
            '--ram', str(memory),
            '--vcpus', str(vcpus),
            '--disk', f'path={output_qcow2},size={disk_size},format=qcow2',
            '--network', 'network=default,model=virtio',
            '--graphics', 'none',
            '--osinfo', 'detect=on,require=off',
            '--console', 'pty,target_type=serial',
            '--boot', 'loader=/usr/share/AAVMF/AAVMF_CODE.fd,loader.readonly=yes,loader.type=pflash,nvram.template=/usr/share/AAVMF/AAVMF_VARS.fd'
        ]
        
        # 检查默认网络是否运行
        try:
            result = subprocess.run(
                ['virsh', 'net-info', 'default'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.warning("警告: 默认网络可能未运行，尝试启动...")
                subprocess.run(['virsh', 'net-start', 'default'], check=False)
                subprocess.run(['virsh', 'net-autostart', 'default'], check=False)
        except Exception as e:
            logger.error(f"网络检查失败: {e}")
        
        # DVD ISO使用--cdrom，netinst使用--location
        if is_dvd:
            virt_install_cmd.extend(['--cdrom', str(iso_path)])
        else:
            virt_install_cmd.extend(['--location', str(iso_path)])
            # 只有netinst ISO可以使用extra-args
            if iso_type == 'deb':
                virt_install_cmd.extend(['--extra-args', f'auto=true priority=critical preseed/url={config_url} console=ttyS0'])
            else:
                virt_install_cmd.extend(['--extra-args', f'inst.ks={config_url} console=ttyS0'])
        
        virt_install_cmd.extend(['--wait', '-1', '--noautoconsole'])
        
        logger.info(f"执行virt-install命令...")
        logger.debug(f"命令: {' '.join(virt_install_cmd)}")
        
        # 执行virt-install
        process = subprocess.Popen(
            virt_install_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 如果是DVD ISO，需要等待虚拟机启动后使用expect配置GRUB
        if is_dvd:
            logger.info("\n等待虚拟机启动...")
            time.sleep(2)  # 等待虚拟机启动
            
            # 等待虚拟机进入运行状态
            max_wait = 60
            waited = 0
            while waited < max_wait:
                try:
                    result = subprocess.run(
                        ['virsh', 'domstate', vm_name],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if 'running' in result.stdout:
                        logger.info("虚拟机已启动，开始配置GRUB...")
                        break
                except Exception:
                    pass
                time.sleep(2)
                waited += 2
            
            # 使用expect脚本配置GRUB
            logger.info("\n使用expect脚本配置GRUB启动参数...")
            if iso_type == 'deb':
                success = deb_auto_install_grub(vm_name, config_url)
            else:
                success = rpm_auto_install_grub(vm_name, config_url)
            
            if not success:
                logger.warning("警告: GRUB配置可能失败，但继续安装过程...")
        
        # 等待安装完成或超时
        start_time = time.time()
        while True:
            if process.poll() is not None:
                break
            
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"安装超时（{timeout}秒），终止虚拟机...")
                subprocess.run(['virsh', 'destroy', vm_name], check=False)
                raise TimeoutError(f"安装超时: {timeout}秒")
            
            time.sleep(10)
            # 检查虚拟机状态
            try:
                result = subprocess.run(
                    ['virsh', 'domstate', vm_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if 'shut off' in result.stdout:
                    logger.info("虚拟机已关闭，安装可能已完成")
                    break
            except Exception:
                pass
        
        # 等待进程结束
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"virt-install错误输出: {stderr}")
            raise RuntimeError(f"virt-install失败: {stderr}")
        
        logger.info("安装完成!")
        
    finally:
        # 确保虚拟机已停止
        try:
            ensure_vm_stopped(vm_name)
        except Exception as e:
            logger.warning(f"警告: 虚拟机关闭过程中出现错误: {e}")
        
        # 停止HTTP服务器
        if http_server:
            http_server.shutdown()
        
        # 清理临时目录
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(description='ISO转QCOW2工具')
    parser.add_argument('-i', '--iso', required=True, help='ISO文件路径')
    parser.add_argument('-o', '--output', required=True, help='输出QCOW2文件路径')
    parser.add_argument('-p', '--preseed', help='Preseed文件路径（Debian/Ubuntu）')
    parser.add_argument('-k', '--kickstart', help='Kickstart文件路径（RHEL/CentOS/Fedora/OpenEuler）')
    parser.add_argument('-d', '--distribution', 
                        choices=['debian', 'ubuntu', 'openeuler', 'centos', 'rhel', 'fedora'],
                        help='指定发行版名称（用于自动选择模板，如果不指定则从ISO文件名检测）')
    parser.add_argument('-s', '--size', default='20G', help='磁盘大小（默认: 20G）')
    parser.add_argument('-m', '--memory', type=int, default=2048, help='内存大小MB（默认: 2048）')
    parser.add_argument('-c', '--vcpus', type=int, default=2, help='CPU核心数（默认: 2）')
    parser.add_argument('-t', '--timeout', type=int, default=3600, help='安装超时时间秒（默认: 3600）')
    parser.add_argument('-n', '--vm-name', help='虚拟机名称（默认: 自动生成）')
    parser.add_argument('--http-port', type=int, default=8080, help='HTTP服务器端口（默认: 8080）')
    
    args = parser.parse_args()
    
    try:
        iso2qcow2(
            args.iso,
            args.output,
            preseed_file=args.preseed,
            ks_file=args.kickstart,
            disk_size=args.size,
            memory=args.memory,
            vcpus=args.vcpus,
            timeout=args.timeout,
            vm_name=args.vm_name,
            distribution=args.distribution,
            http_port=args.http_port
        )
        logger.info(f"成功创建QCOW2镜像: {args.output}")
    except Exception as e:
        logger.error(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

