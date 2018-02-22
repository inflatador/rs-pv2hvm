# rs-pv2hvm
a script that performs the following steps:
 - Build server from image
 - Perform OS-level steps needed to support HVM mode
 - Image server
 - Set HVM mode flag on Cloud Server image
 - Rebuild new server on top of server created in first step

## Use Case

Converts Rackspace Cloud Servers from PV to HVM mode. This increases
performance and security.

## Requirements

Rackspace Cloud Server image.

## Compatibility

### Distros
 - CentOS/RHEL 6
 - Debian 7 
 - Ubuntu 12/14
Newer distro versions are only offered as PV-HVM, so no need for conversion.

### RackConnect

Not yet compatible with RackConnect v3 environments, but support is planned.

## Usage

```bash
python rs-pv2hvm.py $IMG
```
where $IMG is a Rackspace Cloud Server image UUID.
