from typing import Any, Dict, Hashable, List, Mapping, Optional, Sequence, Union

import torch
import numpy as np
from monai.config import DtypeLike, KeysCollection
from monai.config.type_definitions import NdarrayOrTensor
from monai.data.meta_obj import get_track_meta
from monai.transforms import Transform, MapTransform, RandomizableTransform
from monai.transforms.utils_pytorch_numpy_unification import clip, max, min
from monai.utils.enums import TransformBackends
from monai.utils.misc import ensure_tuple_rep
from monai.utils.type_conversion import convert_data_type, convert_to_tensor

class RandAdjustBrightnessAndContrast(RandomizableTransform):
    """
    Randomly adjust the brightness and contrast of the input image.
    """

    backend = [TransformBackends.TORCH, TransformBackends.NUMPY]

    def __init__(
        self,
        probs: Union[float, List[float]] = [0.15, 0.15],
        brightness_range: Optional[List[float]] = None,
        contrast_range: Optional[List[float]] = None,
        dtype: DtypeLike = np.float32
    ):
        """
        Args:
            probs: Probability of applying the brightness and contrast adjustment.
            brightness_range: Range of brightness adjustment. Must be a list with length 2.
            contrast_range: Range of contrast adjustment. Must be a list with length 2.
            dtype: Data type of the output image.
        """
        probs = ensure_tuple_rep(probs, 2)

        if brightness_range is None:
            p = 0.0
        else:
            p = probs[0]
            if len(brightness_range) == 2:
                self.brightness = sorted(brightness_range)
            else:
                raise ValueError(
                    "Brightness range must be None or a list with length 2."
                )

        if contrast_range is None:
            q = 0.0
        else:
            q = probs[1]
            if len(contrast_range) == 2:
                self.contrast = sorted(contrast_range)
            else:
                raise ValueError(
                    "Contrast range must be None or a list with length 2."
                )

        prob = (p + q) - p * q
        RandomizableTransform.__init__(self, prob)

        self.prob_b = p
        self.prob_c = q

        self._brightness = None
        self._contrast = None

        self.dtype = dtype

    def clear(self):
        """
        Clear the internal states.
        """
        self._brightness = None
        self._contrast = None
        self._do_transform = False

    def randomize(self, data: Any = None) -> None:
        """
        Randomize the brightness and contrast adjustment.
        """
        self.clear()
        p, q = self.R.rand(2)

        if p < self.prob_b:
            self._brightness = self.R.uniform(
                low=self.brightness[0],
                high=self.brightness[1]
            )
            self._do_transform = True

        if q < self.prob_c:
            self._contrast = self.R.uniform(
                low=self.contrast[0],
                high=self.contrast[1]
            )
            self._do_transform = True

    def __call__(
        self,
        img: NdarrayOrTensor,
        randomize: bool = True
    ) -> NdarrayOrTensor:
        """
        Apply the brightness and contrast adjustment to the input image.

        Args:
            img: The input image to be adjusted.
            randomize: Whether to randomize the brightness and contrast adjustment.

        Returns:
            The adjusted image.
        """
        if randomize:
            self.randomize()
        if not self._do_transform:
            return img

        img = convert_to_tensor(img, track_meta=get_track_meta())
        min_intensity = min(img)
        max_intensity = max(img)
        scale = 1.0

        if self._brightness:
            scale *= self._brightness
            min_intensity *= self._brightness
            max_intensity *= self._brightness

        if self._contrast:
            scale *= self._contrast

        img *= scale
        img = clip(img, min_intensity, max_intensity)

        ret: NdarrayOrTensor = convert_data_type(img, dtype=self.dtype)[0]
        return ret

class RandAdjustBrightnessAndContrastd(MapTransform, RandomizableTransform):
    """
    Randomly adjust the brightness and contrast of the input image for a batch of images.
    """

    backend = RandAdjustBrightnessAndContrast.backend

    def __init__(
        self,
        keys: KeysCollection,
        probs: Union[float, List[float]] = [0.15, 0.15],
        brightness_range: Optional[List[float]] = None,
        contrast_range: Optional[List[float]] = None,
        dtype: DtypeLike = np.float32
    ):
        """
        Args:
            keys: Keys of the corresponding items to be transformed.
            probs: Probability of applying the brightness and contrast adjustment.
            brightness_range: Range of brightness adjustment. Must be a list with length 2.
            contrast_range: Range of contrast adjustment. Must be a list with length 2.
            dtype: Data type of the output image.
        """
        MapTransform.__init__(self, keys)
        RandomizableTransform.__init__(self, 1.0)

        self.t = RandAdjustBrightnessAndContrast(
            probs, brightness_range, contrast_range, dtype
        )

    def randomize(self) -> None:
        """
        Randomize the brightness and contrast adjustment.
        """
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
        """
        Apply the brightness and contrast adjustment to the input images.

        Args:
            data: A dictionary containing the input images.

        Returns:
            A dictionary containing the adjusted images.
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

class RandInverseIntensityGamma(RandomizableTransform):
    """
    Randomly adjust the inverse intensity gamma of the input image.
    """

    backend = [TransformBackends.TORCH, TransformBackends.NUMPY]

    def __init__(
        self,
        prob: float = 0.15,
        gamma: Union[Sequence[float], float] = (0.7, 1.5)
    ):
        """
        Args:
            prob: Probability of applying the inverse intensity gamma adjustment.
            gamma: Range of gamma adjustment. Must be a pair of numbers or a single number >= 0.5.
        """
        RandomizableTransform.__init__(self, prob)

        if isinstance(gamma, (int, float)):
            if gamma <= 0.5:
                raise ValueError("If gamma is single number, gamma must >= 0.5.")
            self.gamma = (0.5, gamma)
        elif len(gamma) != 2:
            raise ValueError("Gamma must a pair of numbers.")
        else:
            self.gamma = (min(gamma), max(gamma))

        self.gamma_value: Optional[float] = None

    def randomize(self, data: Optional[Any] = None) -> None:
        """
        Randomize the inverse intensity gamma adjustment.
        """
        super().randomize(None)
        if not self._do_transform:
            return None
        self.gamma_value = self.R.uniform(low=self.gamma[0], high=self.gamma[1])

    def __call__(self, img: NdarrayOrTensor, randomize: bool = True) -> NdarrayOrTensor:
        """
        Apply the inverse intensity gamma adjustment to the input image.

        Args:
            img: The input image to be adjusted.
            randomize: Whether to randomize the inverse intensity gamma adjustment.

        Returns:
            The adjusted image.
        """
        img = convert_to_tensor(img, track_meta=get_track_meta())
        if randomize:
            self.randomize()

        if not self._do_transform:
            return img

        if self.gamma_value is None:
            raise RuntimeError("`gamma_value` is None, call randomize first.")

        eps = 1e-7
        min_intensity = min(img)
        max_intensity = max(img)

        y = 1.0 - (img - min_intensity) / (max_intensity - min_intensity + eps)
        y = y ** self.gamma_value
        y = (1.0 - y) * (max_intensity - min_intensity) + min_intensity

        return y

class RandInverseIntensityGammad(MapTransform, RandomizableTransform):
    """
    Randomly adjust the inverse intensity gamma of the input image for a batch of images.
    """

    backend = RandInverseIntensityGamma.backend

    def __init__(
        self,
        keys: KeysCollection,
        prob: float = 0.15,
        gamma: Union[Sequence[float], float] = (0.7, 1.5)
    ):
        """
        Args:
            keys: Keys of the corresponding items to be transformed.
            prob: Probability of applying the inverse intensity gamma adjustment.
            gamma: Range of gamma adjustment. Must be a pair of numbers or a single number >= 0.5.
        """
        MapTransform.__init__(self, keys)
        RandomizableTransform.__init__(self, 1.0)

        self.t = RandInverseIntensityGamma(prob, gamma)

    def randomize(self, data: Optional[Any] = None) -> None:
        """
        Randomize the inverse intensity gamma adjustment.
        """
        self.t.randomize()

    def __call__(
        self,
        data: Mapping[Hashable, NdarrayOrTensor]
    ) -> Dict[Hashable, NdarrayOrTensor]:
        """
        Apply the inverse intensity gamma adjustment to the input images.

        Args:
            data: A dictionary containing the input images.

        Returns:
            A dictionary containing the adjusted images.
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

