# ******************************************************************************
#   Copyright (c) 2018-2022. FAUCHER Julien & FRANCE Loic.                     *
#                                                                              *
#   This file is part of SooL generator.                                       *
#                                                                              *
#   SooL generator is free software: you can redistribute it and/or modify     *
#   it under the terms of the GNU Lesser General Public License                *
#   as published by the Free Software Foundation, either version 3             *
#   of the License, or (at your option) any later version.                     *
#                                                                              *
#   SooL core Library is distributed in the hope that it will be useful,       *
#   but WITHOUT ANY WARRANTY; without even the implied warranty of             *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the               *
#   GNU Lesser General Public License for more details.                        *
#                                                                              *
#   You should have received a copy of the GNU Lesser General Public License   *
#   along with SooL core Library. If not, see  <https://www.gnu.org/licenses/>.*
# ******************************************************************************

import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import datetime
import os
import sys
import typing as T
import hashlib
import subprocess

from sool.structure import Chip, ChipSet

from sool.tools import global_parameters

class SoolManifest:
    def __init__(self,path):
        self.file_path  = path
        os.makedirs(os.path.dirname(path),exist_ok=True)

        self.pdsc_version : T.Dict[str,str] = dict()
        self.generated_groups : T.List[str] = list()
        self.chip_association : T.List[Chip] = list()
        """Association chipname -> SVD,cmsis header"""
        self.generation_date : str = datetime.datetime.now().isoformat(timespec='seconds')

        self.root : ET.Element = ET.Element("manifest")
        self.hash : ET.Element = ET.SubElement(self.root,"hash")

        try :
            sha1 = subprocess.check_output(["git", "rev-parse","HEAD"]).strip().decode()
        except :
            sha1 = "0"*40

        self.hash.append(ET.Element("mainv", {"short": sha1[:6], "value": sha1}))

        self.write_generation_info()

    def add_pdsc_version(self,family : str, version : str):
        self.pdsc_version[family] = version

    def add_generated_group(self,group : str):
        if group not in self.generated_groups:
            self.generated_groups.append(group)

    def add_chip(self,chip : T.Union[Chip,ChipSet]):
        if isinstance(chip, ChipSet) :
            for c in chip :
                self.add_chip(c)
        else:
            if chip not in self.chip_association :
                self.chip_association.append(chip)

    def write_generation_info(self):
        gen_info : ET.Element = ET.SubElement(self.root,"generation")

        gen_info.append(ET.Element("date",{"value" : self.generation_date}))
        gen_info.append(ET.Element("command-line",{"args":" ".join(sys.argv[1:])}))
        gen_info.append(global_parameters.to_xml)

    def write_pdsc_infos(self):
        hasher = hashlib.sha1()
        pdsc_root : ET.Element = ET.SubElement(self.root,"fileset")

        for k in sorted(self.pdsc_version.keys()) :
            pdsc_root.append(ET.Element("family",{"name":k,"version":self.pdsc_version[k]}))
            hasher.update(bytes(f"{k}={self.pdsc_version[k]}","us-ascii"))

        digest = hasher.hexdigest()
        self.hash.append(ET.Element("files",{"short":digest[:6],"value": digest}))

    def write_groups_info(self):
        hasher = hashlib.sha1()
        groups_root : ET.Element = ET.SubElement(self.root,"groups")
        for group in sorted(self.generated_groups) :
            groups_root.append(ET.Element("group", {"name": group}))
            hasher.update(bytes(group,"us-ascii"))

        digest = hasher.hexdigest()

        self.hash.append(ET.Element("group",{"short": digest[:6], "value": digest}))

    def write_chips_info(self):
        hasher = hashlib.sha1()
        chips_root: ET.Element = ET.SubElement(self.root, "chips")

        families : T.Dict[str,ET.Element] = dict()

        for chip in sorted(self.chip_association,key=lambda x : x.name) :
            family = chip.family
            if family not in families :
                families[family] = ET.SubElement(chips_root,"family",{"name":family})
            elt = ET.Element("chip", {"define": chip.define,
                                      "header":os.path.basename(chip.header),
                                      "svd" : os.path.basename(chip.svd)})
            families[family].append(elt)
            hasher.update(bytes(str(ET.tostring(elt)),"us-ascii"))

        digest = hasher.hexdigest()
        self.hash.append(ET.Element("chips",{"short": digest[:6], "value": digest}))

    def construct_xml(self):
        self.write_pdsc_infos()
        self.write_groups_info()
        self.write_chips_info()

    def write_file(self):
        with open(self.file_path,"w") as out :
            dom = minidom.parseString(ET.tostring(self.root))
            pi = dom.createProcessingInstruction('xml-stylesheet','type="text/xsl" href="manifest.xsl"')
            root = dom.firstChild
            dom.insertBefore(pi, root)

            out.write(dom.toprettyxml())