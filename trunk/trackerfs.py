#!/usr/bin/env python
#
#    Copyright (C) 2006 Alex Kritikos <alex dot kritikos at gmail dot com>
#    
#    TrackerFS - Tracker Filesystem Version 0.0.1
#    This program can be distributed under the terms of the GNU GPL.
#    See the file COPYING.
#

"""
TrackerFS provides a filesystem of symlinks using Tracker
"""

import fuse
from fuse import Fuse
import errno
from stat import *
import string
import dbus
import logging

if getattr(dbus, 'version', (0,0,0)) >= (0,41,0):
    import dbus.glib

### 
# Set up logging
###
log = logging.getLogger("trackerfs")
log.setLevel(logging.DEBUG)
fh = logging.FileHandler("trackerfs.log")
fh.setLevel(logging.DEBUG)
#create formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
log.addHandler(fh)

class MyStat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0
        self.st_blocks = 0
        self.st_blksize = 512
        self.st_rdev = 0

class Client:
    """
    A tracker client object
    """
    def __init__(self):
    

        self._bus = dbus.SessionBus()
        self._obj = self._bus.get_object('org.freedesktop.Tracker', '/org/freedesktop/tracker')
        self._iface = dbus.Interface(self._obj, 'org.freedesktop.Tracker.Search')
    
    def query(self, qstring):
        log.debug("preparing query with %s",qstring)
        return self._iface.Text(-1, "Files", qstring, 0, 512, False)

class Trackerfs(Fuse):
    
    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        #self.query = 'katie'
        self.tclient = Client()

    def hit_target(self, path, qstring):
        hits = self.tclient.query(qstring)
        matches = [x for x in hits if x.endswith(path)]
        if matches != []:
            return matches[0].encode()
        else:
            return None

    def get_hits(self, qstring):
        log.debug("get_hits: %s", qstring)
        matches = self.tclient.query(qstring)
        log.debug("done")

        # return the filenames, which occur after the last slash,
        # and convert from unicode
        return [x[(string.rindex(x,'/')+1):].encode() for x in matches]
        
    def getattr(self, path):

        st = MyStat()
        if path == '/':
            st.st_mode = S_IFDIR | 0755
            st.st_nlin = 2
        elif self.hit_target(path, self.query) != None:
            st.st_mode = S_IFLNK|S_IRWXU|S_IRWXG|S_IRWXO
            st.st_nlink = 1
            st.st_size = 0
        else:
            return -errno.ENOENT
        return st
   
    def readlink(self, path):
        target = self.hit_target(path, self.query)
        if target != None:
            return target
        else:
            e = OSError("Not a link"+path)
            e.errno = EINVAL
            raise e
    
    def readdir(self, path, offset):
        for r in  '.', '..':
            yield fuse.Direntry(r)
        for r in self.get_hits(self.query):
            yield fuse.Direntry(r)

    def statfs(self):
        """
        Should return a tuple with the following 6 elements:
            - blocksize - size of file blocks, in bytes
            - totalblocks - total number of blocks in the filesystem
            - freeblocks - number of free blocks
            - availblocks - number of blocks available to non-superuser
            - totalfiles - total number of file inodes
            - freefiles - nunber of free file inodes
    
        Feel free to set any of the above values to 0, which tells
        the kernel that the info is not available.
        """
        block_size = 0
        blocks = 0
        blocks_free = 0
        blocks_avail = 0
        files = 0
        files_free = 0
        namelen = 80
        return (block_size, blocks, blocks_free, blocks_avail, files, files_free, namelen)

def main():
    usage="""
Tracker filesystem

""" + Fuse.fusage
    server = Trackerfs(version="%prog " + fuse.__version__,
                       usage=usage)
    #, dash_s_do='setsingle')
    server.multithreaded = 0;
    server.parser.add_option(mountopt="query", metavar="TERM", default='kritikos', help="sets Tracker query [default: %default]")

    server.parse(values=server, errex=1)
    server.main()

if __name__ == '__main__':
    main()
    
