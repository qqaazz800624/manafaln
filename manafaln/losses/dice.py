from typing import List, Union, Optional

import torch
import torch.nn as nn
from torch.nn.modules.loss import _Loss
from monai.losses import DiceLoss
from monai.networks import one_hot
from monai.utils import DiceCEReduction, Weight, look_up_option

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
        ce_weight: Optional[torch.Tensor] = None,
        lambda_dice: float = 1.0,
        lambda_ce: float = 1.0
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
            batch=False
        )
        self.cross_entropy = nn.CrossEntropyLoss(weight=ce_weight, reduction=reduction)

        if lambda_dice < 0.0:
            raise ValueError("lambda_dice should be no less than 0.0.")
        if lambda_ce < 0.0:
            raise ValueError("lambda_ce should be no less than 0.0.")
        self.lambda_dice = lambda_dice
        self.lambda_ce = lambda_ce

    def reduce_background_channels(self, tensor: torch.Tensor) -> torch.Tensor:
        n_chs = tensor.shape[1]
        slices = torch.split(tensor, 1, dim=1)

        bg = sum([slices[i] for i in self.background_channels])
        fg = [slices[i] for i in range(n_chs) if i not in self.background_channels]

        output = torch.cat([bg] + fg, dim=1)
        return output

    def ce(self, input: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        n_pred_ch, n_target_ch = input.shape[1], target.shape[1]
        if n_pred_ch == n_target_ch:
            # target is in the one-hot format, convert to BH[WD] format to calculate ce loss
            target = torch.argmax(target, dim=1)
        else:
            target = torch.squeeze(target, dim=1)
        target = target.long()
        return self.cross_entropy(input, target)

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
        ce_loss = self.ce(input, target)
        total_loss: torch.Tensor = self.lambda_dice * dice_loss + self.lambda_ce * ce_loss

        return total_loss
