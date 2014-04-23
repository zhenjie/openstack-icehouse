#! /usr/bin/python
import sys
import os
import time
import fcntl
import struct
import socket
import subprocess

# These are module names which are not installed by default.
# These modules will be loaded later after downloading
iniparse = None
psutil = None


def kill_process(process_name):
    for proc in psutil.process_iter():
        if proc.name == process_name:
            proc.kill()


def delete_file(file_path):
    if os.path.isfile(file_path):
        os.remove(file_path)
    else:
        print("Error: %s file not found" % file_path)

def write_to_file(file_path, content):
    open(file_path, "a").write(content)

def add_to_conf(conf_file, section, param, val):
    config = iniparse.ConfigParser()
    config.readfp(open(conf_file))
    if not config.has_section(section):
        config.add_section(section)
        val += '\n'
    config.set(section, param, val)
    with open(conf_file, 'w') as f:
        config.write(f)


def delete_from_conf(conf_file, section, param):
    config = iniparse.ConfigParser()
    config.readfp(open(conf_file))
    if param is None:
        config.remove_section(section)
    else:
        config.remove_option(section, param)
    with open(conf_file, 'w') as f:
        config.write(f)


def get_from_conf(conf_file, section, param):
    config = iniparse.ConfigParser()
    config.readfp(open(conf_file))
    if param is None:
        raise Exception("parameter missing")
    else:
        return config.get(section, param)

def print_format(string):
    print "+%s+" %("-" * len(string))
    print "|%s|" % string
    print "+%s+" %("-" * len(string))

def execute(command, display=False):
    print_format("Executing  :  %s " % command)
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if display:
        while True:
            nextline = process.stdout.readline()
            if nextline == '' and process.poll() != None:
                break
            sys.stdout.write(nextline)
            sys.stdout.flush()

        output, stderr = process.communicate()
        exitCode = process.returncode
    else:
        output, stderr = process.communicate()
        exitCode = process.returncode

    if (exitCode == 0):
        return output.strip()
    else:
        print "Error", stderr
        print "Failed to execute command %s" % command
        print exitCode, output
        raise Exception(output)



def initialize_system():
    if not os.geteuid() == 0:
        sys.exit('Please re-run the script with root user')

    execute("apt-get clean" , True)
    execute("apt-get autoclean -y" , True)
    execute("apt-get update -y" , True)
    execute("apt-get install ubuntu-cloud-keyring python-setuptools python-iniparse python-psutil -y", True)
    delete_file("/etc/apt/sources.list.d/icehouse.list")
    execute("echo deb http://ubuntu-cloud.archive.canonical.com/ubuntu precise-updates/icehouse main >> /etc/apt/sources.list.d/icehouse.list")
    execute("apt-get update -y", True)
    execute("apt-get install vlan bridge-utils -y", True)
    execute("sed -i 's/#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf")

    global iniparse
    if iniparse is None:
        iniparse = __import__('iniparse')

    global psutil
    if psutil is None:
        psutil = __import__('psutil')
#=================================================================================
#==================   Components Installation Starts Here ========================
#=================================================================================

ip_address = raw_input('Controller IP: ')
ip_address_mgnt= raw_input('Controller Mgmt IP: ')

def install_and_configure_lvm():
    # install LVM 
    execute("apt-get install lvm2 -y", True)
    
    # create LVM physical and logical volumes
    hdd = raw_input('Reserved disk for cinder-volume?(eg. sdb): ')
    execute("pvcreate /dev/%s -ff -y" % hdd, True)
    execute("vgcreate cinder-volumes /dev/%s" % hdd, True)

    # devices filter
    execute("sed -i 's/filter = \[ \"a\/\.\*\/\" \]/filter = \[ \"a\/%s\/\", \"r\/\.\*\/\" \]/g' /etc/lvm/lvm.conf" % hdd, True)

    # install cinder-volume
    execute("apt-get install cinder-volume -y", True)
    
    # configure cinder-volume
    cinder_conf = "/etc/cinder/cinder.conf"
    add_to_conf(cinder_conf, "keystone_authtoken", "auth_uri", "http://%s:500" % ip_address_mgnt)
    add_to_conf(cinder_conf, "keystone_authtoken", "auth_host", ip_address_mgnt) 
    add_to_conf(cinder_conf, "keystone_authtoken", "auth_port", "35357") 
    add_to_conf(cinder_conf, "keystone_authtoken", "auth_protocol", "http") 
    add_to_conf(cinder_conf, "keystone_authtoken", "admin_tenant_name", "service") 
    add_to_conf(cinder_conf, "keystone_authtoken", "admin_user", "cinder") 
    add_to_conf(cinder_conf, "keystone_authtoken", "admin_password", "cinder") 

    # Configure block storage to use rabbitMQ message broker
    add_to_conf(cinder_conf, "DEFAULT", "rpc_backend", "cinder.openstack.common.rpc.impl_kombu")
    add_to_conf(cinder_conf, "DEFAULT", "rabbit_host", ip_address_mgnt)  
    add_to_conf(cinder_conf, "DEFAULT", "rabbit_port", 5672)  
    # add_to_conf(cinder_conf, "DEFAULT", "rabbit_userid", guest)  
    # add_to_conf(cinder_conf, "DEFAULT", "rabbit_password", RABBIT_PASS)  
    

    # Configure Block Storage to use MySQL database 
    add_to_conf(cinder_conf, "database", "connection", "mysql://cinder:cinder@%s/cinder" % ip_address_mgnt)

    # Configure Block Storage to use the image service
    add_to_conf(cinder_conf, "DEFAULT", "glance_host", ip_address_mgnt)

    # restart service
    execute("service cinder-volume restart", True)
    execute("service tgt restart", True)

initialize_system()
install_and_configure_lvm()
