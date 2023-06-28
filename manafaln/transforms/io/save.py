from monai.transforms import SaveImage as _SaveImage
from monai.transforms import SaveImaged as _SaveImaged


class SaveImage(_SaveImage):
    """
    Overrides monai.transforms.SaveImage with options.
    """

    def __init__(
        self,
        init_kwargs=None,
        data_kwargs=None,
        meta_kwargs=None,
        write_kwargs=None,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.set_options(
            init_kwargs=init_kwargs,
            data_kwargs=data_kwargs,
            meta_kwargs=meta_kwargs,
            write_kwargs=write_kwargs,
        )


class SaveImaged(_SaveImaged):
    """
    Overrides monai.transforms.SaveImaged with options.
    """

    def __init__(
        self,
        init_kwargs=None,
        data_kwargs=None,
        meta_kwargs=None,
        write_kwargs=None,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.set_options(
            init_kwargs=init_kwargs,
            data_kwargs=data_kwargs,
            meta_kwargs=meta_kwargs,
            write_kwargs=write_kwargs,
        )
