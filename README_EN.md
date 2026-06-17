# RootFS Generation Tool

This toolset is used to automatically convert ISO and QCOW2 images into the `rootfs` directory, extract the Linux kernel, and compress the images into the .cgz format. It supports mainstream Linux distributions, such as Debian or Ubuntu (Debian-based) and RHEL, CentOS, Fedora,or openEuler (RPM-based).

## Function

- **ISO to rootfs**: The real virt-install installation is used to automatically respond to configurations (custom templates are supported).
- **QCOW2 to rootfs**: The complete root file system (rootfs) is extracted directly from QCOW2 images.
- **Automatic kernel extraction**: Kernel files are automatically searched for and separated from images.
- **CGZ compression**: The rootfs directory can be packed into the gzip-compressed cpio format (.cgz).

## Environment Setup

### Quick Start

Run the script to automatically initialize the environment:

```bash
python3 setup.py
# or
uv run python setup.py
```

The setup script performs the following operations:

1. Check and install `uv`.
2. Verify and display missing system dependencies (such as virt-install and qemu-nbd).
3. Configure the Python virtual environment.
4. Install the Python dependency.

### Basic Dependency

- Python 3.8+
- [`uv`](https://github.com/astral-sh/uv) (recommended dependency manager)
- `virt-install` (ISO to QCOW2 virtualization installation)
- `qemu-nbd` (QCOW2 mounting, required in Linux)
- `cpio`, `gzip` (rootfs .cgz compression)
- `libvirt` (virtualization backend support)
- `pexpect` (Linux automatic installation interaction script)

#### System Dependency Installation

**Debian/Ubuntu**

```bash
sudo apt-get update
sudo apt-get install -y libvirt qemu-utils cpio gzip virt-install
```

**RHEL/CentOS/Fedora**

```bash
sudo yum install -y libvirt qemu-img cpio gzip virt-install
```

#### Python Dependency Installation

`uv` method (recommended):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

Or conventional method:

```bash
pip install -r requirements.txt
```

## Project Structure

```sh
gen_rootfs/
├── src/
│   ├── iso2qcow2.py      # Convert ISO images to QCOW2 format.
│ ├── qcow2rootfs.py # Extract rootfs from QCOW2.
│ ├── iso2rootfs.py # Convert ISO to rootfs (one-click integration).
│ ├── deb_expect.py # Automation script for Debian or Ubuntu installation.
│ ├── rpm_expect.py # Automation script for RPM-based installation.
│   └── lib/
│       ├── __init__.py
│ └── cgz_utils.py # Tool for gzip-compressed cpio format (.cgz) packaging.
├── templates/
│   ├── debian/preseed.cfg
│   ├── ubuntu/preseed.cfg
│   ├── openeuler/ks.ks
│   ├── centos/ks.ks
│   ├── rhel/ks.ks
│   └── fedora/ks.ks
├── demo/ # Test case script.
└── doc/ # Document.
```

## Example

### 1. Converting ISO to rootfs (recommended, automatically generating rootfs from ISO)

```bash
# Automatic template mode
./src/iso2rootfs.py -i debian-12.iso -o ./output

# Specifying a distribution template
./src/iso2rootfs.py -i centos-7.iso -o ./output -d centos

# Customizing the preseed or kickstart file
./src/iso2rootfs.py -i debian.iso -o ./output -p custom-preseed.cfg
./src/iso2rootfs.py -i centos.iso -o ./output -k custom.ks

# Common parameters
./src/iso2rootfs.py \
    -i debian.iso \
    -o ./output \
    -d debian \
    -s 30G \
    -m 4096 \
    -c 4 \
    -t 7200
```

**Key parameters:**

- `-i, --iso`: ISO path.
- `-o, --output`: output directory.
- `-p, --preseed`: automatic Debian-based configuration (if customization is required).
- `-k, --kickstart`: automatic RPM-based configuration (if customization is required).
- `-d, --distribution`: distribution name (such as Debian, Ubuntu, or CentOS).
- `-s, --size`: size of the virtual drive. The default value is `20` GB.
- `-m, --memory`: VM memory size, in MB. The default value is `2048`.
- `-c, --vcpus`: number of CPU cores of a VM. The default value is `2`.
- `-t, --timeout`: installation timeout interval. The default value is `3600`.
- `--kernel`: kernel output path. The default value is `output/kernel`.
- `--no-cgz`: does not generate a .cgz compressed package.
- `--keep-qcow2`: retains the intermediate file of QCOW2.

### 2. QCOW2 to rootfs

Quickly extract the existing QCOW2 to rootfs.

```bash
./src/qcow2rootfs.py -i vm.qcow2 -o ./output

# Enhanced example
./src/qcow2rootfs.py -i vm.qcow2 -o ./output --kernel ./kernel --no-cgz
```

### 3. Convert ISO to QCOW2 (if only QCOW2 virtual disks are required)

```bash
./src/iso2qcow2.py -i debian.iso -o debian.qcow2 -p preseed.cfg
```

### 4. Independent CGZ Compression/Decompression

```bash
python3 src/lib/cgz_utils.py compress /path/to/rootfs output.cgz
python3 src/lib/cgz_utils.py extract rootfs.cgz /path/to/output
```

## Output Structure Description

The standard output is as follows:

```sh
output/
├── kernel # Separated vmlinuz.
├── rootfs/ # Complete root file system.
│   ├── bin/
│   ├── etc/
│   └── ...
└── rootfs.cgz # Compressed package (optional).
```

## Configuration Template Mechanism

All automatic installation configuration templates are stored in the `templates/` directory and can be customized and overwritten.

- **debian/ubuntu**: `preseed.cfg`
- **openeuler/centos/rhel/fedora**: `ks.ks` (kickstart)

### Template Priority (Automatic Selection Sequence)

1. Specify a template using `-p` or `-k`. This takes the highest priority.
2. Specify a distribution template using `-d`.
3. Obtain a template by automatically identifying the ISO file name.
4. Use `debian` or `centos`, which is the default option.

## Workflow Overview

### ISO to rootfs

1. Analyze the ISO type (Debian-based or RPM-based).
2. Prepare automatic configuration file and provide services through HTTP.
3. Use virt-install for automatic installation and interaction with GRUB or bootloaders.
4. Obtain the QCOW2 file.
5. Use qemu-nbd to mount the file, extract the system file and kernel, and generate the output (including .cgz packages)

### QCOW2 to rootfs

- Use qemu-nbd to mount the file, extract rootfs and kernel, and compress the output.

### Differences Between DVD ISO and netinst ISO

- netinst ISO: performs automatic installation by using the `extra-args` parameter.
- DVD ISO: requires automated GRUB interaction to insert the configuration URL parameter.

## Troubleshooting

### Faults Related to virt-install

- Check the libvirt service and permissions.
- You are advised to run the command as the root user or ensure that the user is added to the libvirt group.

```bash
sudo systemctl status libvirt
sudo systemctl start libvirt
virsh net-list
```

### QCOW2 Mounting Failures

- Check whether the qemu-nbd and nbd kernel modules have been loaded.

```bash
sudo modprobe nbd max_part=16
which qemu-nbd
```

### Installation Timeout

- Add the `-t` parameter or increase the VM resource allocation.

## Precautions

- This document is mainly applicable to Linux. Some phases (for macOS) are unavailable.
- Some operations require the root permission.
- The HTTP service of the local host must be accessible for automatic installation using an ISO file.
- The VM drive and memory must be sufficient. Otherwise, the installation may time out.

## Development and Extension Reference

The main logic is divided as follows:

- `iso2qcow2.py`: Automates full-virtualization installation to convert ISO to QCOW2.
- `qcow2rootfs.py`: mounts QCOW2 and performs extraction.
- `iso2rootfs.py`: serves as the entry to automatically integrate the preceding two steps.
- `lib/cgz_utils.py`: standardizes `cpio` or `gz` packaging.

To support the extraction and conversion of other rootfs, you can compile new scripts by referring to the preceding structure.

## License

[Please fill in the specific license.]

## Contribution

You are welcomed to submit issues, PRs, and suggestions.
