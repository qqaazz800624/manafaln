import os
import json
import traceback
from typing import List

import torch
from nvflare.apis.dxo import DXO, DataKind
from nvflare.apis.fl_constant import FLContextKey
from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.model_locator import ModelLocator
from nvflare.app_common.pt.pt_fed_utils import PTModelPersistenceFormatManager
from nvflare.app_common.app_constant import DefaultCheckpointFileName

class LightningModelLocator(ModelLocator):
    SERVER_MODEL_NAME = "server"
    SERVER_BEST_MODEL_NAME = "server_best"

    def __init__(
        self,
        model_dir="app_server",
        model_name=DefaultCheckpointFileName.GLOBAL_MODEL,
        best_model_name=DefaultCheckpointFileName.BEST_GLOBAL_MODEL
    ):
        super().__init__()

        self.model_dir = model_dir
        self.model_file_name = model_name
        self.best_model_file_name = best_model_name

    def get_model_names(self, fl_ctx: FLContext) -> List[str]:
        return [
            LightningModelLocator.SERVER_MODEL_NAME,
            LightningModelLocator.SERVER_BEST_MODEL_NAME
        ]

    def locate_model(self, model_name, fl_ctx: FLContext) -> DXO:
        dxo = None
        engine = fl_ctx.get_engine()
        app_root = fl_ctx.get_prop(FLContextKey.APP_ROOT)

        if model_name in self.get_model_names(fl_ctx):
            # Get run information
            run_number = fl_ctx.get_prop(FLContextKey.CURRENT_RUN)
            run_dir = engine.get_workspace().get_run_dir(run_number)
            model_path = os.path.join(run_dir, self.model_dir)

            # Generate model path
            if model_name == LightningModelLocator.SERVER_BEST_MODEL_NAME:
                model_load_path = os.path.join(
                    model_path, self.best_model_file_name
                )
            else:
                model_load_path = os.path.join(
                    model_path, self.model_file_name
                )

            # Load checkpoint
            model_data = None
            try:
                checkpoint = torch.load(model_load_path, map_location="cpu")
                model_data = checkpoint["model"]
            except:
                self.log_error(fl_ctx, traceback.format_exc())

            if model_data is not None:
                mgr = PTModelPersistenceFormatManager(model_data)
                dxo = DXO(data_kind=DataKind.WEIGHTS, data=mgr.var_dict, meta=mgr.meta)

        return dxo

