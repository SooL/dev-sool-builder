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
from functools import partial
from fnmatch import fnmatch

from . import *
from sool.structure import Component

def modify(obj, name=None, type=None, brief=None, size=None) :
	if name is not None :
		obj.name = name
	if type is not None :
		obj.type = type
	if brief is not None :
		obj.brief = brief
	if size is not None :
		obj.size = size

def remove_prefix(obj, times=1) :
	for i in range(times) :
		if "_" not in obj.name :
			return
		modify(obj,name=obj.name[obj.name.index('_')+1:])

def clone_field(field, name=None, pos=None, brief=None, size=None) :
	newField = Field(field.chips,
	                 field.name if name is None else name,
	                 field.brief if brief is None else brief,
	                 field.position if pos is None else pos,
	                 field.size if size is None else size)
	if newField not in field.parent.parent :
		field.parent.parent.add_field(newField)

def remove_periph_prefix(obj : Component) :
	from sool.structure import Peripheral
	periph = obj.parent
	instances = list()
	while not isinstance(periph, Peripheral) :
		periph = periph.parent
	instances = periph.instances
	if periph.name is None :
		periph = periph.parent # use group name instead

	if periph.name in ["DFSDM"] :
		return # shitty peripherals

	pattern = fr"^{periph.name}[A-Za-z\d]*_\w+$"
	if re.match(pattern, obj.name) :
		if len(instances) == 1 and periph.name == instances[0].name :
			# one-instance peripheral. if prefix is different from name, leave as is
			if not obj.name.startswith(periph.name+"_") :
				return
		obj_name = obj.name[obj.name.index("_", len(periph.name))+1:]
		if obj_name in obj.parent :
			logger.warning(periph.name +" contains registers " + obj_name + " and " + obj.name)
		elif obj_name.isidentifier() :
			obj.name = obj_name

def cmsis_remove_reg_prefix(reg : Component) :
	parent_name = reg.parent.name
	if reg.name.startswith(parent_name+"_") :
		reg.name = reg.name[len(parent_name)+1:]

def create_array(periph, component, name = None, keep_originals = False) :
	if isinstance(component, str) :
		component = periph[component]

	if name is None :
		name = component.name

	for m in periph.mappings :
		if name in m and m[name].array_size != 0 :
			return
	for m in periph.mappings :
		if component in m :
			m.create_array_for_component(component, name, keep_originals)

class Corrector:
	def __init__(self,
	             arg1: T.Union[T.Callable, T.Dict[str, T.Any]] = None,
	             arg2: T.Union[T.Callable, T.Dict[str, T.Any]] = None) :
		if isinstance(arg1, T.Callable) :
			self.function: T.Optional[T.Callable] = arg1
			self.child_correctors: T.Optional[T.Dict[T.Optional[str], Corrector]] = arg2
		elif isinstance(arg1, T.Dict) :
			self.function: T.Optional[T.Callable] = arg2
			self.child_correctors: T.Optional[T.Dict[T.Optional[str], Corrector]] = arg1
		else :
			raise TypeError("Unable to build Corrector with arguments " + repr(arg1) + " & " + repr(arg2))

		if self.child_correctors is not None :
			for key in self.child_correctors :
				corr = self.child_correctors[key]
				if isinstance(corr, T.Callable) :
					self.child_correctors[key] = Corrector(corr)
				elif isinstance(corr, T.Dict) :
					self.child_correctors[key] = Corrector(corr)
				elif isinstance(corr, T.Tuple) :
					if len(corr) != 2 :
						raise TypeError("Cannot create Corrector with a tuple if the tuple has not 2 elments : " + repr(corr))
					self.child_correctors[key] = Corrector(corr[0], corr[1])
				elif not isinstance(self.child_correctors[key], Corrector) :
					raise TypeError("Cannot create Corrector without Dict, function, Set or other corrector")

	def __getitem__(self, item):
		return tuple(self.sub_correctors(item))

	def sub_correctors(self, item):
		if self.child_correctors is None :
			return list()
		if isinstance(item, str) :
			res: T.List[Corrector] = list()
			for key in self.child_correctors :
				if fnmatch(item, key) :
					res.append(self.child_correctors[key])
			return res
		elif isinstance(item, Component) :
			return self.sub_correctors("" if item.name is None else item.name)
		else :
			raise TypeError()

	def __contains__(self, item) :
		if self.child_correctors is None :
			return False
		elif isinstance(item, str) :
			for key in self.child_correctors :
				if fnmatch(item, key) :
					return True
		elif isinstance(item, Component) :
			return item.name in self

	def __call__(self, component: "Component"):
		if self.function is None :
			return
		else :
			return self.function(component)



# /!\ Group name correctors are used before peripherals are added.
# So when a corrector is used to change the group name,
# the corrector cannot be used to change peripherals or registers

base_root_corrector = Corrector({

	"ADC"       : { "*" : ADC_periph_cleaner },
	"AES?"      : partial(modify, name="AES"),
	"BSEC"      : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
	"CAN"       : { "*" : CAN_periph_base_cleaner },
	"COMP?"     : partial(modify, name="COMP"),
	"CRC"       : {
		"*"         : (CRC_periph_cleaner, {
			"DR"        : { "*" : {"Data_register" : partial(modify, name="DR") }},
			"IDR"       : { "*" : {"Independent_data_register" : partial(modify, name="IDR") }},
			"POL"       : { "*" : {"Polynomialcoefficients" : partial(modify, name="POL") }},
		})
	},
	"CRYP"      : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
	"DAC"       : { "*" : DAC_periph_cleaner },
	"DBGMCU"    : { "*" : DBGMCU_periph_cleaner },
	"DCMI"      : {
		"*"         : (PERIPH_VERSION_REGISTERS_cleaner, {
			"RIS"       : partial(modify, name="RISR"),
			"MIS"       : partial(modify, name="MISR"),
			"CWSTRT"    : partial(modify, name="CWSTRTR"),
			"CWSIZE"    : partial(modify, name="CWSIZER"),
		})
	},
	"DMA"		: { "*" : DMA_periph_cleaner },
	"DMAMUX*"   : partial(modify, name="DMAMUX"),
	"DSIHOST"   : partial(modify, name="DSI"),
	"DSI" 		: {
		"*" : (DSI_periph_cleaner,{
			"DSIHSOT_*" : remove_prefix,
			"DSI_*" : remove_prefix})} ,
	"ETHERNET"  : { "*" : ETHERNET_periph_cleaner },
	"FDCAN"     : { "*" : FDCAN_periph_cleaner },
	"FLASH"     : {
		"*"         : (FLASH_periph_cleaner, {
			"PCROP*"    : { "*" : {
				"PCROP*_*"  : lambda field : modify(field, name=field.name[field.name.index('_')+1:]),
				"STRT"      : partial(modify, size=16),
			}},
			"WRP*"      : { "*" : {
				"WRP*_*"    : lambda field : modify(field, name=field.name[field.name.index('_')+1:]),
				"WRP?"      : lambda field : modify(field, name=field.name[:-1]),
				"STRT"      : FLASH_WRPxR_field_cleaner,
				"END"       : FLASH_WRPxR_field_cleaner,
			}}
		})
	},
	"GIC*"    : partial(modify, name="GIC"),
	"GPIO"      : {
		"*"        : (GPIO_periph_cleaner, {
			"OSPEEDER"  : partial(modify, name="OSPEEDR"),
			"*"         : {
			    "*"         : (GPIO_reg_var_cleaner, {
				    "*"         : GPIO_field_cleaner
			    })
			},
		})
	},
	"GTZC"		: partial(modify, name="TZC"),
	"HASH"     : {
		"*"         : {
			"HASH_HR*"  : lambda reg : modify(reg, name=reg.name[5:]),
			"HR*"       : { "*" : {
				"H*"        : partial(modify, name="H")
			}},
			"CSR*"      : { "*" : {
				"CS*"       : partial(modify, name="CS")
			}}
		},
	},
	"HRTIM"     : { "*" : HRTIM_periph_cleaner },
	"I2C"       : { "*" : I2C_periph_cleaner },
	"IPCC"      : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
	"LPUART"    : partial(modify, name="USART"),
	"LTDC"		: { "*" : LTCD_fix_periph_cleaner},
	"MDMA"      : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
	"RAMECC"    : { "*" : partial(modify, name="RAMECC") },
	"RCC"       : {
		"*"         : {
			"C*_*" : lambda reg : modify(reg,name=reg.name[reg.name.find("_")+1:]),
			"*ENR"      : { "*" : {
				"GPIOP?EN"  : lambda field : modify(field, name=f"GPIO{field.name[-3]}EN")
			}},
			"xA?B*EN*R*" : lambda reg : modify(reg, name=reg.name[1 :]),
			"MxA?B*EN*R*" : lambda reg : modify(reg, name=reg.name[2 :]),
			"PLLSYSCFGR" : partial(modify, name="PLLCFGR"),
			"CCIPR1"    : partial(modify, name="CCIPR"),
			"PLL*"   : { "*" : RCC_PLL_cleaner },
		}
	},
	"RTC"       : {
		"*"         : {
			"ALRMBSSR"  : { "*" : RTC_ALMRBSSR_cleaner },
			"TAFCR"     : { "*" : RTC_TAFCR_cleaner },
			"CFGR"      : RTC_CFGR_cleaner,
		}
	},
	"SDMMC" : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
	"SERIALCONTROLL" : partial(modify, name="SERIAL_CONTROL"),
	"SYSCFG"    : {
		"*"         : {
			"EXTICR?"   : { "*" : {
				"EXTI?*"    : lambda field : modify(field, brief=f"EXTI {field.name[4:]} configuration")
			}}
		}
	},
	"TIM?*"     : partial(modify, name="TIM"),
	"TIM"       : { "*" : TIM_periph_cleaner },
	"TZC"		: {"*" : TZC_periph_cleaner},
	"USART"     : {
		"*"         : (USART_periph_cleaner, {
			"0x00000000": partial(modify, name="CR1"),
			"CR2"       : { "*" : {
				"TAINV" : partial(modify, name="DATAINV")
			}}
		}),
	},
	"USB_*"     : partial(modify, name="USB"),
	"USB"       : { "*" : USB_periph_cleaner },
	"RNG1"     : partial(modify, name="RNG"),
	"SERIAL_CONTROL" : (SERIAL_CONTROL_group_cleaner, {
		"*"         : (SERIAL_CONTROL_periph_cleaner, {
			"SC?_*"     : lambda reg : modify(reg, name=reg.name[4:])
		}),
	}),

	"STGENR" : partial(modify, name="STGEN"),

	"*"	        : {
		"*"         : {
			"*_*"       : remove_periph_prefix,
			"*"         : {"*" : {"*_*" : remove_periph_prefix }}
	}},

	"WWDG"  : { "*" : PERIPH_VERSION_REGISTERS_cleaner },
})


advanced_root_corrector = Corrector({
	"CAN"       : { "*" : CAN_periph_advanced_cleaner},
	"GPIO"      : { "*" : GPIO_periph_advanced_cleaner},
	"HASH"      : {
		"*"         : {
			"HRx"       : lambda reg : create_array(reg.parent, component=reg, name="HR"),
			"CSRx"       : lambda reg : create_array(reg.parent, component=reg, name="CSR"),
		}
    },
	"RCC"       : {
		"*"         : {
			"*ENR"      : { "*" : {
				"IOP?EN"  : lambda field : clone_field(field, name=f"GPIO{field.name[-3]}EN")
			}},
			"xA?B*EN*R*"  : lambda reg : modify(reg, name=reg.name[1:]),
			"MxA?B*EN*R*" : lambda reg : modify(reg, name=reg.name[2:])
		}
	},
	"SYSCFG"    : { "*" : SYSCFG_periph_advanced_cleaner},
})

cmsis_root_corrector = Corrector({
	"*"	        : {
		"*_*"       : cmsis_remove_reg_prefix
	},
})
