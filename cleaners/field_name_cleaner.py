import typing as T
from fnmatch import fnmatch


def DEFAULT_field_cleaner(register : "Register", r_name = None) :
	pass


def GPIO_reg_cleaner(field : "Field", parent : "Register" = None):
	if parent.name in ["OSPEEDR"] :
		field.name = f"OSPEED{int(field.offset/field.width)}"
	if parent.name in ["MODER"] :
		field.name = f"MODE{int(field.offset/field.width)}"
	if parent.name in ["IDR"]:
		field.name = f"ID{int(field.offset / field.width)}"
	if parent.name in ["ODR"]:
		field.name = f"OD{int(field.offset / field.width)}"
	if parent.name in ["PUPDR"]:
		field.name = f"PUPD{int(field.offset / field.width)}"



# For a given group, provide a proper cleaner function. None is the default one.
field_association_table : T.Dict[T.Union[None,str],T.Callable] = {
	"PUPDR" : GPIO_reg_cleaner,
	"IDR"	: GPIO_reg_cleaner,
	"ODR"	: GPIO_reg_cleaner,
	"MODER"		: GPIO_reg_cleaner,
	"OSPEEDR"	: GPIO_reg_cleaner,
	None        : DEFAULT_field_cleaner
}