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

from lxml import etree as ET
from multiprocessing import Pool
import typing as T
import logging

from .pack import KeilPack
from sool.tools import global_parameters
logger = logging.getLogger()

class KeilPackManager:
	def __init__(self):
		self.handlers : T.Dict[str,KeilPack]= {family : KeilPack(family) for family in global_parameters.defined_keil_archive.keys()}
		self.selected_handlers = {family : True for family in global_parameters.defined_keil_archive.keys()}
		#self.updated_handles = {family: False for family in global_parameters.defined_keil_archive.keys()}

		self.repo_path = global_parameters.packs_path
		self._keil_webpage_content : str = None

		self.njobs = global_parameters.jobs

	@property
	def keil_webpage_content(self):
		if self._keil_webpage_content is None :
			self._keil_webpage_content = KeilPack.fetch_keil_page_content()
		return self._keil_webpage_content

	def set_family_selection(self,family : str,select : bool):
		self.selected_handlers[family] = select

	def select_family(self, family):
		self.set_family_selection(family,True)

	def unselect_family(self, family):
		self.set_family_selection(family,False)

	def resfresh_versions(self, force = False):
		"""
		Fetch all selected versions
		:return:
		"""
		pack_to_handle = list()
		for handler in [self.handlers[family] for family in self.selected_handlers if self.selected_handlers[family]] :
			if force or not handler.have_retrieved_version :
				handler.scraped_base_page = self.keil_webpage_content
				pack_to_handle.append((handler,))

		if self.njobs == 1 :
			for handler in pack_to_handle :
				self._pack_version_refresh(handler[0])
		else :
			with Pool(self.njobs) as pool:
				logger.info(f"Dispatching refreshing task to {self.njobs} jobs.")
				runners = pool.starmap(self._pack_version_refresh,
							 [(self.handlers[family],) for family in self.selected_handlers if
							  self.selected_handlers[family] and (force or not self.handlers[family].have_retrieved_version) ] )
				pool.close()
				pool.join()

				for family, versions in runners :
					self.handlers[family].valid_versions = versions
				logger.info("\tDone")

	@staticmethod
	def _pack_version_refresh(handler: KeilPack):
		logger.info(f"Scrape for {handler.family}")
		handler.scrape_online_versions()
		return (handler.family,handler.valid_versions)

	def to_xml(self) -> ET.Element:
		"""
		Save the state of the pack manager as a XML element that can be embedded into a manifest.
		:return:
		"""
		root = ET.Element("ressource-pack-manager",{"source":"keil", "path":self.repo_path})
		for family, handler in self.handlers.items() :
			xml_fam = ET.SubElement(root,"family",{"name":family, "selected":self.selected_handlers[family],"version":handler.version})
			for version in handler.valid_versions:
				ET.SubElement(xml_fam,"version",{"value":version})

		return root

	def __iter__(self):
		return [self.handlers[pname] for pname in self.handlers if self.selected_handlers[pname]].__iter__()
