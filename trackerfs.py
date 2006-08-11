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
import time

if getattr(dbus, 'version', (0,0,0)) >= (0,41,0):
    import dbus.glib

### 
# Set up logging
###
log = logging.getLogger("trackerfs")
log.setLevel(logging.ERROR)
fh = logging.StreamHandler()
fh.setLevel(logging.ERROR)
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
        self.cached_time = 0
        self.cached_string = ''
        self.cached_hits = []
    
    def query(self, qstring):
        log.debug("preparing query with %s",qstring)
        current_time = time.time()
        if current_time - self.cached_time < 10 and qstring == self.cached_string:
            log.debug("cache hit")
            return self.cached_hits
        else:
            results = self._iface.Text(-1, "Files", qstring, 0, 512, False)
            
            hits = []
            for result in results:
                shortname = result[(string.rindex(result,'/')+1):].encode()
                uniq = 0
                possible_name = shortname
                while filter(lambda x: x['name'] == possible_name, hits):
                    uniq += 1
                    possible_name = shortname + ' (' + str(uniq) + ')'
                hits.append({'name': possible_name, 'link': result})
                    
            self.cached_time = current_time
            self.cached_string = qstring
            self.cached_hits = hits
            log.debug("performed search")
            return hits

class Trackerfs(Fuse):
    
    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        self.tclient = Client()
        self.dirs = {}

    def hit_target(self, path):
        """
        path should be in the form of /dir/link
            but it won't always be
        FIXME: sloppy checking for this
        """
        try:
            qstring = path[1:path.rindex('/')]
            filename = path[path.rindex('/')+1:]
            hits = self.tclient.query(qstring)
        except:
            hits = []

        matches = [x['link'] for x in hits if x['name'] == filename]
        if matches != []:
            return matches[0].encode()
        else:
            return None

    def get_hits(self, qstring):
        """
        TODO: if it's not needed anywhere else, fold into readdir
        """
        log.debug("get_hits: %s", qstring)
        hits = self.tclient.query(qstring)
        return [x['name'] for x in hits]
        
    def getattr(self, path):
        st = MyStat()
        if path == '/' or self.dirs.has_key(path[1:]):
            st.st_mode = S_IFDIR | 0755
            st.st_nlin = 2
        elif self.hit_target(path) != None:
            st.st_mode = S_IFLNK|S_IRWXU|S_IRWXG|S_IRWXO
            st.st_nlink = 1
            st.st_size = 0
        else:
            return -errno.ENOENT
        return st
   
    def readlink(self, path):
        target = self.hit_target(path)
        if target != None:
            return target
        else:
            e = OSError("Not a link"+path)
            e.errno = EINVAL
            raise e
    
    def readdir(self, path, offset):
        """
        if path is /, return all dirs
        if path is /dir, and "dir" exists, return hits for the "dir" query
        """
        if path == '/':
            for r in  '.', '..':
                yield fuse.Direntry(r)
            for r in self.dirs:
                yield fuse.Direntry(r)
        elif self.dirs.has_key(path[1:]):
            for r in '.', '..':
                yield fuse.Direntry(r)
            for r in self.get_hits(path[1:]):
                yield fuse.Direntry(r)
    
    def mkdir(self, path, mode):
        new_dir = path[1:]
        if (self.dirs.has_key(new_dir) == False) and (len(new_dir) > 0) and (new_dir.find('/') == -1):
            self.dirs[new_dir] = new_dir
                
    def rename(self, path, path1):
        new_dir = path1[1:]
        old_dir = path[1:]
        if (self.dirs.has_key(new_dir) == False) and (len(new_dir) > 0) and (new_dir.find('/') == -1):
            try:
                del self.dirs[old_dir]
                self.dirs[new_dir] = new_dir
            except:
                return # FIXME: return an error!
   
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
        #FIXME: Update for the new python-fuse API
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
                       usage=usage, dash_s_do='setsingle')
    server.multithreaded = 0;
    # server.parser.add_option(mountopt="query", metavar="TERM", default='kritikos', help="sets Tracker query [default: %default]")

    server.parse(values=server, errex=1)
    server.main()

if __name__ == '__main__':
    main()
    
