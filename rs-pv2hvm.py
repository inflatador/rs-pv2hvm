#!/usr/bin/env python
# rc-pv2hvm, a script that converts Rackspace Cloud Servers from PV to HVM mode
# version: 0.0.3a
# Copyright 2018 Brian King
# License: Apache

import argparse
import base64
from collections import defaultdict
import datetime
from getpass import getpass
import json
import keyring
import os
import plac
import re
import requests
import sys
import time
import uuid


def getset_keyring_credentials(username=None, password=None):
    """Method to retrieve credentials from keyring."""
    username = keyring.get_password("raxcloud", "username")
    if username is None:
        if sys.version_info.major < 3:
            username = raw_input("Enter Rackspace Username: ")
            keyring.set_password("raxcloud", 'username', username)
            print ("Username value saved in keychain as raxcloud username.")
        elif creds == "username":
            username = input("Enter Rackspace Username: ")
            keyring.set_password("raxcloud", 'username', username)
            print ("Username value saved in keychain as raxcloud username.")
    else:
        print ("Authenticating to Rackspace cloud as %s" % username)
    password = keyring.get_password("raxcloud", "password")
    if password is None:
        password = getpass("Enter Rackspace API key:")
        keyring.set_password("raxcloud", 'password' , password)
        print ("API key value saved in keychain as raxcloud password.")
    return username, password

def wipe_keyring_credentials(username, password):
    """Wipe credentials from keyring."""
    try:
        keyring.delete_password('raxcloud', 'username')
        keyring.delete_password('raxcloud', 'password')
    except:
        pass

    return True

# Request to authenticate using password
def get_auth_token(username,password):
    #setting up api call
    url = "https://identity.api.rackspacecloud.com/v2.0/tokens"
    headers = {'Content-type': 'application/json'}
    payload = {'auth':{'passwordCredentials':{'username': username,'password': password}}}
    payload2 = {'auth':{'RAX-KSKEY:apiKeyCredentials':{'username': username,'apiKey': password}}}

    #authenticating against the identity
    try:
        r = requests.post(url, headers=headers, json=payload)
    except requests.ConnectionError as e:
        print("Connection Error: Check your interwebs!")
        sys.exit()


    if r.status_code != 200:
        r = requests.post(url, headers=headers, json=payload2)
        if r.status_code != 200:
            print ("Error! API responds with %d" % r.status_code)
            print("Rerun the script and you will be prompted to re-enter username/password.")
            wipe_keyring_credentials(username, password)
            sys.exit()
        else:
            print("Authentication was successful!")
    elif r.status_code == 200:
        print("Authentication was successful!")

    #loads json reponse into data as a dictionary.
    data = r.json()
    #assign token and account variables with info from json response.
    auth_token = data["access"]["token"]["id"]
    return auth_token

def find_endpoints(auth_token):
    #init Cloud Servers endpoints as an empty list
    glance_endpoints=[]
    cs_endpoints=[]
    #setting up api call
    url = ("https://identity.api.rackspacecloud.com/v2.0/tokens/%s/endpoints" % auth_token)
    headers = {'content-type': 'application/json', 'Accept': 'application/json',
               'X-Auth-Token': auth_token}
    raw_service_catalog = requests.get(url, headers=headers)
    the_service_catalog = raw_service_catalog.json()
    endpoints = the_service_catalog["endpoints"]
    for service in range(len(endpoints)):
        if "cloudImages" == endpoints[service]["name"]:
            glance_endpoints.append(endpoints[service]["publicURL"])
        if "cloudServersOpenStack" == endpoints[service]["name"]:
            cs_endpoints.append(endpoints[service]["publicURL"])
    return glance_endpoints, cs_endpoints, headers

def find_glance_image_and_cs_endpoint(auth_token, headers, cs_endpoints, glance_endpoints, glance_image):
    print ("Determining which region your cloud server image is in...")
    for endpoint in range(len(glance_endpoints)):
        potential_url = ( "%s/images/%s" % (glance_endpoints[endpoint], glance_image) )
        potential_image = requests.get(url=potential_url, headers=headers)
        if potential_image.status_code == 200:
            glance_object = potential_image
            region = potential_url.split('//')[1].split('.')[0]
            print ("Found image %s in %s region" % (glance_image, region))
            break
    for endpoint in cs_endpoints:
        if region in endpoint:
            cs_endpoint = endpoint
    return glance_object, cs_endpoint, region

    #if we make it this far, the glance image UUID is invalid
    print ("Error! Rackspace Cloud Server Image UUID %s was not found." % (glance_image) )
    sys.exit()

def check_glance_image(auth_token, headers, glance_image, glance_object):
    # sanity checks
    print ("Verifying image status...")
    glance_image_type = (glance_object.json()["image_type"])
    # will not try to convert base image
    if glance_image_type != "snapshot":
        print ("Error! I won't convert a base image.")
        sys.exit()
    glance_status = (glance_object.json()["status"])
    if glance_status != "active":
        print ("Error! Wrong status for glance image %s. Expected 'active' ,\
        but found '%s'" % (glance_image, glance_status))
        sys.exit()
    # vm_mode is not always set. Without it, servers will build in PV mode.
    if "vm_mode" not in glance_object.json():
        glance_object.json()["vm_mode"] = ""
    else:
        image_vm_mode = glance_object.json()["vm_mode"]
        if image_vm_mode == "hvm":
            print(
            "Error! Image vm_mode already set to HVM, conversion not needed."
            )
            sys.exit()
    # Confirm the OS is supported
    image_os = (glance_object.json()["org.openstack__1__os_distro"])
    return image_os
    image_version = (glance_object.json()["org.openstack__1__os_version"])
    supported_os =('centos', 'debian', 'redhat', 'ubuntu')
    supported = False
    for os in supported_os:
        if os in image_os:
            #Check RHEL/CentOS version. We don't do this with Deb/Ubuntu because
            # release upgrades make this value unreliable
            if image_os == 'com.redhat' or 'org.centos':
                if "6." in image_version:
                    supported = True
                else:
                    supported = False
            supported = True
    if supported == False:
        print("Error! Image built from unsupported OS! Exiting.")
        sys.exit()

def determine_cs_flavor(auth_token, headers, glance_image, glance_object):
    # for speed's sake, we will build General Purpose servers if possible
    min_disk = (glance_object.json()["min_disk"])
    if min_disk <= 160:
        disk_multiplier = 20
        flavor_type = "general"
        if (min_disk % disk_multiplier) != 0:
            print ("Error! min_disk value should be a multiple of 20.")
            sys.exit()
        flavor_memory = str(min_disk / disk_multiplier)
        flavor = flavor_type + "1-" + flavor_memory
        return flavor
    elif min_disk == 320:
        flavor = 6
        return flavor
    elif min_disk == 620:
        flavor = 7
        return flavor
    elif min_disk == 1200:
        flavor = 8
        return flavor
    print ("Error! Could not determine flavor to use.")
    sys.exit()

def build_server(auth_token, headers, cs_endpoint, glance_image, glance_object, image_os, flavor):
    cs_endpoint = ("%s/servers" % (cs_endpoint))
    image_name=(glance_object.json()["name"])
    rand_postpend = str(uuid.uuid4())
    cs_name = image_name + "-pv2hvm-" + rand_postpend[0:7]
    #The script to inject at boot time. For Deb/Ubuntu, we use cloud-init.
    if image_os == "com.ubuntu" or image_os == "org.debian":
        dl_script = '''
        #cloud-config
        packages:
          - grub
        runcmd:
          - [sh, -xc, "wget -qO /tmp/hvm.sh http://e942b029c256ec323134-d1408b968928561823109cb66c47ebcd.r37.cf5.rackcdn.com/hvm.sh " ]
          - [sh, -xc, "bash /tmp/hvm.sh" ]
        '''
        user_data = base64.b64encode(dl_script)
        payload = (
                    { "server": {"name": cs_name, "key_name": "rackesc",
                    "imageRef": glance_image, "flavorRef": flavor,
                    "config_drive": True,
                    "user_data": user_data }}
                  )
    elif "centos" in image_os or "redhat" in image_os:
    #The script to inject at boot time.
    #We can't use cloud-init on RH as it's not installed on older images.
    #Instead, we use server personality.
    #We have to use a crontab because of personality doesn't inject files with
    #the execute bit.
        path = "/var/spool/cron/root"
        dl_script =  '''
#Download script to perform PV to HVM conversion
@reboot /usr/bin/wget -qO /tmp/hvm.sh http://e942b029c256ec323134-d1408b968928561823109cb66c47ebcd.r37.cf5.rackcdn.com/hvm.sh; /bin/bash /tmp/hvm.sh
'''
        personality = base64.b64encode(dl_script)
        payload = (
            { "server": {"name": cs_name, "key_name": "rackesc",
                        "imageRef": glance_image, "flavorRef": flavor,
                        "personality": [{"path": path,
                        "contents": personality}]}}
                    )
    #FIXME: remove SSH key in final version
    cs_object = requests.post(url=cs_endpoint, headers=headers, json=payload)
    cs_url = cs_object.json()["server"]["links"][0]["href"]
    print("Sent build request for server %s" % (cs_name))
    return cs_name, cs_object, cs_url

def poll_cs_status(auth_token, headers, cs_name, cs_object, cs_url, image_os):
    period = "."
    counter = 1
    cs_status = "INIT"
    while cs_status != "ACTIVE":
        try:
            cs_status_object = requests.get(url=cs_url, headers=headers)
        except requests.ConnectionError as e:
            print("Can't connect to API, trying again....")
        if cs_status_object.status_code == 200:
            cs_status = cs_status_object.json()["server"]["status"]
        print ("Server %s is in %s status%s" % (cs_name, cs_status, (period * counter)))
        counter = counter + 1
        time.sleep(15)
    if "centos" in image_os or "redhat" in image_os:
        reboot_server(auth_token, headers, cs_name, cs_url)

def reboot_server(auth_token, headers, cs_name, cs_url):
    print ("Rebooting server %s to activate the script" % (cs_name))
    cs_url = ("%s/action" % (cs_url))
    payload = (
    { "reboot": {
                "type" : "HARD"
                }
    }
                )
    rb_request = requests.post(url=cs_url, headers=headers,json=payload)
    rb_request.raise_for_status()

def create_cs_image(auth_token, headers, cs_name, cs_object, cs_url):
#sleep so the script can convert the servers
    print ("Sleeping for 4 minutes so the script can finish.")
    for step in xrange(240,0,-1):
        time.sleep(1)
        sys.stdout.write(str(step)+' ')
        sys.stdout.flush()
    print ("Creating image of server %s" % (cs_name))
    cs_url = ("%s/action" % (cs_object.json()["server"]["links"][0]["href"]))
    rand_postpend = str(uuid.uuid4())
    image_creator = "rs-pv2hvm"
    image_name = ("%s-%s" % (cs_name, image_creator))
    payload = (
    { "createImage" : {
        "name" : image_name,
        "metadata": {
            "created_by": image_creator
                    }
                        }
    }
                )
    image_create = requests.post(url=cs_url, headers=headers, json=payload)
    image_create.raise_for_status()
    if image_create.ok:
        image_url = image_create.headers["Location"]
        return image_name, image_url
    #if we made it this far, somehow we never got the image URL.
    if not image_url:
        print ("Error! Did not receive image URL from Cloud Servers API. Exiting." )
        sys.exit()


def poll_image_status(auth_token, headers, image_name, image_url):
    image_info = requests.get(url=image_url, headers=headers)
    image_status=image_info.json()["image"]["status"]
    image_id=image_info.json()["image"]["name"]
    period = "."
    counter = 1
    image_status = "INIT"
    while image_status != "ACTIVE":
        try:
            image_status_object = requests.get (url=image_url, headers=headers)
        except requests.ConnectionError as e:
            print("Can't connect to API, trying again...")
        if image_status_object.status_code == 200:
            image_status = image_status_object.json()["image"]["status"]
        print ("Image %s is in %s status%s" % (image_name, image_status, (period * counter)))
        counter = counter + 1
        time.sleep(30)


def set_image_metadata(auth_token, headers, image_name, image_url):
    metadata_url = ("%s/metadata" % image_url)
    payload = {
            "metadata": {
                "vm_mode": "hvm"
                        }
              }
    image_vm_mode = requests.post(url=metadata_url, headers=headers, json=payload)
    image_vm_mode.raise_for_status()
    if image_vm_mode.ok:
        print ("I set image metadata on %s" % image_name)

# def rebuild_server(auth_token, headers, cs_name, image_url):


#begin main function
@plac.annotations(
    glance_image=plac.Annotation("UUID of Cloud Server image")
                )
def main(glance_image):
    username,password = getset_keyring_credentials()
    auth_token = get_auth_token(username, password)
    glance_endpoints, cs_endpoints, headers = find_endpoints(auth_token)
    glance_object, cs_endpoint, region = find_glance_image_and_cs_endpoint(auth_token, headers, cs_endpoints, glance_endpoints, glance_image)
    image_os = check_glance_image(auth_token, headers, glance_image, glance_object)
    flavor = determine_cs_flavor(auth_token, headers, glance_image, glance_object)
    cs_name, cs_object, cs_url = build_server(auth_token, headers, cs_endpoint, glance_image, glance_object, image_os, flavor)
    poll_cs_status(auth_token, headers, cs_name, cs_object, cs_url, image_os)

    image_name, image_url = create_cs_image(auth_token, headers, cs_name, cs_object, cs_url)
    poll_image_status(auth_token, headers, image_name, image_url)
    set_image_metadata(auth_token, headers, image_name, image_url)

if __name__ == '__main__':
    import plac
    plac.call(main)
