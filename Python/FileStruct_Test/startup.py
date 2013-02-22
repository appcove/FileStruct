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
      

import unittest
from . import StandardTestCase, SHA1



class Test1(StandardTestCase):

  def test_PutData1(self):
    client = self.TempFS.Client
    hash = client.PutData(b'')
    
    self.assertEqual(hash, SHA1.EmptyFile)
    




