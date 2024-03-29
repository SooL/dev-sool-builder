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

from . import Component, ChipSet, Register
from .utils import get_node_text, fill_periph_hole, TabManager
import typing as T
import xml.etree.ElementTree as ET


class MappingElement(Component) :
	"""
	Bind an address (register offset) to a register or a sub-peripheral within its peripheral.
	Also allows to specify an array of register or sub-peripheral.
	"""
	@staticmethod
	def create_from_xml(chips: ChipSet, register: Register,
	                    xml_data: ET.Element) -> "MappingElement" :
		name = get_node_text(xml_data, "name").strip(None)
		offset = int(get_node_text(xml_data, "addressOffset"), 0)
		return MappingElement(chips=chips, name=name, component=register,
		                      address=offset)

	# noinspection PyUnresolvedReferences
	def __init__(self, chips: ChipSet, name: T.Union[str, None],
	             component: T.Union[Register, "Peripheral"],
				 address: int,
				 array_size: int = 0, array_space: int = 0) :

		from . import Peripheral
		if not(isinstance(component, Register) or isinstance(component, Peripheral)) :
			raise TypeError(f"Cannot create placement of {component} : not a register or peripheral")

		super().__init__(chips=chips, name=name, brief=component.brief)

		self.component : T.Union[Register, Peripheral] = component
		self.address: int  = address
		self.array_size : int = array_size
		self.array_space : int = array_space

################################################################################
#                                  OPERATORS                                   #
################################################################################

	def __eq__(self, other) -> bool:
		if isinstance(other, MappingElement) :
			return self.address == other.address and \
				   self.name == other.name and \
				   self.array_size == other.array_size and\
			       self.array_space == other.array_space and \
			       self.component.size == other.component.size and \
				   self.component.name == other.component.name
		else :
			return False

	def __cmp__(self, other : "MappingElement") -> int:
		if isinstance(other, MappingElement) :
			return self.address - other.address
		else :
			raise TypeError()
		
	def __lt__(self, other : "MappingElement") -> bool:
		if isinstance(other, MappingElement) :
			if self.address != other.address :
				return self.address < other.address
			else :
				return self.name < other.name
		else :
			raise TypeError()

	def __gt__(self, other : "MappingElement") -> bool:
		if isinstance(other, MappingElement) :
			if self.address != other.address :
				return self.address > other.address
			else :
				return self.name > other.name
		else :
			raise TypeError()

	@property
	def size(self) -> int :
		if self.array_size == 0:
			return self.component.size
		else :
			return ((self.component.size + self.array_space) * self.array_size) - self.array_space

	@property
	def register(self) -> Register :
		raise AttributeError("register property doesn't exist")

################################################################################
#                               PLACE MANAGEMENT                               #
################################################################################

	def overlap(self, other: "MappingElement"):
		if other.address < self.address :
			size = other.byte_size
			return other.address + size > self.address
		else : # self.address <= other.address
			size = self.byte_size
			return self.address + size > other.address

################################################################################
#                          DEFINE, UNDEFINE & DECLARE                          #
################################################################################
	@property
	def defined_value(self) -> T.Union[str, None]:
		template : str = "{0.name}"
		if isinstance(self.component, Register) :
			if self.component.has_template :
				template = "typename tmpl::" + template
			template += "_t"
		template += " {1.name}"
		if self.array_size > 0 :
			if self.array_space > 0 :
				"" # TODO array of registers with space between them
			template += "[{1.array_size}]"
		return template.format(self.component, self)

	@property
	def define_not(self) -> str:
		return fill_periph_hole(self.byte_size, sep=";")

	def declare(self, indent: TabManager = TabManager()) -> T.Union[None, str] :
		out: str
		if self.needs_define :
			out = f"{indent}{self.defined_name};"
		else :
			out = f"{indent}{self.defined_value};"
		if self.brief is not None :
			out += f" /// {self.brief}"
		elif self.component.brief is not None :
			out += f" /// {self.component.brief}"
		return out + "\n"
