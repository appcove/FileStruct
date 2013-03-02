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
import random
import string


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

  def setUp(self):
    self.ValidConfig = '{"Version":1}'
    self.ValidConfigVersion = 1

    self.Path = tempfile.mkdtemp(suffix='_FileStruct_Test')
    self.DataPath = join(self.Path, 'Data') # expected to be there by e.g. httpd
    self.PathConfig = join(self.Path, 'FileStruct.json')

  def tearDown(self):
    try: shutil.rmtree(self.Path)
    except OSError: pass

  def write_config(self, config, json_encode=True):
    if json_encode: config = json.dumps(config, indent=2)
    with open(self.PathConfig, 'w', encoding='utf-8') as fp:
      fp.write(config)

  def client_from_valid_config(self):
    return self.client_from_config(self.ValidConfig, False)

  def client_from_config(self, config, json_encode=True):
    self.write_config(config, json_encode=json_encode)
    return FileStruct.Client(self.Path)

  def client_from_config_err(self, config, json_encode=True):
    with self.assertRaises(FileStruct.ConfigError):
      self.client_from_config(config, json_encode=json_encode)


class TestClientBasic(TestClientBase):

  def test_Minimal(self):
    self.assertTrue(self.client_from_valid_config()) # to make sure that "if client:" will work
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
    self.client_from_config_err(self.ValidConfig.rstrip() + '#test', False)

  def test_Signature(self):
    self.write_config(self.ValidConfig, False)
    FileStruct.Client(Path=self.Path, InternalLocation='/Whatever')
    FileStruct.Client(self.Path, '/Whatever')
    with self.assertRaises(TypeError):
      FileStruct.Client()
    with self.assertRaises(TypeError):
      FileStruct.Client(InternalLocation='/Whatever')

  def test_Types(self):
    self.write_config(self.ValidConfig, False)
    with self.assertRaises(Exception):
      FileStruct.Client(None)
    with self.assertRaises(Exception):
      FileStruct.Client(object())
    FileStruct.Client(self.Path, None)
    FileStruct.Client(self.Path, object())
    with self.assertRaises(TypeError):
      FileStruct.Client(self.Path.encode('utf-8'))
    FileStruct.Client(self.Path, b'/Whatever')

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

    self.write_config(self.ValidConfig, False)
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
      fp.write(self.ValidConfig)
    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)
    self.assertTrue(isfile(self.Path))

  def test_DataDirCreated(self):
    # Expected to be there, according to frontend httpd setup
    self.assertFalse(isdir(self.DataPath))
    self.client_from_valid_config()
    self.assertTrue(isdir(self.DataPath))


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


class TestClientOps(TestClientBase):

  def setUp(self):
    super(TestClientOps, self).setUp()

    self.write_config(self.ValidConfig, False)
    self.InternalLocation = '/Whatever'
    self.Client = FileStruct.Client(self.Path, self.InternalLocation)

    self.FileContents = b'abcd'
    self.FileHash = self.Client.PutData(self.FileContents)

    self.FileHashNX = self.Client.PutData(b'')
    os.unlink(self.Client[self.FileHashNX].Path)

    random.seed(42)
    self.FileHashInvalidList = [
      self.FileHash[:-1] + '\0',
      'x' + self.FileHash[1:],
      '123',
      'варвр',
      ''.join( random.choice(string.hexdigits.lower())
        for i in range(len(self.FileHash) - 2) ),
      self.FileHash[2:],
      self.FileHash + 'a123',
      self.FileHash[:-2] + 'AB' ]

    self.FileHashInvalidType = [
      None, object(), str, type, True, self.FileHash.encode('ascii') ]


class TestClientAttrs(TestClientOps):

  def test_PublicAttrs(self):
    self.assertEqual(self.Path, self.Client.Path)
    self.assertEqual(self.DataPath, self.Client.DataPath)

  def test_PrivateAttrs(self):
    self.assertEqual(self.PathConfig, self.Client.ConfPath)
    self.assertEqual(self.ValidConfigVersion, self.Client.Version)
    self.assertEqual(self.InternalLocation, self.Client.InternalLocation)


class TestClientHashes(TestClientOps):

  def test_Get(self):
    self.assertTrue(self.Client[self.FileHash])
    with self.assertRaises(KeyError):
      self.Client[self.FileHashNX]

  def test_GetInvalidHash(self):
    for bad_hash in self.FileHashInvalidList:
      with self.assertRaises(ValueError):
        self.Client[bad_hash]

  def test_GetInvalidType(self):
    for bad_type in self.FileHashInvalidType:
      with self.assertRaises(TypeError):
        self.Client[bad_type]

  def test_Contains(self):
    self.assertIs(self.FileHash in self.Client, True)
    self.assertIs(self.FileHashNX in self.Client, False)

  def test_ContainsInvalidType(self):
    for bad_type in self.FileHashInvalidType:
      with self.assertRaises(TypeError):
        bad_type in self.Client

  def test_ContainsInvalidHash(self):
    for bad_hash in self.FileHashInvalidList:
      self.assertFalse(bad_hash in self.Client)

  def test_InternalURI(self):
    self.assertTrue(self.Client.HashToInternalURI(self.FileHash))
    self.assertTrue(self.Client.HashToInternalURI(self.FileHashNX))
    self.assertIsInstance(self.Client.HashToInternalURI(self.FileHash), str)
    for bad_hash in self.FileHashInvalidList:
      with self.assertRaises(ValueError):
        self.Client.HashToInternalURI(bad_hash)
    for bad_type in self.FileHashInvalidType:
      with self.assertRaises(TypeError):
        self.Client.HashToInternalURI(bad_type)
    self.assertTrue(
      self.Client.HashToInternalURI(self.FileHash).startswith(self.InternalLocation + '/') )
    self.assertFalse('//' in self.Client.HashToInternalURI(self.FileHash))
    self.assertTrue(
      self.Client.HashToInternalURI(self.FileHashNX).startswith(self.InternalLocation + '/') )

  def test_InternalURISlashes(self):
    # Make sure paths are *not* auto-fixed (if fails, update docs)
    bad_path = '//some///broken/path/../whatever//./'
    client = FileStruct.Client(self.Path, bad_path)
    file_hash = client.PutData(self.FileContents)
    self.assertTrue(client.HashToInternalURI(file_hash).startswith(bad_path))
    self.assertFalse(client.HashToInternalURI(file_hash).startswith(bad_path + '/'))

  def test_InternalURIRecode(self):
    # Make sure path encoding is *not* auto-fixed (if fails, update docs)
    bad_path = '//some\0///broken\n\n/path/../фывапр//./'
    client = FileStruct.Client(self.Path, bad_path)
    file_hash = client.PutData(self.FileContents)
    self.assertTrue(client.HashToInternalURI(file_hash).startswith(bad_path))

  def test_Path(self):
    self.assertTrue(self.Client.HashToPath(self.FileHash))
    self.assertTrue(self.Client.HashToPath(self.FileHashNX))
    self.assertIsInstance(self.Client.HashToPath(self.FileHash), str)
    for bad_hash in self.FileHashInvalidList:
      with self.assertRaises(ValueError):
        self.Client.HashToPath(bad_hash)
    for bad_type in self.FileHashInvalidType:
      with self.assertRaises(TypeError):
        self.Client.HashToPath(bad_type)
    self.assertTrue(
      self.Client.HashToPath(self.FileHash).startswith(self.Path) )
    self.assertTrue(
      self.Client.HashToPath(self.FileHashNX).startswith(self.Path) )

  def test_GetTempDir(self):
    self.assertTrue(self.Client.TempDir)


# class TestClientFile(TestClientBase):

# 	def test_Stream(self):
# 	def test_Data(self):
# 	def test_NotADict(self):
# 	def test_InternalURI(self):


# class TestClientPut(TestClientBase):
# class TestClientTempDir(TestClientBase):




if __name__ == '__main__':
  unittest.main()