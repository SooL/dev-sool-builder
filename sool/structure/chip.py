# ******************************************************************************
#   Copyright (c) 2018-2023. FAUCHER Julien & FRANCE Loic.                     *
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

import os
import logging
import typing as T
import xml.etree.ElementTree as ET
from fnmatch import fnmatch
from sool.cmsis_analysis import CMSISHeader

logger = logging.getLogger()

class Chip:
	def __init__(self,
				 define: T.Optional[str] = None,
				 header: T.Optional[str] = None,
				 svd: T.Optional[str] = None,
				 processor: T.Optional[str] = None,
				 pdefine: T.Optional[str] = None,
				 cmsis_options : T.Optional[T.Dict[str,str]] = None):
		self.define = define
		self.header = header
		self.svd = svd
		self.processor = processor
		self.processor_define = pdefine
		self.header_handler : T.Union[CMSISHeader, None] = None
		self.cmsis_options = cmsis_options

	def __hash__(self):
		return hash((self.define, self.header, self.svd, self.processor))

	def __eq__(self, other):
		if isinstance(other, Chip) :
			return self.define == other.define and self.header == other.header and self.svd == other.svd and \
				   self.processor == other.processor

	def __repr__(self):
		return f'{self.define}{"" if self.processor is None else "_" + self.processor:<5s} : H = {self.header} S = {self.svd}'

	def __str__(self):
		return self.name

	def match(self, pattern):
		return fnmatch(self.name, pattern)

	@property
	def is_complete(self):
		return self.define is not None \
		   and self.header is not None \
		   and self.svd is not None

	def complete_from_node(self, element : ET.Element):
		headers = element.findall("compile[@header]")
		defines = element.findall("compile[@define]")
		svds = element.findall("debug[@svd]")

		for header_node in headers:
			if self.processor is None or ("Pname" in header_node.attrib and header_node.attrib["Pname"] == self.processor) :
				self.header = header_node.attrib["header"]
		for define_node in defines :
			if self.processor is None or ("Pname" in define_node.attrib and define_node.attrib["Pname"] == self.processor):
				self.define = define_node.attrib["define"]
		for svd_node in svds:
			self.svd = svd_node.attrib["svd"]

		if self.processor is not None :
			pdefs = element.findall("compile[@Pdefine]")
			for pdef_node in pdefs:
				if "Pname" in pdef_node.attrib and pdef_node.attrib["Pname"] == self.processor:
					self.processor_define = pdef_node.attrib["Pdefine"]

	@property
	def computed_define(self):
		return f'{self.define}{"_" + self.processor_define if self.processor_define is not None else ""}'

	@property
	def name(self):
		return self.computed_define

	def normalize(self):
		self.header = self.header.replace("\\", "/")
		self.svd = self.svd.replace("\\", "/")
		self.define = self.define.upper().replace("X", "x")
		# if 'g' in self.define:
		# 	self.define = self.define.replace("g", "G")

	def fix(self,chip_name : str) -> bool:
		#if fnmatch(chip_name, "STM32F401?[BCDE]*"):
		#	return True # fixed by Keil or ST, probably
		#	self.svd = os.path.dirname(self.svd) + "/STM32F401xE.svd"
		if fnmatch(chip_name, "STM32F401?[!BCDE]*"):
			self.svd = os.path.dirname(self.svd) + "/STM32F401x.svd"
		elif fnmatch(chip_name, "STM32G483*"):
			return False # Remove the chip as not used by us and tricky to fix. (Wrong binding SVD/Header (ノಠ益ಠ)ノ彡┻━┻)
		return True
	
	@staticmethod
	def get_family(chip_name : str):
		if not fnmatch(chip_name, "STM32*") :
			raise ValueError("Incompatible name")
		if fnmatch(chip_name, "STM32MP*"):
			return chip_name[:8]
		return chip_name[:7]

	@property
	def family(self) -> str:
		return Chip.get_family(self.name)