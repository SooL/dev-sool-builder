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
import re
from copy import copy
from fnmatch import fnmatch

from sool.structure import Field, RegisterVariant, ChipSet, Register


def TIM_reg_cleaner(register: "Register") :
	if register.name in ["TIM2_OR"] :
		register.name = "OR"

def GPIO_reg_var_cleaner(var : RegisterVariant):
	reg_name = var.parent.name
	var.force_remove_template()
	if var.parent.name in ["MODER", "ODR", "IDR", "OTYPER", "OSPEEDR", "PUPDR", "BSR", "BRR", "LCKR"] :
		first_field = sorted(var.fields)[0]
		field_size = first_field.size
		prefix = ""
		if first_field.position > 9*field_size :
			prefix = first_field.name[:-2] # remove digit. Assumes at least one pin below 10 is defined
		else :
			prefix = first_field.name[:-1]

		for i in range(0, 16) :
			field_name = prefix+str(i)
			if field_name not in var :
				var.add_field(Field(chips=var.chips, name=field_name, brief=None,
				                    position=i*field_size, size=field_size))
	elif var.parent.name == "BSRR" :
		field_size = sorted(var.fields)[0].size
		for i in range(0, 16) :
			field_name = "BS"+str(i)
			if field_name not in var :
				var.add_field(Field(chips=var.chips, name=field_name, brief=None,
				                    position=i*field_size, size=field_size))
			field_name = "BR"+str(i)
			if field_name not in var :
				var.add_field(Field(chips=var.chips, name=field_name, brief=None,
				                    position=16 + i*field_size, size=field_size))
	elif var.parent.name in ["AFRH", "AFRL"] :

		field_size = sorted(var.fields)[0].size
		start = 8 if var.parent.name == "AFRH" else 0
		for i in range(start, start+8) :
			field_name = "AFSEL"+str(i)
			if field_name not in var :
				var.add_field(Field(chips=var.chips, name=field_name, brief=None,
				                    position= start*4 + i*field_size, size=field_size))

def RCC_PLL_cleaner(var: RegisterVariant) :
	for f in var :
		if re.match("PLL[A-Z]0", f.name) and f.name[:-1] not in var.parent :
			pos = f.position
			base_name = f.name[:-1]
			i = 1
			split = False
			while f"{base_name}{i}" in var :
				if var[f"{base_name}{i}"].position != pos + i :
					split = True
				var.remove_field(var[f"{base_name}{i}"])
				i += 1
			if split :
				raise AssertionError(f"{base_name} is split")
			else :
				var.remove_field(f)
				size = i
				var.parent.add_field(Field(f.chips, f"{base_name}", f.brief, pos, size))

def RTC_ALMRBSSR_cleaner(var : RegisterVariant) :
	if "BKP" in var : # wrong fields
		var.remove_field(var["BKP"])
		var.add_field(Field(var.chips, "SS", None, 0, 15))
		var.add_field(Field(var.chips, "MASKSS", None, 24, 4))

def RTC_TAFCR_cleaner(var : RegisterVariant) :
	if "MASKSS" in var : # wrong fields
		var.remove_field(var["MASKSS"])
		var.add_field(Field(var.chips, "ALARMOUTTYPE", None, 16, 1))
		var.add_field(Field(var.chips, "TAMPPUDIS   ", None, 15, 1))
		var.add_field(Field(var.chips, "TAMPPRCH    ", None, 13, 2))
		var.add_field(Field(var.chips, "TAMPFLT     ", None, 11, 2))
		var.add_field(Field(var.chips, "TAMPFREQ    ", None, 8, 3))
		var.add_field(Field(var.chips, "TAMPTS      ", None, 7, 1))
		var.add_field(Field(var.chips, "TAMP3TRG    ", None, 6, 1))
		var.add_field(Field(var.chips, "TAMP3E      ", None, 5, 1))
		var.add_field(Field(var.chips, "TAMP2TRG    ", None, 4, 1))
		var.add_field(Field(var.chips, "TAMP2E      ", None, 3, 1))
		var.add_field(Field(var.chips, "TAMPIE      ", None, 2, 1))
		var.add_field(Field(var.chips, "TAMP1TRG    ", None, 1, 1))
		var.add_field(Field(var.chips, "TAMP1E      ", None, 0, 1))

def RTC_CFGR_cleaner(reg : Register) :
	OR_chips = ChipSet()
	CFGR_chips = copy(reg.chips.chips)
	for chip in CFGR_chips :
		header_periph = chip.header_handler.periph_table["RTC"]
		if "CFGR" not in header_periph :
			if "OR" in header_periph :
				OR_chips.add(chip)
			reg.chips.remove(chip)
	if reg.chips.empty :
		if not OR_chips.empty :
			reg.name = "OR"
			reg.description = "Option register"
		else :
			reg.parent.remove_register(reg)
	elif not OR_chips.empty :
		raise AssertionError("RTC.CFGR and RTC.OR cohabiting")
