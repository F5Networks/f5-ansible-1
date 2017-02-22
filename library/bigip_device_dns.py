#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2016 F5 Networks Inc.
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = '''
---
module: bigip_device_dns
short_description: Manage BIG-IP device DNS settings
description:
  - Manage BIG-IP device DNS settings
version_added: "2.2"
options:
  cache:
    description:
      - Specifies whether the system caches DNS lookups or performs the
        operation each time a lookup is needed. Please note that this applies
        only to Access Policy Manager features, such as ACLs, web application
        rewrites, and authentication.
    required: false
    default: disable
    choices:
       - enable
       - disable
  name_servers:
    description:
      - A list of name serverz that the system uses to validate DNS lookups
  forwarders:
    description:
      - A list of BIND servers that the system can use to perform DNS lookups
  search:
    description:
      - A list of domains that the system searches for local domain lookups,
        to resolve local host names.
  ip_version:
    description:
      - Specifies whether the DNS specifies IP addresses using IPv4 or IPv6.
    required: false
    choices:
      - 4
      - 6
notes:
  - Requires the f5-sdk Python package on the host. This is as easy as pip
    install requests
extends_documentation_fragment: f5
requirements:
  - f5-sdk
author:
  - Tim Rupp (@caphrim007)
'''

EXAMPLES = '''
- name: Set the DNS settings on the BIG-IP
  bigip_device_dns:
      name_servers:
          - 208.67.222.222
          - 208.67.220.220
      search:
          - localdomain
          - lab.local
      password: "secret"
      server: "lb.mydomain.com"
      user: "admin"
      validate_certs: "no"
  delegate_to: localhost
'''

RETURN = '''
cache:
    description: The new value of the DNS caching
    returned: changed
    type: string
    sample: "enabled"
name_servers:
    description: List of name servers that were set
    returned: changed
    type: list
    sample: "['192.0.2.10', '172.17.12.10']"
forwarders:
    description: List of forwarders that were set
    returned: changed
    type: list
    sample: "['192.0.2.10', '172.17.12.10']"
search:
    description: List of search domains that were set
    returned: changed
    type: list
    sample: "['192.0.2.10', '172.17.12.10']"
ip_version:
    description: IP version that was set that DNS will specify IP addresses in
    returned: changed
    type: int
    sample: 4
'''

from ansible.module_utils.basic import *
from ansible.module_utils.f5_utils import *


class Parameters(AnsibleF5Parameters):
    param_api_map = dict(
        cache='dns.cache',
        forwarders='dns.proxy.__iter__',
        name_servers='nameServers',
        search='search',
        ip_version='include'
    )

    def __init__(self, params=None):
        self._ip_version = None
        self._dhcp = None
        self._cache = None
        self._forwarders = None
        self._name_servers = None
        self._search = None
        super(Parameters, self).__init__(params)

    @property
    def search(self):
        result = []
        if self._search is None:
            return None
        for server in self._search:
            result.append(str(server))
        return result

    @search.setter
    def search(self, value):
        self._search = value

    @property
    def name_servers(self):
        result = []
        if self._name_servers is None:
            return None
        for server in self._name_servers:
            result.append(str(server))
        return result

    @name_servers.setter
    def name_servers(self, value):
        self._name_servers = value

    @property
    def cache(self):
        if str(self._cache) in ['enabled', 'enable']:
            return 'enable'
        else:
            return 'disable'

    @cache.setter
    def cache(self, value):
        self._cache = value

    @property
    def dhcp(self):
        return True if self._dhcp == 'enable' else False

    @dhcp.setter
    def dhcp(self, value):
        self._dhcp = value

    @property
    def forwarders(self):
        if self._forwarders is None:
            return None
        else:
            return ' '.join(self._forwarders)

    @forwarders.setter
    def forwarders(self, value):
        try:
            self._forwarders = value.split(' ')
        except AttributeError:
            self._forwarders = value

    @property
    def ip_version(self):
        if self._ip_version in [6,'6','options inet6']:
            return "options inet6"
        elif self._ip_version in [4,'4','']:
            return ""
        else:
            return None

    @ip_version.setter
    def ip_version(self, value):
        self._ip_version = value

    def api_params(self):
        result = super(Parameters, self).api_params()

        # Remove items that are simple keys. This allows the more complex
        # set of parameters be returned as the api params.
        result.pop('dns.cache', None)
        result.pop('dns.proxy.__iter__', None)
        return result


class ModuleManager(object):
    def __init__(self, client):
        self.client = client
        self.have = None
        self.want = Parameters(self.client.module.params)
        self.changes = Parameters()

    def exec_module(self):
        if not HAS_F5SDK:
            raise F5ModuleError("The python f5-sdk module is required")

        changed = False
        result = dict()
        state = self.want.state

        try:
            if state == "present":
                changed = self.update()
            elif state == "absent":
                changed = self.absent()
        except iControlUnexpectedHTTPError as e:
            raise F5ModuleError(str(e))

        #result.update(**self.changes.to_dict())
        result.update(dict(changed=changed))
        return result

    def read_current_from_device(self):
        want_keys = ['dhclient.mgmt', 'dns.cache', 'dns.proxy.__iter__']
        result = dict()
        dbs = self.client.api.tm.sys.dbs.get_collection()
        for db in dbs:
            if db.name in want_keys:
                result[db.name] = db.value
        dns = self.client.api.tm.sys.dns.load()
        dns = dns.to_dict()
        dns.pop('_meta_data', None)
        if 'include' not in dns:
            dns['include'] = 4
        result.update(dns)

        return Parameters.from_api(result)

    def update(self):
        self.have = self.read_current_from_device()
        if self.have.dhcp:
            raise F5ModuleError(
                "DHCP on the mgmt interface must be disabled to make use of"
                "this module"
            )
        if not self.should_update():
            return False
        if self.client.check_mode:
            return True
        self.update_on_device()
        return True

    def should_update(self):
        for key in self.want.param_api_map.keys():
            if getattr(self.want, key) is not None:
                attr1 = getattr(self.want, key)
                attr2 = getattr(self.have, key)
                if attr1 != attr2:
                    setattr(self.changes, key, getattr(self.want, key))
                    return True


    def update_on_device(self):
        params = self.want.api_params()
        tx = self.client.api.tm.transactions.transaction
        with BigIpTxContext(tx) as api:
            cache = api.tm.sys.dbs.db.load(name='dns.cache')
            proxy = api.tm.sys.dbs.db.load(name='dns.proxy.__iter__')
            dns = api.tm.sys.dns.load()

            # Empty values can be supplied, but you cannot supply the
            # None value, so we check for that specifically
            if self.want.cache is not None:
                cache.update(value=self.want.cache)
            if self.want.forwarders is not None:
                proxy.update(value=self.want.forwarders)
            if params:
                dns.update(**params)


class ArgumentSpec(object):
    def __init__(self):
        self.supports_check_mode = True
        self.argument_spec = dict(
            cache=dict(
                required=False,
                choices=['disabled', 'enabled', 'disable', 'enable'],
                default=None
            ),
            name_servers=dict(
                required=False,
                default=None,
                type='list'
            ),
            forwarders=dict(
                required=False,
                default=None,
                type='list'
            ),
            search=dict(
                required=False,
                default=None,
                type='list'
            ),
            ip_version=dict(
                required=False,
                default=None,
                choices=[4, 6],
                type='int'
            )
        )
        self.required_one_of = [
            ['name_servers', 'search', 'forwarders', 'ip_version', 'cache']
        ]
        self.f5_product_name = 'bigip'


def main():
    spec = ArgumentSpec()

    client = AnsibleF5Client(
        argument_spec=spec.argument_spec,
        supports_check_mode=spec.supports_check_mode,
        f5_product_name=spec.f5_product_name,
        required_one_of=spec.required_one_of
    )

    mm = ModuleManager(client)
    results = mm.exec_module()
    client.module.exit_json(**results)

if __name__ == '__main__':
    main()



































