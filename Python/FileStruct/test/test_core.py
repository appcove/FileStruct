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



class TestClientInit(unittest.TestCase):

  def setUp(self):
    self.Path = tempfile.mkdtemp(suffix='_FileStruct_Test')
    self.PathConfig = join(self.Path, 'FileStruct.json')

  def tearDown(self):
    try: shutil.rmtree(self.Path)
    except OSError: pass


  valid_config = '{"Version":1}'

  def write_config(self, config, json_encode=True):
    if json_encode: config = json.dumps(config, indent=2)
    with open(self.PathConfig, 'w', encoding='utf-8') as fp:
      fp.write(config)

  def client_from_config(self, config, json_encode=True):
    self.write_config(config, json_encode=json_encode)
    return FileStruct.Client(self.Path)

  def client_from_config_err(self, config, json_encode=True):
    with self.assertRaises(FileStruct.ConfigError):
      self.client_from_config(config, json_encode=json_encode)


  def test_Basic(self):
    # Bare minimum
    self.client_from_config({'Version': 1})
    self.client_from_config({'Version': '1'})
    self.client_from_config('{"Version": "1"}', False)
    self.client_from_config(self.valid_config, False)

    # Comments
    self.client_from_config('''{
      # Some test comment
      "Version": 1}''', False)
    self.client_from_config('''{
      # Some test comment
      "Version": 1
      #Waka waka
    }''', False)
    self.client_from_config('{"Version": 1\r#test}\n}', False)

    # Misc data
    self.client_from_config({'Version': 1, 'WhateverKey': 2, 3: 'SomeValue'})
    self.client_from_config({'Version': 1, 'User': 'whoever', 'Group': 'whatever'})

    # Random User/Group types
    self.client_from_config({'Version': 1, 'User': 123, 'Group': 456})
    self.client_from_config({'Version': 1, 'User': None, 'Group': None})
    self.client_from_config({'Version': 1, 'User': [1, 'asd'], 'Group': {'a': [42]}})


  def test_LoadConfigInvalid(self):
    # Empty/gibberish config
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

    # Random json
    self.client_from_config_err({})
    self.client_from_config_err(None)
    self.client_from_config_err({'RandomKey': 'WhateverValue'})
    self.client_from_config_err({'Verson': 1})
    self.client_from_config_err([1, 2, {'test': 'data'}])

    # Version - allow for any positive-int one
    for ver in [-1,0,'1beta','beta1','-1','a','1a','123b',[]]:
      self.client_from_config_err({'Version': ver})


  def test_LoadConfigNX(self):
    self.assertFalse(exists(self.PathConfig))

    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)
    self.assertFalse(exists(self.PathConfig)) # make sure it wasn't auto-created

    self.write_config(self.valid_config, False)
    os.chmod(self.PathConfig, 0)
    with self.assertRaises(FileStruct.ConfigError):
      FileStruct.Client(self.Path)

    self.assertTrue(exists(self.PathConfig))


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


  def test_DirPermissions(self):
    import pwd, grp
    uid_real = os.geteuid()
    uid_test = uid_real + 1
    uid_real_pwd_struct = pwd.getpwuid(uid_real)

    def mangle_stat(stat_result, gid=False, uid=False):
      self.assertTrue(uid or gid)
      dir_grp_struct = grp.getgrgid(stat_result.st_gid)
      # Make sure "original" data passes *expected* check
      stat_result = type( 'mock_stat', (object,),
        dict((k, getattr(stat_result, k)) for k in dir(stat_result) if not k.startswith('_')) )
      self.assertFalse(
        uid_real_pwd_struct.pw_gid != dir_grp_struct.gr_gid
        and uid_real_pwd_struct.pw_name not in dir_grp_struct.gr_mem )
      if gid: stat_result.st_gid += 1
      if uid: stat_result.st_uid += 1
      return stat_result

    self.write_config(self.valid_config, False)
    FileStruct.Client(self.Path)

    # Fails if euid.pw_gid doesn't match path group
    geteuid, os.geteuid = os.geteuid, lambda: uid_test
    try:
      with self.assertRaises(FileStruct.ConfigError):
        FileStruct.Client(self.Path)
    finally:
      os.geteuid = geteuid

    # Fails if os.stat returns invalid gid
    stat, os.stat = os.stat, lambda path: mangle_stat(stat(path), gid=True)
    try:
      with self.assertRaises(FileStruct.ConfigError):
        FileStruct.Client(self.Path)
    finally:
      os.stat = stat

    # Doesn't care about path uid
    stat, os.stat = os.stat, lambda path: mangle_stat(stat(path), uid=True)
    try:
      FileStruct.Client(self.Path)
    finally:
      os.stat = stat


  def test_DataDirCreated(self):
    # Expected to be there, according to frontend httpd setup
    data_dir = join(self.Path, 'Data')
    self.assertFalse(isdir(data_dir))
    self.client_from_config(self.valid_config, False)
    self.assertTrue(isdir(data_dir))



if __name__ == '__main__':
  unittest.main()
