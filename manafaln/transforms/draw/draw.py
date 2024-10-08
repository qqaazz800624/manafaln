from typing import Any, Literal, Optional, Sequence, Tuple, Union

import numpy as np
from monai.config import KeysCollection
from monai.transforms import MapTransform, Transform
from monai.utils import MetaKeys, PostFix
from monai.utils.enums import PostFix
from scipy.interpolate import interp1d
from skimage.morphology import binary_dilation
from skimage.morphology.footprints import disk, rectangle

DEFAULT_POST_FIX = PostFix.meta()
META_POINTS_KEY  = "meta_points"

class DrawPoints(Transform):
    """
    Generate a binary mask by drawing given points.
    Apply binary dilation if footprint is given.
    """
    def __init__(
        self,
        spatial_size: Sequence[int],
        apply_index: Optional[Sequence[int]]=None,
        channel_dim: int=0,
        footprint_shape: Optional[Literal['rectangle', 'disk']]=None,
        footprint_size: Union[int, Tuple[int, int]] = 5,
        mask_only: bool=False,
    ):
        """
        Args:
            spatial_size (Sequence[int], optional): Mask shape to be interpolated
            apply_index (Sequence[int], optional): Which index to read data and draw. Apply to all if None. Defaults to None.
            channel_dim (int, optional): Dimension to stack masks. Defaults to 0.
            footprint_shape ('rectangle', 'disk', optional): Shape of footprint for dilation. Defaults to None.
            footprint_size (int, Tuple[int, int]): Size of footprint. Defaults to 5.
            mask_only (bool): Whether to return mask only or with meta data, Defaults to False.
        """
        self.spatial_size = np.array(spatial_size)
        self.apply_index = [apply_index] if isinstance(apply_index, int) else apply_index
        self.channel_dim = channel_dim
        self.mask_only = mask_only

        if footprint_shape is None:
            self.footprint = None
        elif footprint_shape == "rectangle":
            if isinstance(footprint_size, int):
                footprint_size = (footprint_size, )*2
            self.footprint = rectangle(*footprint_size, bool)
        elif footprint_shape == "disk":
            self.footprint = disk(footprint_size, bool)
        else:
            raise NotImplementedError(f"{footprint_shape} is not a valid footprint_shape")

    def draw_points(
        self,
        points: Sequence[Tuple[int, int]]
    ) -> np.ndarray:
        """
        Generate a binary mask where given points is True and otherwise False,
        then apply binary dilation with self.footprint.
        Args:
            points: Sequence of integer points, [(x, y), ...]
        Returns:
            mask: boolean array of shape self.spatial_size
        """
        mask = np.zeros(self.spatial_size, dtype=bool)
        for point in points:
            mask[point[0], point[1]] = True
        if self.footprint is not None:
            mask = binary_dilation(mask, self.footprint).astype(bool)
        return mask

    def extract_points(
        self,
        data: Any
    ) -> Sequence[Tuple[int, int]]:
        """
        A placeholder for points extractor to be replaced.
        """
        return data

    def __call__(
        self,
        datas: Sequence[Any]
    ) -> np.ndarray:

        masks = []
        meta_points = []

        if self.apply_index is not None:
            datas = [datas[i] for i in self.apply_index]

        for data in datas:
            if data is None: data = []
            points = self.extract_points(data)
            mask = self.draw_points(points)
            masks.append(mask)
            meta_points.append(points)
        masks = np.stack(masks, axis=self.channel_dim)

        if self.mask_only:
            return masks

        meta_data = {
            MetaKeys.SPATIAL_SHAPE: self.spatial_size,
            MetaKeys.ORIGINAL_CHANNEL_DIM: self.channel_dim,
            META_POINTS_KEY: meta_points
        }

        return masks, meta_data

class DrawPointsd(MapTransform):
    def __init__(
        self,
        keys: KeysCollection,
        spatial_size: Sequence[int],
        apply_index: Optional[Sequence[int]]=None,
        channel_dim: int=0,
        footprint_shape: Optional[Literal['rectangle', 'disk']]=None,
        footprint_size: Union[int, Tuple[int, int]] = 5,
        from_meta: bool=False,
        stack: bool=False,
        meta_key_postfix: str=DEFAULT_POST_FIX,
        allow_missing_keys: bool=False
    ):
        """Dictionary version of DrawPoints

        Args:
            from_meta (bool): Whether to read data from meta dict. Defaults to False.
            stack (bool): Whether to stack result to previous data. Defaults to False.
        """
        super().__init__(keys, allow_missing_keys)
        self.t = DrawPoints(
            spatial_size=spatial_size,
            apply_index=apply_index,
            channel_dim=channel_dim,
            footprint_shape=footprint_shape,
            footprint_size=footprint_size,
            mask_only=False)
        self.channel_dim = channel_dim
        self.meta_key_postfix = meta_key_postfix
        self.from_meta = from_meta
        self.stack = stack

    def __call__(self, data):
        d = dict(data)
        for key in self.key_iterator(d):
            meta_key = f"{key}_{self.meta_key_postfix}"

            if self.from_meta:
                ori_meta_points = d[meta_key][META_POINTS_KEY]
            else:
                ori_meta_points = d[key]
                # Swap to channel first for sequence indexing
                if isinstance(ori_meta_points, np.ndarray):
                    ori_meta_points = np.swapaxes(ori_meta_points, self.channel_dim, 0)

            # Apply transform
            masks, meta_data = self.t(ori_meta_points)

            if self.stack:
                d[key] = np.concatenate([d[key], masks], axis=self.channel_dim)
                d[meta_key][META_POINTS_KEY] += meta_data[META_POINTS_KEY]
            else:
                d[key] = masks
                d[meta_key] = {**d.get(meta_key, {}), **meta_data}
        return d

class Interpolate(DrawPoints):
    """
    Interpolate a sequence of (x, y) to a 2D mask,
    dilated with square(footprint).
    """
    def __init__(
        self,
        spatial_size: Sequence[int],
        apply_index: Optional[Sequence[int]]=None,
        channel_dim: int=0,
        footprint_shape: Optional[Literal['rectangle', 'disk']]='rectangle',
        footprint_size: Union[int, Tuple[int, int]] = 5,
        mask_only: bool=False,
    ):
        """
        Args:
            spatial_size (Sequence[int], optional): Mask shape to be interpolated
            apply_index (Sequence[int], optional): Which index to read data and draw. Apply to all if None. Defaults to None.
            channel_dim (int, optional): Dimension to stack masks. Defaults to 0.
            footprint_shape ('rectangle', 'disk', optional): Shape of footprint for dilation. Defaults to 'rectangle'.
            footprint_size (int, Tuple[int, int]): Size of footprint. Defaults to 5.
            mask_only (bool): Whether to return mask only or with meta data, Defaults to False.
        """
        super().__init__(
            spatial_size=spatial_size,
            apply_index=apply_index,
            channel_dim=channel_dim,
            footprint_shape=footprint_shape,
            footprint_size=footprint_size,
            mask_only=mask_only
        )

    def extract_points(
        self,
        ptss: Sequence[Sequence[Tuple[float, float]]]
    ) -> Sequence[Tuple[int, int]]:
        """
        Args:
            pts: A sequence of sequence of float points, [[(x, y), ...], ...]
        Returns:
            pts: A sequence of integer points, [(x, y), ...]
        """
        flatten_pts = []
        for pts in ptss:
            pts = self.rescale_size(pts)
            pts = self.remove_duplicate(pts)
            pts = self.interpolate(pts)
            flatten_pts.extend(pts)
        return flatten_pts

    def rescale_size(
        self,
        pts: Sequence[Tuple[float, float]]
    ) -> Sequence[Tuple[int, int]]:
        pts = [(int(p[0]*self.spatial_size[0]), int(p[1]*self.spatial_size[1])) for p in pts]
        return pts

    def remove_duplicate(
        self,
        pts: Sequence[Tuple[int, int]]
    ) -> Sequence[Tuple[int, int]]:
        res = [pts[0]]
        for i in range(1, len(pts)):
            if pts[i] != pts[i - 1]:
                res.append(pts[i])
        return res

    def interpolate(
        self,
        pts: Sequence[Tuple[int, int]]
    ) -> Sequence[Tuple[int, int]]:
        """
        Interpolate points to continuous coordinates.
        """
        pts = np.array(pts)
        l = np.linalg.norm(pts[1:] - pts[:-1], axis=-1)
        t = np.cumsum(l)
        t = np.concatenate([[0], t])
        t2 = np.arange(t[-1])
        x, y = pts[:, 0], pts[:, 1]
        x = interp1d(t, x, kind="linear" if len(pts) < 4 else "cubic",
                    bounds_error=False, fill_value="extrapolate")(t2)
        y = interp1d(t, y, kind="linear" if len(pts) < 4 else "cubic",
                    bounds_error=False, fill_value="extrapolate")(t2)
        pts = np.stack([x, y], axis=-1).astype(int)
        pts = np.clip(pts, 0, self.spatial_size-1)
        pts = pts.tolist()
        return pts

class Interpolated(DrawPointsd):
    def __init__(
        self,
        keys: KeysCollection,
        spatial_size: Sequence[int],
        apply_index: Optional[Sequence[int]]=None,
        channel_dim: int=0,
        footprint_shape: Optional[Literal['rectangle', 'disk']]='rectangle',
        footprint_size: Union[int, Tuple[int, int]] = 5,
        from_meta: bool=False,
        stack: bool=False,
        meta_key_postfix: str=DEFAULT_POST_FIX,
        allow_missing_keys: bool=False
    ):
        super().__init__(
            keys=keys,
            spatial_size=spatial_size,
            apply_index=apply_index,
            channel_dim=channel_dim,
            from_meta=from_meta,
            stack=stack,
            meta_key_postfix=meta_key_postfix,
            allow_missing_keys=allow_missing_keys
        )

        self.t = Interpolate(
            spatial_size=spatial_size,
            channel_dim=channel_dim,
            footprint_shape=footprint_shape,
            footprint_size=footprint_size,
            mask_only=False
        )
