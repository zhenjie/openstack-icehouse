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

mysql_password = "secret"
service_tenant = None

def kill_process(process_name):
    for proc in psutil.process_iter():
        if proc.name == process_name:
            proc.kill()

def get_ip_address(ifname):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            return socket.inet_ntoa(fcntl.ioctl(s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', ifname[:15])
            )[20:24])
        except Exception:
            print "Cannot get IP Address for Interface %s" % ifname
            sys.exit(1)

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


def execute_db_commnads(command):
    cmd = """mysql -uroot -p%s -e "%s" """ % (mysql_password, command)
    output = execute(cmd)
    return output


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

    global iniparse
    if iniparse is None:
        iniparse = __import__('iniparse')

    global psutil
    if psutil is None:
        psutil = __import__('psutil')
#=================================================================================
#==================   Components Installation Starts Here ========================
#=================================================================================

ip_address = get_ip_address("eth0")
ip_address_mgnt = get_ip_address("eth1")

def install_rabbitmq():
    execute("apt-get install rabbitmq-server -y", True)
    execute("service rabbitmq-server restart", True)
    time.sleep(2)


def install_database():
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    execute("apt-get install mysql-server python-mysqldb mysql-client-5.5 -y", True)
    execute("sed -i 's/127.0.0.1/0.0.0.0/g' /etc/mysql/my.cnf")
    execute("service mysql restart", True)
    time.sleep(2)
    try:
        execute("mysqladmin -u root password %s" % mysql_password)
    except Exception:
        print " Mysql Password already set as : %s " % mysql_password



def _create_keystone_users():
    os.environ['SERVICE_TOKEN'] = 'ADMINTOKEN'
    os.environ['SERVICE_ENDPOINT'] = 'http://%s:35357/v2.0'% ip_address
    os.environ['no_proxy'] = "localhost,127.0.0.1,%s" % ip_address
    global service_tenant 

    #TODO(ish) : This is crude way of doing. Install keystone client and use that to create tenants, role etc
    admin_tenant = execute("keystone tenant-create --name admin --description 'Admin Tenant' --enabled true |grep ' id '|awk '{print $4}'")
    admin_user = execute("keystone user-create --tenant_id %s --name admin --pass secret --enabled true|grep ' id '|awk '{print $4}'" % admin_tenant)
    admin_role = execute("keystone role-create --name admin|grep ' id '|awk '{print $4}'")
    execute("keystone user-role-add --user_id %s --tenant_id %s --role_id %s" % (admin_user, admin_tenant, admin_role))


    service_tenant = execute("keystone tenant-create --name service --description 'Service Tenant' --enabled true |grep ' id '|awk '{print $4}'")


    #keystone
    keystone_service = execute("keystone service-create --name=keystone --type=identity --description='Keystone Identity Service'|grep ' id '|awk '{print $4}'")
    execute("keystone endpoint-create --region region --service_id=%s --publicurl=http://%s:5000/v2.0 --internalurl=http://%s:5000/v2.0 --adminurl=http://%s:35357/v2.0" % (keystone_service, ip_address,ip_address_mgnt,ip_address_mgnt))


    #Glance
    glance_user = execute("keystone user-create --tenant_id %s --name glance --pass glance --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)
    execute("keystone user-role-add --user_id %s --tenant_id %s --role_id %s" % (glance_user, service_tenant, admin_role))

    glance_service = execute("keystone service-create --name=glance --type=image --description='Glance Image Service'|grep ' id '|awk '{print $4}'")
    execute("keystone endpoint-create --region region --service_id=%s --publicurl=http://%s:9292/v2 --internalurl=http://%s:9292/v2 --adminurl=http://%s:9292/v2" % (glance_service, ip_address,ip_address_mgnt,ip_address_mgnt))


    #nova
    nova_user = execute("keystone user-create --tenant_id %s --name nova --pass nova --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)
    execute("keystone user-role-add --user_id %s --tenant_id %s --role_id %s" % (nova_user, service_tenant, admin_role))

    nova_service = execute("keystone service-create --name=nova --type=compute --description='Nova Compute Service'|grep ' id '|awk '{print $4}'")
    execute("keystone endpoint-create --region region --service_id=%s --publicurl='http://%s:8774/v2/$(tenant_id)s' --internalurl='http://%s:8774/v2/$(tenant_id)s' --adminurl='http://%s:8774/v2/$(tenant_id)s'" % (nova_service, ip_address,ip_address_mgnt,ip_address_mgnt))


    #neutron
    neutron_user = execute("keystone user-create --tenant_id %s --name neutron --pass neutron --enabled true|grep ' id '|awk '{print $4}'" % service_tenant)
    execute("keystone user-role-add --user_id %s --tenant_id %s --role_id %s" % (neutron_user, service_tenant, admin_role))

    neutron_service = execute("keystone service-create --name=neutron --type=network  --description='OpenStack Networking service'|grep ' id '|awk '{print $4}'")
    execute("keystone endpoint-create --region region --service_id=%s --publicurl=http://%s:9696/ --internalurl=http://%s:9696/ --adminurl=http://%s:9696/" % (neutron_service, ip_address,ip_address_mgnt,ip_address_mgnt))

    #write a rc file
    adminrc = "/root/adminrc"
    delete_file(adminrc)
    write_to_file(adminrc, "export OS_USERNAME=admin\n")
    write_to_file(adminrc, "export OS_PASSWORD=secret\n")
    write_to_file(adminrc, "export OS_TENANT_NAME=admin\n")
    write_to_file(adminrc, "export OS_AUTH_URL=http://%s:5000/v2.0\n" %ip_address)



def install_and_configure_keystone():
    keystone_conf = "/etc/keystone/keystone.conf"

    execute_db_commnads("DROP DATABASE IF EXISTS keystone;")
    execute_db_commnads("CREATE DATABASE keystone DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;")
    execute_db_commnads("GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%' IDENTIFIED BY 'keystone';")
    execute_db_commnads("GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'localhost' IDENTIFIED BY 'keystone';")

    # Just in case!
    execute("apt-get install python-prettytable -y")
    
    execute("apt-get install keystone -y", True)

    # keystone conf has a section name [database] for sqlite, we have to disable it!
    execute("sed -i 's/connection = sqlite:\/\/\/\/var\/lib\/keystone\/keystone.db//' %s" % keystone_conf)
    
    add_to_conf(keystone_conf, "DEFAULT", "admin_token", "ADMINTOKEN")
    add_to_conf(keystone_conf, "DEFAULT", "admin_port", 35357)
    add_to_conf(keystone_conf, "database", "connection", "mysql://keystone:keystone@localhost/keystone")
    add_to_conf(keystone_conf, "signing", "token_format", "UUID")

    execute("keystone-manage db_sync")

    execute("service keystone restart", True)

    time.sleep(3)
    _create_keystone_users()



def install_and_configure_glance():
    glance_api_conf = "/etc/glance/glance-api.conf"
    glance_registry_conf = "/etc/glance/glance-registry.conf"
    glance_api_paste_conf = "/etc/glance/glance-api-paste.ini"
    glance_registry_paste_conf = "/etc/glance/glance-registry-paste.ini"

    execute_db_commnads("DROP DATABASE IF EXISTS glance;")
    execute_db_commnads("CREATE DATABASE glance DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;")
    execute_db_commnads("GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY 'glance';")
    execute_db_commnads("GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY 'glance';")

    execute("apt-get install glance -y", True)


    add_to_conf(glance_api_paste_conf, "filter:authtoken", "auth_host", ip_address)
    add_to_conf(glance_api_paste_conf, "filter:authtoken", "auth_port", "35357")
    add_to_conf(glance_api_paste_conf, "filter:authtoken", "auth_protocol", "http")
    add_to_conf(glance_api_paste_conf, "filter:authtoken", "admin_tenant_name", "service")
    add_to_conf(glance_api_paste_conf, "filter:authtoken", "admin_user", "glance")
    add_to_conf(glance_api_paste_conf, "filter:authtoken", "admin_password", "glance")


    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "auth_host", ip_address)
    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "auth_port", "35357")
    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "auth_protocol", "http")
    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "admin_tenant_name", "service")
    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "admin_user", "glance")
    add_to_conf(glance_registry_paste_conf, "filter:authtoken", "admin_password", "glance")


    add_to_conf(glance_api_conf, "DEFAULT", "sql_connection", "mysql://glance:glance@localhost/glance")
    add_to_conf(glance_api_conf, "paste_deploy", "flavor", "keystone")
    add_to_conf(glance_api_conf, "DEFAULT", "verbose", "true")
    add_to_conf(glance_api_conf, "DEFAULT", "debug", "true")
    add_to_conf(glance_api_conf, "DEFAULT", "db_enforce_mysql_charset", "false")

    add_to_conf(glance_registry_conf, "DEFAULT", "sql_connection", "mysql://glance:glance@localhost/glance")
    add_to_conf(glance_registry_conf, "paste_deploy", "flavor", "keystone")
    add_to_conf(glance_registry_conf, "DEFAULT", "verbose", "true")
    add_to_conf(glance_registry_conf, "DEFAULT", "debug", "true")

    execute("glance-manage db_sync")

    execute("service glance-api restart", True)
    execute("service glance-registry restart", True)
	




def install_and_configure_nova():
    nova_conf = "/etc/nova/nova.conf"
    nova_paste_conf = "/etc/nova/api-paste.ini"
    
    execute_db_commnads("DROP DATABASE IF EXISTS nova;")
    execute_db_commnads("CREATE DATABASE nova DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;")
    execute_db_commnads("GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY 'nova';")
    execute_db_commnads("GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost' IDENTIFIED BY 'nova';")

    execute("apt-get install nova-api nova-cert nova-scheduler nova-conductor novnc nova-consoleauth nova-novncproxy -y", True)


    add_to_conf(nova_paste_conf, "filter:authtoken", "auth_host", ip_address)
    add_to_conf(nova_paste_conf, "filter:authtoken", "auth_port", "35357")
    add_to_conf(nova_paste_conf, "filter:authtoken", "auth_protocol", "http")
    add_to_conf(nova_paste_conf, "filter:authtoken", "admin_tenant_name", "service")
    add_to_conf(nova_paste_conf, "filter:authtoken", "admin_user", "nova")
    add_to_conf(nova_paste_conf, "filter:authtoken", "admin_password", "nova")


    add_to_conf(nova_conf, "DEFAULT", "logdir", "/var/log/nova")
    add_to_conf(nova_conf, "DEFAULT", "lock_path", "/var/lib/nova")
    add_to_conf(nova_conf, "DEFAULT", "root_helper", "sudo nova-rootwrap /etc/nova/rootwrap.conf")
    add_to_conf(nova_conf, "DEFAULT", "verbose", "True")
    add_to_conf(nova_conf, "DEFAULT", "debug", "True")
    add_to_conf(nova_conf, "DEFAULT", "rabbit_host", "127.0.0.1" )
    add_to_conf(nova_conf, "DEFAULT", "rpc_backend", "nova.rpc.impl_kombu" )
    add_to_conf(nova_conf, "DEFAULT", "sql_connection", "mysql://nova:nova@localhost/nova")
    add_to_conf(nova_conf, "DEFAULT", "glance_api_servers", "%s:9292" %ip_address)
    add_to_conf(nova_conf, "DEFAULT", "dhcpbridge_flagfile", "/etc/nova/nova.conf")
    add_to_conf(nova_conf, "DEFAULT", "auth_strategy", "keystone")
    add_to_conf(nova_conf, "DEFAULT", "novnc_enabled", "true")
    add_to_conf(nova_conf, "DEFAULT", "novncproxy_base_url", "http://%s:6080/vnc_auto.html" % ip_address)
    add_to_conf(nova_conf, "DEFAULT", "vncserver_proxyclient_address", ip_address_mgnt)
    add_to_conf(nova_conf, "DEFAULT", "novncproxy_port", "6080")
    add_to_conf(nova_conf, "DEFAULT", "vncserver_listen", "0.0.0.0")
    add_to_conf(nova_conf, "DEFAULT", "network_api_class", "nova.network.neutronv2.api.API")
    add_to_conf(nova_conf, "DEFAULT", "neutron_admin_username", "neutron")
    add_to_conf(nova_conf, "DEFAULT", "neutron_admin_password", "neutron")
    add_to_conf(nova_conf, "DEFAULT", "neutron_admin_tenant_name", "service")
    add_to_conf(nova_conf, "DEFAULT", "neutron_admin_auth_url", "http://%s:5000/v2.0/"%ip_address)
    add_to_conf(nova_conf, "DEFAULT", "neutron_auth_strategy", "keystone")
    add_to_conf(nova_conf, "DEFAULT", "neutron_url", "http://%s:9696/"%ip_address)
    add_to_conf(nova_conf, "DEFAULT", "firewall_driver", "nova.virt.firewall.NoopFirewallDriver")
    add_to_conf(nova_conf, "DEFAULT", "security_group_api", "neutron")
  
    execute("nova-manage db sync")
    execute("service nova-api restart", True)
    execute("service nova-cert restart", True)
    execute("service nova-scheduler restart", True)
    execute("service nova-conductor restart", True)
    execute("service nova-consoleauth restart", True)
    execute("service nova-novncproxy restart", True)


def install_and_configure_neutron():
    neutron_conf = "/etc/neutron/neutron.conf"
    neutron_paste_conf = "/etc/neutron/api-paste.ini"
    neutron_plugin_conf = "/etc/neutron/plugins/ml2/ml2_conf.ini"
       

    execute_db_commnads("DROP DATABASE IF EXISTS neutron;")
    execute_db_commnads("CREATE DATABASE neutron DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;")
    execute_db_commnads("GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%' IDENTIFIED BY 'neutron';")
    execute_db_commnads("GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost' IDENTIFIED BY 'neutron';")

    execute("apt-get install neutron-server -y", True)
    execute("apt-get install neutron-plugin-ml2 -y",True)
    add_to_conf(neutron_conf, "DEFAULT", "core_plugin", "neutron.plugins.ml2.plugin.Ml2Plugin")
    add_to_conf(neutron_conf, "DEFAULT", "service_plugins", "neutron.services.l3_router.l3_router_plugin.L3RouterPlugin")
    add_to_conf(neutron_conf, "database", "connection", "mysql://neutron:neutron@localhost/neutron")
    add_to_conf(neutron_conf, "DEFAULT", "verbose", "True")
    add_to_conf(neutron_conf, "DEFAULT", "debug", "True")
    add_to_conf(neutron_conf, "DEFAULT", "auth_strategy", "keystone")
    add_to_conf(neutron_conf, "DEFAULT", "rabbit_host", "127.0.0.1")
    add_to_conf(neutron_conf, "DEFAULT", "rabbit_port", "5672")
    add_to_conf(neutron_conf, "DEFAULT", "allow_overlapping_ips", "False")
    add_to_conf(neutron_conf, "DEFAULT", "root_helper", "sudo neutron-rootwrap /etc/neutron/rootwrap.conf")
    add_to_conf(neutron_conf, "DEFAULT", "notify_nova_on_port_status_changes", "True")
    add_to_conf(neutron_conf, "DEFAULT", "notify_nova_on_port_data_changes", "True")
    add_to_conf(neutron_conf, "DEFAULT", "nova_url", "http://127.0.0.1:8774/v2")
    add_to_conf(neutron_conf, "DEFAULT", "nova_admin_username", "nova")
    add_to_conf(neutron_conf, "DEFAULT", "nova_admin_password", "nova")
    add_to_conf(neutron_conf, "DEFAULT", "nova_admin_tenant_id", service_tenant)
    add_to_conf(neutron_conf, "DEFAULT", "nova_admin_auth_url", "http://127.0.0.1:5000/v2.0/")

    add_to_conf(neutron_paste_conf, "filter:authtoken", "auth_host", ip_address)
    add_to_conf(neutron_paste_conf, "filter:authtoken", "auth_port", "35357")
    add_to_conf(neutron_paste_conf, "filter:authtoken", "auth_protocol", "http")
    add_to_conf(neutron_paste_conf, "filter:authtoken", "admin_tenant_name", "service")
    add_to_conf(neutron_paste_conf, "filter:authtoken", "admin_user", "neutron")
    add_to_conf(neutron_paste_conf, "filter:authtoken", "admin_password", "neutron")
	
    add_to_conf(neutron_plugin_conf, "ml2", "type_drivers", "vlan,vxlan")
    add_to_conf(neutron_plugin_conf, "ml2", "tenant_network_types", "vlan,vxlan")
    add_to_conf(neutron_plugin_conf, "ml2", "mechanism_drivers", "openvswitch,linuxbridge")
    add_to_conf(neutron_plugin_conf, "ml2_type_vlan", "network_vlan_ranges", "physnet1:2000:2999")
    add_to_conf(neutron_plugin_conf, "ml2_type_vxlan", "vni_ranges", "500:999")
    add_to_conf(neutron_plugin_conf, "securitygroup", "firewall_driver", "neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver")
	

    execute("service neutron-server restart", True)
   


def install_and_configure_dashboard():
    execute("apt-get install openstack-dashboard -y", True)

    # To fix this bug: https://bugs.launchpad.net/horizon/+bug/1288245
    execute("easy_install mox", True)
    
    # uninstall ubuntu-openstack-theme
    # http://docs.openstack.org/havana/install-guide/install/apt/content/install_dashboard.html
    execute("apt-get remove --purge openstack-dashboard-ubuntu-theme -y", True)

    execute("service apache2 restart", True)

initialize_system()
install_rabbitmq()
install_database()
install_and_configure_keystone()
install_and_configure_glance()
install_and_configure_nova()
install_and_configure_neutron()
install_and_configure_dashboard()
print_format(" Installation successfull! Login into horizon http://%s/horizon  Username:admin  Password:secret " % ip_address)
