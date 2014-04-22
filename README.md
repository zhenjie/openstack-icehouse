Openstack Icehouse Installation scripts for Ubuntu 12.04 LTS
================

For Openstack Controller :
--------------------------

Operating System : Ubuntu12.04 LTS

NIC's:

Eth0 : Public Network

Eth1: Openstack Management Network

This script install following components of openstack and configure them:

Keystone

Glance

Neutron( neutron-server with ml2)

Nova( nova-api nova-cert nova-scheduler nova-conductor novnc nova-consoleauth nova-novncproxy)

Dashboard


For Openstack Compute Node:
--------------------------
Operating System : Ubuntu12.04 LTS

NIC's:

Eth0 : Public Network

Eth1: Openstack Management Network

Eth2: Openstack Data Network

This script install following components of openstack and configure them:

Nova( nova-compute)

Neutron ( ovs-agent)

For Openstack Network Node:
--------------------------
Operating System : Ubuntu12.04 LTS

NIC's:

Eth0 : Public Network

Eth1: Openstack Management Network

Eth2: Openstack Data Network

This script install following components of openstack and configure them:

Neutron (dhcp-agent, l3-agent, ovs-agent)

Create neutron base network
----------------------------
http://docs.openstack.org/havana/install-guide/install/apt/content/install-neutron.configure-networks.html

commands:
step 1: create external network named external-net: (192.168.0.5 is control node)

```
neutron --os-username admin --os-password secret --os-tenant-name admin --os-auth-url http://192.168.0.5:5000/v2.0 net-create external-net --router:external=True
```

step 2: configure external-net: (192.168.0.1 is router ip)
```
neutron --os-username admin --os-password secret --os-tenant-name admin --os-auth-url http://192.168.0.5:5000/v2.0 subnet-create external-net 192.168.0.0/24 --name external-subnet --enable_dhcp=False --allocation-pool start=192.168.0.201,end=192.168.0.250 --gateway=192.168.0.1
```

Reference
---------------
http://docs.openstack.org/havana/install-guide/install/apt/content/section_networking-provider-router_with-provate-networks.html




Troubleshooting
----------------
http://virtual2privatecloud.com/troubleshooting-openstack-nova/
