from typing import Hashable, Mapping

from monai.config import KeysCollection, PathLike
from monai.transforms import MapTransform, Transform
from monai.utils import PostFix
from monai.utils.misc import ImageMetaKey

from manafaln.utils import load_yaml

DEFAULT_POST_FIX = PostFix.meta()

class LoadJSON(Transform):
    """
    Load json file.

    Args:
        json_only (bool, optional): If True, only the json data will be returned. 
            If False, both the json data and meta data will be returned. 
            Defaults to False.

    Returns:
        tuple: A tuple containing the loaded json data and meta data (optional).

    """

    def __init__(
        self,
        json_only: bool = False
    ):
        self.json_only = json_only

    def __call__(self, path: PathLike):
        """
        Load the json file.

        Args:
            path (PathLike): The path to the json file.

        Returns:
            tuple: A tuple containing the loaded json data and meta data (optional).

        """
        # Read json file
        data = load_yaml(path)

        if self.json_only:
            return data

        meta_data = {ImageMetaKey.FILENAME_OR_OBJ: path}
        return data, meta_data


class LoadJSONd(MapTransform):
    """
    Load multiple json files.

    Args:
        keys (KeysCollection): The keys of the json files to load.
        meta_key_postfix (str, optional): The postfix to add to the keys of the meta data.
            Defaults to the default postfix.
        allow_missing_keys (bool, optional): If True, missing keys will be ignored.
            If False, an error will be raised for missing keys.
            Defaults to False.

    Returns:
        dict: A dictionary containing the loaded json data and meta data (optional).

    """

    def __init__(
        self,
        keys: KeysCollection,
        meta_key_postfix: str=DEFAULT_POST_FIX,
        allow_missing_keys: bool=False,
    ):
        super().__init__(keys, allow_missing_keys)
        self.t = LoadJSON(json_only=False)
        self.meta_key_postfix = meta_key_postfix

    def __call__(
        self,
        data: Mapping[Hashable, PathLike]
    ):
        """
        Load the multiple json files.

        Args:
            data (Mapping[Hashable, PathLike]): A mapping of keys to the paths of the json files.

        Returns:
            dict: A dictionary containing the loaded json data and meta data (optional).

        """
        d = dict(data)
        for key in self.key_iterator(d):
            d[key], meta_data = self.t(d[key])
            meta_key = PostFix._get_str(key, self.meta_key_postfix)
            d[meta_key] = {**d.get(meta_key, {}), **meta_data}
        return d
