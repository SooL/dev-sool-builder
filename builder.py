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

from sool.tools import ParametersHandler
from sool.tools import SoolManifest
from sool.tools import Checkpoints

from sool.fileset_handlers import PDSCHandler
from sool.fileset_handlers import FileSetLocator
from sool.fileset_handlers import STFilesetHandler
from sool.fileset_handlers import SVDFile
from sool.fileset_handlers import KeilPack

from sool.structure import Group
from sool.structure import ChipSet

from sool.dispatchers.svd_dispatcher import svd_process_handler

from sool.generators import generate_sool_cmsis_config
from sool.generators import generate_sool_irqn
from sool.generators import generate_sool_chip_setup
from sool.generators import generate_records
from sool.generators import generate_get_reg
from sool.generators import generate_get_bit


import typing as T
import logging
import os
import shutil
import glob
import pickle
import sqlite3 as sql

logger = logging.getLogger()

class SooLBuilder:
	def __init__(self, params : ParametersHandler):
		self.params : ParametersHandler = params
		self.manifest = SoolManifest(self.params.generation_manifest_path)
		self.groups : T.Dict[str,Group] = dict()
		self.unavailable_families : T.List[str] = list()

		self.svd_file_handler_mapping : T.Dict[str,SVDFile] = dict()
		self.pdsc_handlers : T.List[PDSCHandler] = list()
		self.skip_analysis : bool = False

		self.packs_handlers: T.Dict[str,KeilPack] = dict()

		self.checkpoint_status : Checkpoints = Checkpoints()
		for c in ParametersHandler.checkpoint_list :
			self.checkpoint_status.add_chkpt(c)

		self._scraped_page = None

	def initialize_filestructure(self):
		if not os.path.exists(self.params.svd_path) or self.params.fileset_reinit:
			logger.info("First initialization")
			os.makedirs(self.params.svd_path , exist_ok=True)
			os.makedirs(self.params.svdst_path, exist_ok=True)
			os.makedirs(self.params.packs_path, exist_ok=True)
			os.makedirs(self.params.cmsis_path, exist_ok=True)

			if not self.params.update_requested :
				logger.info("No update requested on a first initialisation. Forcing full refresh")
				self.params.update_requested = True
				self.params.process_updates("all","all")


		if self.params.refresh_output:
			if os.path.exists("out/"):
				shutil.rmtree("out")

		os.makedirs(self.params.out_include,exist_ok=True)
		os.makedirs(self.params.out_sys,exist_ok=True)

	def update_fileset(self):
		if not self.params.need_update:
			logger.info("No update needed")
			return

		if self.params.use_local_packs:
			logger.info("Using local packs.")
		logger.warning("Refresh definition for following families :")
		for family in self.params.update_list:
			logger.warning(f"\t{family}")

		for family in self.params.update_list :
			try :
				self.ensure_pack(family)
			except RuntimeError as err:
				logger.error(f"\tIssue while retrieving {family}")
				self.unavailable_families.append(family)

		if len(self.unavailable_families) > 0:
			logger.warning("Several chip families have not been retrieved :")
			for chip in sorted(self.unavailable_families):
				logger.warning(f"\t{chip}")
		else:
			logger.info("All families retrieved")
		self._scraped_page = None

	def retrieve_packs(self,chip_family):

		p = KeilPack(chip_family,scraped_content=self._scraped_page)
		p.setup_version()
		if self._scraped_page is None and p.scraped_base_page is not None :
			self._scraped_page = p.scraped_base_page

		p.download_to(self.params.packs_path if self.params.store_packs or self.params.use_local_packs else None)

		self.packs_handlers[chip_family] = p

	def handle_pack(self, chip_family : str):
		p = self.packs_handlers[chip_family]
		p.extract_to()
		pdsc = PDSCHandler(p.pdsc_path)
		pdsc.process()
		pdsc.extract_to(self.params.main_data)

	def ensure_pack(self,chip_family):
		self.retrieve_packs(chip_family)
		self.handle_pack(chip_family)

	def process_pdsc(self):
		logger.info("Reading .pdsc files to map STM number to svd...")
		for pdsc_file in glob.glob(self.params.pdsc_path_model):
			logger.info(f"Reading {pdsc_file}...")
			self.pdsc_handlers.append(PDSCHandler(pdsc_file))
			self.pdsc_handlers[-1].process()
			self.pdsc_handlers[-1].rebuild_extracted_associations("./.data")
			self.pdsc_handlers[-1].compute_cmsis_handlers()
			pass

		for pdsc_handler in self.pdsc_handlers:
			pdsc_handler.check_svd_define_association()

	def extract_svd_from_pdsc(self):
		i = 1
		define_done_set : T.Set[str] = set()
		logger.info("Build SVD list...")
		for pdsc in self.pdsc_handlers :
			j = 1
			logger.info(f"Read PDSC {pdsc.path}")
			for chip_definition in pdsc.chips :
				logger.debug(f"Handling PDSC {i:2d}/{len(self.pdsc_handlers)} - Assoc {j:3d}/{len(pdsc.chips)}.")
				j += 1
				if not chip_definition.is_complete :
					logger.error("\tSkip not full association.")
					continue

				if os.path.exists(chip_definition.svd) :
					if chip_definition.computed_define in define_done_set :
						logger.error(f"\tSkipped due to define {chip_definition.computed_define} already read")
						if chip_definition.svd not in self.svd_file_handler_mapping :
							logger.error(f"\t\tSVD File {chip_definition.svd} skipped !")
						continue
					define_done_set.add(chip_definition.computed_define)
					if chip_definition.svd not in self.svd_file_handler_mapping :
						self.svd_file_handler_mapping[chip_definition.svd] = SVDFile(chip_definition.svd,{chip_definition})
					else :
						self.svd_file_handler_mapping[chip_definition.svd].chipset.add(chip_definition)
			i += 1

	def harden_svd_using_cube_ide(self):
		if self.params.cubeide_path is None:
			return
		init_def_list = ChipSet.reference_chipset.defines
		fsl = FileSetLocator(self.params.cubeide_path)
		fsl.retrieve_svd("./.data/svd-st")
		overall : STFilesetHandler = None
		for fileset in fsl.targets_list:
			newfs = STFilesetHandler(fileset)
			newfs.process()

			if overall is None:
				overall = newfs
			else:
				overall.merge(newfs)
		define_svd_mapping = overall.match_defines_svd(init_def_list)

		self.svd_file_handler_mapping.clear()
		logger.info("Fix SVD using ST's")
		to_be_removed = list()
		# force a copy to avoid side-effects
		ref_cs = {c for c in ChipSet.reference_chipset.chips}
		for chip in ref_cs :
			if chip.define in define_svd_mapping :
				chip.svd = f"./.data/svd-st/{list(define_svd_mapping[chip.define])[0]}"
				if chip.svd not in self.svd_file_handler_mapping :
					self.svd_file_handler_mapping[chip.svd] = SVDFile(chip.svd,{chip})
				else :
					self.svd_file_handler_mapping[chip.svd].chipset.add(chip)
			else :
				logger.info(f"Removing unmatched chip {chip}")
				to_be_removed.append(chip)

		for c in to_be_removed :
			ChipSet.reference_chipset.remove(c)
			for pdsc in self.pdsc_handlers :
				if c in pdsc.chips :
					pdsc.chips.remove(c)
		ChipSet.reference_chipset.chips = set(list(ChipSet.reference_chipset.chips))

	def process_svd(self):
		logger.info("SVD list done, begin processing")
		self.svd_file_handler_mapping = svd_process_handler(self.svd_file_handler_mapping,self.params.group_filter)

	def write_pdsc_infos_in_manifest(self):
		logger.info("Add PDSC info in manifest.")
		for pdsc in self.pdsc_handlers :
			self.manifest.add_pdsc_version(pdsc.family,pdsc.version_string)

	def write_chips_infos_in_manifest(self):
		logger.info("Add Chips info to manifest...")
		if ChipSet.reference_chipset is not None :
			for chip in ChipSet.reference_chipset :
				self.manifest.add_chip(chip)
		else:
			for g in self.groups.values():
				for c in g.chips:
					self.manifest.add_chip(c)
		logger.info("\tDone.")

	def final_merge(self):
		i = 1
		for name, svd in self.svd_file_handler_mapping.items() :
			logger.info(f"Final merge {i:2d}/{len(self.svd_file_handler_mapping)} of SVD {svd.file_name} ")
			for name, data in svd.groups.items() :
				if name not in self.groups :
					self.groups[name] = data
				else:
					self.groups[name].inter_svd_merge(data)
			i += 1

	def generate_parent_classes(self):
		for group_name in ["TIM"] :
			if group_name in self.groups :
				self.groups[group_name].create_parent_class()

	def finalize(self):
		for name, group in self.groups.items() :
			logger.info(f"Finalizing {name}")
			group.finalize()

	def checkpoint(self, name):
		self.checkpoint_status.pass_checkpoint(name)
		if name in self.params.checkpoint_request :
			self.checkpoint_status.perform_checkpoint(name,self)
		if len(self.params.checkpoint_request) > 0 :
			self.checkpoint_status.save()

	def generate_output(self):
		logger.info("Printing output files...")
		for name, group in self.groups.items():
			if not self.params.got_group_filter or name in self.params.group_filter:
				with open(f"{self.params.out_include}/{name}_struct.h", "w") as header:
					header.write(group.cpp_output())

				self.manifest.add_generated_group(name)

		with open(f"{self.params.main_out}/sool_chip_setup.h", "w") as header:
			header.write(generate_sool_chip_setup())

		with open(f"{self.params.out_sys}/IRQn.h", "w") as irq_table:
			irq_table.write(generate_sool_irqn())

		with open(f"{self.params.out_sys}/cmsis_config.h", "w") as cmsis_configuration:
			cmsis_configuration.write(generate_sool_cmsis_config())

		self.manifest.construct_xml()
		self.manifest.write_file()
		if self.params.copy_manifest :
			logger.info(f"Copy manifest file to {self.params.manifest_copy_path}")
			shutil.copyfile(self.params.generation_manifest_path,self.params.manifest_copy_path)

		if self.params.copy_headers:
			logger.info(f"Copy generated files to {self.params.manifest_copy_path}")
			for f in glob.glob(f"{self.params.out_include}/*.h"):
				shutil.copyfile(f,f"{self.params.headers_copy_path}/{os.path.basename(f)}")

	def generate_rccf(self):
		os.makedirs(self.params.out_rccf, exist_ok=True)
		if "RCC" not in self.groups:
			logger.error(f"Tried to generate RCCF while RCC isn't analyzed. Aborting.")
		else:
			for name, group in self.groups.items():
				if name == "RCC" or self.params.got_group_filter and name not in self.params.group_filter:
					continue
				for periph in group.toplevel_periphs:
					logger.info(f"RCCF generation for {periph.name}")
					with open(f"{self.params.out_rccf}/{periph.name}.h", "w") as rccf:
						records = generate_records(periph, self.groups['RCC'].peripherals[0])
						rccf.write(generate_get_reg(records, periph))
						rccf.write(generate_get_bit(records, periph))

	def generate_sql(self):
		logger.info("Generating SQL database...")
		if os.path.exists("out/database.sqlite3"):
			os.remove("out/database.sqlite3")
		db = sql.connect("out/database.sqlite3")
		with open("sql/create_db.sql", "r") as script:
			db.executescript(script.read())
		cursor = db.cursor()
		logger.info("\tDumping chipset...")
		ChipSet.reference_chipset.generate_sql(cursor)
		db.commit()
		for name, group in self.groups.items():
			if self.params.got_group_filter and name not in self.params.group_filter:
				continue
			logger.info(f"\tDumping {name}...")
			group.generate_sql(cursor)
			db.commit()
		logger.info("Done")

	def generate_optionals(self):
		if self.params.generate_rccf:
			self.generate_rccf()
		if self.params.dump_sql:
			self.generate_sql()

	def restore_analysis(self):
		try:
			logger.info("Trying to restore a previous database...")
			with open(self.params.pickle_data_path, "rb") as pickle_file:
				self.groups = pickle.load(pickle_file)
			self.skip_analysis = True
			logger.info("\tDone !")
		except Exception as e:
			self.groups = dict()
			self.skip_analysis = False
			logger.error(f"Error while trying to reuse a previous database : {e.__cause__}")

	def perform_analysis(self) :
		if not self.checkpoint_status["POST_PDSC"] :
			self.initialize_filestructure()
			self.update_fileset()
			self.process_pdsc()
			self.write_pdsc_infos_in_manifest()
			self.checkpoint("POST_PDSC")

		if not self.checkpoint_status["POST_SVD"] :
			self.extract_svd_from_pdsc()
			# Experimental
			self.harden_svd_using_cube_ide()
			# End - Experimental
			self.process_svd()
			self.checkpoint("POST_SVD")

		if not self.checkpoint_status["POST_MERGE"] :
			self.final_merge()
			self.checkpoint("POST_MERGE")

		if not self.checkpoint_status["POST_ANALYZE"] :
			self.generate_parent_classes()
			self.finalize()
			self.checkpoint("POST_ANALYZE")

	def run(self):
		# if self.params.reuse_db :
		# 	self.restore_analysis()
		# if not self.skip_analysis :
		# 	self.perform_analysis()
		self.perform_analysis()
		self.write_chips_infos_in_manifest()
		self.generate_output()
		self.generate_optionals()


