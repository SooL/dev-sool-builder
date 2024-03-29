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

import logging
import typing as T
from fnmatch import fnmatch

from .chip import Chip

logger = logging.getLogger()

class ChipSet :
	reference_chips_name_list : T.Set[str] = set()
	reference_chipset : "ChipSet" = None
	ref_lock = False
	#reference_families : Dict[str,Set[str]] = dict()

	def __init__(self, chips=None):
		if chips is None:
			chips = set()
		self.chips: T.Set[Chip] = set()
		self._families : T.Dict[str, T.Set[Chip]] = dict()
		self._families_up_to_date : bool = False
		self._hash = None
		self._description = None
		self.add(chips)
		if ChipSet.reference_chipset is None and not ChipSet.ref_lock :
			ChipSet.ref_lock = True
			ChipSet.reference_chipset = ChipSet()
		if ChipSet.reference_chipset is not None :
			ChipSet.reference_chipset.add(chips)

	def __eq__(self, other):
		if isinstance(other,ChipSet) :
			return len(self.chips.symmetric_difference(other.chips)) == 0
		else :
			raise TypeError()
		
	def __iter__(self):
		return iter(self.chips)
	
	def __len__(self) :
		return len(self.chips)

	def __contains__(self, other: T.Union[Chip, "ChipSet"]) :
		if isinstance(other, ChipSet) :
			return self.chips.issuperset(other.chips)
		elif isinstance(other, Chip) :
			return other in self.chips
		else :
			raise TypeError()

	__ge__ = __contains__

	def __hash__(self):
		if self._hash is None :
			self._hash = hash(tuple(sorted([x.name for x in self.chips])))
		return self._hash

	def invalidate(self):
		self._hash = None
		self._description = None
		self._families_up_to_date = False

	def __str__(self):
		if self._description is None : 
			self._description = "\t".join(sorted([str(x) for x in self.chips]))
		return self._description

	def __and__(self, other):
		if isinstance(other,ChipSet) :
			return ChipSet(self.chips & other.chips) # intersection of the two chipsets

	def __iadd__(self, other: T.Union[T.List[Chip], 'ChipSet', Chip]):
		self.add(other)
		return self

	def __add__(self, other: T.Union[T.List[Chip], 'ChipSet', Chip]) -> 'ChipSet':
		ret: ChipSet = ChipSet(self.chips)
		if not isinstance(other, Chip):
			raise TypeError
		ret.add(other)
		return ret

	def __isub__(self, other):
		self.remove(other)
		return self

	def __sub__(self, other):
		ret : ChipSet = ChipSet(self.chips)
		ret.remove(other)
		return ret

	@property
	def families(self) ->T.Dict[str, T.Set[Chip]]:
		if not self._families_up_to_date :
			self.update_families()
		return self._families

	@property
	def empty(self) -> bool:
		return len(self.chips) == 0

	@property
	def defines(self) -> T.List[str]:
		return [x.define for x in self.chips]


	def add(self, other: T.Union[T.List[Chip], T.Set[Chip], 'ChipSet', Chip]):
		if isinstance(other, ChipSet) :
			self.chips.update(other.chips)
		elif isinstance(other, list) :
			self.chips.update(other)
		elif isinstance(other,set) :
			self.chips.update(other)
		elif isinstance(other, Chip) :
			self.chips.add(other)
		else:
			raise TypeError(f"{type(other)} provided")
		
		self.invalidate()

	def remove(self, other: T.Union[T.List[Chip], T.Set[Chip], 'ChipSet', Chip]):
		if isinstance(other, ChipSet) :
			self.chips.difference_update(other.chips)
		elif isinstance(other, list) :
			self.chips.difference_update(other)
		elif isinstance(other,set) :
			self.chips.difference_update(other)
		elif isinstance(other, Chip) :
			self.chips.remove(other)
		else:
			raise TypeError(f"{type(other)} provided")
		
		self.invalidate()

	def update_families(self):
		self._families.clear()
		for chip in self.chips :
			family = Chip.get_family(str(chip)).upper()
			if family not in self._families :
				self._families[family] = set()
			self._families[family].add(chip)
		self._families_up_to_date = True

	def defined_list(self, chips_per_line = 5,reference_chipset = None, newline_prefix = "    "):
		if reference_chipset is None :
			reference_chipset = ChipSet.reference_chipset

		output: str = ""
		line_size: int = 0
		matched_family : T.Dict[str,bool] = dict()

		if self >= reference_chipset :
			return "1"

		for family, chips in reference_chipset.families.items():
			if len(chips - self.chips) == 0 :
				matched_family[family] = True

		# if matched_family.keys() == reference_chipset.families.keys() :
		# 	return "1"

		for family in sorted(matched_family.keys()) :
			if line_size == chips_per_line:
				output += f"\\\n{newline_prefix}"
				line_size = 0
			output += f"defined({family:13s}) || "
			matched_family[family] = False
			line_size += 1
			
		for chip in sorted(self.chips, key=lambda x: x.name) :
			family = Chip.get_family(chip.name)
			if family not in matched_family or matched_family[family] :
				if line_size == chips_per_line :
					output += f"\\\n{newline_prefix}"
					line_size = 0
				if family not in matched_family :
					output += f"defined({chip.name:13s}) || "
				line_size += 1

		return output[:-4]

	def match(self, pattern):
		for chip in self.chips :
			if fnmatch(str(chip), str(pattern)) :
				return True
		return False

	def reverse(self,reference : T.Optional["ChipSet"]= None):
		if reference is None :
			reference = ChipSet.reference_chipset
		self.chips = (reference - self).chips
		self.invalidate()

	def reversed(self,reference : T.Optional["ChipSet"]= None) -> "ChipSet":
		if reference is None :
			reference = ChipSet.reference_chipset
		return reference - self

	def fill_from_name_list(self,name_list : T.List[str], ref : "ChipSet" = None):
		if ref is None :
			ref = ChipSet.reference_chipset
		for c in ref.chips :
			if c.name in name_list :
				self.add(c)
				name_list.remove(c.name)

