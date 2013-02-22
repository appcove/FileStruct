# vim:encoding=utf-8:ts=2:sw=2:expandtab
#
# Copyright 2013 AppCove, Inc.                                                
#                                                                            
# Licensed under the Apache License, Version 2.0 (the "License");            
# you may not use this file except in compliance with the License.           
# You may obtain a copy of the License at                                    
#                                                                            
# http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
      

from os.path import join, abspath, isdir, dirname, exists
import json
import re
import os
import time
import random
import shutil
import traceback
import io
import datetime
import hashlib
import pwd
import grp
import stat



HASH_MATCH = re.compile('^[a-f0-9]{40}$').match
FILENAME_MATCH = re.compile('^[a-zA-Z0-9_.+-]{1,255}$').match

def RequireValidHash(Hash):
  if not HASH_MATCH(Hash):
    raise ValueError('Hash is not valid: {0}'.format(str(Hash)))
  
def FormatException(e):
  rval = io.StringIO()
  rval.write("An exception occured on {0}:\n".format(datetime.datetime.now().isoformat()))
  rval.write("=======================================================\n\n")
  traceback.print_exc(limit=10, file=rval)
  return rval.getvalue()


def RandomName32():
  '''
  Returns a 32 character unique date-based name like: 
    20130220151303.01171875.68456263
  Which translates to:
    YearMonthDayHourMinuteSecond-FractionOfSecond-RandomNumber
  '''
  t=time.time()
  return "{0:.8f}.{1:08n}".format(
    int(time.strftime('%Y%m%d%H%M%S', time.localtime(t))) + t % 1, 
    int(random.random()*100000000)
    ).replace('.', '-')


class ConfigError(Exception):
  pass


class Client():
  def __init__(self, Path, InternalLocation='/FileStruct'):
    self.Path = abspath(Path)
    self.DataPath = join(self.Path, 'Data')
    self.ErrorPath = join(self.Path, 'Error')
    self.TempPath = join(self.Path, 'Temp')
    self.TrashPath = join(self.Path, 'Trash')
    self.ConfPath = join(self.Path, 'FileStruct.json')
    
    
    self.Conf = None

    self.InternalLocation = InternalLocation
    self.Version = 0
    
    self.DatabaseUser = None
    self.DatabaseGroup = None
    self.EffectiveUser = None
    self.EffectiveGroup = None
    

    del(Path, InternalLocation)

    
    try:
      with open(self.ConfPath, 'r', encoding='utf-8') as f:
        self.Conf = json.loads(str.join('', (line for line in f if line[0] != '#')))
    except Exception as e:
      raise ConfigError("Error loading config file '{0}': {1}".format(self.ConfPath, str(e)))

    if not isinstance(self.Conf, dict):
      raise ConfigError("Config file loaded from '{0}' but root element was not an object.".format(self.ConfPath))

    try:
      self.Version = int(self.Conf['Version'])
    except Exception as e:
      raise ConfigError("Error reading 'Version' from config file '{0}': {1}".format(self.ConfPath, str(e)))
    
    if self.Version != 1:
      raise ConfigError("This version of the FileStruct client cannot work with database Version {0} as found in config file: '{1}'".format(self.Version, self.ConfPath))
      
    try:
      v = self.Conf['User']
      if isinstance(v, int):
        self.DatabaseUser = pwd.getpwuid(v)
      elif isinstance(v, str):
        self.DatabaseUser = pwd.getpwnam(v)
      else:
        raise ValueError("Invalid datatype for 'User': {0}".format(type(v)))
    except Exception as e:
      raise ConfigError("Error reading 'User' from config file '{0}': {1}".format(self.ConfPath, str(e)))
    
    try:
      v = self.Conf['Group']
      if isinstance(v, int):
        self.DatabaseGroup = grp.getgrgid(v)
      elif isinstance(v, str):
        self.DatabaseGroup = grp.getgrnam(v)
      else:
        raise ValueError("Invalid datatype for 'Group': {0}".format(type(v)))
    except Exception as e:
      raise ConfigError("Error reading 'Group' from config file '{0}': {1}".format(self.ConfPath, str(e)))

    try:
      self.EffectiveUser = pwd.getpwuid(os.geteuid())
      self.EffectiveGroup = grp.getgrgid(os.getegid())
    except Exception as e:
      raise ConfigError(e)
    
    
    if self.EffectiveUser.pw_uid != self.DatabaseUser.pw_uid:
      raise ConfigError("User '{0}' specified in config file '{1}' does not match effective user (name={2}, uid={3}).".format(self.Conf['User'], self.ConfPath, self.EffectiveUser.pw_name, self.EffectiveUser.pw_uid)) 

    if self.EffectiveGroup.gr_gid != self.DatabaseGroup.gr_gid:
      raise ConfigError("Group '{0}' specified in config file '{1}' does not match effective group (name={2}, gid={3}).".format(self.Conf['Group'], self.ConfPath, self.EffectiveGroup.gr_name, self.EffectiveGroup.gr_gid)) 

    
    try:
      if not isdir(self.DataPath):
        os.mkdir(self.DataPath)
      
      if not isdir(self.ErrorPath):
        os.mkdir(self.ErrorPath)

      if not isdir(self.TempPath):
        os.mkdir(self.TempPath)
      
      if not isdir(self.TrashPath):
        os.mkdir(self.TrashPath)
    except Exception as e:
      raise ConfigError("Error checking or creating database directories in '{0}': {1}".format(self.Path, str(e)))


  def __getitem__(self, hash):
    RequireValidHash(hash)
    path = self.HashToPath(hash)
    
    if not exists(path):
      return KeyError("Hash '{0}' does not exist in database.".format(hash))

    return HashFile(self, path, hash)

  def __contains__(self, hash):
    try:
      return exists(self.HashToPath(hash))
    except ValueError: 
      #designed to catch error from RequireValidHash()
      return False

  def HashToPath(self, hash):
    RequireValidHash(hash)
    return join(self.DataPath, hash[0:2], hash[2:4], hash)
  
  def HashToInternalURI(self, hash):
    RequireValidHash(hash)
    return join(self.InternalLocation, hash[0:2], hash[2:4], hash)


  def TempDir(self):
    return TempDir(self)
 
  
  def PutStream(self, stream):
    sha1 = hashlib.sha1()
    with self.TempDir() as TD:
      with open(TD['StreamFile'].Path, 'wb', buffering=0) as output:
        while True:
          buf = stream.read(4096)
          if not buf:
            break
          sha1.update(buf)
          output.write(buf)
        pass#while
      pass#with
      
      hash = sha1.hexdigest()
      self._MoveFile(TD['StreamFile'].Path, hash)
      return hash
    pass#with  

  
  def PutData(self, data):
    stream = io.BytesIO(data)
    return self.PutStream(stream)

  def PutFile(self, path):
    with open(path, 'rb', buffering=0) as stream:
      return self.PutStream(stream)


 
  def _MoveFile(self, sourcepath, hash):
    destpath = self.HashToPath(hash)

    if exists(destpath):
      return
    
    if not isdir(dirname(destpath)):
      os.makedirs(dirname(destpath))
    
    # Move and remove write privileges
    os.rename(sourcepath, destpath)
    os.chmod(destpath, os.stat(destpath).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    



class TempDir():
  def __init__(self, Client):
    self.Client = Client
    self.Path = join(self.Client.TempPath, RandomName32())
    self.Retain = False

  def __enter__(self):
    os.mkdir(self.Path)
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    if exc_type is not None:
      with open(join(self.Path, 'Python-Exception.txt'), 'wt', encoding='utf-8') as ef:
        ef.write(FormatException(exc_value))
      
    if exc_type is not None or self.Retain:
      shutil.move(self.Path, self.Client.ErrorPath)
    else:
      shutil.rmtree(self.Path)

  def __getitem__(self, FileName):
    if not FILENAME_MATCH(FileName):
      raise ValueError("Invalid file name: {0}".format(FileName))
    return TempFile(self, join(self.Path, FileName))
  


class BaseFile():
  def __init__(self, Client, Path):
    self.Client = Client
    self.Path = Path

  def GetStream(self):
    return open(self.Path, 'rb')

  def GetData(self):
    with self.GetStream() as stream:
      return stream.read()


class HashFile(BaseFile):
  def __init__(self, Client, Path, Hash):
    super().__init__(Client, Path)
    self.Hash = Hash

  @property
  def InternalURI(self):
    return self.Client.HashToInternalURI(self.Hash)


class TempFile(BaseFile):
  def __init__(self, TempDir, Path):
    super().__init__(TempDir.Client, Path)
    self.TempDir = TempDir
  
  def Ingest(self):
    sha1 = hashlib.sha1()
    with open(self.Path, 'rb', buffering=0) as f:
      while True:
        buf = f.read(4096)
        if not buf:
          break
        sha1.update(buf)
    
    hash = sha1.hexdigest()
    self.Client._MoveFile(self.Path, hash)
    return hash

  def PutStream(self, stream):
    with open(self.Path, 'wb', buffering=0) as f:
      while True:
        buf = stream.read(4096)
        if not buf:
          break
        f.write(buf)

  def PutData(self, data):
    stream = io.BytesIO(data)
    return self.PutStream(stream)

  def PutFile(self, path):
    with open(path, 'rb', buffering=0) as stream:
      return self.PutStream(stream)
  
  def Link(self, hash):
    os.symlink(self.Client[hash].Path, self.Path)


  def Delete(self):
    os.unlink(self.Path)







__all__ = (
  'ConfigError',
  'Client',
  )


