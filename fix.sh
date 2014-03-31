#/bin/bash

if [ `id -u` != 0 ]; then
    echo "Permission denied!" 1>&2
    exit 1
fi

# install mox, it's a bug
# https://bugs.launchpad.net/horizon/+bug/1288245
easy_install mox

# delete old keystone db backend configuration
sed -i 's/connection=sqlite:\/\/\/\/keystone\/openstack\/common\/db\/$sqlite_db//' /etc/keystone/keystone.conf
sed -i 's/connection = sqlite:\/\/\/\/var\/lib\/keystone\/keystone.db//' /etc/keystone/keystone.conf

# uninstall ubuntu-openstack-theme
# http://docs.openstack.org/havana/install-guide/install/apt/content/install_dashboard.html
apt-get remove --purge openstack-dashboard-ubuntu-theme

# install python-prettytable, for keystone
apt-get install python-prettytable

