import traceback
from typing import Any, Dict

import torch
import numpy as np
from nvflare.apis.dxo import DataKind, from_bytes
from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.formatter import Formatter
from nvflare.app_common.app_constant import AppConstants

def extract_tensor(data: Any) -> Any:
    """
    Extracts the tensor data as a list.

    Args:
        data (Any): The input data.

    Returns:
        Any: The tensor data as a list.
    """
    if isinstance(data, torch.Tensor):
        return data.tolist()
    if isinstance(data, np.ndarray):
        return data.tolist()
    return data

def simplify_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplifies the metrics dictionary by extracting tensor data as lists.

    Args:
        metrics (Dict[str, Any]): The metrics dictionary.

    Returns:
        Dict[str, Any]: The simplified metrics dictionary.
    """
    return {k: extract_tensor(v) for k, v in metrics}

class SimpleFormatter(Formatter):
    """
    A simple formatter class that formats FLContext data.

    Attributes:
        results (Dict[str, Any]): The formatted results.

    Methods:
        format(fl_ctx: FLContext) -> str: Formats the FLContext data.

    """
    def __init__(self) -> None:
        super().__init__()
        self.results = {}

    def format(self, fl_ctx: FLContext) -> str:
        """
        Formats the FLContext data.

        Args:
            fl_ctx (FLContext): The FLContext object.

        Returns:
            str: The formatted data as a string.
        """
        # Get validation result
        validation_shareables_dict = fl_ctx.get_prop(
            AppConstants.VALIDATION_RESULT,
            {}
        )
        result = {}

        try:
            # Extract results from all clients
            for data_client in validation_shareables_dict.keys():
                validation_dict = validation_shareables_dict[data_client]
                if validation_dict:
                    res[data_client] = {}
                    for model_name in validation_dict.keys():
                        dxo_path = validation_dict[model_name]

                        # Load the shareable
                        with open(dxo_path, "rb") as f:
                            metric_dxo = from_bytes(f.read())

                        # Get metrics from shareable
                        if metric_dxo and metric_dxo.data_kind == DataKind.METRICS:
                            metrics = simplify_metrics(metric_dxo.data)
                            res[data_client][model_name] = metrics
            # add any results
            self.results.update(res)
        except Exception as e:
            traceback.print_exc()

        return repr(result)

