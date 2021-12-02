import os
from typing import Dict, List
from shutil import copytree

import torch
import monai
from monai.data.decathlon_datalist import load_decathlon_datalist
from pytorch_lightning import LightningDataModule

from manafaln.common.constants import ComponentType
from manafaln.utils.builders import (
    instantiate,
    build_transforms
)

class DecathlonDataModule(LightningDataModule):
    def __init__(self, config: Dict):
        super().__init__()

        # Data module do not load from checkpoints, but saving these
        # informations is useful for managing your experiments
        self.save_hyperparameters({"data": config})

        settings = config["settings"]

        # Must get configurations
        self.data_root       = settings["data_root"]
        self.data_list       = settings["data_list"]
        self.is_segmentation = settings["is_segmentation"]

        # Optional configurations
        # Use SHM if you have large size ram disk
        self.use_shm_cache = settings.get("use_shm_cache", False)
        self.shm_cache_path = settings.get("shm_cache_path", ".")

        if self.use_shm_cache:
            self.ori_data_root = self.data_root
            self.data_root = os.path.join(
                self.shm_cache_path,
                os.path.basename(self.data_root)
            )

    def prepare_data(self):
        if (self.use_shm_cache) and (not os.path.exists(self.data_root)):
            # Copy the whole directory to SHM
            copytree(self.ori_data_root, self.data_root)

    def build_dataset(self, config: dict):
        if isinstance(config["data_list_key"], str):
            files = load_decathlon_datalist(
                data_list_file_path=self.data_list,
                is_segmentation=self.is_segmentation,
                data_list_key=config["data_list_key"],
                base_dir=self.data_root
            )
        else:
            files = []
            for key in config["data_list_key"]:
                subset = load_decathlon_datalist(
                    data_list_file_path=self.data_list,
                    is_segmentation=self.is_segmentation,
                    data_list_key=key,
                    base_dir=self.data_root
                )
                files = files + subset

        transforms = build_transforms(config["transforms"])

        dataset = instantiate(
            name=config["dataset"]["name"],
            path=config["dataset"].get("path", None),
            component_type=ComponentType.DATASET,
            data=files,
            transform=transforms,
            **config["dataset"].get("args", {})
        )
        return dataset

    def build_loader(self, phase: str):
        phase_to_dataset = {
            "training": "train_dataset",
            "validation": "val_dataset",
            "test": "test_dataset"
        }

        if not phase in phase_to_dataset.keys():
            raise ValueError(f"{phase} split is not allowed for data module")

        config = self.hparams.data[phase]

        # Don't build dataset again if already exists
        if dataset := getattr(self, phase_to_dataset[phase], None) is None:
            dataset = self.build_dataset(config)
            setattr(self, phase_to_dataset[phase], dataset)

        loader = instantiate(
            name=config["dataloader"]["name"],
            path=config["dataloader"].get("path", None),
            component_type=ComponentType.DATALOADER,
            dataset=dataset,
            **config["dataloader"].get("args", {})
        )

        return loader

    def train_dataloader(self):
        return self.build_loader(phase="training")

    def val_dataloader(self):
        return self.build_loader(phase="validation")

    def test_dataloader(self):
        return self.build_loader(phase="test")

