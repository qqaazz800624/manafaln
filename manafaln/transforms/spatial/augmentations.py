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
            raise ValueError(f"Probability {name} must between 0 and 1.")

        p = ensure_probability(prob_x, "prob_x")
        q = ensure_probability(prob_y, "prob_y")
        r = ensure_probability(prob_z, "prob_z")

        prob = 1.0 - (1.0 - p) * (1.0 - q) * (1.0 - r)
        RandomizableTransform.__init__(self, prob)

        if prob != 0.0:
            self.p = p / prob
            self.q = q / prob
            self.r = r / prob
        else:
            self.p = 0.0
            self.q = 0.0
            self.r = 0.0
        self._flip_x = False
        self._flip_y = False
        self._flip_z = False

        self.dtype = dtype

    def randomize(self) -> None:
        super().randomize(None)
        if not self._do_transform:
            return

        self._flip_x = self.R.rand() < self.p
        self._flip_y = self.R.rand() < self.q
        self._flip_z = self.R.rand() < self.r

    def __call__(
        self,
        img: NdarrayOrTensor,
        randomize: bool = True
    ) -> NdarrayOrTensor:
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
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
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
        super().randomize(None)
        if not self._do_transform:
            return

        self._zoom_scale = self.R.uniform(self.zoom_range[0], self.zoom_range[1])

    def __call__(
        self,
        img: NdarrayOrTensor,
        randomize: bool = True
    ) -> NdarrayOrTensor:
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
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
        d = dict(data)
        self.randomize()

        if not self.t._do_transform:
            for key in self.keys:
                d[key] = convert_to_tensor(d[key], track_meta=get_track_meta())
            return d

        for key in self.keys:
            d[key] = self.t(d[key], randomize=False)
        return d
