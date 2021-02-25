import typing as T
import pickle
from glob import glob
import os

import logging
logger = logging.getLogger()

class Checkpoints:

	@staticmethod
	def load(root_path = ".data" ) -> "Checkpoints":
		path = f"{root_path}/SooL.chkpt.dat"
		if os.path.exists(path) :
			with open(path,"rb") as f :
				return pickle.load(f)
		else :
			return None

	def __init__(self):
		self.chkpt_levels : T.Dict[str,int] = dict()
		self.chkpt_passed: T.Dict[str, bool] = dict()
		self.chkpt_dumped: T.Dict[str,bool] = dict()

		"""Last passed checkpoint"""
		self.current_checkpoint : str = None

		self.root_path = ".data"

	def add_chkpt(self,name: str,level : int = None):
		"""
		Register a new checkpoint with a given name and an optional level.
		If no level is provided, add_chkpt will add a checkpoint after the last one.
		:param name: Name for the checkpoint
		:param level: Optional level for the checkpoint
		"""
		if name in self.chkpt_levels :
			raise KeyError("Checkpoint already defined")
		ckpt_level = 0 if len(self.chkpt_levels) == 0 else max(self.chkpt_levels.values()) +1
		if level is not None :
			ckpt_level = level
		if ckpt_level in self.chkpt_levels.values() :
			raise ValueError("Level already defined")
		self.chkpt_levels[name] = ckpt_level
		self.chkpt_passed[name] = False

	def __setitem__(self, key : str, value: bool):
		if not isinstance(value,bool) :
			raise ValueError
		self.chkpt_passed[key] = value

	def __getitem__(self, item : T.Union[str,int]):
		if isinstance(item, str) :
			return self.chkpt_passed[item]
		elif isinstance(item,int) :
			for c in self.chkpt_levels :
				if self.chkpt_levels[c] == item :
					return c
			raise KeyError
		raise TypeError

	def pass_checkpoint(self,chkpt : str ):
		self.current_checkpoint = chkpt
		self[chkpt] = True

	def get_last_dumped_checkpoint(self,ref : str = None) -> str:
		passed_checkpoints = [x for x in self.chkpt_dumped if self.chkpt_dumped[x]]
		ref_level = max(self.chkpt_levels.values()) if ref is None else self.chkpt_levels[ref]
		passed_chkpt_level = sorted([self.chkpt_levels[x] for x in passed_checkpoints if self.chkpt_levels[x] <= ref_level])
		return  self[max(passed_chkpt_level)]

	def level(self,chkpt : str):
		"""
		Get level for the given checkpoint name
		:param chkpt: Checkpoint to get the level for
		:return: the level
		"""
		return self.chkpt_levels[chkpt]

	def filepath(self,chkpt):
		if chkpt in self.chkpt_passed :
			return f"{self.root_path}/SooL.{chkpt}.dat"

	def perform_checkpoint(self,chkpt,obj : object):
		logger.info(f"Checkpointing step {chkpt} in {os.path.abspath(self.filepath(chkpt))}...")
		with open(self.filepath(chkpt), "wb") as dump_file:
			pickle.dump(obj, dump_file)
		self.chkpt_dumped[chkpt] = True

	def save(self, path : str = None):
		if path is None :
			path = f"{self.root_path}/SooL.chkpt.dat"
		with open(path, "wb") as dump_file:
			pickle.dump(self, dump_file)

	def restore(self, chkpt : str = None):
		logger.info(f"Attempting restoration from {chkpt}.")
		chkpt = self.get_last_dumped_checkpoint(chkpt)
		while not os.path.exists(self.filepath(chkpt)) and self.level(chkpt) > 0:

			self.chkpt_dumped[chkpt] = False
			chkpt = self[self.level(chkpt) - 1]
			logger.warning(f"Checkpoint not found, trying previous available : {chkpt}.")

		if not 	os.path.exists(self.filepath(chkpt)) :
			logger.error("No valid checkpoint found. Restarting from scratch !")
			return None

		else:
			with open(self.filepath(chkpt),"rb") as pkl_f :
				logger.info(f"Loading checkpoint {chkpt}...")
				return pickle.load(pkl_f)






