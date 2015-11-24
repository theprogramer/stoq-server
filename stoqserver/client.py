# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2015 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or
## modify it under the terms of the GNU Lesser General Public License
## as published by the Free Software Foundation; either version 2
## of the License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU Lesser General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

import hashlib
import os
import socket
import subprocess
import sys
import urllib2

import gtk
from zeroconf import ServiceBrowser, Zeroconf

from stoqserver.common import (APP_EGGS_DIR, APP_CONF_FILE, SERVER_EGGS,
                               SERVER_EXECUTABLE_EGG, AVAHI_STYPE)

_ = lambda s: s


class _StoqClient(gtk.Window):
    def __init__(self, *args, **kwargs):
        gtk.Window.__init__(self, *args, **kwargs)

        if not os.path.exists(APP_EGGS_DIR):
            os.makedirs(APP_EGGS_DIR)

        self._iters = {}

        self.executable_path = None
        self.python_paths = []

        self._setup_widgets()

    #
    #  Zeroconf Listener
    #

    def remove_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        # FIXME: How to remove the service when info is None?
        if info is None:
            return

        key = (info.address, info.port)
        if key in self._iters:
            self.store.remove(self._iters[key].pop())

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)

        server_address = 'http://%s:%s' % (
            socket.inet_ntoa(info.address), info.port)
        args = info.properties

        self._iters[(info.address, info.port)] = self.store.append(
            [server_address, args])

    #
    #  Private
    #

    def _setup_widgets(self):
        vbox = gtk.VBox()

        self.store = gtk.ListStore(str, object)
        self.treeview = gtk.TreeView(self.store)

        self.server_column = gtk.TreeViewColumn(_("Server"))
        self.cell = gtk.CellRendererText()
        self.server_column.pack_start(self.cell, True)
        self.server_column.add_attribute(self.cell, 'text', 0)

        self.treeview.append_column(self.server_column)
        self.treeview.connect('row-activated',
                              self._on_treeview__row_activated)
        vbox.pack_start(self.treeview, expand=True)

        self.username = gtk.Entry()
        vbox.pack_start(self.username, expand=False)

        self.password = gtk.Entry()
        vbox.pack_start(self.password, expand=False)

        self.resize(400, 300)
        self.add(vbox)

    def _download_eggs(self, server_address):
        opener = self._get_opener(server_address)

        if not os.path.exists(APP_CONF_FILE):
            tmp = opener.open('%s/login' % (server_address, ))
            with open(APP_CONF_FILE, 'w') as f:
                f.write(tmp.read())
            tmp.close()

        md5sums = {}
        tmp = opener.open('%s/md5sum' % (server_address, ))
        for line in tmp.read().split('\n'):
            if not line:
                continue
            egg, md5sum = line.split(':')
            md5sums[egg] = md5sum

        tmp.close()

        for egg in SERVER_EGGS:
            egg_path = os.path.join(APP_EGGS_DIR, egg)
            if self._check_egg(egg_path, md5sums[egg]):
                continue

            with open(egg_path, 'wb') as f:
                tmp = opener.open('%s/eggs/%s' % (server_address, egg))
                f.write(tmp.read())
                tmp.close()

            assert self._check_egg(egg_path, md5sums[egg])

            self.python_paths.append(egg_path)
            if egg == SERVER_EXECUTABLE_EGG:
                self.executable_path = egg_path

        return True

    def _get_opener(self, server_address):
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, server_address,
                             self.username.get_text(),
                             hashlib.md5(self.password.get_text()).hexdigest())
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        return urllib2.build_opener(authhandler)

    def _check_egg(self, egg_path, md5sum):
        if not os.path.exists(egg_path):
            return False

        md5 = hashlib.md5()
        with open(egg_path, 'rb') as f:
            for chunk in iter(lambda: f.read(md5.block_size), b''):
                md5.update(chunk)

        return md5.hexdigest() == md5sum

    #
    #  Callbacks
    #

    def _on_treeview__row_activated(self, treeview, path, column):
        model, titer = treeview.get_selection().get_selected()
        if not self._download_eggs(model.get_value(titer, 0)):
            return

        self.hide()
        gtk.main_quit()


def main(args):
    try:
        # FIXME: Maybe we should not use zeroconf and instead implement
        # our own avahi browser.
        zeroconf = Zeroconf()
        client = _StoqClient()
        client.show_all()
        ServiceBrowser(zeroconf, '%s.local.' % (AVAHI_STYPE, ), client)
        gtk.gdk.threads_init()
        gtk.main()
    finally:
        zeroconf.close()

    env = os.environ.copy()
    env['PYTHONPATH'] = ':'.join(
        client.python_paths + [env.get('PYTHONPATH', '')])

    popen = subprocess.Popen([sys.executable, client.executable_path], env=env)
    try:
        popen.communicate()
    except KeyboardInterrupt:
        popen.terminate()
