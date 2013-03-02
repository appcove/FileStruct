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


from os.path import join, exists, isfile, isdir, dirname, basename, normpath
import unittest
import os
import pwd
import grp
import tempfile
import shutil
import json
import hashlib


try: import FileStruct
except ImportError:
  # Make sure "python -m unittest discover" will work from source checkout
  import sys
  src_dir = join(dirname(__file__), '..', '..')
  assert isdir(normpath(join(src_dir, 'FileStruct'))), normpath(join(src_dir, 'FileStruct'))
  sys.path.insert(0, src_dir)
  try:
    import FileStruct
  finally:
    sys.path.pop(0)



class TestClientBase(unittest.TestCase):

  valid_config = '{"Version":1}'

  def setUp(self):
    self.Path = tempfile.mkdtemp(suffix='_FileStruct_Test')
    self.PathConfig = join(self.Path, 'FileStruct.json')

  def tearDown(self):
    try: shutil.rmtree(self.Path)
    except OSError: pass

  def write_config(self, config, json_encode=True):
    if json_encode: config = json.dumps(config, indent=2)
    with open(self.PathConfig, 'w', encoding='utf-8') as fp:
      fp.write(config)

  def client_from_valid_config(self):
    return self.client_from_config(self.valid_config, False)

  def client_from_config(self, config, json_encode=True):
    self.write_config(config, json_encode=json_encode)
    return FileStruct.Client(self.Path)

  def client_from_config_err(self, config, json_encode=True):
    with self.assertRaises(FileStruct.ConfigError):
      self.client_from_config(config, json_encode=json_encode)



class TestClientBasic(TestClientBase):

  def test_Minimal(self):
    self.client_from_valid_config()
    self.client_from_config({'Version': 1})
    self.client_from_config({'Version': '1'})
    self.client_from_config('{"Version": "1"}', False)

  def test_Comments(self):
    self.client_from_config('''{
      # Some test comment
      "Version": 1}''', False)
    self.client_from_config('''{
      # Some test comment
      "Version": 1
      #Waka waka
    }''', False)
    self.client_from_config('{"Version": 1\r#test}\n}', False)

  def test_ExtraData(self):
    self.client_from_config({'Version': 1, 'WhateverKey': 2, 3: 'SomeValue'})
    self.client_from_config({'Version': 1, 'User': 'whoever', 'Group': 'whatever'})

  def test_UserGroup(self):
    self.client_from_config({'Version': 1, 'User': 123, 'Group': 456})
    self.client_from_config({'Version': 1, 'User': 'one', 'Group': 'two'})
    self.client_from_config({'Version': 1, 'User': None, 'Group': None})
    self.client_from_config({'Version': 1, 'User': [1, 'asd'], 'Group': {'a': [42]}})


class TestClientInvalidConfig(TestClientBase):

  def test_EmptyOrGibberish(self):
    self.client_from_config_err('', False)
    self.client_from_config_err('some non-json text {{{', False)
    self.client_from_config_err('{"Version": 1', False)
    self.client_from_config_err("Version: 1", False)
    self.client_from_config_err('{"Version": 1}')
    self.client_from_config_err('{"Version": 1\n#comment }', False)
    self.client_from_config_err('{"Version": 1#comment }', False)
    self.client_from_config_err('{#"Version": 1}', False)
    self.client_from_config_err('#{"Version": 1}', False)
    self.client_from_config_err(self.valid_config.rstrip() + '#test', False)

  def test_RandomJSON(self):
    self.client_from_config_err({})
    self.client_from_config_err(None)
    self.client_from_config_err({'RandomKey': 'WhateverValue'})
    self.client_from_config_err({'Verson': 1})
    self.client_from_config_err([1, 2, {'test': 'data'}])

  def test_Version(self):
    # Allow for any positive-int one
    for ver in [-1,0,'1beta','beta1','-1','a','1a','123b',[]]:
      self.client_from_config_err({'Version': ver})

  def test_NoConfig(self):
    self.assertFalse(exists(self.PathConfig))

    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)
    self.assertFalse(exists(self.PathConfig)) # make sure it wasn't auto-created

    self.write_config(self.valid_config, False)
    os.chmod(self.PathConfig, 0)
    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)

    self.assertTrue(exists(self.PathConfig))


class TestClientDBDir(TestClientBase):

  def find_xid(self, getent, skip_check=None, nx=False):
    xid = 1
    while xid < 65535:
      xid += 1
      try: struct = getent(xid)
      except KeyError:
        if not nx: continue
        else: struct = xid
      else:
        if nx: continue
      if skip_check and skip_check(struct): continue
      return xid

  def mangle_stat(self, stat_result, gid=False, uid=False):
    self.assertTrue(uid or gid)
    uid_real_pwd_struct = pwd.getpwuid(os.geteuid())
    dir_grp_struct = grp.getgrgid(stat_result.st_gid)
    # Make sure "original" data passes *expected* check
    stat_result = type( 'mock_stat', (object,),
      dict((k, getattr(stat_result, k)) for k in dir(stat_result) if not k.startswith('_')) )
    self.assertFalse(
      uid_real_pwd_struct.pw_gid != dir_grp_struct.gr_gid
      and uid_real_pwd_struct.pw_name not in dir_grp_struct.gr_mem )
    if uid:
      if uid is not True:
        stat_result.st_uid = uid
      else:
        stat_result.st_uid = self.find_xid( pwd.getpwuid,
          lambda s: s.pw_uid == stat_result.st_uid\
            or s.pw_name in dir_grp_struct.gr_mem )
    if gid:
      if gid is not True:
        stat_result.st_gid = gid
      else:
        stat_result.st_gid = self.find_xid( grp.getgrgid,
          lambda s: s.gr_gid == stat_result.st_gid\
            or uid_real_pwd_struct.pw_name in s.gr_mem )
    return stat_result


  def test_MissingDir(self):
    os.rmdir(self.Path)
    self.assertFalse(exists(self.Path))
    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)
    self.assertFalse(exists(self.Path)) # make sure it wasn't auto-created

    # Valid config file in place of dir
    with open(self.Path, 'w', encoding='utf-8') as fp:
      fp.write(self.valid_config)
    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)
    self.assertTrue(isfile(self.Path))

  def test_DataDirCreated(self):
    # Expected to be there, according to frontend httpd setup
    data_dir = join(self.Path, 'Data')
    self.assertFalse(isdir(data_dir))
    self.client_from_valid_config()
    self.assertTrue(isdir(data_dir))


  def test_GidMismatch(self):
    geteuid = os.geteuid
    os.geteuid = lambda: self.find_xid( pwd.getpwuid,
      lambda s: s.pw_uid == stat_result.st_uid\
        or s.pw_gid == os.stat(self.Path).gr_gid\
        or s.pw_name in dir_grp_struct.gr_mem )
    try:
      with self.assertRaises(FileStruct.ConfigError):
        self.client_from_valid_config()
    finally:
      os.geteuid = geteuid

  def test_NoPasswdGroupEntries(self):
    geteuid, os.geteuid = os.geteuid, lambda: self.find_xid(pwd.getpwuid, nx=True)
    try:
      with self.assertRaises(KeyError):
        pwd.getpwuid(os.geteuid())
      with self.assertRaises(FileStruct.ConfigError):
        self.client_from_valid_config()
    finally:
      os.geteuid = geteuid
    getegid, os.getegid = os.getegid, lambda: self.find_xid(grp.getgrgid, nx=True)
    try:
      with self.assertRaises(KeyError):
        grp.getgrgid(os.getegid())
      with self.assertRaises(FileStruct.ConfigError):
        self.client_from_valid_config()
    finally:
      os.getegid = getegid

  def test_InvalidDirGid(self):
    stat, os.stat = os.stat, lambda path: self.mangle_stat(stat(path), gid=True)
    try:
      with self.assertRaises(FileStruct.ConfigError):
        self.client_from_valid_config()
    finally:
      os.stat = stat

  def test_AnyDirUidInPasswdWorks(self):
    stat, os.stat = os.stat, lambda path: self.mangle_stat(stat(path), uid=True)
    try:
      self.client_from_valid_config()
    finally:
      os.stat = stat

  def test_NoDirGidEntry(self):
    stat, os.stat = os.stat, lambda path:\
      self.mangle_stat(stat(path), gid=self.find_xid(grp.getgrgid, nx=True))
    try:
      with self.assertRaises(FileStruct.ConfigError):
        self.client_from_valid_config()
    finally:
      os.stat = stat


# class TestClientGet(TestClientBase):

# 	def test_Get(self):
# 	def test_GetMissing(self):
# 	def test_GetInvalidHash(self):
# 	def test_Contains(self):
# 	def test_ContainsInvalidHash(self):
# 	def test_ContainsMissing(self):
# 	def test_InternalURI(self):
# 	def test_InternalURIInvalidHash(self):
# 	def test_InternalURIMissing(self):


# class TestClientPut(TestClientBase):
# class TestClientTempDir(TestClientBase):




if __name__ == '__main__':
  unittest.main()
