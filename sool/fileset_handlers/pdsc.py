# ******************************************************************************
#  Copyright (c) 2018-2020 FAUCHER Julien & FRANCE Loic.                       *
#                                                                              *
#  This file is part of SooL generator.                                        *
#                                                                              *
#  SooL generator is free software: you can redistribute it and/or modify      *
#  it under the terms of the GNU Lesser General Public License                 *
#  as published by the Free Software Foundation, either version 3              *
#  of the License, or (at your option) any later version.                      *
#                                                                              *
#  SooL core Library is distributed in the hope that it will be useful,        *
#  but WITHOUT ANY WARRANTY; without even the implied warranty of              *
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the                *
#  GNU Lesser General Public License for more details.                         *
#                                                                              *
#  You should have received a copy of the GNU Lesser General Public License    *
#  along with SooL core Library. If not, see  <https://www.gnu.org/licenses/>. *
# ******************************************************************************

import logging
import os
import shutil
import glob

import typing as T
import xml.etree.ElementTree as ET

from copy import copy
from fnmatch import fnmatch

from sool.cleaners.corrector import cmsis_root_corrector
from sool.structure import Chip
from sool.cmsis_analysis import CMSISHeader
from sool.tools import global_parameters

logger = logging.getLogger()


class PDSCHandler:
	def __init__(self,path, analyze = True):
		self.path = path

		self.root : ET.Element = self.cache_and_remove_ns(self.path) if analyze else None

		self.chips : T.Set[Chip] = set()

		self.file_name : str = os.path.basename(self.path)
		self.version_string : str = ""
		self.family = self.file_name[5:self.file_name.rfind("_")]

		self.dest_paths : T.Dict[str,str] = {"svd" : "svd",
											 "header" : f"cmsis/{self.family}",
											 "pdsc" : "fileset"}

		"""Map of filename -> handler for all CMSIS header used by chips defined in the PDSC"""
		self._cmsis_handlers : T.Dict[str,CMSISHeader] = dict()

	@staticmethod
	def cache_and_remove_ns(filepath):
		"""
		Put the XML content into cache and remove the default namespace if relevant.
		"""
		#logger.info("Removing namespace and caching XML file.")
		with open(filepath, "r", encoding='utf-8') as init_file:
			cached = init_file.read()
			start = cached.find("<package")
			if start > -1:
				stop = cached.find('>', start)
				cached = cached[:start] + "<package" + cached[stop:]
			else:
				logger.warning("No xmlns found")

		return ET.fromstring(cached)

	@property
	def svd_names(self) -> T.List[str]:
		"""
		Returns the file name of all SVD associated with the current PDSC
		"""
		return sorted([os.path.basename(x.svd) for x in self.chips])

	@property
	def svd_to_define(self) -> T.Dict[str,str]:
		"""
		Provide a dictionary giving a SVD name to define mapping
		"""
		return {os.path.basename(x.svd):x.computed_define for x in self.chips}

	def process(self):
		"""
		Process the targeted PDSC file.
		Build the Chip set, associating define, svd and header.
		"""
		proc_list : T.List[ET.Element] = self.root.findall("devices/family/processor")
		family : ET.Element
		proc_ok = len(proc_list) > 0
		self.version_string = self.root.find("releases/release").attrib["version"]

		for family in self.root.findall("devices/family/subFamily") :
			if not proc_ok:
				proc_list = family.findall("processor")

			for processor in proc_list :
				current_assoc = Chip()
				# Can store Dcore if required
				if "Pname" in processor.attrib and processor.attrib["Pname"] :
					current_assoc.processor = processor.attrib["Pname"]

				current_assoc.from_node(family)

				for device in family.findall("device") :
					current_assoc.from_node(device)

					if not current_assoc.is_full :
						logger.error(f"Incomplete fileset for chip {device.attrib['Dname']}.")
					else:
						current_assoc.legalize()
						if current_assoc.fix(device.attrib["Dname"]) :
							# if not "STM32F1" in current_assoc.define and not fnmatch(device.attrib["Dname"],current_assoc.define.replace("x","?") + "*") :
							# 	logger.warning(f"\tChip/Define mismatch {device.attrib['Dname']} got {current_assoc.define}")
							if global_parameters.is_chip_valid(current_assoc.name) :
								self.chips.add(copy(current_assoc))

	def rebuild_extracted_associations(self,root_destination : str):
		"""
		Reconstruct paths to all associated files (Headers and SVD) targeting locally saved copy.
		:param root_destination: Root location where new files are located (by default .data/)
		"""
		destination_paths = self.dest_paths
		for key in destination_paths:
			destination_paths[key] = f"{root_destination}/{destination_paths[key]}"

		for chip in self.chips :
			chip.header = f'{destination_paths["header"]}/{os.path.basename(chip.header)}'
			chip.svd = f'{destination_paths["svd"]}/{os.path.basename(chip.svd)}'

	def init_filetree(self, root_path):
		"""
		Ensure the required filetree exists and clear the header folder before generation
		:param root_path: Root path to generate the filetree in
		:return: A dictionary providing a filetype -> path association.
		"""
		destination_paths = self.dest_paths
		shutil.rmtree(destination_paths["header"], True)
		for key in destination_paths:
			destination_paths[key] = f"{root_path}/{destination_paths[key]}"
			if not os.path.exists(destination_paths[key]):
				os.makedirs(destination_paths[key])
		return destination_paths

	def extract_to(self,root_destination :  str) -> "PDSCHandler":
		"""
		Given a decompressed Keil pack, retrieve all interesting files and copy them to a given directory.

		This function will create if required all the directory structure under root_destination.

		:param root_destination: The target directory which will receive all retrieved files.
		:return: A new PDSC handler, targeting the PDSC file after being moved.
		"""
		destination_paths = self.init_filetree(root_destination)

		ret = PDSCHandler(destination_paths["pdsc"] + "/" + os.path.basename(self.path), analyze=False)

		shutil.copy(self.path,destination_paths["pdsc"])

		header_src_done : T.Set[str] = set()
		base_path = os.path.dirname(self.path) + "/"
		for chip in self.chips :
			if not chip.is_full :
				logger.warning(f"Ignored not full association for define {chip.computed_define}")
				continue
			ret.chips.add(Chip(svd=chip.svd,
							   header=chip.header,
							   define=chip.define,
							   processor=chip.processor,
							   pdefine=chip.processor_define))

			shutil.copy(base_path + chip.svd,destination_paths["svd"])

			header_src =  base_path + chip.header
			if header_src not in header_src_done :
				header_src_done.add(header_src)
				for file in glob.glob(f"{os.path.dirname(base_path + chip.header)}/*.h"):
					logger.info(f"\tBatch retrieving header file {self.family}/{os.path.basename(file)}")
					shutil.copy(file, destination_paths["header"])
		logger.info(f"Files from {os.path.basename(self.path)} extracted to {root_destination}.")
		ret.rebuild_extracted_associations(root_destination)
		return ret



	def compute_cmsis_handlers(self):
		"""
		Ensures that all CMSIS headers handlers are initialized and processed.
		:return:
		"""
		self._cmsis_handlers.clear()

		for chip in self.chips :
			curr_handler = self.provide_cmsis_handler(chip)
			#Now the right handler is selected.
			chip.header = curr_handler.path
			chip.header_handler = curr_handler
			chip.cmsis_options = curr_handler.cmsis_conf
			if not chip.header_handler.is_structural :
				raise AssertionError(f"Chip header handler should be structural ! ({chip.computed_define}")

	def provide_cmsis_handler(self, chip : Chip) -> CMSISHeader:
		"""
		This function will return a valid CMSISHeader handler for a given chip
		:param chip: Chip for which we need a handler
		:return: Handler
		"""
		if chip.header not in self._cmsis_handlers:
			self._create_cmsis_handler(chip)
		handler = self._cmsis_handlers[chip.header]
		if handler.is_include_map:
			handler = self.provide_structural_from_include_map(chip, handler)
		return handler

	def _create_cmsis_handler(self, assoc : Chip):
		"""
		This function create the CMSIS header handler for the header file provided by assoc.
		:param assoc: Chip for which we need to create the handler
		:return: None
		"""
		self._cmsis_handlers[assoc.header] = CMSISHeader(assoc.header)
		new_handler = self._cmsis_handlers[assoc.header]
		new_handler.read()
		new_handler.process_include_table()
		if not new_handler.is_include_map:
			new_handler.process_structural()
		new_handler.clean()

	def provide_structural_from_include_map(self, chip : Chip, cmsis_handler : CMSISHeader) -> CMSISHeader:
		"""
		Given a chip and a CMSIS handler containing an include map (typically stm32f0xx.h), this function provide the
		CMSIS handler targeting the structural CMSIS header matching the chip define.

		:param chip: Chip which define should be looked up
		:param cmsis_handler: Include map handler
		:return: Structural handler
		"""
		if cmsis_handler.include_table[chip.define] not in self._cmsis_handlers:
			self._cmsis_handlers[cmsis_handler.include_table[chip.define]] = CMSISHeader(
				cmsis_handler.include_table[chip.define])
			cmsis_handler = self._cmsis_handlers[cmsis_handler.include_table[chip.define]]
			cmsis_handler.read()
			cmsis_handler.process_structural()
			cmsis_handler.apply_corrector(cmsis_root_corrector)
			cmsis_handler.clean()
		else:
			cmsis_handler = self._cmsis_handlers[cmsis_handler.include_table[chip.define]]
		return cmsis_handler

	def check_svd_define_association(self):
		define_to_svd : T.Dict[str,T.List[str]]= dict()
		svd_list : T.Dict[str,str] = dict()
		defines_to_fix : T.List[str] = list()

		logger.info(f"Checking define to SVD association for {self.file_name}...")
		for c in self.chips :
			# Build a formated SVD name, without extension
			formated_svd_name = os.path.basename(c.svd)
			formated_svd_name = formated_svd_name[:formated_svd_name.find(".svd")]
			if "_" in formated_svd_name :
				formated_svd_name = formated_svd_name[:formated_svd_name.find("_")]

			formated_svd_name = formated_svd_name.replace("x","*") + "*"

			# Integrity check on formated SVD names, avoiding ambiguous references.
			if formated_svd_name in svd_list and svd_list[formated_svd_name] != c.svd :
				logger.error(f"\tVarious SVD match same formated template : {svd_list[formated_svd_name]} and {c.svd}")
			svd_list[formated_svd_name] = c.svd


			if c.define not in define_to_svd :
				# New association
				define_to_svd[c.define] = [formated_svd_name]
			elif define_to_svd[c.define] == formated_svd_name :
				# No issue
				pass
			elif formated_svd_name not in define_to_svd[c.define] :
				# The SVD name match a define already matched to another SVD
				define_to_svd[c.define].append(formated_svd_name)
				defines_to_fix.append(c.define)
				logger.error(f"\tDefine to SVD integrity failure : {c.define} mapped to {[svd_list[x] for x in define_to_svd[c.define]]} and {c.svd}")

		# Try to fix associations based on most specific pattern matching.
		for broken_def in defines_to_fix :
			for broken_chip in [x for x in self.chips if x.define == broken_def]:
				fixed = False
				for potential_svd_pattern in sorted(define_to_svd[broken_def],key=lambda x: x.count("*")) :
					if not fixed and fnmatch(broken_chip.define,potential_svd_pattern) :
						logger.warning(f"\t\tResolved {broken_chip.name} SVD from {broken_chip.svd} to {svd_list[potential_svd_pattern]}")
						broken_chip.svd = svd_list[potential_svd_pattern]
						fixed = True

					if fixed :
						break

				if not fixed :
					logger.warning(f"\t\tUnable to fix {broken_chip.name} SVD")


