# rc-pv2hvm
a script that converts Rackspace Cloud Servers from PV to HVM mode
# Not complete!
This is pre-alpha software. README will be updated when this is ready.

## Use Case

Converts Rackspace Cloud Servers from PV to HVM mode. This should increase
performance and security.

## Requirements

Rackspace Cloud Server image.

## Usage

```bash
python rs-pv2hvm.py $IMG
```
where $IMG is a Rackspace Cloud server UUID.
