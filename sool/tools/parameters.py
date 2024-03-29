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

import typing as T
import logging
import xml.etree.ElementTree as ET
import fnmatch
import os

logger = logging.getLogger()


class ParametersHandler :
	generate_options = {"no-phy" 	: "Generate to allow targetting a non-physical device (emulation).",
						"big-endian": "Swich to big endian memory organization.",
						"rccf"		: "RCC functions"}

	defined_keil_archive = {
		"STM32F0": "Keil.STM32F0xx_DFP.",
		"STM32F1": "Keil.STM32F1xx_DFP.",
		"STM32F2": "Keil.STM32F2xx_DFP.",
		"STM32F3": "Keil.STM32F3xx_DFP.",
		"STM32F4": "Keil.STM32F4xx_DFP.",
		"STM32F7": "Keil.STM32F7xx_DFP.",
		"STM32H7": "Keil.STM32H7xx_DFP.",
		"STM32L0": "Keil.STM32L0xx_DFP.",
		"STM32L1": "Keil.STM32L1xx_DFP.",
		"STM32L4": "Keil.STM32L4xx_DFP.",
		"STM32L5": "Keil.STM32L5xx_DFP.",
		"STM32MP1": "Keil.STM32MP1xx_DFP.",
		"STM32G0": "Keil.STM32G0xx_DFP.",
		"STM32G4": "Keil.STM32G4xx_DFP.",
		"STM32W1": "Keil.STM32W1xx_DFP.",
		"STM32WB": "Keil.STM32WBxx_DFP."
	}

	default_archives_version = {
		"STM32F0": "2.1.0",
		"STM32F1": "2.3.0",
		"STM32F2": "2.9.0",
		"STM32F3": "2.1.0",
		"STM32F4": "2.15.0",
		"STM32F7": "2.14.0",
		"STM32G0": "1.2.0",
		"STM32G4": "1.2.0",
		"STM32H7": "2.6.0",
		"STM32L0": "2.1.0",
		"STM32L1": "1.3.0",
		"STM32L4": "2.5.0",
		"STM32L5": "1.3.0",
		"STM32MP1": "1.3.0",
		"STM32WB": "1.1.0"
	}

	checkpoint_list = [
		"POST_PDSC",
		"POST_SVD",
		"POST_MERGE",
		"POST_ANALYZE"
	]

	def __init__(self):
		self.reuse_db			: bool = False
		self.dump_db			: bool = False
		self.dump_sql			: bool = False
		self.generate_rccf		: bool = False
		self.physical_mapping	: bool = True
		self.big_endian			: bool = False
		self.store_packs 		: bool = False
		self.use_local_packs 	: bool = False
		self.update_requested 	: bool = False
		self.force_pack_version	: bool = False
		self.refresh_output     : bool = False

		self.group_filter		: T.List[str] = list()
		self.chips_filter		: T.List[str] = list()
		self.chips_exclude		: T.List[str] = list()

		self.family_update_request : T.List[str] = list()
		self.family_upgrade_request: T.List[str] = list()
		self.fileset_reinit		: bool = False

		self.checkpoint_request : T.Set[str] = set()
		self.checkpoint_restore_point : str = None

		self.cubeide_path		: str = None
		self.manifest_copy_path : str = None
		self.headers_copy_path  : str = None

		self.jobs : int = 1

		self.archives = dict()

		# Constants as of now
		self.main_out = "out"
		self.out_include = f"{self.main_out}/include"
		self.out_sys = f"{self.main_out}/system/include"
		self.out_rccf = f"{self.main_out}/rccf"

		self.main_data = ".data"
		self.svd_path = f"{self.main_data}/svd"
		self.svdst_path = f"{self.main_data}/svd-st"
		self.packs_path = f"{self.main_data}/packs"
		self.cmsis_path = f"{self.main_data}/cmsis"
		self.config_file = f"{self.main_data}/versions.ini"

		self.fileset_path = f"{self.main_data}/fileset"
		self.pdsc_path_model = f"{self.fileset_path}/*.pdsc"
		self.pickle_data_path = f"{self.main_data}/SooL.dat"

		self.generation_manifest_path = f"{self.main_out}/manifest.xml"


	@property
	def to_xml(self) -> ET.Element:
		root = ET.Element("runtime-parameters")
		generation_sec : ET.Element = ET.SubElement(root,"generation")
		generation_sec.append(ET.Element("dump-sql", {"value": "true" if self.dump_sql else "false"}))
		generation_sec.append(ET.Element("no-phy-avail", {"value": "false" if self.physical_mapping else "true"}))
		generation_sec.append(ET.Element("endianness", {"value": "big" if self.big_endian else "little"}))

		filters_sec : ET.Element = ET.SubElement(root,"filters",{"requested":"true" if len(self.group_filter) else "false"})
		for group in sorted(self.group_filter) :
			filters_sec.append(ET.Element("group",{"name":group}))

		for chip in sorted(self.chips_filter):
			filters_sec.append(ET.Element("chips", {"keep": chip}))

		for chip in sorted(self.chips_exclude):
			filters_sec.append(ET.Element("chips", {"remove": chip}))


		update_sec : ET.Element = ET.SubElement(root,"update",{"requested":"true" if self.update_requested else "false"})
		for f in sorted(self.update_list) :
			update_sec.append(ET.Element("family",{"name":f}))

		return root

	@property
	def need_update(self):
		return self.update_requested and (len(self.family_update_request) or len(self.family_upgrade_request))

	@property
	def update_list(self):
		return sorted(list(set(self.family_upgrade_request + self.family_update_request)))

	@property
	def got_group_filter(self):
		return len(self.group_filter) > 0

	@property
	def got_chip_filter(self):
		return len(self.chips_filter) > 0

	@property
	def copy_manifest(self):
		return self.manifest_copy_path is not None	\

	@property
	def copy_headers(self):
		return self.headers_copy_path is not None

	@property
	def got_chip_exclude(self):
		return len(self.chips_exclude) > 0

	def __chip_keep(self,chip_name : str) -> bool:
		if not self.got_chip_filter :
			return True
		for p in self.chips_filter :
			if fnmatch.fnmatch(chip_name,p) :
				return True

	def __chip_exclude(self, chip_name: str) -> bool:
		if not self.got_chip_exclude:
			return False
		for p in self.chips_exclude:
			if fnmatch.fnmatch(chip_name, p):
				return True
		return False

	def is_chip_valid(self, chip_name : str):
		return self.__chip_keep(chip_name) and not self.__chip_exclude(chip_name)

	def process_generate(self,options : T.List[str]):

		if len(options) == 0 : return
		for token in options :
			if token == "no-phy" :
				self.physical_mapping = False
				logger.warning("The library will be generated with non-physical capabilities.")
			elif token == "big-endian" :
				self.big_endian = True
				logger.warning("The library will be generated for big endian.")
			elif token == "dump":
				self.dump_db = True
			elif token == "sql":
				self.dump_sql = True
			elif token == "rccf":
				self.generate_rccf = True
			else :
				logger.error(f"Unrecognized option provided to generate : {token} will be ignored.")

	def process_checkpoints(self,chkpt_request,chkpt_restore):
		for chkpt in chkpt_request :
			if chkpt == "ALL" :
				self.checkpoint_request = set(self.checkpoint_list)
				break
			elif chkpt in ParametersHandler.checkpoint_list :
				self.checkpoint_request.add(chkpt)
			else:
				raise KeyError

		if chkpt_restore is not None :
			if chkpt_restore == "LAST" :
				self.checkpoint_restore_point = self.checkpoint_list[-1]
			elif chkpt_restore not in self.checkpoint_list :
				raise KeyError
			else :
				self.checkpoint_restore_point = chkpt_restore

	def checkpoint_needed(self,chkpt):
		return chkpt in self.checkpoint_request

	def process_updates(self, update,upgrade):
		if self.update_requested:
			if 'all' in update:
				self.fileset_reinit = True
				self.family_update_request = list(self.archives.keys())
			elif 'all' in upgrade:
				self.family_update_request.extend(update)
				self.family_upgrade_request = list(self.archives.keys())
			else:
				self.family_update_request.extend(update)
				self.family_upgrade_request.extend(upgrade)

	def read_args(self,args,archive_list):
		self.archives = archive_list

		self.process_generate(args.generate)
		self.process_checkpoints(args.checkpoint, args.restore)
		# self.physical_mapping 	= not args.no_phy
		# self.big_endian			= args.big_endian

		self.force_pack_version	= args.force_version
		self.store_packs		= args.store_packs
		self.use_local_packs	= args.use_local_packs
		self.update_requested	= args.update_svd or args.upgrade_svd
		self.jobs				= args.jobs
		self.cubeide_path		= args.cubeide_path
		self.group_filter       = args.group_filter
		self.refresh_output     = args.refresh_output

		self.manifest_copy_path = args.manifest_path
		if self.copy_manifest and os.path.isdir(self.manifest_copy_path) :
			self.manifest_copy_path = f"{os.path.abspath(self.manifest_copy_path)}/manifest.xml"

		self.headers_copy_path = args.header_path

		if "all" in [x.lower() for x in self.group_filter] :
			self.group_filter.clear()

		self.chips_filter = args.chips_filter
		self.chips_exclude = args.chips_exclude

		update_list = args.update_svd
		upgrade_list = args.upgrade_svd
		self.process_updates(update_list,upgrade_list)

		for exclude in self.chips_exclude :
			self.family_upgrade_request = [f for f in self.family_upgrade_request if not fnmatch.fnmatch(f, exclude)]
			self.family_update_request =  [f for f in self.family_update_request  if not fnmatch.fnmatch(f, exclude)]




global_parameters = ParametersHandler()
