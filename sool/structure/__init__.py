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

# Reminder : import variables and such before importing a module which may import it from here
from .chipset import ChipSet, Chip
from .component import Component
from .field import Field
from .registervariant import RegisterVariant
from .register import Register
from .mappingelement import MappingElement
from .peripheralinstance import PeripheralInstance
from .peripheralmapping import PeripheralMapping
from .peripheraltemplate import PeripheralTemplate

from .peripheral import Peripheral

from .group import Group

