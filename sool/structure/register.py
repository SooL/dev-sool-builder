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

from enum import Enum
import re
import typing as T
import sqlite3 as sql
import xml.etree.ElementTree as ET

import logging
from copy import copy

from ..cleaners import Corrector

from . import Component, Field, ChipSet
from .utils import get_node_text, TabManager
from .utils import DefinesHandler, fill_periph_hole

logger = logging.getLogger()

################################################################################
################################### REGISTER ###################################
################################################################################
REGISTER_DEFAULT_SIZE: int = 32
REGISTER_DECLARATION: str = """\
{indent}struct {reg.name}_t: public {type} /// {reg.brief}
{indent}{{
{indent}\tusing {type}::operator=;
{content}\
{indent}\t//SOOL-{reg.alias}-DECLARATIONS
{indent}}};
"""

class AccessType(Enum) :
	READ_WRITE: int = 0,
	READ_ONLY: int = 1,
	WRITE_ONLY: int = 2,

	@staticmethod
	def from_string(str: str) :
		if str == "read-write" :
			return AccessType.READ_WRITE
		if str == "read-only" :
			return AccessType.READ_ONLY
		if str == "write-only" :
			return AccessType.WRITE_ONLY

		raise AssertionError(f"unknown access type {str}")

class Register(Component) :

	@staticmethod
	def merge_names(name1: str, name2: str) -> T.Union[str, None]:
		if len(name_1) > len(name_2) :
			tmp = name_1
			name_1 = name_2
			name_2 = tmp

		if name_2.startswith(name_1) :
			return name_1
		else :
			tokens_1 = re.split('([nxyz\d]+)', name_1)
			tokens_2 = re.split('([nxyz\d]+)', name_2)
			no_digit_1 = (''.join(map(lambda c : 'x' if re.match('([nxyz\d]+)', c) else c, tokens_1)))
			no_digit_2 = (''.join(map(lambda c : 'x' if re.match('([nxyz\d]+)', c) else c, tokens_2)))
			if no_digit_1 == no_digit_2 :
				if tokens_1[0] + ''.join(tokens_1[2:]) == tokens_2[0] + ''.join(tokens_2[2:]) :
					return tokens_1[0] + 'x' + ''.join(tokens_1[2:])
				elif tokens_2[0] + ''.join(tokens_2[2:]) == name_1 :
					return name_1
				elif ''.join(tokens_1[:-2]) + tokens_1[-1] == ''.join(tokens_2[:-2]) + tokens_2[-1] :
					return ''.join(tokens_1[:-2]) + 'x' + tokens_1[-1]
				elif ''.join(tokens_2[:-2]) + tokens_2[-1] == name_1 :
					return name_1
				else :
					return no_digit_1
			else :

				suffix = name_1
				prefix = name_1
				while len(suffix) > 0 and (suffix[0] == '_' or not name_2.endswith(suffix)) :
					suffix = suffix[1:]
				while len(prefix) > 0 and (prefix[-1] == '_' or not name_2.startswith(prefix)) :
					prefix = prefix[:-1]

				filler_length = (len(name_1) - len(prefix) - len(suffix)) if len(prefix) > 0 and len(suffix) > 0 else 0

				if (filler_length > 0 and abs(len(name_1) - len(name_2)) > 0) or \
						filler_length > 2 or \
						(len(prefix) + len(suffix)) < 2 :
					return None
				else :
					filler = "x"
					return prefix + filler + suffix

################################################################################
#                                 CONSTRUCTORS                                 #
################################################################################

	@classmethod
	def create_from_xml(cls, chips: ChipSet, xml_data: ET.Element) -> "Register":
		"""
		Create a register from an SVD XML node.
		:param chips: Chip or set of chips related to the SVD node.
		:param xml_data: SVD file node to handle. Should correspond to the path
						 `device/peripherals/peripheral/registers/register`
		"""
		name = get_node_text(xml_data, "name").strip(None)
		brief = get_node_text(xml_data, "description").strip(None)
		access = get_node_text(xml_data, "access").strip(None)

		# check if displayName is different from name
		disp_name = get_node_text(xml_data, "displayName").strip(None)
		if disp_name != name :
			logger.warning(f"Register name and display discrepancy :"
			               f" {name} displayed as {disp_name}")

		read_size_value = get_node_text(xml_data, "size")
		size = REGISTER_DEFAULT_SIZE if (read_size_value == str()) \
			else int(read_size_value, 0)

		
		# self.rst = int(get_node_text(xml_base,"resetValue"),0)  # Is a mask
		register = cls(chips=chips, name=name, brief=brief,
		                    size=size, access=AccessType.from_string(access))

		xml_fields = xml_data.findall("fields/field")
		if xml_fields is not None :
			for xml_field in xml_fields :
				field = Field.create_from_xml(chips, xml_field)
				register.add_field(field=field, in_xml_node=True)

		return register

	def __init__(self,
	             chips: T.Optional[ChipSet] = None,
	             name: T.Optional[str] = None,
	             brief: T.Optional[str] = None,
	             size: int = 32,
	             access: AccessType = AccessType.READ_WRITE) :
		super().__init__(chips=chips, name=name, brief=brief)
		self._size = size
		self.access = access
		self.type = None # Reg{size}_t by default

################################################################################
#                                  OPERATORS                                   #
################################################################################

	def __iter__(self) -> T.Iterable[Field]:
		"""
		Iterate over fields that belong to the register
		"""
		return iter(self.fields)

	def __eq__(self, other) :
		"""
		Perform an equality check
		:param other: Other element to compare 
		:return: True if other is also a register and the content (fields) 
		         of both register are equals (through __eq__).
			     False otherwise.
		"""
		if isinstance(other, Register) :
			for field in self :
				if field not in other :
					return False
			for field in other :
				if field not in self :
					return False
			return True
		else :
			return False

	def __copy__(self) :
		"""
		Generate a deep-ish copy of the register.
		It can then be used as standalone.
		:return: A register equivalent to the current one, but independant.
		"""
		
		result = Register(chips=self.chips, name=self.name, brief=self.brief, size=self.size, access=self.access)
		for field in self :
			result.add_field(copy(field))
		return result
	
	@property
	def size(self) -> int :
		return self._size

	@size.setter
	def size(self, new_size: int) :
		self._size = new_size
		self.invalidate()

	@property
	def fields(self) :
		return self.children
	
################################################################################
#                         FIELDS & VARIANTS MANAGEMENT                         #
################################################################################

	add_field = super().add_child

	def absorb(self, other: "Register") :
		super().absorb(other)
		if self.name != other.name :
			new_name = Register.merge_names(self.name, other.name)
			
			if new_name is None :
				logger.warning(f"\tCan't decide name when merging {self.name} with {other.name}. Keeping {self.name}.")
				new_name = self.name
			
			while self.name != new_name and other.name != new_name and new_name in self.parent : # name already taken
				#TODO comment this shit
				assert "n" not in new_name, "Replacement name already taken"
				
				if 'z' in new_name :
					new_name = new_name.replace('z', 'n')
				elif 'y' in new_name :
					new_name = new_name.replace('y', 'z')
				elif 'x' in new_name :
					new_name = new_name.replace('x', 'y')
				else :
					assert False, "Cannot automatically rename already taken register name"
			self.name = new_name
	
	def apply_fixes(self, parent_corrector: Corrector) :
		old_name = self.name
		super().apply_fixes(parent_corrector)
		# change the name of the mappings if they shared the name of the register
		if self.name != old_name :
			for m in self.parent.mappings :
				for elmt in m :
					if elmt.component is self and elmt.name == old_name :
						elmt.name = self.name

################################################################################
#                                CPP GENERATION                                #
################################################################################

	# def svd_compile(self) :
	# 	super().svd_compile()

	# 	var_index = 0
	# 	while var_index < len(self.variants)-1 :
	# 		var_offset = 1
	# 		while var_index + var_offset < len(self.variants) :
	# 			if self.variants[var_index] == self.variants[var_index + var_offset] :
	# 				for f in self.variants[var_index + var_offset] :
	# 					self.variants[var_index][f].intra_svd_merge(f)
	# 				self.variants.pop(var_index + var_offset)
	# 				self.edited = True
	# 			else :
	# 				var_offset += 1
	# 		var_index += 1

	# def finalize(self):
	# 	super().finalize()
	# 	#TODO create variants, take into account templates, etc
	
	@property
	def undefine(self) -> True:
		return False

	@property
	def defined_value(self) -> T.Union[str, None]:
		return None

	# def declare(self, indent: TabManager = TabManager(), instances: T.Optional[T.List["PeripheralInstance"]] = None)\
	# 		-> T.Union[None,str] :
	# 	out: str = ""
	# 	variants = None
	# 	if self.has_template :
	# 		variants = list()
	# 		if instances is not None and len(instances) > 0 :
	# 			for instance in instances :
	# 				for var in self.variants :
	# 					if var not in variants and var.for_instance(instance) :
	# 						variants.append(var)
	# 		else :
	# 			variants.extend(filter(lambda v : not v.for_template, self.variants))
	# 	else :
	# 		variants = self.variants

	# 	if len(variants) == 0 :
	# 		return ""

	# 	is_union = len(variants) > 1
	# 	if is_union :
	# 		indent.increment()
	# 		out += f"{indent}union\n{indent}{{\n"

	# 	indent.increment()
	# 	out += "".join(map(lambda v : v.declare(indent), variants))
	# 	indent.decrement()

	# 	if is_union :
	# 		out += f"{indent}}};\n"
	# 		indent.decrement()

	# 	out = REGISTER_DECLARATION.format(
	# 		indent=indent, reg=self,
	# 		type=self.type if self.type is not None else f"Reg{self.size}_t",
	# 		content=out)
	# 	if self.needs_define :
	# 		out = f"{indent}#ifdef {self.defined_name}\n{out}{indent}#endif\n"
	# 	return out
	