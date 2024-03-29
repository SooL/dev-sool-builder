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

import re
import typing as T
import xml.etree.ElementTree as ET
import logging
#from structure import Group
from sool.cmsis_analysis.header import CMSISPeripheral, CMSISHeader
from . import Component, Register
from . import MappingElement, PeripheralInstance, PeripheralMapping, PeripheralTemplate
from . import ChipSet
from .utils import get_node_text, TabManager

from .utils import DefinesHandler

from sool.tools import global_parameters
import sqlite3 as sql

logger = logging.getLogger()

class Peripheral(Component) :

	@classmethod
	def create_from_xml(cls, chips: ChipSet, xml_data: ET.Element) -> "Peripheral" :

		brief: str = get_node_text(xml_data, "description")\
			.lower()\
			.replace("-", " ")
		brief = " ".join(brief.split())

		ret =  cls(chips=chips, name=None, brief=brief)

		for xml_reg in xml_data.findall("registers/register") :
			new_register = Register.create_from_xml(chips, xml_reg)
			ret.add_register(new_register)

			reg_placement = MappingElement.create_from_xml(chips=chips, register=new_register, xml_data= xml_reg)
			ret.add_placement(reg_placement)

		return ret

	def __init__(self, chips: T.Union[ChipSet, None] = None,
	             name: T.Union[str, None] = None,
	             brief: T.Union[str, None] = None) :
		super().__init__(chips=chips, name=name, brief=brief)

		self.mappings: T.List[PeripheralMapping] = list()
		self.instances: T.List[PeripheralInstance] = list()
		self.max_size = 0
		self.inheritFrom : Peripheral = None

################################################################################
#                                  OPERATORS                                   #
################################################################################

	def __lt__(self, other):
		if self.inheritFrom is None and other.inheritFrom is not None :
			return True
		elif self.inheritFrom is not None and other.inheritFrom is None :
			return False
		else :
			return self.name < other.name

	def __eq__(self, other):
		if isinstance(other, Peripheral) :
			return (super().__eq__(other) and
					self.mapping_equivalent_to(other))

		elif isinstance(other, str) :
			return other == self.name
		else :
			raise TypeError()

	def __contains__(self, item) -> bool:
		if isinstance(item, PeripheralMapping) :
			return item in self.mappings
		elif isinstance(item, PeripheralInstance) :
			return item in self.instances
		else :
			return super().__contains__(item)

	def __getitem__(self, item) -> T.Union["Peripheral", Register]:
		if isinstance(item, PeripheralMapping) :
			return self.mappings[item]
		elif isinstance(item, PeripheralInstance) :
			return self.instances[item]
		else :
			return super().__getitem__(item)


	@property
	def alias(self) -> T.Union[None, str]:
		return self.name
	
	@property
	def size(self):
		max_size: int = 0
		for m in self.mappings :
			s = m.size
			if s > max_size :
				max_size = s
		return max_size

	@property
	def inherits(self):
		return self.inheritFrom is not None
	
	@property
	def registers(self) -> T.List[Register]:
		return self.children

################################################################################
#                             REGISTERS MANAGEMENT                             #
################################################################################
	add_register = super().add_child
	
	def remove_register(self, reg: T.Union["Peripheral", Register]):
		if reg.name is not None and reg.name in self :
			reg = self[reg.name]
			idx = self.registers.index(reg)
			while idx >= 0 and self.registers[idx].name != reg.name :
				idx = self.registers.index(reg, idx+1)
			if idx >= 0:
				self.registers.pop(idx)
			else :
				raise KeyError(f"{reg} is not in {self}")
			for m in self.mappings :
				m.remove_elements_for(reg)
		self.edited = True

################################################################################
#                             INSTANCES MANAGEMENT                             #
################################################################################

	def add_instance(self, other: T.Union[T.List["PeripheralInstance"], "Peripheral","PeripheralInstance"]) :
		if isinstance(other, Peripheral) :
			for inst in other.instances :
				self.add_instance(inst)
		elif isinstance(other,list) :
			for inst in other :
				self.add_instance(inst)
		elif isinstance(other, PeripheralInstance) :
			self.chips.add(other.chips)

			for i in self.instances :
				if i == other :
					i.inter_svd_merge(other)
					return
			other.set_parent(self)
			self.instances.append(other)
			self.edited = True
		else:
			raise TypeError(f"Expected a peripheral, an instance or a list of those. Got {type(other)}.")

################################################################################
#                              MAPPING MANAGEMENT                              #
################################################################################

	def mapping_equivalent_to(self,other : "Peripheral") -> bool :
		"""
		This function will check if the current peripheral has a mapping equivalent to the other one.
		:param other: The other peripheral
		:return:
		"""
		self_placements = list()
		other_placements = list()
		
		for m in self.mappings :
			self_placements.extend(m.elements)
		for m in other.mappings :
			other_placements.extend(m.elements)

		if len(self_placements) != len(other_placements) :
			return False
		
		for elt in self_placements :
			if elt not in other_placements :
				return False
		for elmt in other_placements :
			if elmt not in self_placements :
				return False
			
		return True
		
		# diff = list()
		# if ignore_templates :
		# 	for elmt in diff :
		# 		# if the register is only present in one of the two peripherals, merging is allowed only if the register in templated
		# 		if not elmt.component.has_template :
		# 			return False

		# 	for i in range(0, len(diff)-1) :
		# 		for j in range(i+1, len(diff)) :
		# 			# if the templated register's address is used by another templated register with the same name,
		# 			# the two peripherals can be merged together. Otherwise, merging is possible only if the address is not used
		# 			if diff[i].overlap(diff[j]) and diff[i].name != diff[j].name :
		# 				return False
		# 	return True
		# else :
		#	return len(diff) == 0

	def add_mapping(self, mapping: PeripheralMapping) :
		for elmt in mapping :
			self.add_placement(elmt)

	def place_component(self, component: T.Union["Peripheral", Register], address: int, name: str = None, chips = None):
		if chips is None :
			chips = component.chips
		if name is None :
			name = component.name

		self.add_placement(MappingElement(chips, name, component, address))

	def place_array(self, component: T.Union["Peripheral", Register], address: int, array_size: int,
	                array_space: int = 0, name: str = None, chips = None):
		if chips is None :
			chips = component.chips
		if name is None :
			name = component.name

		self.add_placement(MappingElement(chips, name, component, address, array_size, array_space))

	def add_placement(self, element: MappingElement) :
		mapping: T.Union[PeripheralMapping, None] = None

		element.component = self[element.component.name]
		for m in self.mappings :
			if element in m :
				m[element].inter_svd_merge(element)
				return
			elif m.has_room_for(element) :
				mapping = m
		if mapping is None :
			mapping = PeripheralMapping()
			mapping.parent = self
			self.mappings.append(mapping)
			self.edited = True
		mapping.add_element(element)

	def remove_placements_for(self, reg: T.Union["Peripheral", Register]):
		for m in self.mappings :
			m.remove_placements_for(reg)

################################################################################
#                             COMPILATION, MERGING                             #
################################################################################

	def svd_compile(self):
		super().svd_compile()

		m_idx = 0
		while m_idx < len(self.mappings) :
			m_offset = 1

			while m_idx + m_offset < len(self.mappings) :
				if self.mappings[m_idx].compatible(self.mappings[m_idx + m_offset]) :
					self.mappings[m_idx].intra_svd_merge(self.mappings[m_idx + m_offset])
					self.mappings.pop(m_idx + m_offset)
					self.edited = True
					continue
				else :
					m_offset += 1
			m_idx += 1

		r_idx = 0
		while r_idx < len(self.registers) :
			r_offset = 1
			while r_idx + r_offset < len(self.registers) :
				if self.registers[r_idx] == self.registers[r_idx + r_offset]:
					self.registers[r_idx].inter_svd_merge(self.registers[r_idx + r_offset])
					for mapping in self.mappings :
						for elmt in mapping :
							if elmt.component is self.registers[r_idx + r_offset] :
								elmt.component = self.registers[r_idx]
					self.registers.pop(r_idx + r_offset)
					self.edited = True
					continue
				else :
					r_offset += 1
			r_idx += 1

	def after_svd_compile(self, parent_corrector):
		super().after_svd_compile(parent_corrector)
		# remove unused registers
		i = 0
		while i < len(self.registers) :
			used = False
			for m in self.mappings :
				if m.has_elements_for(self.registers[i]) :
					used = True
					break
			if used :
				i+= 1
			else :
				self.registers.pop(i)

		self.after_svd_compile_cmsis_coherency_check()

	def after_svd_compile_cmsis_coherency_check(self):
		# Checking structure against registered headers to try to find discrepancies.
		# In case no CMSIS structure is found, we just assume that the SVD is right.
		headers: T.List[CMSISHeader] = list()
		for chip in self.chips.chips:
			if not chip.header_handler.is_structural:
				raise AssertionError(f"Header {chip.header_handler.path} doesn't contain structures")
			elif chip.header_handler not in headers and \
					self.name in chip.header_handler.periph_table:
				headers.append(chip.header_handler)
		if len(headers) > 0:
			for header in headers:
				cmsis_periph = header.periph_table[self.name]
				self.check_cmsis_header(cmsis_periph)
		else:
			logger.warning(f"No header has a definition for peripheral {self} given chips {self.chips}")

	def intra_svd_merge(self, other: "Peripheral") :
		super().intra_svd_merge(other)
		for r in other.registers : self.add_register(r)
		for i in other.instances : self.add_instance(i)
		for m in other.mappings  : self.add_mapping(m)

	def inter_svd_merge(self, other: "Peripheral") :
		super().inter_svd_merge(other)
		for r in other.registers : self.add_register(r)
		for i in other.instances : self.add_instance(i)
		for m in other.mappings  : self.add_mapping(m)

	def check_cmsis_header(self, cmsis_periph: CMSISPeripheral) :
		for cmsis_reg in cmsis_periph.registers :
			if re.match("^(RESERVED|reserved)[\d\w]?",  cmsis_reg.name) :
				continue

			match = False
			for m in self.mappings :
				if cmsis_reg.name in m :
					elmt = m[cmsis_reg.name]
					match = True
					if (cmsis_reg.array_size != 1) if (elmt.array_size == 0) else (cmsis_reg.array_size != elmt.array_size) :
						logger.warning(f"Array size mismatch for {elmt} and header "
						               f"{cmsis_periph.name}.{cmsis_reg.name}")
					elif re.match("^u?int\d+_t", cmsis_reg.type) :
						if not isinstance(elmt.component, Register) :
							logger.warning(f"Header register {cmsis_reg.name} doesn't match subperipheral {elmt}")
					else :
						if isinstance(elmt, Register) :
							logger.warning(f"Header sub-peripheral {cmsis_reg.name} doesn' match register {elmt}")

	def finalize(self):
		super().finalize()
		nb_reg = len(self.registers)
		r_i1 = 0
		while r_i1 < nb_reg :
			r_i2 = r_i1+1
			while r_i2 < nb_reg :
				if self.registers[r_i1] == self.registers[r_i2] :
					r1 = self.registers[r_i1]
					r2 = self.registers[r_i2]
					r1.inter_svd_merge(r2)
					self.registers.pop(r_i2)
					nb_reg -= 1
					nb_maps = len(self.mappings)
					m_i = 0
					while m_i < nb_maps :
						m = self.mappings[m_i]
						elmts = list(filter(lambda e : e.component is r2, m.elements))
						for elmt in elmts :
							elmt.component = r1
							m.remove_element(elmt)
							self.add_placement(elmt)
						if len(m.elements) == 0 :
							self.mappings.pop(m_i)
							nb_maps -= 1
						else :
							m_i += 1

				else :
					r_i2 += 1
			r_i1 += 1

		for i in self.instances :
			i.set_parent(self)
			i.finalize()

		if self.has_template :
			for inst in self.instances :
				if inst.has_template :
					template = None
					for tmpl in self.templates :
						if tmpl.compatible_with(inst) :
							template = tmpl
							break
					if template is None :
						template = PeripheralTemplate(f"{self.name}_tmpl_{len(self.templates)}", parent=self)
						self.templates.append(template)
					template.add_instance(inst)

			self.templates.append(PeripheralTemplate(f"{self.name}_tmpl_default", parent=self))

			for tmpl in self.templates :
				tmpl.finalize()

		map_idx: int = 0
		for m in self.mappings :
			m.set_parent(self)
			m.name = f"MAP{map_idx}"
			map_idx += 1
			m.finalize()

################################################################################
#                          DEFINE, UNDEFINE, DECLARE                           #
################################################################################

	def declare_templates(self, indent: TabManager = TabManager()) -> str :
		out = ""
		if self.has_template :
			for tmpl in self.templates :
				out += tmpl.declare(indent)
		return out

	def declare(self, indent: TabManager = TabManager()) -> str :
		out =""
		if self.needs_define :
			out += f"{indent}#ifdef {self.defined_name}\n"
		if self.has_template and not isinstance(self.parent, Peripheral):
			out += f"{indent}template<typename tmpl={self.templates[-1].name}>\n"
		inherit = f": public {self.inheritFrom.name}" if self.inherits else ""
		out += f"#define SOOL_{self.name}_AVAILABLE\n" \
			   f"{indent}class {self.name} {inherit}/// {self.brief}\n" \
		       f"{indent}{{\n"\
			   f"{indent}public:\n"
		indent.increment()
		out += f"{indent}//SOOL-{self.alias}-SUB-TYPES\n"
		for reg in self.registers :
			if not reg.has_template :
				out += reg.declare(indent)

		if len(self.mappings) > 1 :
			out += f"{indent}union\n" \
			       f"{indent}{{\n"
			indent.increment()
		for m in self.mappings :
			out += m.declare(indent)
		if len(self.mappings) > 1 :
			indent.decrement()
			out += f"{indent}}};\n"

		out += f"{indent}//SOOL-{self.alias}-DECLARATIONS\n"

		if self.inheritFrom is None:
			NO_PHY = not global_parameters.physical_mapping
			if NO_PHY :
				out += f"\n{indent}#if __SOOL_DEBUG_NOPHY\n"
				out += f"{indent + 1}{self.name}(uintptr_t addr) : myaddr(addr){{}};\n"
				out += f"{indent + 1}const uintptr_t myaddr;\n"
				out += f"{indent + 1}inline const uintptr_t get_addr() const volatile {{return myaddr;}};\n"
				out += f"{indent}#else\n"
			out += f"{indent + 1}inline const uintptr_t get_addr() const volatile {{return reinterpret_cast<uintptr_t>(this);}};\n"

			out += f"{indent}private:\n"
			out += f"{indent + 1}{self.name}() = delete;\n"
			if NO_PHY :
				out += f"{indent}#endif\n"


		indent.decrement()
		out += f"{indent}}};\n"

		if self.needs_define :
			out += f"{indent}#endif\n"
		if isinstance(self.parent, Peripheral) and self.needs_define :
			out = f"{indent}#ifdef {self.defined_name}\n{out}{indent}#endif\n"
		return out
		# Instances are declared after all classes of the group.
		# Instances declaration is handled in the 'cpp_output' method fo the class Group

	@property
	def defined_name(self) -> str :
		return f"PERIPH_{self.alias}"

	def define(self, defines: T.Dict[ChipSet, DefinesHandler]):
		super().define(defines)
		for mapping in self.mappings :
			mapping.define(defines)

		for tmpl in self.templates :
			tmpl.define(defines)

	def define_instances(self,defines: T.Dict[ChipSet, DefinesHandler]):
		for instance in self.instances :
			instance.define(defines)

	def declare_instances(self, tab_manager : TabManager) -> str:
		out = f"\n//Instances for peripheral {self.name}\n"
		virtual_instances: T.Dict[str, PeripheralInstance] = dict()
		for instance in self.instances:
			if instance.name in virtual_instances:
				virtual_instances[instance.name].chips.add(instance.chips)
			else:
				# The actual address is not relevant
				virtual_instances[instance.name] = PeripheralInstance(instance.chips, instance.name, instance.brief, 0)
				virtual_instances[instance.name].parent = self

		for i in sorted(virtual_instances.keys(), key= lambda x : ("1_" if not virtual_instances[x].needs_define else "2_") + virtual_instances[x].name):
			out += virtual_instances[i].declare(tab_manager)

		return out

	def generate_sql(self, cursor : sql.Cursor, group_id : int):

		gid = int(group_id)
		cursor.execute("INSERT INTO peripherals (name,grp_id) VALUES (:n,:g)", {"n":self.name,"g":gid})
		this_id = int(cursor.lastrowid)
		reg_map = dict()
		"""Maps a register name to its SQL ID"""
		placement_map = dict()
		done_map = dict()

		for instance in self.instances:
			instance.generate_sql(cursor, this_id)

		for mappings in self.mappings:
			for elt in mappings :
				if isinstance(elt.component,Register) :
					# We create the component (here register) if it hasn't been created before.
					# This is not related to fields declaration.
					if elt.component.name not in reg_map :
						reg_id = elt.component.generate_sql(cursor)
						reg_map[elt.component.name] = reg_id
					else :
						# If the register exists, we just get its ID.
						reg_id = reg_map[elt.component.name]
				elif isinstance(elt.component,Peripheral) :
					if elt.component.name not in reg_map:
						sub_periph_id = elt.component.generate_sql(cursor, gid)
						cursor.execute("INSERT INTO registers (name,size,sub_periph_id) VALUES (:n,:s,:pid)",
									   {"n":elt.name,"s":elt.size,"pid":sub_periph_id})
						reg_id = int(cursor.lastrowid)
						reg_map[elt.component.name] = reg_id
					else :
						reg_id = reg_map[elt.component.name]
				else :
					raise ValueError()

				# A register placement will be considered done if its id and addr are already done.
				key = (reg_id,elt.address,this_id)

				skip_regplacement = False
				if key in done_map :
					if done_map[key] == elt.name :
						skip_regplacement = True
				else :
					done_map[key] = elt.name

				if not skip_regplacement :
					try :
						cursor.execute("""INSERT INTO reg_placements(periph_id,register_id,name,array_size,pos) 
											VALUES (:pid,:rid,:n,:asize,:pos)""",
									   {"pid":this_id,"rid":reg_id,"n":elt.name,"asize":elt.array_size,"pos":elt.address})
						placement_map[elt.name] = cursor.lastrowid

					except sql.IntegrityError:
						logger.error(f"Register mapping unicity failure on peripheral {self.name} : double mapping of {elt.name} onto {done_map[key]}")

					reg_map[reg_id] = (elt.name,elt.array_size,elt.address)

				if isinstance(elt.component,Register) :
					elt.component.generate_fields_sql(cursor,placement_map[elt.name])

		return this_id


