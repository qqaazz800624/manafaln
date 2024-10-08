import traceback
from nvflare.apis.dxo import DataKind, from_bytes
from nvflare.apis.fl_context import FLContext
from nvflare.app_common.abstract.formatter import Formatter
from nvflare.app_common.app_constant import AppConstants

class LightningFormatter(Formatter):
    def __init__(self) -> None:
        super().__init__()
        self.results = {}

    def format(self, fl_ctx: FLContext) -> str:
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
                            metrics = metric_dxo.data
                            res[data_client][model_name] = metrics
            # add any results
            print(f"Updating results {res}")
            self.results.update(res)
            print(f"Updating results {self.results}")
        except Exception as e:
            traceback.print_exc()

        return repr(result)
