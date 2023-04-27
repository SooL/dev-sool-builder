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

	def __init__(self,
	             chips: T.Optional[ChipSet] = None,
	             name: T.Optional[str] = None,
	             brief: T.Optional[str] = None,
	             ):
		self._parent = None 
		self._name = None
		self._edited = True

		self._lock = False
		
		# Use custom name setter for correct processing.
		self.name = name
		if brief is not None and brief != name :
			self.brief = ' '.join(brief.split())
		else :
			self.brief = None
		
		self.chips = ChipSet(chips)
		self.children: T.List["Component"] = None

	def __eq__(self, other):
		return self.name == other.name

################################################################################
#                                  ACCESSORS                                   #
################################################################################

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
			self.invalidate()
	

	@property
	def size(self) -> int :
		"""
		:return: Size of the component, in bits
		"""
		return 0

	@property
	def byte_size(self) -> int :
		return ceil(self.size/8)

################################################################################
#                                EDIT TRACKING                                 #
################################################################################

	@property
	def edited(self):
		return self._edited

	def invalidate(self):
		"""
		Set self as edited, and all parents as edited de facto.
		"""
		assert not self._lock, f"Tried to invalidate the component {self!r} while it's locked"
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

################################################################################
#                                  HIERARCHY                                   #
################################################################################

	def __iter__(self) -> T.Iterable["Component"]:
		if self.children is None :
			return self # no iteration
		else :
			return iter(self.children)
	
	def __next__(self) :
		raise StopIteration
	
	def __getitem__(self, item : T.Union[str,"Component"]) -> T.Union["Component", None]:
		if isinstance(item,str) :
			for child in self :
				if child.name == item :
					return child
		elif isinstance(item, Component):
			for child in self :
				if child is item or child == item :
					return child
		else :
			raise TypeError(f"Invalid key type {type(item).__name__}.")
		raise KeyError(f"Item {item!r} not found in {self!r}.")

	def __contains__(self, item: T.Union[str, "Component"]) -> bool:
		try :
			item = self[item]
			return True
		except KeyError :
			pass
		return False

	@property
	def parent(self):
		return self._parent
	
	@parent.setter
	def parent(self, parent: T.Optional["Component"]):
		self.set_parent(parent)
	
	def set_parent(self, parent: T.Optional["Component"]):
		if parent is not self._parent :
			if self._parent is not None :
				self._parent.children.remove(self)
				self._parent.invalidate()
			self._parent = parent
			# Use invalidate after setting parent to force invalidate the new parent.
			self.invalidate()
			if parent is not None :
				self.parent.add_child(self)
	
	def add_child(self, child: "Component"):
		if child not in self :
			self.invalidate()
			if self.children is None:
				self.children = list()
			self.children.append(child)
			self.add_chips(child.chips)
			child.set_parent(self)
		else :
			self[child].absorb(child)
	
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
		if other is self :
			return
		
		if self.brief is None and other.brief is not None :
			self.brief = other.brief
		
		self.add_chips(other.chips)
		
		for other_child in other :
			for self_child in self :
				if other_child == self_child :
					self_child.absorb(other_child)
					break
			else :
				self.add_child(other_child)
	
	def merge_children(self) :
		"""
		Merge identical children.
		Shall be called after using correctors.
		"""

		if self.edited :
			pos_ref = 0
			
			while pos_ref < len(self.children)-1 :	
				child_ref = self.children[pos_ref]
				pos_other = pos_ref + 1
				
				while pos_other < len(self.children) :
					child_other = self.children[pos_other]
					
					if child_other is child_ref :
						# Drop duplicates
						self.children.pop(pos_other)
					elif child_other == child_ref :
						# Merge equivalents
						child_ref.absorb(child_other)
						self.children.pop(pos_other)
					else :
						# Go to next comparison
						pos_other += 1

				pos_ref += 1 

################################################################################
#                            STRING REPRESENTATIONS                            #
################################################################################

	def __str__(self) -> T.Union[None, str]:
		return self.name if self.name is not None else f"{self.parent!s}.<???>"

	def __repr__(self):
		return f"<{type(self).__name__} {self!s}>"

	@property
	def alias(self) -> T.Union[None, str] :
		"""
		Returns the hierarchy up to this point.
		Used as the defined pre-processor constant when needed.
		:return: the full name of the Component. Usually "<parent alias>_<name>"
		"""
		if self.parent is None : return self.name
		else :
			parent_alias: T.Union[str, None] = self.parent.alias
			if parent_alias is None : return self.name
			elif self.name is None  : return parent_alias
			else                    : return f"{parent_alias}_{self.name}"

################################################################################
#                                CPP GENERATION                                #
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
		"""
		Name of the preprocessor constant to use for '#define' statements
		"""
		return self.alias

	def finalize(self) :
		"""
		Perform last steps before outputing the C++ code. 
		Component should not be changed afterward.
		"""
		self._lock = True
		for child in self.children :
			child.finalize()

	def define(self, defines: T.Dict[ChipSet, DefinesHandler]) :
		"""
		Insert the definition of the component in the list of all definitions
		of the output file. All definitions that share the same condition
		(i.e., same chip set) are grouped to be defined in one block.
		This method is recursively applied to all children of this component.
		"""
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
#                                    FIXES                                     #
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
			if self in parent_corrector :
				for corrector in parent_corrector[self] :
					corrector(self)
					for child in self :
						child.apply_fixes(parent_corrector=corrector)
			
			self.merge_children()
			
			if not self.edited :
				break
		else :
			raise FixConvergenceError(f"Component {self} not valid "
									   "after 100 fix iterations")