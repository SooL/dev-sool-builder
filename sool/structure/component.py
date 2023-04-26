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
from math import ceil

from ..cleaners.corrector import Corrector

from .chipset import ChipSet
from .utils import TabManager
from .utils import DefinesHandler

logger = logging.getLogger()

class FixConvergenceError(Exception):
	pass

class Component:
################################################################################
#                                   BUILDERS                                   #
################################################################################

	def __init__(self,
	             chips: T.Union[None, ChipSet] = None,
	             name: T.Union[None, str] = None,
	             brief: T.Union[None, str] = None,
				 parent: "Component" = None
	             ):
		self.name = name
		if brief is not None and brief != name :
			self.brief = ' '.join(brief.split())
		else :
			self.brief = None
		
		self.chips = ChipSet(chips)
		self.parent = parent
		self.children: T.List["Component"] = None

	def __eq__(self, other):
		return self.name == other.name
	
	def __iter__(self) -> T.Iterable["Component"]:
		if self.children is None :
			return self # no iteration
		else :
			return iter(self.children)
		
	def __next__(self) :
		raise StopIteration

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self, new : str):
		if self._name is None or new != self._name :
			if new is not None :
				if not new.isidentifier() and not new.isalnum():
					logger.error(f"Setting non-alphanum component name {new}")
			self._name = new
			self.edited = True
	
	@property
	def edited(self):
		return self._edited
	
	def invalidate(self):
		"""
		Set self as edited, and all parents as edited de facto.
		"""
		if not self._edited :
			self._edited = True
			if self.parent is not None :
				self.parent.invalidate()

	def invalidate_recursive(self) :
		"""
		Invalidate self as edited and all children, recursively.
		De facto invalidate parents.
		"""
		self.invalidate()
		for child in self :
			child.invalidate_recursive()

	def validate(self):
		"""
		Validate self and all children, recursively.
		"""
		if self._edited :
			self._edited = False
			for child in self :
				child.validate()

#vvvvv TODO vvvvv
#	def validate_edit(self):
#		if self.edited :
#			self.edited = False
#		if hasattr(self,'__iter__') :
#			# noinspection PyTypeChecker
#			for child in self :
#				child.validate_edit()
#
#	def attach_hierarchy(self):
#		if hasattr(self,'__iter__') :
#			# noinspection PyTypeChecker
#			for child in self :
#				child.set_parent(self)
#				child.attach_hierarchy()
#
#	def finalize(self):
#		if hasattr(self,'__iter__') :
#			# noinspection PyTypeChecker
#			for child in self :
#				child.set_parent(self)
#				child.finalize()
#				self.chips.add(child.chips)
#		self.chips.update_families()
# ^^^^^^^^^^

	@property
	def computed_chips(self):
		out = ChipSet(self.chips)
		for child in self :
			out.add(child.computed_chips)
		return out

	@property
	def size(self) -> int :
		"""
		:return: Size of the component, in bits
		"""
		return 0

	@property
	def byte_size(self) -> int :
		return ceil(self.size/8)

	def exists_for(self, chip_pattern: str) -> bool :
		return self.chips.match(chip_pattern)

	def set_parent(self, parent: "Component"):
		if self.parent is not parent :
			self.invalidate()
			self.parent = parent
			self.parent.add_child(self)
	
	def add_child(self, child: "Component"):
		self.invalidate()
		self.children.append(child)
		child.set_parent(self)
		self.add_chips(child.chips)
	
	def add_chips(self, chips: T.Optional[ChipSet]):
		if chips not in self.chips:
			self.invalidate()
			self.chips.add(chips)
			self.parent.add_chips(chips)

	def absorb(self, other: "Component"):
		"""
		Merge other in self.
		Keep self brief if not None, otherwise use other brief.
		Merge ChipSets.
		"""
		if self.brief is None and other.brief is not None :
			self.brief = other.brief
		
		for other_child in other :
			for self_child in self :
				if other_child == self_child :
					self_child.absorb(other_child)
					break
			else :
				self.add_child(other_child)
				

################################################################################
#                            STRING REPRESENTATIONS                            #
################################################################################

	def __str__(self) -> T.Union[None, str]:
		return self.name if self.name is not None else f"{self.parent!s}.???"

	def __repr__(self):
		return f"<{type(self).__name__} {self!s}>"

	@property
	def alias(self) -> T.Union[None, str] :
		"""
		Returns the hierarchy up to this point.
		Used as the defined pre-processor constant when needed.
		:return: the full name of the Component. Usually "<parent_alias>_<name>"
		"""
		if self.parent is None : return self.name
		else :
			parent_alias: T.Union[str, None] = self.parent.alias
			if parent_alias is None : return self.name
			elif self.name is None  : return parent_alias
			else                    : return f"{parent_alias}_{self.name}"

################################################################################
#                          DEFINE, UNDEFINE & DECLARE                          #
################################################################################

	@property
	def needs_define(self) -> bool :
		"""
		Checks whether or not the Component needs to have its alias defined.
		:return: True if the Component needs to have its alias defined
		"""
		return (self.name is not None) and\
		       (self.parent is not None) and\
		       (self.chips != self.parent.chips)

	@property
	def undefine(self) -> bool:
		"""
		Require '#undefine' directive at the end of generated header file
		"""
		return True

	@property
	def defined_value(self) -> T.Optional[str]:
		"""
		Value to assign in the '#define' statement,
		or None if no '#define' is required
		"""
		return None

	@property
	def define_not(self) -> T.Optional[str] :
		"""
		Value to assign in '#define' statement when the conditions are not met,
		or None id no '#define' is required in that case
		"""
		if self.defined_value is None :
			return None
		else :
			return ""

	@property
	def defined_name(self) -> str :
		return self.alias

	def define(self, defines: T.Dict[ChipSet, DefinesHandler]) :
		if self.needs_define :
			if self.chips not in defines :
				defines[self.chips] = DefinesHandler()
			defines[self.chips].add(
				alias = self.defined_name,
				defined_value = self.defined_value,
				define_not = self.define_not,
				undefine = self.undefine)

		for child in self :
			child.define(defines)

	def declare(self, indent: TabManager = TabManager()) -> T.Optional[str] :
		return None

################################################################################
#                                     FIX                                      #
################################################################################

	def apply_fixes(self, parent_corrector: Corrector) :
		"""
		Extract appropriate correctors from the parent corrector,
		and apply them to the component.
		If the component is invalidated by one of the correctors,
		Re-apply all correctors.
		The correctors are recursively applied to children components.
		"""
		for _ in range(0, 100) :
			self.validate()
			correctors = parent_corrector[self]
			if (correctors is not None and len(correctors) > 0) :
				for corrector in correctors :
					corrector(self)
					for child in self :
						child.apply_fixes(corrector)
			if not self.edited :
				break
		else :
			raise FixConvergenceError(f"Component {self} not valid "
									   "after 100 fix iterations")



#vvvvv TODO vvvvv
#	def before_svd_compile(self, parent_corrector) :
#		"""
#		Applies corrections, prepare templates
#		"""
#
#		correctors = None if (parent_corrector is None) else parent_corrector[self]
#
#		if (correctors is not None) and (len(correctors) > 0) :
#			for corrector in correctors :
#				for child in self :
#					child.before_svd_compile(corrector)
#				corrector(self)
#		else :
#			for child in self :
#				child.before_svd_compile(None)
#
#
#	def svd_compile(self) :
#		"""
#		Merges identical child components
#		"""
#		for child in self :
#			child.svd_compile()
#
#	def after_svd_compile(self, parent_corrector) :
#		"""
#		Cleans the component and its children, checks for potential errors, applies advanced corrections
#		:return:
#		"""
#
#		correctors = None if (parent_corrector is None) else parent_corrector[self]
#
#		if (correctors is not None) and (len(correctors) > 0) :
#			for corrector in correctors :
#				for child in self :
#					child.after_svd_compile(corrector)
#				corrector(self)
#		else :
#			for child in self :
#				child.after_svd_compile(None)
#^^^^^^^^^^