import warnings
from typing import List, Optional

import torch
from torch.nn.modules.loss import _Loss
from monai.losses import DiceLoss, FocalLoss
from monai.networks import one_hot
from monai.utils import DiceCEReduction, look_up_option

class MultipleBackgroundDiceFocalLoss(_Loss):
    """
    Loss function that combines Dice loss and Focal loss for multiple background channels.

    Args:
        background_channels (List[int]): List of indices of background channels.
        to_onehot_y (bool): Whether to convert target to one-hot encoding. Default is False.
        sigmoid (bool): Whether to apply sigmoid activation to the input. Default is False.
        softmax (bool): Whether to apply softmax activation to the input. Default is False.
        squared_pred (bool): Whether to square the predictions. Default is False.
        jaccard (bool): Whether to use Jaccard index instead of Dice coefficient. Default is False.
        reduction (str): Type of reduction to apply. Default is "mean".
        smooth_nr (float): Smoothing factor for numerator. Default is 1e-5.
        smooth_dr (float): Smoothing factor for denominator. Default is 1e-5.
        batch (bool): Whether to compute loss per batch. Default is False.
        gamma (float): Focal loss gamma parameter. Default is 1.0.
        focal_weight (Optional[torch.Tensor]): Weight tensor for focal loss. Default is None.
        lambda_dice (float): Weight for Dice loss. Default is 1.0.
        lambda_focal (float): Weight for Focal loss. Default is 1.0.
    """
    
    def __init__(
        self,
        background_channels: List[int],
        to_onehot_y: bool = False,
        sigmoid: bool = False,
        softmax: bool = False,
        squared_pred: bool = False,
        jaccard: bool = False,
        reduction: str = "mean",
        smooth_nr: float = 1e-5,
        smooth_dr: float = 1e-5,
        batch: bool = False,
        gamma: float = 1.0,
        focal_weight: Optional[torch.Tensor] = None,
        lambda_dice: float = 1.0,
        lambda_focal: float = 1.0
    ) -> None:
        super().__init__()
        reduction = look_up_option(reduction, DiceCEReduction).value

        # These options should be handled here
        self.background_channels = background_channels
        self.to_onehot_y = to_onehot_y
        self.sigmoid = sigmoid
        self.softmax = softmax

        self.dice = DiceLoss(
            include_background=True,
            to_onehot_y=False,
            sigmoid=False,
            softmax=False,
            other_act=None,
            squared_pred=squared_pred,
            jaccard=jaccard,
            reduction=reduction,
            smooth_nr=smooth_nr,
            smooth_dr=smooth_dr,
            batch=batch
        )
        self.focal = FocalLoss(
            include_background=True,
            to_onehot_y=False,
            gamma=gamma,
            weight=focal_weight,
            reduction=reduction
        )

        if lambda_dice < 0.0:
            raise ValueError("lambda_dice should be no less than 0.0.")
        if lambda_focal < 0.0:
            raise ValueError("lambda_ce should be no less than 0.0.")
        self.lambda_dice = lambda_dice
        self.lambda_focal = lambda_focal

    def reduce_background_channels(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Reduce the background channels in the tensor.

        Args:
            tensor (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Tensor with reduced background channels.
        """

        n_chs = tensor.shape[1]
        slices = torch.split(tensor, 1, dim=1)

        bg = sum([slices[i] for i in self.background_channels])
        fg = [slices[i] for i in range(n_chs) if i not in self.background_channels]

        output = torch.cat([bg] + fg, dim=1)
        return output

    def forward(self, input: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        # Sigmoid
        if self.sigmoid:
            input = torch.sigmoid(input)

        # Softmax
        n_pred_ch = input.shape[1]
        if self.softmax:
            if n_pred_ch == 1:
                warnings.warn("single channel prediction, `softmax=True` ignored.")
            else:
                input = torch.softmax(input, 1)

        # One hot encoding
        if self.to_onehot_y:
            if n_pred_ch == 1:
                warnings.warn("single channel prediction, `to_onehot_y=True` ignored.")
            else:
                target = one_hot(target, num_classes=n_pred_ch)

        # Sum background channels
        input = self.reduce_background_channels(input)
        target = self.reduce_background_channels(target)

        dice_loss = self.dice(input, target)
        focal_loss = self.focal(input, target)
        total_loss: torch.Tensor = self.lambda_dice * dice_loss + self.lambda_focal * focal_loss

        return total_loss

class MultipleBackgroundDiceCELoss(_Loss):
    def __init__(
        self,
        background_channels: List[int],
        to_onehot_y: bool = False,
        sigmoid: bool = False,
        softmax: bool = False,
        squared_pred: bool = False,
        jaccard: bool = False,
        reduction: str = "mean",
        smooth_nr: float = 1e-5,
        smooth_dr: float = 1e-5,
        batch: bool = False,
        ce_weight: Optional[torch.Tensor] = None,
        lambda_dice: float = 1.0,
        lambda_ce: float = 1.0
    ) -> None:
        super().__init__()

        self.loss = MultipleBackgroundDiceFocalLoss(
            background_channels=background_channels,
            to_onehot_y=to_onehot_y,
            sigmoid=sigmoid,
            softmax=softmax,
            squared_pred=squared_pred,
            jaccard=jaccard,
            reduction=reduction,
            smooth_nr=smooth_nr,
            smooth_dr=smooth_dr,
            batch=batch,
            gamma=1.0,
            focal_weight=ce_weight,
            lambda_dice=lambda_dice,
            lambda_focal=lambda_ce
        )

    def forward(self, input: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return self.loss(input, target)
