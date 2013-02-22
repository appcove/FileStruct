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
      

from os.path import join
import unittest
import os
import pwd
import grp
import tempfile
import shutil
import json
import hashlib

import FileStruct





###############################################################################
class SHA1():
  EmptyFile = 'da39a3ee5e6b4b0d3255bfef95601890afd80709'


###############################################################################


class TempFS():
  def __init__(self):
    self.Path = None
    self.Client = None

    self.Config = {
      'Version': 1,
      'User': self.EffectiveUser.pw_name,
      'Group': self.EffectiveGroup.gr_name,
      }

  @property
  def EffectiveUser(self):
    return pwd.getpwuid(os.geteuid())

  @property
  def EffectiveGroup(self):
    return grp.getgrgid(os.getegid())


  def Create(self):
    if self.Path:
      raise Exception("Database already exists: {0}".format(self.Path))

    self.Path = tempfile.mkdtemp(suffix='_FileStruct_Test')
    
    with open(join(self.Path, 'FileStruct.json'), 'wt', encoding='utf-8') as fp:
      json.dump(self.Config, fp, indent=2)

    self.Client = FileStruct.Client(self.Path)  

  def Remove(self):
    if not self.Path:
      raise Exception("No database to remove: {0}".format(self.Path))
    
    shutil.rmtree(self.Path)
    self.Path = None
    self.Client = None



###############################################################################


class StandardTestCase(unittest.TestCase):
  def setUp(self):
    self.TempFS = TempFS()
    self.TempFS.Create()

  def tearDown(self):
    self.TempFS.Remove()


###############################################################################


