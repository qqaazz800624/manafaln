from typing import Dict, Hashable, List, Mapping, Optional, Union

import torch
import torch.nn.functional as F
import numpy as np
from monai.config import DtypeLike, KeysCollection
from monai.config.type_definitions import NdarrayOrTensor
from monai.data.meta_obj import get_track_meta
from monai.transforms import Transform, MapTransform, RandomizableTransform
from monai.transforms.utils_pytorch_numpy_unification import clip, max, min
from monai.utils.enums import TransformBackends
from monai.utils.type_conversion import convert_data_type, convert_to_tensor

class RandFlipAxes3D(RandomizableTransform):
    """
    Randomly flips the axes of a 3D image tensor.

    Args:
        prob_x: Probability of flipping along the x-axis. Defaults to 0.5.
        prob_y: Probability of flipping along the y-axis. Defaults to 0.5.
        prob_z: Probability of flipping along the z-axis. Defaults to 0.5.
        dtype: Data type of the output. Defaults to np.float32.
    """

    backend = [TransformBackends.TORCH, TransformBackends.NUMPY]

    def __init__(
        self,
        prob_x: float = 0.5,
        prob_y: float = 0.5,
        prob_z: float = 0.5,
        dtype: DtypeLike = np.float32
    ):
        def ensure_probability(p, name):
            if 0.0 <= p <= 1.0:
                return p
            raise ValueError(f"Probability {name} must be between 0 and 1.")

        p = ensure_probability(prob_x, "prob_x")
        q = ensure_probability(prob_y, "prob_y")
        r = ensure_probability(prob_z, "prob_z")

        prob = 1.0 - (1.0 - p) * (1.0 - q) * (1.0 - r)
        RandomizableTransform.__init__(self, prob)

        self.p = p
        self.q = q
        self.r = r

        self._flip_x = False
        self._flip_y = False
        self._flip_z = False

        self.dtype = dtype

    def randomize(self) -> None:
        """
        Randomize the flipping axes based on the given probabilities.
        """
        p, q, r = self.R.rand(3)

        self._flip_x = p < self.p
        self._flip_y = q < self.q
        self._flip_z = r < self.r

        if self._flip_x or self._flip_y or self._flip_z:
            self._do_transform = True
        else:
            self._do_transform = False

    def __call__(
        self,
        img: NdarrayOrTensor,
        randomize: bool = True
    ) -> NdarrayOrTensor:
        """
        Apply the random flipping to the input image.

        Args:
            img: The input image tensor.
            randomize: Whether to randomize the flipping axes. Defaults to True.

        Returns:
            The transformed image tensor.
        """
        if randomize:
            self.randomize()
        if not self._do_transform:
            return img

        img = convert_to_tensor(img, track_meta=get_track_meta())
        dim = len(img.shape)

        axes = []
        if self._flip_x:
            axes.append(dim - 3)
        if self._flip_y:
            axes.append(dim - 2)
        if self._flip_z:
            axes.append(dim - 1)

        if len(axes) > 0:
            img = torch.flip(img, axes)

        ret: NdarrayOrTensor = convert_data_type(img, dtype=self.dtype)[0]
        return ret

class RandFlipAxes3Dd(RandomizableTransform, MapTransform):
    """
    Randomly flips the axes of multiple 3D image tensors.

    Args:
        keys: The keys corresponding to the image tensors to be transformed.
        prob_x: Probability of flipping along the x-axis. Defaults to 0.5.
        prob_y: Probability of flipping along the y-axis. Defaults to 0.5.
        prob_z: Probability of flipping along the z-axis. Defaults to 0.5.
        dtype: Data type of the output. Defaults to np.float32.
    """

    def __init__(
        self,
        keys: KeysCollection,
        prob_x: float = 0.5,
        prob_y: float = 0.5,
        prob_z: float = 0.5,
        dtype: DtypeLike = np.float32
    ):
        MapTransform.__init__(self, keys)
        RandomizableTransform.__init__(self, 1.0)

        self.t = RandFlipAxes3D(prob_x, prob_y, prob_z, dtype)

    def randomize(self) -> None:
        """
        Randomize the flipping axes.
        """
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
        """
        Apply the random flipping to the input image tensors.

        Args:
            data: The input data dictionary.

        Returns:
            The transformed data dictionary.
        """
        d = dict(data)
        self.randomize()

        if not self.t._do_transform:
            for key in self.keys:
                d[key] = convert_to_tensor(d[key], track_meta=get_track_meta())
            return d

        for key in self.keys:
            d[key] = self.t(d[key], randomize=False)
        return d

class SimulateLowResolution(RandomizableTransform):
    """
    Simulate low resolution by zooming in on a 3D image tensor.

    Args:
        prob: Probability of applying the transformation. Defaults to 0.125.
        zoom_range: Range of zooming scale. Defaults to [0.5, 1.0].
        dtype: Data type of the output. Defaults to np.float32.
    """

    backend = [TransformBackends.TORCH, TransformBackends.NUMPY]

    def __init__(
        self,
        prob: float = 0.125,
        zoom_range: List[float] = [0.5, 1.0],
        dtype: DtypeLike = np.float32
    ):
        RandomizableTransform.__init__(self, prob)

        self.zoom_range = zoom_range
        self._zoom_scale = 1.0
        self.dtype = dtype

    def randomize(self) -> None:
        """
        Randomize the zooming scale.
        """
        super().randomize(None)
        if not self._do_transform:
            return

        self._zoom_scale = self.R.uniform(self.zoom_range[0], self.zoom_range[1])

    def __call__(
        self,
        img: NdarrayOrTensor,
        randomize: bool = True
    ) -> NdarrayOrTensor:
        """
        Apply the low resolution simulation to the input image.

        Args:
            img: The input image tensor.
            randomize: Whether to randomize the zooming scale. Defaults to True.

        Returns:
            The transformed image tensor.
        """
        if randomize:
            self.randomize()
        if not self._do_transform:
            return img

        img = convert_to_tensor(img, track_meta=get_track_meta())
        img = img.unsqueeze(0) # Add batch dimension

        # Compute target shape
        target_shape = [int(round(s * self._zoom_scale)) for s in img.shape[2:]]
        tmp = F.interpolate(img, size=target_shape, mode="nearest-exact")
        img = F.interpolate(tmp, size=img.shape[2:], mode="trilinear")

        img = img.squeeze(0) # Remove batch dimension
        ret: NdarrayOrTensor = convert_data_type(img, dtype=self.dtype)[0]
        return ret

class SimulateLowResolutiond(RandomizableTransform, MapTransform):
    """
    Simulate low resolution by zooming in on multiple 3D image tensors.

    Args:
        keys: The keys corresponding to the image tensors to be transformed.
        prob: Probability of applying the transformation. Defaults to 0.125.
        zoom_range: Range of zooming scale. Defaults to [0.5, 1.0].
        dtype: Data type of the output. Defaults to np.float32.
    """

    backend = SimulateLowResolution.backend

    def __init__(
        self,
        keys: KeysCollection,
        prob: float = 0.125,
        zoom_range: List[float] = [0.5, 1.0],
        dtype: DtypeLike = np.float32
    ):
        MapTransform.__init__(self, keys)
        RandomizableTransform.__init__(self, 1.0)

        self.t = SimulateLowResolution(prob, zoom_range, dtype)

    def randomize(self) -> None:
        """
        Randomize the zooming scale.
        """
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
        """
        Apply the low resolution simulation to the input image tensors.

        Args:
            data: The input data dictionary.

        Returns:
            The transformed data dictionary.
        """
        d = dict(data)
        self.randomize()

        if not self.t._do_transform:
            for key in self.keys:
                d[key] = convert_to_tensor(d[key], track_meta=get_track_meta())
            return d

        for key in self.keys:
            d[key] = self.t(d[key], randomize=False)
        return d

