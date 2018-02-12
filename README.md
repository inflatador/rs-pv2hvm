# rc-pv2hvm
a script that converts Rackspace Cloud Servers from PV to HVM mode
# Not complete!
This is pre-alpha software. README will be updated when this is ready.

## Use Case

Converts Rackspace Cloud Servers from PV to HVM mode. This increases
performance and security.

## Requirements

Rackspace Cloud Server image. Works with CentOS/RHEL 6, Debian 7, and Ubuntu 12/14.

## Usage

```bash
python rs-pv2hvm.py $IMG
```
where $IMG is a Rackspace Cloud server UUID.
