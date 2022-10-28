import torch
import monai
from monai.transforms import Decollated
from pytorch_lightning import LightningModule
from pytorch_lightning.utilities.distributed import rank_zero_only

from manafaln.core.metric import MetricCollection
from manafaln.core.builders import (
    ModelBuilder,
    LossBuilder,
    InfererBuilder,
    OptimizerBuilder,
    SchedulerBuilder
)
from manafaln.core.transforms import build_transforms

def configure_batch_decollate(settings, phase, keys):
    decollate = settings.get("decollate", False)
    decollate_phases = settings.get("decollate_phases", [])
    if decollate and phase in decollate_phases:
        return Decollated(keys=keys, allow_missing_keys=True)
    return None

class SupervisedLearning(LightningModule):
    def __init__(self, config: dict):
        super().__init__()

        # Save all hyperparameters
        self.save_hyperparameters({ "workflow": config })

        # Get configurations for all components
        components = self.hparams.workflow["components"]

        self.model   = self.build_model(components["model"])
        self.loss_fn = self.build_loss_fn(components["loss"])
        self.inferer = self.build_inferer(components["inferer"])

        # Configure batch decollate
        settings = config.get("settings", {})
        self.train_decollate = self.configure_batch_decollate(
            settings, "training"
        )
        self.valid_decollate = self.configure_batch_decollate(
            settings, "validation"
        )
        self.test_decollate = self.configure_batch_decollate(
            settings, "test"
        )

        self.post_transforms = {}
        for phase in ["training", "validation", "test"]:
            self.post_transforms[phase] = build_transforms(
                components["post_transforms"].get(phase, [])
            )

        self.train_metrics = MetricCollection(components["training_metrics"])
        self.valid_metrics = MetricCollection(components["validation_metrics"])

    def build_model(self, config):
        builder = ModelBuilder()
        return builder(config)

    def build_loss_fn(self, config):
        builder = LossBuilder()
        return builder(config)

    def build_inferer(self, config):
        builder = InfererBuilder()
        return builder(config)

    def configure_batch_decollate(self, config, phase):
        if phase == "training" or phase == "validation":
            keys = [
                "image", "image_meta_dict", "image_transforms",
                "label", "label_meta_dict", "label_transforms",
                "preds"
            ]
        elif phase == "test":
            keys = ["image", "image_meta_dict", "image_transforms", "preds"]
        else:
            raise RuntimeError("Cannot configure decollate for unknow phase.")

        if config.get("decollate", False):
            if phase in config.get("decollate_phases", []):
                return Decollated(keys=keys, allow_missing_keys=True)
        return None

    def forward(self, data):
        return self.inferer(data, self.model)

    def training_step(self, batch, batch_idx):
        image = batch["image"]
        label = batch["label"]

        # Apply model & compute loss
        batch["preds"] = self.model(image)
        loss = self.loss_fn(batch["preds"], batch["label"])

        if self.train_decollate is not None:
            # Decolloate batch before post transform
            for item in self.train_decollate(batch):
                # Apply post transform on single item
                item = self.post_transforms["training"](item)
                # Compute metric for single item
                self.train_metrics.apply(item)
        else:
            # Apply post transforms on the whole batch
            batch = self.post_transforms["training"](batch)
            # Add result of whole batch to metric
            self.train_metrics.apply(batch)

        # Log current loss value
        self.log_dict({ "train_loss": loss })

        return loss

    def training_epoch_end(self, outputs):
        m = self.train_metrics.aggregate()
        self.log_dict(m)
        self.train_metrics.reset()

    def validation_step(self, batch, batch_idx):
        image = batch["image"]
        label = batch["label"]

        # Run inference
        batch["preds"] = self.forward(image)

        # Post transform & compute metrics
        metrics = []
        if self.valid_decollate is not None:
            for item in self.valid_decollate(batch):
                # Apply post transforms first
                item = self.post_transforms["validation"](item)
                # Calculate iteration metrics
                m = self.valid_metrics.apply(item)
                # Save meta data and results
                # m["preds"] = item["preds"]
                m["image_meta_dict"] = item.get("image_meta_dict", {})
                m["label_meta_dict"] = item.get("label_meta_dict", {})
                metrics.append(m)
        else:
            batch = self.post_transforms["validation"](batch)
            m = self.valid_metrics.apply(batch)
            # m["preds"] = batch["preds"]
            m["image_meta_dict"] = batch.get("image_meta_dict")
            m["label_meta_dict"] = batch.get("label_meta_dict")
            metrics.append(m)

        # Output metrics and meta data of this batch
        return metrics

    def validation_epoch_end(self, validation_step_outputs):
        m = self.valid_metrics.aggregate()
        self.log_dict(m)
        self.valid_metrics.reset()

    def test_step(self, batch, batch_idx):
        # No label for test
        image = batch["image"]

        # Run inference
        batch["preds"] = self.forward(image)

        if self.test_decollate is not None:
            for item in self.test_decollate(batch):
                item = self.post_transforms["test"](item)
        else:
            batch = self.post_transforms["test"](batch)

        # Nothing to output for pure inference
        return None

    def get_optimize_parameters(self):
        return self.model.parameters()

    def configure_optimizers(self):
        # Extract optimizer & scheduler configurations
        workflow = self.hparams.workflow
        opt_config = workflow["components"]["optimizer"]
        sch_config = workflow["components"].get("scheduler", None)

        opt_builder = OptimizerBuilder()
        sch_builder = SchedulerBuilder()

        opt = {
            "optimizer": opt_builder(
                opt_config,
                params=self.get_optimize_parameters()
            )
        }

        if not sch_config is None:
            # Get or set default scheduler mode
            sch_opts = workflow["settings"].get("scheduler", None)
            if sch_opts is not None:
                interval = sch_opts.get("interval", "epoch")
                frequency = sch_opts.get("frequency", 1)
            else:
                interval = "epoch"
                frequency = 1

            opt["lr_scheduler"] = {
                "scheduler": sch_builder(sch_config, opt=opt["optimizer"]),
                "interval": interval,
                "frequency": frequency
            }

        return opt

